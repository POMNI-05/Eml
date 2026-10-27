"""Optional UI integration tests; Gmail and Outlook are never contacted."""

import importlib.util
import copy
import json
import os
import tempfile
import unittest
from datetime import date
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

    def connect(self, app):
        try:
            if app.session_state["workspace_account"]:
                return
        except KeyError:
            pass
        auth_dir = Path(os.environ["EML_AUTH_DIR"])
        auth_dir.mkdir(exist_ok=True)
        if not (auth_dir / "credentials.json").exists():
            (auth_dir / "credentials.json").write_text("{}")
        app.run()
        element(app.button, "Connect Gmail").click().run()
        self.assertFalse(app.exception)

    def create(self, app, name):
        self.connect(app)
        element(app.text_input, "Client name").set_value(name)
        element(app.button, "Add client").click().run()
        self.assertFalse(app.exception)
        # Synthetic test messages should not depend on the machine's current month.
        element(app.checkbox, "Filter by date").set_value(False).run()

    def load_selection(self, app):
        element(app.radio, "Email source").set_value("Client folders (IMAP)").run()
        element(app.button, "Load folders").click().run()
        element(app.multiselect, "Client folders").set_value(["L1"]).run()
        element(app.button, "Open selected folders →").click().run()
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
        self.assertFalse(any(item.label == "Client" for item in app.selectbox))
        self.assertTrue(all(
            element(app.button, title).disabled
            for title in ("1. Client & folders", "2. Review emails", "3. Draft & export")
        ))

    def test_saved_credentials_show_sign_in_without_upload_or_client_setup(self):
        auth_dir = Path(os.environ["EML_AUTH_DIR"])
        auth_dir.mkdir()
        (auth_dir / "credentials.json").write_text("{}")
        app = AppTest.from_file(str(ROOT / "client_workspace.py")).run()
        self.assertFalse(app.exception)
        self.assertFalse(element(app.button, "Connect Gmail").disabled)
        self.assertFalse(any(
            item.proto.label == "Drop Google credentials JSON here" for item in app.get("file_uploader")
        ))
        self.assertFalse(any(item.label == "Client" for item in app.selectbox))
        self.get_service.assert_not_called()

    def test_saved_authorization_does_not_require_uploading_credentials_again(self):
        auth_dir = Path(os.environ["EML_AUTH_DIR"])
        auth_dir.mkdir()
        (auth_dir / "token.json").write_text("{}")
        app = AppTest.from_file(str(ROOT / "client_workspace.py")).run()
        self.assertFalse(app.exception)
        self.assertFalse(element(app.button, "Connect Gmail").disabled)
        self.assertFalse(any(
            item.proto.label == "Drop Google credentials JSON here" for item in app.get("file_uploader")
        ))
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
        element(app.multiselect, "Client folders").set_value(["L3"]).run()
        with self.assertRaises(KeyError):
            app.session_state["workspace_result"]
        self.assertEqual(app.session_state["workspace_step"], "1. Client & folders")

    def test_client_background_is_independent_of_period_and_reaches_the_draft(self):
        from eml_core import ProfileStore
        from tests.test_generation import FakeModel
        model = FakeModel()
        note = "Wholesale client with two related companies. Quarterly bookkeeping review."
        with patch("workspace_panels.OllamaClient", side_effect=lambda *a, **k: model):
            app = AppTest.from_file(str(ROOT / "client_workspace.py")).run()
            self.create(app, "Alex")
            alex = app.session_state["workspace_client"]
            element(app.text_area, "Background note").set_value(note)
            element(app.button, "Save background").click().run()
            self.assertFalse(app.exception)
            element(app.checkbox, "Filter by date").set_value(True).run()
            element(app.date_input, "From").set_value(date(2026, 10, 1)).run()
            element(app.date_input, "Through").set_value(date(2026, 10, 31)).run()
            self.assertEqual(element(app.text_area, "Background note").value, note)
            with ProfileStore(os.environ["EML_PROFILE_DB"]) as profiles:
                self.assertEqual(profiles.context(alex)["confirmed_facts"][0]["value"], note)
            self.load_selection(app)
            element(app.button, "Load local models").click().run()
            element(app.button, "Generate work record draft").click().run()
            self.assertFalse(app.exception)
            self.assertIn(note, [fact["value"] for fact in model.payload["client_profile"]["confirmed_facts"]])
            element(app.button, "Save background").click().run()
            self.assertTrue(any(
                item.proto.label == "Download Word record" for item in app.get("download_button")
            ))
            self.create(app, "Other")
            self.assertEqual(element(app.text_area, "Background note").value, "")
            element(app.selectbox, "Client").set_value(alex).run()
            self.assertEqual(element(app.text_area, "Background note").value, note)

    def test_action_buttons_advance_and_go_back_without_refetching(self):
        app = AppTest.from_file(str(ROOT / "client_workspace.py")).run()
        self.create(app, "Alex group")
        self.assertEqual(element(app.radio, "Email source").value, "Client folders (IMAP)")
        self.load_selection(app)
        self.assertEqual(app.session_state["workspace_step"], "2. Review emails")
        message_reads = len([c for c in self.api.calls if c[0] == "messages.get"])
        element(app.button, "Use selected emails →").click().run()
        self.assertEqual(app.session_state["workspace_step"], "3. Draft & export")
        element(app.button, "← Back to email review").click().run()
        self.assertEqual(app.session_state["workspace_step"], "2. Review emails")
        self.assertEqual(app.session_state["workspace_selected_ids"], ["m1"])
        element(app.button, "← Change client folders").click().run()
        self.assertEqual(app.session_state["workspace_step"], "1. Client & folders")
        self.assertEqual(len([c for c in self.api.calls if c[0] == "messages.get"]), message_reads)
        self.assertFalse(app.exception)

    def test_sender_bulk_actions_preserve_individual_choices_and_group_by_address(self):
        self.api.data = {mid: raw_message(mid, sender=sender) for mid, sender in [
            ("a1", "Alex <Alex@client.example>"), ("a2", "Accounts <alex@client.example>"),
            ("b", "Alex <other@client.example>"), ("c", "news@example.com"),
        ]}
        app = AppTest.from_file(str(ROOT / "client_workspace.py")).run()
        self.create(app, "Alex")
        self.load_selection(app)
        import streamlit as st
        original_editor = st.data_editor
        def omit_one_message(data, **kwargs):
            rows = original_editor(data, **kwargs)
            if kwargs.get("key") == "workspace_email_table" and "workspace_email_baseline_ids" not in st.session_state:
                return [{**row, "Include": row["Message ID"] != "b"} for row in rows]
            return rows
        # AppTest cannot interact with the canvas editor; supply its edited rows.
        with patch("workspace_panels.st.data_editor", side_effect=omit_one_message):
            app.run()
            self.assertEqual(app.session_state["workspace_selected_ids"], ["a1", "a2", "c"])
            element(app.selectbox, "Sender").set_value("alex@client.example").run()
            element(app.button, "Exclude sender").click().run()
        self.assertEqual(app.session_state["workspace_selected_ids"], ["c"])
        element(app.button, "Select sender").click().run()
        self.assertEqual(app.session_state["workspace_selected_ids"], ["a1", "a2", "c"])
        element(app.selectbox, "Sender").set_value("").run()
        element(app.button, "Exclude all").click().run()
        self.assertEqual(app.session_state["workspace_selected_ids"], [])
        self.assertTrue(element(app.button, "Use selected emails →").disabled)
        element(app.button, "Select all").click().run()
        self.assertEqual(app.session_state["workspace_selected_ids"], ["a1", "a2", "b", "c"])
        self.assertFalse(app.exception)

    def test_client_folders_and_nested_choice_restore_without_crossing_clients(self):
        self.api.data["child"] = raw_message("child", labels=("L2",))
        app = AppTest.from_file(str(ROOT / "client_workspace.py")).run()
        self.create(app, "Alex group")
        alex = app.session_state["workspace_client"]
        element(app.button, "Load folders").click().run()
        element(app.multiselect, "Client folders").set_value(["L1"]).run()
        element(app.checkbox, "Include subfolders").set_value(True).run()
        element(app.button, "Open selected folders →").click().run()
        self.assertEqual(
            {m.message_id for m in app.session_state["workspace_result"].messages}, {"m1", "child"}
        )
        self.create(app, "Other group")
        self.assertEqual(element(app.multiselect, "Client folders").value, [])
        self.assertFalse(element(app.checkbox, "Include subfolders").value)
        self.assertTrue(element(app.button, "Open selected folders →").disabled)
        element(app.selectbox, "Client").set_value(alex).run()
        self.assertEqual(element(app.multiselect, "Client folders").value, ["L1"])
        self.assertTrue(element(app.checkbox, "Include subfolders").value)
        element(app.radio, "Email source").set_value("Client search").run()
        element(app.radio, "Email source").set_value("Client folders (IMAP)").run()
        self.assertEqual(element(app.multiselect, "Client folders").value, ["L1"])
        self.assertTrue(element(app.checkbox, "Include subfolders").value)
        self.assertFalse(app.exception)

    def test_folder_renames_keep_ids_and_removed_folders_require_a_new_choice(self):
        app = AppTest.from_file(str(ROOT / "client_workspace.py")).run()
        self.create(app, "Alex group")
        self.load_selection(app)
        self.api.label_data[0]["name"] = "Clients/Alex Group"
        element(app.button, "Load folders").click().run()
        self.assertEqual(element(app.multiselect, "Client folders").value, ["L1"])
        self.assertIn("📁 Clients/Alex Group", element(app.multiselect, "Client folders").options)
        self.api.label_data = [label for label in self.api.label_data if label["id"] != "L1"]
        element(app.button, "Load folders").click().run()
        self.assertEqual(element(app.multiselect, "Client folders").value, [])
        self.assertTrue(element(app.button, "Open selected folders →").disabled)
        self.assertTrue(any("Saved folders no longer found" in e.value for e in app.warning))
        with self.assertRaises(KeyError):
            app.session_state["workspace_result"]
        self.assertFalse(app.exception)

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

    def test_plain_search_filters_select_mail_and_survive_source_switches(self):
        self.api.data = {}
        for key, subject, body in [
            ("keep", "Tax advice", "Alex bookkeeping completed"),
            ("one_term", "Tax advice", "Alex only"),
            ("excluded", "Tax advice", "Alex bookkeeping newsletter"),
            ("wrong_start", "Re: Tax advice", "Alex bookkeeping completed"),
        ]:
            message = raw_message(key, body=body)
            next(h for h in message["payload"]["headers"] if h["name"] == "Subject")["value"] = subject
            self.api.data[key] = message
        app = AppTest.from_file(str(ROOT / "client_workspace.py")).run()
        self.create(app, "Alex")
        element(app.radio, "Email source").set_value("Client search").run()
        element(app.multiselect, "Find").set_value(["Alex", "bookkeeping"]).run()
        all_label = element(app.radio, "Match").options[1]
        element(app.radio, "Match").set_value(all_label).run()
        element(app.multiselect, "Leave out").set_value(["newsletter"]).run()
        element(app.text_input, "Subject begins with").set_value("Tax").run()
        element(app.button, "Find emails →").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(
            [m.message_id for m in app.session_state["workspace_result"].messages], ["keep"]
        )
        element(app.text_input, "Subject begins with").set_value("Re:").run()
        with self.assertRaises(KeyError):
            app.session_state["workspace_result"]
        self.assertEqual(app.session_state["workspace_step"], "1. Client & folders")
        element(app.radio, "Email source").set_value("Client folders (IMAP)").run()
        element(app.radio, "Email source").set_value("Client search").run()
        self.assertEqual(element(app.multiselect, "Find").value, ["Alex", "bookkeeping"])
        self.assertEqual(element(app.radio, "Match").value, all_label)
        self.assertEqual(element(app.multiselect, "Leave out").value, ["newsletter"])
        self.assertEqual(element(app.text_input, "Subject begins with").value, "Re:")
        self.assertFalse(app.exception)

    def test_search_reset_restores_visible_defaults_and_empty_search_cannot_fetch(self):
        from eml_core import ProfileStore
        app = AppTest.from_file(str(ROOT / "client_workspace.py")).run()
        self.create(app, "Alex")
        with ProfileStore(os.environ["EML_PROFILE_DB"]) as profiles:
            profiles.add_manual(app.session_state["workspace_client"], "aliases", "Alex")
        element(app.radio, "Email source").set_value("Client search").run()
        self.assertEqual(element(app.multiselect, "Find").value, ["Alex"])
        self.assertFalse(any(item.label == "Match" for item in app.radio))
        element(app.multiselect, "Find").set_value([]).run()
        element(app.multiselect, "Leave out").set_value(["newsletter"]).run()
        self.assertTrue(element(app.button, "Find emails →").disabled)
        element(app.text_input, "Hide subjects beginning with").set_value("Re:").run()
        element(app.button, "Reset search").click().run()
        self.assertEqual(element(app.multiselect, "Find").value, ["Alex"])
        self.assertEqual(element(app.multiselect, "Leave out").value, [])
        self.assertEqual(element(app.text_input, "Hide subjects beginning with").value, "")
        self.assertFalse(element(app.button, "Find emails →").disabled)
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
        import streamlit as st
        original_editor = st.data_editor
        def edit_activities(data, **kwargs):
            if str(kwargs.get("key", "")).startswith("activities_"):
                return edited
            return original_editor(data, **kwargs)
        with patch("workspace_panels.st.data_editor", side_effect=edit_activities):
            app.run()
            self.assertFalse(app.exception)
            self.assertTrue(element(app.button, "Save edited draft").disabled)
            self.assertTrue(any("Included activities need" in e.value for e in app.error))
            with ProfileStore(os.environ["EML_PROFILE_DB"]) as profiles:
                self.assertEqual(len(DraftStore(profiles).list(cid)), 1)
        app.run()
        self.assertFalse(element(app.button, "Save edited draft").disabled)
        self.assertEqual(app.session_state[f"work_draft_{cid}"]["draft_id"], draft["draft_id"])

    def test_excluded_messages_stay_excluded_and_never_reach_the_model(self):
        from tests.test_generation import FakeModel
        model = FakeModel()
        self.api.data["m1"] = raw_message("m1", body="I completed the bookkeeping review.")
        self.api.data["m2"] = raw_message("m2", body="Unrelated correspondence")
        with patch("workspace_panels.OllamaClient", side_effect=lambda *a, **k: model):
            app = AppTest.from_file(str(ROOT / "client_workspace.py")).run()
            self.create(app, "Alex group")
            self.load_selection(app)
            import streamlit as st
            original_editor = st.data_editor
            def choose_messages(data, **kwargs):
                rows = original_editor(data, **kwargs)
                if kwargs.get("key") == "workspace_email_table":
                    return [{**row, "Include": row["Message ID"] != "m2"} for row in rows]
                return rows
            # AppTest does not provide an interactive data-editor widget.
            # Return the user's edited rows and verify the resulting AI scope.
            with patch("workspace_panels.st.data_editor", side_effect=choose_messages):
                app.run()
                self.assertEqual(app.session_state["workspace_selected_ids"], ["m1"])
                app.run()
                self.assertEqual(app.session_state["workspace_selected_ids"], ["m1"])
                element(app.button, "Load local models").click().run()
                element(app.button, "Generate work record draft").click().run()
                self.assertFalse(app.exception)
                self.assertEqual(
                    [m["message_id"] for m in model.payload["selected_email_evidence"]], ["m1"]
                )
            element(app.button, "Open selected folders →").click().run()
            self.assertEqual(app.session_state["workspace_selected_ids"], ["m1", "m2"])

    def test_connecting_gmail_confirms_account_without_fetching_messages(self):
        auth_dir = Path(os.environ["EML_AUTH_DIR"])
        auth_dir.mkdir()
        (auth_dir / "credentials.json").write_text("{}")
        app = AppTest.from_file(str(ROOT / "client_workspace.py")).run()
        element(app.button, "Connect Gmail").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["workspace_account"], self.api.account)
        self.assertTrue(any("Connected mailbox" in message.value for message in app.success))
        self.assertFalse(any(name.startswith("messages.") for name, _ in self.api.calls))
        self.assertTrue(any(item.label == "Client" for item in app.selectbox))
        self.assertFalse(any(item.label == "Client group" for item in app.selectbox))

    def test_disconnecting_hides_client_workflow_and_clears_old_email_scope(self):
        app = AppTest.from_file(str(ROOT / "client_workspace.py")).run()
        self.create(app, "Alex")
        self.load_selection(app)
        element(app.button, "Disconnect Gmail").click().run()
        self.assertFalse(app.exception)
        with self.assertRaises(KeyError):
            app.session_state["workspace_result"]
        self.assertFalse(any(item.label == "Client" for item in app.selectbox))
        self.assertFalse(any(item.label == "Load folders" for item in app.button))
        self.assertFalse(any(
            item.proto.label == "Drop Google credentials JSON here" for item in app.get("file_uploader")
        ))

    def test_credentials_can_be_changed_from_compact_account_settings_and_cancelled(self):
        app = AppTest.from_file(str(ROOT / "client_workspace.py")).run()
        self.create(app, "Alex")
        element(app.button, "Change Google app file").click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any(
            item.proto.label == "Drop Google credentials JSON here" for item in app.get("file_uploader")
        ))
        element(app.button, "Cancel").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["workspace_account"], self.api.account)
        self.assertFalse(any(
            item.proto.label == "Drop Google credentials JSON here" for item in app.get("file_uploader")
        ))

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
            element(app.button, "Find emails →").click().run()
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
