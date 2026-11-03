from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from helpers.check_runtime import diagnose, dns_check, https_check
from tests.test_auth_documents import credential_bytes


class RuntimeDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.database = self.root / "profiles.sqlite3"
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("CREATE TABLE example(value TEXT)")
            connection.execute("INSERT INTO example VALUES ('private-client-content')")
            connection.commit()
        (self.root / "credentials.json").write_bytes(credential_bytes())
        token = self.root / "token.json"
        token.write_text(json.dumps({
            "client_id": "test-client.apps.googleusercontent.com", "client_secret": "private-client-secret",
            "token": "private-access-token", "refresh_token": "private-refresh-token",
        }))
        token.chmod(0o600)
        environment = patch.dict(os.environ, {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        health = patch("helpers.check_runtime.workspace_check", return_value=("ok", "Local server answers."))
        health.start()
        self.addCleanup(health.stop)

    def report(self, **kwargs):
        return diagnose(auth_directory=self.root, database=self.database, **kwargs)

    def checks(self, report):
        return {item["name"]: item for item in report["checks"]}

    def test_offline_scan_is_read_only_and_does_not_expose_credentials_or_client_data(self):
        token_before = (self.root / "token.json").read_bytes()
        database_before = self.database.read_bytes()
        with patch("helpers.check_runtime.dns_check") as dns, patch("helpers.check_runtime.https_check") as https:
            report = self.report(network=False)
        dns.assert_not_called()
        https.assert_not_called()
        for secret in ("private-access-token", "private-refresh-token", "private-client-secret", "test-only", "private-client-content"):
            self.assertNotIn(secret, json.dumps(report))
        self.assertEqual((self.root / "token.json").read_bytes(), token_before)
        self.assertEqual(self.database.read_bytes(), database_before)
        self.assertEqual(self.checks(report)["profile_database"]["status"], "ok")

    def test_missing_database_is_never_created(self):
        missing = self.root / "missing" / "profiles.sqlite3"
        report = diagnose(auth_directory=self.root, database=missing, network=False)
        self.assertEqual(self.checks(report)["profile_database"]["status"], "warning")
        self.assertFalse(missing.parent.exists())

    def test_dns_failure_skips_https_and_preserves_saved_authorization(self):
        with patch("helpers.check_runtime.dns_check", return_value=("error", "DNS failed.")), \
                patch("helpers.check_runtime.https_check") as https:
            report = self.report()
        https.assert_not_called()
        self.assertEqual(self.checks(report)["google_https"]["status"], "skipped")
        self.assertEqual(self.checks(report)["saved_authorization"]["status"], "ok")

    def test_restricted_runtime_marker_is_a_warning_not_a_replacement_for_network_tests(self):
        with patch.dict(os.environ, {"CODEX_SANDBOX_NETWORK_DISABLED": "1"}), \
                patch("helpers.check_runtime.dns_check", return_value=("ok", "DNS works.")) as dns, \
                patch("helpers.check_runtime.https_check", return_value=("ok", "HTTPS works.")) as https:
            report = self.report()
        self.assertEqual(self.checks(report)["execution_context"]["status"], "warning")
        self.assertEqual(dns.call_count, 2)
        https.assert_called_once_with()

    def test_mismatched_oauth_apps_are_reported_without_printing_ids_or_secrets(self):
        (self.root / "credentials.json").write_bytes(credential_bytes(client="different-app"))
        report = self.report(network=False)
        self.assertEqual(self.checks(report)["saved_authorization"]["status"], "error")
        self.assertNotIn("different-app", json.dumps(report))

    def test_invalid_private_files_do_not_echo_their_contents(self):
        for filename in ("credentials.json", "token.json"):
            (self.root / filename).write_text('["private-broken-configuration"]')
        report = self.report(network=False)
        self.assertEqual(self.checks(report)["oauth_configuration"]["status"], "error")
        self.assertEqual(self.checks(report)["saved_authorization"]["status"], "error")
        self.assertNotIn("private-broken-configuration", json.dumps(report))

    def test_dns_probe_has_a_deadline_and_never_returns_provider_output(self):
        with patch("helpers.check_runtime.subprocess.run", side_effect=subprocess.TimeoutExpired("python", 5)) as run:
            status, detail = dns_check("oauth2.googleapis.com")
        self.assertEqual(status, "error")
        self.assertIn("five seconds", detail)
        self.assertEqual(run.call_args.kwargs["timeout"], 5)
        self.assertEqual(run.call_args.kwargs["stderr"], subprocess.DEVNULL)

    def test_expected_google_404_proves_https_transport_without_sending_credentials(self):
        error = HTTPError("https://oauth2.googleapis.com/token", 404, "unused-private-body", {}, None)
        with patch("helpers.check_runtime.build_opener") as opener:
            opener.return_value.open.side_effect = error
            status, detail = https_check()
        self.assertEqual(status, "ok")
        self.assertIn("404", detail)
        self.assertNotIn("unused-private-body", detail)
        self.assertEqual(opener.return_value.open.call_args.args, ("https://oauth2.googleapis.com/token",))

    def test_https_failures_do_not_expose_error_bodies(self):
        with patch("helpers.check_runtime.build_opener") as opener:
            opener.return_value.open.side_effect = URLError("private-network-details")
            status, detail = https_check()
        self.assertEqual(status, "error")
        self.assertNotIn("private-network-details", detail)

    def test_invalid_port_is_rejected_before_any_scan(self):
        with self.assertRaises(ValueError):
            self.report(port=80)
