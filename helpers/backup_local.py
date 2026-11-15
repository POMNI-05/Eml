"""Back up local profiles, evidence mappings and Google auth. Stop Eml first.

The archive contains confidential data and credentials. Store it privately.
"""
import argparse
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from helpers.launch_local import default_data_directory


def backup(directory, output):
    directory, output = Path(directory).resolve(), Path(output).resolve()
    db = Path(os.environ.get("EML_PROFILE_DB", directory / "client_profiles.sqlite3")).resolve()
    auth = Path(os.environ.get("EML_AUTH_DIR", directory / "auth")).resolve()
    if not db.is_file():
        raise ValueError("No client database found. Check the launcher's data directory.")
    # Snapshot SQLite with its backup API, including committed WAL content.
    with tempfile.TemporaryDirectory(prefix="eml-backup-") as temp:
        snapshot = Path(temp) / "client_profiles.sqlite3"
        with closing(sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)) as source, \
                closing(sqlite3.connect(snapshot)) as destination:
            source.backup(destination)
            if destination.execute("PRAGMA quick_check").fetchone() != ("ok",):
                raise ValueError("Database integrity check failed; archive was not created.")
        # Exclusive creation: never replace an existing backup.
        fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as target, zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.write(snapshot, "client_profiles.sqlite3")
            for name in ("credentials.json", "token.json"):
                if (auth / name).is_file():
                    archive.write(auth / name, "auth/" + name)
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=default_data_directory())
    parser.add_argument("--output", type=Path, required=True, help="New ZIP path in a private backup folder.")
    args = parser.parse_args()
    try:
        result = backup(args.data_dir, args.output)
    except (OSError, ValueError, sqlite3.Error) as error:
        parser.exit(1, f"Backup failed ({type(error).__name__}); check paths, permissions and database integrity. Existing backups were not replaced.\n")
    print(f"Backup saved: {result}\nContains client evidence and credentials. Keep it private.")
