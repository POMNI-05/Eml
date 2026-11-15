from contextlib import closing
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from helpers.backup_local import backup


class BackupTests(unittest.TestCase):
    def test_archive_restores_database_and_auth_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {}, clear=True):
            root = Path(temp)
            (root / "auth").mkdir()
            (root / "auth/token.json").write_text('{"synthetic":true}')
            with closing(sqlite3.connect(root / "client_profiles.sqlite3")) as db:
                db.execute("CREATE TABLE mappings(value TEXT)")
                db.execute("INSERT INTO mappings VALUES ('synthetic recovery mapping')")
                db.commit()
            archive = backup(root, root / "backup.zip")
            with zipfile.ZipFile(archive) as saved:
                self.assertIn("auth/token.json", saved.namelist())
                saved.extractall(root / "restored")  # Our own fixed-name archive.
            with closing(sqlite3.connect(root / "restored/client_profiles.sqlite3")) as db:
                self.assertEqual(db.execute("SELECT value FROM mappings").fetchone()[0], "synthetic recovery mapping")
            before = archive.read_bytes()
            with self.assertRaises(FileExistsError):
                backup(root, archive)
            self.assertEqual(before, archive.read_bytes())
