import io
from pathlib import Path
import tempfile
import unittest
import zipfile

from helpers.package_windows import ENTRYPOINTS, PREFIX, package_source


def source_archive(extra=None):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name in (*ENTRYPOINTS.values(), "helpers/windows_trial.py", "eml_ui/client_workspace.py"):
            archive.writestr(name, "synthetic")
        for name, value in (extra or {}).items():
            archive.writestr(name, value)
    return buffer.getvalue()


class WindowsPackageTests(unittest.TestCase):
    def test_user_facing_root_is_small_and_all_source_is_preserved_under_app(self):
        with tempfile.TemporaryDirectory() as temp:
            output = package_source(source_archive({"eml_core/example.py": "synthetic-core"}), Path(temp) / "handoff.zip")
            with zipfile.ZipFile(output) as package:
                children = {name.removeprefix(PREFIX).split("/")[0] for name in package.namelist()}
                self.assertEqual(children, {"Install.cmd", "Start.cmd", "Try-Demo.cmd", "README.txt", "_app"})
                self.assertEqual(package.read(PREFIX + "_app/eml_core/example.py"), b"synthetic-core")
                launcher = package.read(PREFIX + "Start.cmd")
                self.assertIn(b'cd /d "%~dp0_app"', launcher)
                self.assertIn(b'call "Launch-Windows-Test.cmd"', launcher)
            with self.assertRaises(FileExistsError):
                package_source(source_archive(), output)

    def test_private_files_and_path_traversal_are_rejected_before_zip_creation(self):
        with tempfile.TemporaryDirectory() as temp:
            for name in ("token.json", "credentials.json", "data/example.txt", "../escape.txt", ".venv/python.exe"):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    package_source(source_archive({name: "synthetic"}), Path(temp) / "handoff.zip")
                self.assertFalse((Path(temp) / "handoff.zip").exists())
