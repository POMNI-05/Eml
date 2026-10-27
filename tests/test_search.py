import unittest

from eml_core import GmailMailbox, Selection
from eml_core.search import build_client_search
from tests.fakes import FakeGmail, raw_message


class SearchTests(unittest.TestCase):
    def select(self, terms, messages, **kwargs):
        plan = build_client_search({"confirmed_facts": []}, terms, **kwargs)
        result = GmailMailbox(FakeGmail(messages)).select(Selection(client_query=plan.query))
        return {message.message_id for message in result.messages}

    def test_any_and_all_match_distinct_messages(self):
        messages = [raw_message("a", body="BAS"), raw_message("b", body="bookkeeping"),
                    raw_message("both", body="BAS and bookkeeping"), raw_message("none", body="Hello")]
        self.assertEqual(self.select(["BAS", "bookkeeping"], messages), {"a", "b", "both"})
        self.assertEqual(self.select(["BAS", "bookkeeping"], messages, match_mode="all"), {"both"})

    def test_all_groups_sender_recipient_or_cc_as_one_email_entry(self):
        sender = raw_message("from", body="BAS", sender="alex@example.com")
        recipient = raw_message("to", body="BAS", sender="staff@firm.example", to="alex@example.com")
        cc = raw_message("cc", body="BAS", sender="staff@firm.example")
        cc["payload"]["headers"].append({"name": "Cc", "value": "Alex <alex@example.com>"})
        body_only = raw_message("body", body="BAS alex@example.com")
        missing_word = raw_message("no-word", body="Hello", sender="alex@example.com")
        self.assertEqual(
            self.select(["alex@example.com", "BAS"], [sender, recipient, cc, body_only, missing_word], match_mode="all"),
            {"from", "to", "cc"},
        )

    def test_exclusions_apply_to_every_any_match_and_spam_and_trash_stay_excluded(self):
        messages = [
            raw_message("clean", body="BAS"), raw_message("news", body="BAS newsletter"),
            raw_message("other-news", body="bookkeeping newsletter"),
            raw_message("spam", body="BAS", labels=("SPAM",)),
            raw_message("trash", body="bookkeeping", labels=("TRASH",)),
        ]
        self.assertEqual(self.select(["BAS", "bookkeeping"], messages, excluded_terms=["newsletter"]), {"clean"})

    def test_excluded_email_removes_sender_recipient_and_cc(self):
        blocked = raw_message("blocked", body="BAS", sender="newsletter@example.com")
        clean = raw_message("clean", body="BAS")
        self.assertEqual(self.select(["BAS"], [blocked, clean], excluded_terms=["newsletter@example.com"]), {"clean"})

    def test_removed_saved_identities_are_not_silently_added_back(self):
        context = {"confirmed_facts": [
            {"field": "aliases", "value": "Shared alias", "fact_id": "alias"},
            {"field": "contacts", "value": {"email": "alex@example.com"}, "fact_id": "contact"},
        ]}
        plan = build_client_search(context, ["BAS"], include_profile=False)
        self.assertEqual(plan.terms, ("BAS",))
        self.assertEqual(plan.source_fact_ids, ())
        plan = build_client_search(context, ["alex@example.com"], include_profile=False)
        self.assertEqual(plan.source_fact_ids, ("contact",))

    def test_terms_are_literal_phrases_and_do_not_become_boolean_instructions(self):
        messages = [raw_message("literal", body="BAS AND GST"), raw_message("separate", body="BAS GST")]
        self.assertEqual(self.select(["BAS AND GST"], messages), {"literal"})
        messages = [raw_message("ordinary", body="Hello"), raw_message("spam", body="Hello", labels=("SPAM",))]
        self.assertEqual(self.select(['" OR in:anywhere {other}'], messages), set())

    def test_empty_or_exclusion_only_search_is_rejected_and_entries_are_deduplicated(self):
        with self.assertRaises(ValueError):
            build_client_search({}, [], excluded_terms=["newsletter"])
        with self.assertRaises(ValueError):
            build_client_search({}, ["BAS"], match_mode="unknown")
        plan = build_client_search({}, [" Tax  review ", "tax review"])
        self.assertEqual(plan.terms, ("Tax review",))
