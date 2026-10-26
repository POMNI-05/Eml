import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from eml_core import Email, ProfileStore, RuleExtractor, update_profile
from eml_core.profiles import Candidate, Evidence


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "profiles.sqlite3"
        self.store = ProfileStore(self.path)
        self.addCleanup(self.store.close)
        self.cid = self.store.create_client("Alex group")
        self.mailbox = "staff@firm.example"
        self.message = Email(
            "m1", "t1", sender="Alex <alex@client.example>", to=self.mailbox,
            body="Company: Example Pty Ltd\nIndustry: Wholesale\nPlease prepare BAS.",
            date="2026-10-01",
        )
        self.extractor = RuleExtractor(own_addresses=[self.mailbox])

    def update(self, message=None, extractor=None, mailbox=None):
        return update_profile(
            self.store, self.cid, mailbox or self.mailbox,
            [message or self.message], extractor or self.extractor,
        )

    def test_suggestions_are_not_confirmed_facts(self):
        self.update()
        self.assertEqual(self.store.context(self.cid)["confirmed_facts"], [])
        fields = {f["field"] for f in self.store.list_facts(self.cid, "pending")}
        self.assertEqual(fields, {"contacts", "entities", "industry"})
        self.assertNotIn("potential_need", fields)

    def test_own_addresses_and_firm_domains_are_excluded(self):
        message = replace(self.message, cc="Colleague <other@firm.example>")
        extractor = RuleExtractor(own_addresses=[self.mailbox],
                                  excluded_domains=["firm.example"])
        candidates = list(extractor.extract(message, self.mailbox))
        contacts = [c.value["email"] for c in candidates if c.field == "contacts"]
        self.assertEqual(contacts, ["alex@client.example"])

    def test_quoted_company_does_not_become_a_new_suggestion(self):
        message = replace(self.message, body="Thanks\nOn Monday Alex wrote:\nCompany: Old Pty Ltd")
        self.assertFalse(any(c.field == "entities" for c in self.extractor.extract(message, self.mailbox)))

    def test_repeat_is_skipped_after_reopening_store(self):
        self.update()
        self.store.close()
        self.store = ProfileStore(self.path)
        self.addCleanup(self.store.close)
        summary = self.update()
        self.assertEqual(summary["skipped_messages"], 1)
        self.assertEqual(summary["new_suggestions"], 0)

    def test_new_message_merges_evidence_without_overwriting_confirmation(self):
        self.update()
        contact = next(f for f in self.store.list_facts(self.cid) if f["field"] == "contacts")
        self.store.review(self.cid, contact["fact_id"], "confirmed")
        self.update(replace(self.message, message_id="m2"))
        contact = next(f for f in self.store.list_facts(self.cid) if f["field"] == "contacts")
        self.assertEqual(contact["status"], "confirmed")
        self.assertEqual(len(contact["evidence"]), 2)

    def test_rejected_suggestion_stays_rejected(self):
        self.update()
        fact = self.store.list_facts(self.cid)[0]
        self.store.review(self.cid, fact["fact_id"], "rejected")
        self.update(replace(self.message, message_id="m2"))
        current = next(f for f in self.store.list_facts(self.cid) if f["fact_id"] == fact["fact_id"])
        self.assertEqual(current["status"], "rejected")

    def test_account_and_client_checkpoints_are_isolated(self):
        self.update()
        summary = self.update(mailbox="another@firm.example")
        self.assertEqual(summary["processed_messages"], 1)
        other = self.store.create_client("Other group")
        summary = update_profile(self.store, other, self.mailbox, [self.message], self.extractor)
        self.assertEqual(summary["processed_messages"], 1)

    def test_changed_content_or_extractor_config_is_reprocessed(self):
        self.update()
        self.assertEqual(self.update(replace(self.message, body="Company: New Pty Ltd"))[
            "processed_messages"], 1)
        changed = RuleExtractor(own_addresses=[self.mailbox, "new-alias@firm.example"])
        self.assertEqual(self.update(extractor=changed)["processed_messages"], 1)

    def test_failed_extraction_can_be_retried(self):
        class Broken:
            version = "broken-v1"
            def extract(self, message, mailbox_id):
                raise RuntimeError("model unavailable")
        with self.assertRaises(RuntimeError):
            self.update(extractor=Broken())
        self.assertFalse(self.store.is_processed(self.cid, self.mailbox, self.message, "broken-v1"))
        self.assertEqual(self.store.list_facts(self.cid), [])
        self.assertEqual(self.update()["processed_messages"], 1)

    def test_out_of_scope_or_invented_evidence_is_rejected(self):
        bad = [
            Candidate("industry", "Wholesale", (
                Evidence("email_body", "Industry: Wholesale", self.mailbox, "different"),)),
            Candidate("industry", "Wholesale", (
                Evidence("email_body", "Industry: Invented", self.mailbox, "m1"),)),
        ]
        for candidate in bad:
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                self.store.ingest(self.cid, self.mailbox, self.message, "test", [candidate])
        self.assertEqual(self.store.list_facts(self.cid), [])
        self.assertFalse(self.store.is_processed(self.cid, self.mailbox, self.message, "test"))

    def test_scalar_replacement_requires_explicit_decision_and_keeps_history(self):
        old = self.store.add_manual(self.cid, "industry", "Wholesale")
        with self.assertRaisesRegex(ValueError, "replacement"):
            self.store.add_manual(self.cid, "industry", "Retail")
        self.assertEqual(self.store.context(self.cid)["confirmed_facts"][0]["value"], "Wholesale")
        self.store.add_manual(self.cid, "industry", "Retail", replace_existing=True)
        facts = {f["fact_id"]: f for f in self.store.list_facts(self.cid)}
        self.assertEqual(facts[old]["status"], "superseded")
        self.assertEqual(self.store.context(self.cid)["confirmed_facts"][0]["value"], "Retail")

    def test_fact_from_another_client_cannot_be_reviewed(self):
        fact = self.store.add_manual(self.cid, "industry", "Wholesale")
        other = self.store.create_client("Other")
        with self.assertRaises(ValueError):
            self.store.review(other, fact, "rejected")

    def test_possible_needs_are_kept_separate_and_not_exported_as_services(self):
        self.store.add_manual(self.cid, "potential_need", "Review cross-border arrangements")
        context = self.store.context(self.cid)
        self.assertEqual(context["confirmed_facts"], [])
        self.assertEqual(len(context["possible_needs"]), 1)
        exported = self.store.export_legacy()[0]
        self.assertNotIn("potential_need", exported)
        self.assertNotIn("services", exported)

    def test_one_contact_can_appear_in_multiple_client_groups(self):
        contact = {"name": "Alex", "email": "alex@client.example"}
        self.store.add_manual(self.cid, "contacts", contact)
        other = self.store.create_client("Other company")
        self.store.add_manual(other, "contacts", contact)
        self.assertEqual(len(self.store.context(other)["confirmed_facts"]), 1)

    def test_import_existing_clients_and_export_for_original_app(self):
        data = {
            "client_id": "legacy", "display_name": "Existing group",
            "company_name": "Example Pty Ltd", "emails": ["ALEX@client.example"],
            "primary_contacts": [{"name": "Alex", "email": "alex@client.example"}],
            "domains": ["client.example"], "aliases": ["Example"],
        }
        self.assertEqual(self.store.import_legacy(data), 1)
        self.assertEqual(self.store.import_legacy({"clients": [data]}), 0)
        exported = next(c for c in self.store.export_legacy() if c["client_id"] == "legacy")
        self.assertEqual(exported["emails"], ["alex@client.example"])
        self.assertEqual(exported["primary_contacts"][0]["name"], "Alex")
        self.assertEqual(exported["company_name"], "Example Pty Ltd")

    def test_invalid_import_does_not_leave_partial_clients(self):
        with self.assertRaises(ValueError):
            self.store.import_legacy([
                {"client_id": "good", "display_name": "Good"},
                {"client_id": "bad", "display_name": "Bad", "emails": ["invalid"]},
            ])
        self.assertEqual([c["client_id"] for c in self.store.list_clients()], [self.cid])


if __name__ == "__main__":
    unittest.main()
