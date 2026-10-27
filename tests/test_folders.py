import tempfile
import unittest
from pathlib import Path

from eml_core import ProfileStore
from eml_core.folders import ClientFolderStore


class ClientFolderTests(unittest.TestCase):
    def test_choices_survive_reopening_and_are_isolated_by_client_and_mailbox(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "profiles.sqlite3"
            with ProfileStore(path) as profiles:
                alex = profiles.create_client("Alex")
                other = profiles.create_client("Other")
                folders = ClientFolderStore(profiles)
                folders.save(alex, "STAFF@FIRM.EXAMPLE", [{"id": "L1", "name": "Clients/Alex"}], True)
                self.assertIsNone(folders.get(other, "staff@firm.example"))
                self.assertIsNone(folders.get(alex, "other@firm.example"))
            with ProfileStore(path) as profiles:
                saved = ClientFolderStore(profiles).get(alex, "staff@firm.example")
                self.assertEqual(saved["label_ids"], ["L1"])
                self.assertTrue(saved["include_sub_labels"])

    def test_updating_a_choice_keeps_ids_and_replaces_paths_and_nested_setting(self):
        with ProfileStore(":memory:") as profiles:
            cid = profiles.create_client("Alex")
            folders = ClientFolderStore(profiles)
            folders.save(cid, "staff@firm.example", [{"id": "L1", "name": "Clients/Alex"}], True)
            renamed = {"id": "L1", "name": "Clients/Alex Group"}
            folders.save(cid, "staff@firm.example", [renamed, renamed], False)
            saved = folders.get(cid, "staff@firm.example")
            self.assertEqual(saved["folders"], [renamed])
            self.assertFalse(saved["include_sub_labels"])
            folders.save(cid, "staff@firm.example", [])
            self.assertEqual(folders.get(cid, "staff@firm.example")["label_ids"], [])

    def test_invalid_choices_do_not_overwrite_an_existing_mapping(self):
        with ProfileStore(":memory:") as profiles:
            cid = profiles.create_client("Alex")
            folders = ClientFolderStore(profiles)
            folders.save(cid, "staff@firm.example", [{"id": "L1", "name": "Clients/Alex"}])
            with self.assertRaises(ValueError):
                folders.save(cid, "staff@firm.example", [{"name": "Guessed name"}])
            with self.assertRaises(ValueError):
                folders.save(cid, "", [{"id": "L1", "name": "Clients/Alex"}])
            self.assertEqual(folders.get(cid, "staff@firm.example")["label_ids"], ["L1"])
