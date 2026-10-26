"""Optional UI integration tests; Gmail and Outlook are never contacted."""

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.fakes import FakeGmail, raw_message

HAS_STREAMLIT = importlib.util.find_spec("streamlit") is not None
if HAS_STREAMLIT:
    from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


def element(elements, label):
    return next(item for item in elements if item.label == label)


@unittest.skipUnless(HAS_STREAMLIT, "Install requirements.txt for UI tests")
class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, {
            "EML_PROFILE_DB": str(Path(self.temp.name) / "profiles.sqlite3")
        })
        env.start()
        self.addCleanup(env.stop)
        self.api = FakeGmail([
            raw_message("m1", body="Company: Example Pty Ltd\nIndustry: Wholesale"),
            raw_message("outside", labels=("L3",), sender="Other <other@outside.example>"),
        ])
        gmail = patch("fetch_emails.get_gmail_service", return_value=self.api)
        self.get_service = gmail.start()
        self.addCleanup(gmail.stop)

    def create(self, app, name):
        element(app.text_input, "New client group name").set_value(name)
        element(app.button, "Create client group").click().run()
        self.assertFalse(app.exception)

    def load_selection(self, app):
        element(app.button, "Load Gmail labels").click().run()
        element(app.multiselect, "Labels").set_value(["L1"]).run()
        element(app.button, "Fetch chosen emails").click().run()
        self.assertFalse(app.exception)

    def test_launch_does_not_read_mail_or_require_credentials(self):
        app = AppTest.from_file(str(ROOT / "client_workspace.py")).run()
        self.assertFalse(app.exception)
        self.get_service.assert_not_called()

    def test_select_extract_confirm_and_switch_client(self):
        app = AppTest.from_file(str(ROOT / "client_workspace.py")).run()
        self.create(app, "Alex group")
        self.load_selection(app)
        self.assertEqual(
            [m.message_id for m in app.session_state["workspace_result"].messages], ["m1"]
        )
        element(app.button, "Suggest client details").click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any("3 new suggestions" in s.value for s in app.success))
        element(app.button, "Confirm suggestion").click().run()
        self.assertFalse(app.exception)
        self.create(app, "Another group")
        with self.assertRaises(KeyError):
            app.session_state["workspace_result"]
        self.assertFalse(any(b.label == "Suggest client details" for b in app.button))
        self.assertTrue(any("No confirmed context" in message.value for message in app.info))

    def test_changed_label_scope_clears_previous_evidence(self):
        app = AppTest.from_file(str(ROOT / "client_workspace.py")).run()
        self.create(app, "Alex group")
        self.load_selection(app)
        element(app.multiselect, "Labels").set_value(["L3"]).run()
        with self.assertRaises(KeyError):
            app.session_state["workspace_result"]

    def test_original_app_clears_committed_selection_when_search_changes(self):
        threads = [{
            "thread_id": "t1", "subject": "Example", "message_count": 1,
            "full_text": "Example evidence", "messages": [],
        }]
        with patch("fetch_emails.fetch_threads", return_value=threads), patch(
            "fetch_emails.filter_threads", return_value=threads
        ):
            app = AppTest.from_file(str(ROOT / "app.py")).run()
            element(app.button, "Fetch emails").click().run()
            element(app.multiselect, "Choose relevant conversations").set_value([0]).run()
            element(app.button, "Use selected conversations").click().run()
            self.assertEqual(len(app.session_state["selected_threads"]), 1)
            element(app.text_input, "Keyword for Gmail search").set_value("new client").run()
            with self.assertRaises(KeyError):
                app.session_state["selected_threads"]
            self.assertFalse(app.exception)


if __name__ == "__main__":
    unittest.main()
