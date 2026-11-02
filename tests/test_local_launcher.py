import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from helpers.launch_local import launch_command, migrate_project_data, runtime_environment


class LocalLauncherTests(unittest.TestCase):
    def test_local_address_and_data_do_not_depend_on_checkout_or_cwd(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {}, clear=True):
            env = runtime_environment(Path(temp) / "persistent")
            self.assertTrue(Path(env["EML_PROFILE_DB"]).is_absolute())
            self.assertTrue(Path(env["EML_AUTH_DIR"]).is_absolute())
            command = launch_command(8502)
            self.assertIn("--server.address=127.0.0.1", command)
            self.assertIn("--server.port=8502", command)
            self.assertIn("--server.headless=true", command)
            self.assertNotIn("--server.enableXsrfProtection=false", command)
            self.assertTrue(any(item.endswith("client_workspace.py") and Path(item).is_absolute() for item in command))

    def test_explicit_migration_copies_sqlite_and_never_overwrites_existing_data(self):
        with tempfile.TemporaryDirectory() as temp:
            root, destination = Path(temp) / "checkout", Path(temp) / "persist"
            (root / "data").mkdir(parents=True)
            (root / "credentials.json").write_text('{"synthetic": true}')
            with sqlite3.connect(root / "data" / "client_profiles.sqlite3") as db:
                db.execute("CREATE TABLE example(value TEXT)")
                db.execute("INSERT INTO example VALUES ('old-profile')")
            with patch.dict(os.environ, {}, clear=True), patch("helpers.launch_local.ROOT", root):
                env = runtime_environment(destination)
                migrate_project_data(env)
                with sqlite3.connect(env["EML_PROFILE_DB"]) as db:
                    self.assertEqual(db.execute("SELECT value FROM example").fetchone()[0], "old-profile")
                (Path(env["EML_AUTH_DIR"]) / "credentials.json").write_text("existing-secret")
                with self.assertRaises(ValueError):
                    migrate_project_data(env)
                self.assertEqual((Path(env["EML_AUTH_DIR"]) / "credentials.json").read_text(), "existing-secret")
