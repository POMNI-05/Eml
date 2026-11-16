import json
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from helpers.windows_trial import trial_environment
from eml_core.outlook_adapter import get_selected_outlook_message_ids, OutlookSelectionError


class WindowsTrialTests(unittest.TestCase):
    def test_production_paths_and_cloud_key_cannot_bleed_into_trial(self):
        with patch.dict(os.environ, {"LOCALAPPDATA": "C:/Synthetic/AppData", "EML_AUTH_DIR": "production-auth",
                                     "EML_PROFILE_DB": "production-db", "EML_DATA_DIR": "production",
                                     "EML_ENABLE_LOCAL_LLM": "1", "GEMINI_API_KEY": "synthetic-key"}):
            real, demo = trial_environment(), trial_environment(demo=True)
        self.assertNotEqual(real["EML_PROFILE_DB"], demo["EML_PROFILE_DB"])
        for env in (real, demo):
            self.assertNotIn("production", env["EML_AUTH_DIR"])
            self.assertNotIn("production", env["EML_PROFILE_DB"])
            self.assertEqual(Path(env["EML_PROFILE_DB"]).parent, Path(env["EML_DATA_DIR"]))
            self.assertEqual(env["EML_ENABLE_LOCAL_LLM"], "0")
            self.assertNotIn("GEMINI_API_KEY", env)

    def invoke(self, data, code=0):
        with patch("eml_core.outlook_adapter.sys.platform", "win32"), \
                patch("eml_core.outlook_adapter.subprocess.CREATE_NO_WINDOW", 0x08000000, create=True), \
                patch("eml_core.outlook_adapter.subprocess.run", return_value=subprocess.CompletedProcess([], code, json.dumps(data), "private-provider-details")) as run:
            result = get_selected_outlook_message_ids()
            self.assertEqual(run.call_args.args[0][0], "powershell.exe")
            self.assertEqual(run.call_args.kwargs["timeout"], 60)
            return result

    def test_classic_outlook_selection_deduplicates_only_exact_ids(self):
        self.assertEqual(self.invoke({"ids": ["<a@b>", "<a@b>", "<c@d>"]}), ["<a@b>", "<c@d>"])

    def test_empty_or_mixed_selection_never_returns_a_partial_result(self):
        for code in ("empty", "not_mail", "missing_id", "too_many", "unavailable"):
            with self.subTest(code=code), self.assertRaises(OutlookSelectionError) as caught:
                self.invoke({"error": code, "ids": ["<a@b>"]}, code=1)
            self.assertNotIn("private-provider", str(caught.exception))

    def test_malformed_identifiers_are_rejected_before_gmail(self):
        for ids in ([], ["<a@b> OR subject:private"], ["<a@b"], [123], "<a@b>"):
            with self.subTest(ids=ids), self.assertRaises(OutlookSelectionError):
                self.invoke({"ids": ids})

    def test_outlook_timeout_has_safe_actionable_error(self):
        with patch("eml_core.outlook_adapter.sys.platform", "win32"), \
                patch("eml_core.outlook_adapter.subprocess.CREATE_NO_WINDOW", 0x08000000, create=True), \
                patch("eml_core.outlook_adapter.subprocess.run", side_effect=subprocess.TimeoutExpired("powershell", 60)), \
                self.assertRaisesRegex(OutlookSelectionError, "Gmail folders/search"):
            get_selected_outlook_message_ids()
