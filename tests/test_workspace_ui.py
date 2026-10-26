"""Optional UI integration tests; Gmail and Outlook are never contacted."""

import importlib.util
import copy
import json
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
            "EML_PROFILE_DB": str(Path(self.temp.name) / "profiles.sqlite3"),
            "EML_AUTH_DIR": str(Path(self.temp.name) / "auth"),
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

    def generate_test_draft(self):
        from tests.test_generation import FakeModel
        model = patch("workspace_panels.OllamaClient", side_effect=lambda *a, **k: FakeModel())
        model.start()
        self.addCleanup(model.stop)
        self.api.data["m1"] = raw_message("m1", body="I completed the bookkeeping review.")
        app = AppTest.from_file(str(ROOT / "client_workspace.py")).run()
        self.create(app, "Alex group")
        self.load_selection(app)
        element(app.button, "Load local models").click().run()
        element(app.button, "Generate work record draft").click().run()
        self.assertFalse(app.exception)
        cid = app.session_state["workspace_client"]
        return app, cid, app.session_state[f"work_draft_{cid}"]

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

    def test_credential_upload_and_tutorial_are_available_before_client_creation(self):
        app = AppTest.from_file(str(ROOT / "client_workspace.py")).run()
        labels = [item.proto.label for item in app.get("file_uploader")]
        self.assertIn("Drop Google credentials JSON here", labels)
        self.assertTrue(any("获取 Gmail 凭证" in item.value for item in app.markdown))
        self.get_service.assert_not_called()

    def test_invalid_activity_edits_disable_saving_until_corrected(self):
        from eml_core import ProfileStore
        from invoice.service import DraftStore
        app, cid, draft = self.generate_test_draft()
        edited = [{
            "Item": 1, "Include": True, "Entity": "Example Pty Ltd",
            "Description": "", "Status": "completed", "Reviewer note": "",
        }]
        with patch("workspace_panels.st.data_editor", return_value=edited):
            app.run()
            self.assertFalse(app.exception)
            self.assertTrue(element(app.button, "Save edited draft").disabled)
            self.assertTrue(any("Included activities need" in e.value for e in app.error))
            with ProfileStore(os.environ["EML_PROFILE_DB"]) as profiles:
                self.assertEqual(len(DraftStore(profiles).list(cid)), 1)
        app.run()
        self.assertFalse(element(app.button, "Save edited draft").disabled)
        self.assertEqual(app.session_state[f"work_draft_{cid}"]["draft_id"], draft["draft_id"])

    def test_opening_an_older_invalid_draft_keeps_the_workspace_usable(self):
        from eml_core import ProfileStore
        app, cid, draft = self.generate_test_draft()
        invalid = copy.deepcopy(draft)
        invalid["draft_id"] = "older-invalid-draft"
        invalid["review_edits"] = [{
            "Item": 1, "Include": True, "Description": "", "Status": "completed",
        }]
        # Simulate a draft saved before edit validation was added.
        with ProfileStore(os.environ["EML_PROFILE_DB"]) as profiles:
            with profiles.connection:
                profiles.connection.execute(
                    "INSERT INTO billing_drafts VALUES (?,?,?,?)",
                    (invalid["draft_id"], cid, json.dumps(invalid), invalid["created_at"]),
                )
        app.run()
        element(app.selectbox, "Saved draft").set_value(invalid["draft_id"]).run()
        element(app.button, "Open saved draft").click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any("saved draft contains invalid activity edits" in e.value for e in app.error))
        self.assertTrue(any(
            d.proto.label == "Download Word record" for d in app.get("download_button")
        ))

    def test_document_understanding_search_and_word_generation_use_one_client_context(self):
        from eml_core import ProfileStore
        from eml_core.documents import BackgroundStore
        from tests.test_generation import FakeModel
        model = FakeModel()
        self.api.data["m1"] = raw_message(
            "m1", body="I completed the bookkeeping review.",
            sender="staff@firm.example", to="alex@client.example",
        )
        with patch("workspace_panels.OllamaClient", side_effect=lambda *a, **k: model):
            app = AppTest.from_file(str(ROOT / "client_workspace.py")).run()
            self.create(app, "Alex group")
            cid = app.session_state["workspace_client"]
            with ProfileStore(os.environ["EML_PROFILE_DB"]) as profiles:
                BackgroundStore(profiles).save(
                    cid, "background.txt",
                    b"Alex represents Example Pty Ltd. Contact alex@client.example. Wholesale business.",
                )
            app.run()
            element(app.button, "Load local models").click().run()
            element(app.button, "Analyse documents with AI").click().run()
            self.assertFalse(app.exception)
            with ProfileStore(os.environ["EML_PROFILE_DB"]) as profiles:
                fact_ids = [f["fact_id"] for f in profiles.list_facts(cid, "pending")]
            self.assertEqual(len(fact_ids), 2)
            for fid in fact_ids:
                element(app.selectbox, "Suggestion").set_value(fid).run()
                element(app.button, "Confirm suggestion").click().run()
            element(app.radio, "Email source").set_value("Client search").run()
            element(app.button, "Fetch chosen emails").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(
                [m.message_id for m in app.session_state["workspace_result"].messages], ["m1"]
            )
            element(app.button, "Generate work record draft").click().run()
            self.assertFalse(app.exception)
            draft = app.session_state[f"work_draft_{cid}"]
            self.assertEqual(len(draft["inputs"]["client_profile"]["confirmed_facts"]), 2)
            self.assertEqual(len(draft["inputs"]["background_documents"]), 1)
            self.assertEqual(draft["inputs"]["selected_email_evidence"][0]["message_id"], "m1")
            self.assertTrue(any(
                d.proto.label == "Download Word record" for d in app.get("download_button")
            ))
            element(app.text_input, "Reviewer name").set_value("Test reviewer").run()
            element(
                app.checkbox, "I have checked the included activities against the email evidence"
            ).set_value(True).run()
            element(app.button, "Save edited draft").click().run()
            self.assertFalse(app.exception)
            revised = app.session_state[f"work_draft_{cid}"]
            self.assertTrue(revised["reviewed"])
            self.assertEqual(revised["reviewer"], "Test reviewer")
            self.assertNotEqual(revised["draft_id"], draft["draft_id"])
            self.assertTrue(element(
                app.checkbox, "I have checked the included activities against the email evidence"
            ).value)
            element(app.multiselect, "Background documents sent to AI").set_value([]).run()
            self.assertTrue(any("changed" in item.value for item in app.info))
            self.assertFalse(any(
                d.proto.label == "Download Word record" for d in app.get("download_button")
            ))


if __name__ == "__main__":
    unittest.main()
