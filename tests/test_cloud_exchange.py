import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from eml_core import Email, ProfileStore, Selection, SelectionResult
from eml_core.ai import ModelError
from eml_core.attachments import EmailAttachment
from eml_core.documents import BackgroundStore, DocumentPart
from eml_core.gemini import GeminiClient
from eml_core.privacy import Pseudonymizer, parse_literal_rules
from invoice.exchange import CloudPackage, ExchangeResponse, ExchangeStore
from invoice.service import DraftStore, build_inputs
from invoice.templates import GenerationTemplateStore


class PrivacyTests(unittest.TestCase):
    def test_overlaps_boundaries_repeated_mentions_and_exact_round_trip(self):
        mask = Pseudonymizer(parse_literal_rules("ANZ => BANK\nANZ Bank Limited => BANK"))
        text = "ANZ Bank Limited emailed ANZ and ANZ at Alex@anz.example; TANZ remains. https://anz.example/Alex"
        hidden = mask.mask_text(text)
        self.assertNotIn("Alex@anz.example", hidden)
        self.assertNotIn("https://anz.example", hidden)
        self.assertIn("TANZ remains", hidden)
        self.assertEqual(mask.restore(hidden), text)
        self.assertEqual(mask.mask_text("ANZ"), mask.mask_text("ANZ"))

    def test_regexes_cover_nested_fields_without_changing_schema_keys(self):
        source = {"sender": "person@example.com", "parts": [{"text": "TFN 123 456 789; phone 0412 345 678; BSB 123-456"}]}
        mask = Pseudonymizer()
        hidden = mask.mask(source)
        self.assertEqual(set(source), set(hidden))
        self.assertNotIn("123 456 789", json.dumps(hidden))
        self.assertNotIn("0412 345 678", json.dumps(hidden))
        self.assertEqual(mask.restore(hidden), source)

    def test_unknown_and_preexisting_tokens_are_rejected(self):
        first, second = Pseudonymizer(), Pseudonymizer()
        hidden = first.mask_text("person@example.com")
        with self.assertRaises(ModelError):
            second.restore(hidden)
        with self.assertRaises(ModelError):
            second.mask_text(hidden)

    def test_literal_rules_are_data_not_executable_patterns(self):
        for invalid in ("ANZ", "ANZ => hello world", " => BANK"):
            with self.subTest(invalid=invalid), self.assertRaises(ModelError):
                parse_literal_rules(invalid)
        mask = Pseudonymizer(parse_literal_rules("A.+ => COMPANY"))
        self.assertEqual(mask.mask_text("Alice"), "Alice")


