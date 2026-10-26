import subprocess
import unittest
from unittest.mock import patch

from helpers.inspect_outlook_dictionary import folder_terms
from outlook_adapter import (
    FIELD_SEPARATOR, OutlookSelectionError,
    get_selected_outlook_email, get_selected_outlook_message_ids,
)


class OutlookHelperTests(unittest.TestCase):
    @patch("outlook_adapter.subprocess.run")
    def test_empty_folder_field_is_preserved(self, run):
        run.return_value = subprocess.CompletedProcess(
            [], 0, FIELD_SEPARATOR.join(["<a@b>", "Subject", "Alex", "a@b", "date", ""]) + "\n", ""
        )
        self.assertIsNone(get_selected_outlook_email()["folder_name"])

    @patch("outlook_adapter.subprocess.run")
    def test_multiple_ids_are_deduplicated(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, "<a@b>\n<a@b>\n<c@d>\n", "")
        self.assertEqual(get_selected_outlook_message_ids(), ["<a@b>", "<c@d>"])

    @patch("outlook_adapter.subprocess.run", side_effect=FileNotFoundError)
    def test_non_mac_error_is_actionable(self, run):
        with self.assertRaisesRegex(OutlookSelectionError, "Run on a Mac"):
            get_selected_outlook_message_ids()

    def test_dictionary_inspection_reports_actual_folder_terms(self):
        xml = """<dictionary><suite name="Mail">
            <class name="application"><property name="selected folder" type="mail folder"/></class>
            <class name="mail folder"><element type="message"/><property name="name" type="text"/></class>
            <class name="contact"><property name="name" type="text"/></class>
            </suite></dictionary>"""
        result = folder_terms(xml)
        self.assertEqual({item["name"] for item in result}, {"application", "mail folder"})


if __name__ == "__main__":
    unittest.main()
