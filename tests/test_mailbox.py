import base64
import unittest
from datetime import date, datetime
from zoneinfo import ZoneInfo

from eml_core.mailbox import Email, GmailMailbox, Selection
from tests.fakes import FakeGmail, raw_message


class MailboxTests(unittest.TestCase):
    def test_empty_or_ambiguous_scope_is_rejected(self):
        for kwargs in ({}, {"label_ids": ("L1",), "message_ids": ("m1",)},
                       {"label_ids": ("",)}, {"message_ids": ("m1",), "max_messages": 0}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                Selection(**kwargs)

    def test_lists_real_label_ids(self):
        labels = GmailMailbox(FakeGmail()).list_labels(user_only=True)
        self.assertEqual({l["id"] for l in labels}, {"L1", "L2", "L3"})

    def test_reads_every_page(self):
        api = FakeGmail([raw_message(f"m{i}") for i in range(3)])
        result = GmailMailbox(api).select(Selection(label_ids=("L1",)))
        self.assertEqual(len(result.messages), 3)
        self.assertTrue(result.complete)
        self.assertEqual(len([c for c in api.calls if c[0] == "messages.list"]), 3)

    def test_label_union_deduplicates_and_does_not_expand_threads(self):
        api = FakeGmail([
            raw_message("m1", labels=("L1", "L3")),
            raw_message("m2", labels=("L3",)),
            raw_message("outside", labels=("L2",), thread="t1"),
        ])
        result = GmailMailbox(api).select(Selection(label_ids=("L1", "L3")))
        self.assertEqual({m.message_id for m in result.messages}, {"m1", "m2"})
        self.assertFalse(any(c[0] == "threads.get" for c in api.calls))
        self.assertTrue(all(len(c[1].get("labelIds", [])) == 1
                            for c in api.calls if c[0] == "messages.list"))

    def test_sub_labels_are_opt_in(self):
        api = FakeGmail([raw_message("parent"), raw_message("child", labels=("L2",))])
        mailbox = GmailMailbox(api)
        self.assertEqual(len(mailbox.select(Selection(label_ids=("L1",))).messages), 1)
        result = mailbox.select(Selection(label_ids=("L1",), include_sub_labels=True))
        self.assertEqual({m.message_id for m in result.messages}, {"parent", "child"})

    def test_missing_label_fails_instead_of_fetching_all_mail(self):
        api = FakeGmail([raw_message("m1")])
        with self.assertRaisesRegex(ValueError, "Unknown Gmail label"):
            GmailMailbox(api).select(Selection(label_ids=("old-id",)))
        self.assertFalse(any(c[0] == "messages.list" for c in api.calls))

    def test_explicit_message_selection_preserves_exact_ids(self):
        api = FakeGmail([raw_message("m1"), raw_message("m2")])
        result = GmailMailbox(api).select(Selection(message_ids=("m1", "m1")))
        self.assertEqual([m.message_id for m in result.messages], ["m1"])

    def test_limit_is_reported_as_incomplete(self):
        result = GmailMailbox(FakeGmail([
            raw_message("m1"), raw_message("m2"), raw_message("m3")
        ])).select(Selection(label_ids=("L1",), max_messages=2))
        self.assertEqual(len(result.messages), 2)
        self.assertFalse(result.complete)
        self.assertTrue(result.warnings)

    def test_exact_limit_can_still_be_complete(self):
        result = GmailMailbox(FakeGmail([raw_message("m1")])).select(
            Selection(label_ids=("L1",), max_messages=1)
        )
        self.assertTrue(result.complete)

    def test_sydney_inclusive_dates_and_dst(self):
        spec = Selection(label_ids=("L1",), start_date=date(2026, 10, 4),
                         end_date=date(2026, 10, 4))
        lower, upper = spec.bounds()
        self.assertEqual(upper - lower, 23 * 60 * 60 * 1000)
        api = FakeGmail([
            raw_message("before", timestamp=lower - 1),
            raw_message("start", timestamp=lower),
            raw_message("end", timestamp=upper - 1),
            raw_message("after", timestamp=upper),
        ])
        result = GmailMailbox(api).select(spec)
        self.assertEqual([m.message_id for m in result.messages], ["start", "end"])
        self.assertIn(f"after:{lower // 1000 - 1}", spec.query())

    def test_whole_thread_is_filtered_per_message(self):
        tz = ZoneInfo("Australia/Sydney")
        outside = int(datetime(2026, 9, 30, tzinfo=tz).timestamp() * 1000)
        inside = int(datetime(2026, 10, 15, tzinfo=tz).timestamp() * 1000)
        api = FakeGmail([
            raw_message("old", timestamp=outside),
            raw_message("current", timestamp=inside),
        ])
        result = GmailMailbox(api).select(Selection(
            thread_ids=("t1",), start_date=date(2026, 10, 1), end_date=date(2026, 10, 31)
        ))
        self.assertEqual([m.message_id for m in result.messages], ["current"])

    def test_unknown_date_is_explicitly_incomplete(self):
        raw = raw_message("m1")
        raw.pop("internalDate")
        raw["payload"]["headers"] = []
        result = GmailMailbox(FakeGmail([raw])).select(
            Selection(label_ids=("L1",), start_date=date(2026, 1, 1))
        )
        self.assertFalse(result.complete)
        self.assertIn("cannot establish", result.warnings[0])

    def test_internet_id_resolves_without_expanding_thread(self):
        api = FakeGmail([raw_message("m1"), raw_message("m2")])
        result = GmailMailbox(api).select(
            Selection(internet_message_ids=("<m1@client.example>",))
        )
        self.assertEqual([m.message_id for m in result.messages], ["m1"])

    def test_internet_id_ambiguity_or_missing_is_not_guessed(self):
        first, duplicate = raw_message("m1"), raw_message("duplicate")
        duplicate["payload"]["headers"][-1]["value"] = "<m1@client.example>"
        mailbox = GmailMailbox(FakeGmail([first, duplicate]))
        with self.assertRaisesRegex(ValueError, "multiple matches"):
            mailbox.select(Selection(internet_message_ids=("<m1@client.example>",)))
        with self.assertRaisesRegex(ValueError, "not found"):
            mailbox.select(Selection(internet_message_ids=("<missing@client.example>",)))

    def test_internet_id_query_injection_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Invalid Internet"):
            GmailMailbox(FakeGmail()).select(
                Selection(internet_message_ids=('a@b" OR in:anywhere',))
            )


class ParsingTests(unittest.TestCase):
    def test_external_text_body_is_not_silently_treated_as_empty(self):
        raw = raw_message("m1")
        raw["payload"]["body"] = {"attachmentId": "external-body"}
        with self.assertRaisesRegex(ValueError, "text body externally"):
            Email.from_gmail(raw)

    def test_plain_text_is_not_truncated_and_unpadded_base64_decodes(self):
        text = "你好" + "x" * 7000
        self.assertEqual(Email.from_gmail(raw_message("m1", body=text)).body, text)

    def test_html_only_fallback_excludes_scripts(self):
        raw = raw_message("m1")
        raw["payload"]["mimeType"] = "text/html"
        raw["payload"]["body"]["data"] = base64.urlsafe_b64encode(
            b"<style>hidden</style><p>Company: Example Pty Ltd</p><script>bad()</script>"
        ).decode()
        text = Email.from_gmail(raw).body
        self.assertIn("Example Pty Ltd", text)
        self.assertNotIn("bad", text)
        self.assertNotIn("hidden", text)

    def test_mime_alternatives_are_not_duplicated_and_attachments_not_read(self):
        raw = raw_message("m1", body="actual body")
        plain = raw["payload"]
        html = {"mimeType": "text/html", "body": {
            "data": base64.urlsafe_b64encode(b"<p>duplicate HTML</p>").decode()}}
        attachment = {"mimeType": "text/plain", "filename": "secret.txt",
                      "body": {"data": base64.urlsafe_b64encode(b"file content").decode()}}
        raw["payload"] = {"mimeType": "multipart/mixed", "parts": [
            {"mimeType": "multipart/alternative", "parts": [html, plain]}, attachment]}
        result = Email.from_gmail(raw)
        self.assertEqual(result.body, "actual body")
        self.assertEqual(result.attachments, ("secret.txt",))

    def test_declared_charset_is_used(self):
        raw = raw_message("m1")
        raw["payload"]["headers"].append(
            {"name": "Content-Type", "value": "text/plain; charset=iso-8859-1"}
        )
        raw["payload"]["body"]["data"] = base64.urlsafe_b64encode(b"caf\xe9").decode()
        self.assertEqual(Email.from_gmail(raw).body, "café")


if __name__ == "__main__":
    unittest.main()