class ExchangeTests(unittest.TestCase):
    def setUp(self):
        self.store = ProfileStore(":memory:")
        self.addCleanup(self.store.close)
        self.cid = self.store.create_client("Alex Group")
        self.other = self.store.create_client("Other client")
        self.store.add_manual(self.cid, "entities", {"name": "Example Pty Ltd"}, note="AUDIT-ONLY-MARKER")
        self.store.add_manual(self.cid, "contacts", {"name": "Alex", "email": "alex@client.example"})
        self.document = BackgroundStore(self.store).save(
            self.cid, "UNRECOGNISED-CONFIDENTIAL-FILENAME.txt",
            b"Example Pty Ltd is a wholesale business. Alex uses ANZ.",
        )
        self.message = Email(
            "private-gmail-id", "private-thread-id", sender="Sam <sam@firm.example>",
            to="Alex <alex@client.example>", subject="Example Pty Ltd: records reviewed",
            date="2026-10-01", body="Alex: I completed the ANZ reconciliation for Example Pty Ltd.",
            internet_message_id="private-rfc-id@client.example", label_ids=("private-label",),
            attachments=("PRIVATE-FILENAME.csv",), attachment_contents=(EmailAttachment(
                "part-private-id", "PRIVATE-FILENAME.csv", "text/csv", sha256="PRIVATE-FINGERPRINT",
                parts=(DocumentPart("sheet PRIVATE-SHEET, row 1", "Example Pty Ltd | ANZ | reviewed"),),
            ),),
        )
        self.result = SelectionResult(
            "mailbox@firm.example", Selection(message_ids=(self.message.message_id,)),
            [self.message, Email("excluded-private-id", "t2", body="EXCLUDED-BODY")],
        )
        self.context = self.store.context(self.cid)
        self.context["saved_search_methods"] = [{"terms": ["PRIVATE-SEARCH"]}]
        self.inputs, _ = build_inputs(
            self.context, [self.document], self.result, [self.message.message_id],
            style_instructions="Short paragraphs for Example Pty Ltd.",
        )

    def package(self):
        return CloudPackage.prepare(self.inputs, privacy_rules="ANZ => BANK", local_only=False)

    def reply(self, package, attachment=False):
        message = package.request["input"]["evidence"]["selected_email_evidence"][0]
        source = {"message_id": message["message_id"], "quote": message["body"]}
        if attachment:
            a = message["attachments"][0]
            source.update(quote=a["parts"][0]["text"], attachment_part_id=a["part_id"], location=a["parts"][0]["location"])
        return {
            "bundle_id": package.bundle_id, "evidence_sha256": package.request["input"]["evidence_sha256"],
            "analysis": {
                "client_summary": "Review of " + message["subject"],
                "activities": [{"entity": "", "description": message["body"], "status": "completed",
                                "evidence": [source], "uncertainties": []}],
                "open_questions": [],
            },
        }

    def test_allowlisted_request_drops_audit_metadata_and_masks_every_content_channel(self):
        package = self.package()
        outgoing = json.dumps(package.request)
        for secret in (
            "Alex", "Example Pty Ltd", "ANZ", "client.example", "firm.example",
            "private-gmail-id", "private-thread-id", "private-label", "private-rfc-id",
            "AUDIT-ONLY-MARKER", "PRIVATE-SEARCH", "excluded-private-id", "EXCLUDED-BODY",
            "PRIVATE-FILENAME", "PRIVATE-FINGERPRINT", "PRIVATE-SHEET", "UNRECOGNISED-CONFIDENTIAL-FILENAME",
            self.cid, self.document.document_id,
        ):
            with self.subTest(secret=secret):
                self.assertNotIn(secret, outgoing)
        self.assertIn("wholesale", outgoing)
        self.assertIn("reconciliation", outgoing)
        self.assertEqual(package.inputs, json.loads(json.dumps(self.inputs)))

    def test_response_restores_exact_body_and_attachment_sources_before_validation(self):
        package = self.package()
        body_draft = package.accept(json.dumps(self.reply(package)))
        self.assertEqual(body_draft["analysis"]["activities"][0]["evidence"][0]["quote"], self.message.body)
        self.assertEqual(body_draft["analysis"]["activities"][0]["evidence"][0]["message_id"], self.message.message_id)
        attachment_draft = package.accept(self.reply(package, attachment=True))
        source = attachment_draft["analysis"]["activities"][0]["evidence"][0]
        self.assertEqual(source["attachment_part_id"], "part-private-id")
        self.assertEqual(source["location"], "sheet PRIVATE-SHEET, row 1")
        DraftStore(self.store).save(attachment_draft)

    def test_mismatched_package_digest_invented_quotes_and_ids_are_rejected(self):
        package = self.package()
        original = self.reply(package)
        bad = []
        for field in ("bundle_id", "evidence_sha256"):
            value = copy.deepcopy(original)
            value[field] = "another-package"
            bad.append(value)
        for field, value in (("quote", "Invented completion"), ("message_id", "excluded-private-id")):
            reply = copy.deepcopy(original)
            reply["analysis"]["activities"][0]["evidence"][0][field] = value
            bad.append(reply)
        reply = copy.deepcopy(original)
        reply["analysis"]["activities"][0]["description"] = "[[EML_000000000000_ENTITY_0001]]"
        bad.append(reply)
        for reply in bad:
            with self.subTest(reply=reply), self.assertRaises(ModelError):
                package.accept(reply)
        self.assertEqual(DraftStore(self.store).list(self.cid), [])

    def test_gemini_send_requires_current_review_paid_declaration_and_nonlocal_client(self):
        from unittest.mock import Mock
        package = self.package()
        model = Mock(model="gemini-test")
        model.generate.return_value = ExchangeResponse.model_validate(self.reply(package))
        for options in (
            {"reviewed_request_sha256": "old", "paid_project_confirmed": True, "local_only": False},
            {"reviewed_request_sha256": package.request_sha256, "paid_project_confirmed": False, "local_only": False},
            {"reviewed_request_sha256": package.request_sha256, "paid_project_confirmed": True, "local_only": True},
        ):
            with self.subTest(options=options), self.assertRaises(ModelError):
                package.generate(model, **options)
        model.generate.assert_not_called()
        draft = package.generate(model, reviewed_request_sha256=package.request_sha256,
                                 paid_project_confirmed=True, local_only=False)
        self.assertEqual(draft["model"], "gemini-test")
        self.assertEqual(model.generate.call_args.args[2], package.request["input"])
        self.assertNotIn("mapping", model.generate.call_args.args[2])

    def test_packages_are_client_scoped_and_survive_database_reopen(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "profiles.sqlite3"
            with ProfileStore(path) as store:
                store.create_client("Alex", self.cid)
                store.create_client("Other", self.other)
                package = self.package()
                ExchangeStore(store).save(package)
            with ProfileStore(path) as store:
                exchanges = ExchangeStore(store)
                package = exchanges.get(self.cid, package.bundle_id)
                self.assertEqual(package.accept(self.reply(package))["client_id"], self.cid)
                with self.assertRaises(ModelError):
                    exchanges.get(self.other, package.bundle_id)
                self.assertEqual(exchanges.list(self.other), [])
                exchanges.delete(self.cid, package.bundle_id)
                self.assertEqual(exchanges.list(self.cid), [])

    def test_local_only_and_oversized_packages_fail_without_sending_or_truncating(self):
        with self.assertRaises(ModelError):
            CloudPackage.prepare(self.inputs)
        inputs = copy.deepcopy(self.inputs)
        inputs["selected_email_evidence"][0]["body"] = "x" * 1_100_000
        with self.assertRaisesRegex(ModelError, "exceeds"):
            CloudPackage.prepare(inputs, local_only=False)

    def test_generation_templates_do_not_overwrite_profiles_and_are_client_scoped(self):
        templates = GenerationTemplateStore(self.store)
        self.assertTrue(templates.get(self.cid)["local_only"])
        templates.save(self.cid, style="Concise", privacy_rules="ANZ => BANK", local_only=False)
        self.assertFalse(templates.get(self.cid)["local_only"])
        self.assertTrue(templates.get(self.other)["local_only"])
        self.assertEqual(self.store.context(self.cid)["confirmed_facts"], self.context["confirmed_facts"])


class GeminiTransportTests(unittest.TestCase):
    def test_official_endpoint_header_key_schema_and_no_tools_or_retry(self):
        import io
        response = {"bundle_id": "b", "evidence_sha256": "d", "analysis": {"client_summary": "", "activities": [], "open_questions": []}}
        wire = {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(response)}]}}]}
        class Reply(io.BytesIO):
            pass
        with patch("eml_core.gemini.build_opener") as make:
            make.return_value.open.return_value = Reply(json.dumps(wire).encode())
            result = GeminiClient("gemini-test", "key-not-to-be-logged").generate(ExchangeResponse, "system", {"selected": True})
        request = make.return_value.open.call_args.args[0]
        self.assertTrue(request.full_url.startswith("https://generativelanguage.googleapis.com/"))
        self.assertNotIn("key-not-to-be-logged", request.full_url)
        self.assertEqual(request.get_header("X-goog-api-key"), "key-not-to-be-logged")
        body = json.loads(request.data)
        self.assertNotIn("tools", body)
        self.assertNotIn("key-not-to-be-logged", request.data.decode())
        self.assertIn("responseJsonSchema", body["generationConfig"])
        self.assertEqual(result.bundle_id, "b")
        self.assertEqual(make.return_value.open.call_count, 1)

    def test_error_bodies_are_not_exposed_and_blocked_responses_are_rejected(self):
        import io
        with patch("eml_core.gemini.build_opener") as make:
            make.return_value.open.side_effect = HTTPError("https://provider.example", 429, "PRIVATE", {}, io.BytesIO(b"SECRET-INPUT"))
            with self.assertRaises(ModelError) as caught:
                GeminiClient("gemini-test", "secret-key").generate(ExchangeResponse, "system", {})
        self.assertIn("429", str(caught.exception))
        self.assertNotIn("SECRET", str(caught.exception))
        for value in ({"candidates": []}, {"candidates": [{"finishReason": "MAX_TOKENS"}]}):
            with patch("eml_core.gemini.build_opener") as make:
                make.return_value.open.return_value = io.BytesIO(json.dumps(value).encode())
                with self.assertRaises(ModelError):
                    GeminiClient("gemini-test", "secret-key").generate(ExchangeResponse, "system", {})

    def test_invalid_model_cannot_change_endpoint(self):
        for model in ("https://other.example", "gemini-test/../../x", "gemini-test?key=leak"):
            with self.subTest(model=model), self.assertRaises(ModelError):
                GeminiClient(model, "key")
