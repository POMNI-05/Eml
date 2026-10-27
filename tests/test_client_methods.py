import unittest
from eml_core import ClientSearchMethodStore, ProfileStore

class ClientSearchMethodTests(unittest.TestCase):
    def test_methods_are_isolated_and_newest_first(self):
        with ProfileStore(":memory:") as profiles:
            client = profiles.create_client("First")
            store = ClientSearchMethodStore(profiles)
            base = {"terms": ["Alex"], "match_mode": "any", "excluded_terms": [], "subject_prefix": "", "excluded_subject_prefix": ""}
            store.save(client, "staff@firm.example", base)
            store.save(client, "staff@firm.example", {**base, "terms": ["Alex", "bookkeeping"]})
            self.assertEqual(store.get(client, "staff@firm.example")[0]["terms"], ["Alex", "bookkeeping"])
            self.assertEqual(store.get(client, "other@firm.example"), [])
    def test_context_exposes_saved_methods(self):
        with ProfileStore(":memory:") as profiles:
            client = profiles.create_client("First")
            ClientSearchMethodStore(profiles).save(client, "staff@firm.example", {"terms": ["Alex"], "match_mode": "any", "excluded_terms": [], "subject_prefix": "Tax", "excluded_subject_prefix": "Re:"})
            self.assertEqual(profiles.context(client)["saved_search_methods"][0]["subject_prefix"], "Tax")
