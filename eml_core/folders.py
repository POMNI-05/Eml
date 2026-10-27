"""Explicit client-to-Gmail-folder choices, isolated by mailbox account."""

import json

from .profiles import _now


class ClientFolderStore:
    def __init__(self, profiles):
        self.profiles = profiles
        self.db = profiles.connection
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS client_folders (
                client_id TEXT NOT NULL REFERENCES clients(client_id),
                account_id TEXT NOT NULL,
                folders_json TEXT NOT NULL,
                include_sub_labels INTEGER NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (client_id, account_id)
            )
        """)
        self.db.commit()

    def get(self, client_id, account_id):
        self.profiles._require_client(client_id)
        row = self.db.execute(
            "SELECT folders_json, include_sub_labels FROM client_folders "
            "WHERE client_id=? AND account_id=?", (client_id, account_id.strip().casefold()),
        ).fetchone()
        if row is None:
            return None
        folders = json.loads(row["folders_json"])
        return {"folders": folders, "label_ids": [f["id"] for f in folders],
                "include_sub_labels": bool(row["include_sub_labels"])}

    def save(self, client_id, account_id, folders, include_sub_labels=False):
        self.profiles._require_client(client_id)
        if not isinstance(account_id, str) or not account_id.strip():
            raise ValueError("Choose a mailbox before saving client folders.")
        unique = {}
        for folder in folders:
            if not isinstance(folder, dict) or any(
                not isinstance(folder.get(key), str) or not folder[key].strip()
                for key in ("id", "name")
            ):
                raise ValueError("Folders need their Gmail ID and full path.")
            unique[folder["id"]] = {"id": folder["id"], "name": folder["name"]}
        with self.db:
            self.db.execute(
                "INSERT INTO client_folders VALUES (?,?,?,?,?) "
                "ON CONFLICT(client_id, account_id) DO UPDATE SET "
                "folders_json=excluded.folders_json, "
                "include_sub_labels=excluded.include_sub_labels, updated_at=excluded.updated_at",
                (client_id, account_id.strip().casefold(), json.dumps(list(unique.values()), ensure_ascii=False),
                 int(bool(include_sub_labels)), _now()),
            )
