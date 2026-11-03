"""Small additive per-client generation settings; no credentials or results."""

import json
from pathlib import Path

from eml_core.profiles import _now
from eml_core.privacy import parse_literal_rules

DEFAULT_STYLE = (Path(__file__).resolve().parents[1] / "prompts" / "billing_style.md").read_text(encoding="utf-8")

LEGACY_STYLE = """Write concise descriptions suitable for an accountant's billing work record.
Use the client's confirmed entity structure to distinguish related companies.
Group repeated correspondence about the same work. Keep requests and unfinished
work distinguishable from completed work. Flag possible overlap with past bills.
Do not invent time, prices or tasks to fill a template.
"""


class GenerationTemplateStore:
    def __init__(self, profiles):
        self.profiles, self.db = profiles, profiles.connection
        self.db.execute("""CREATE TABLE IF NOT EXISTS generation_templates (
            client_id TEXT PRIMARY KEY REFERENCES clients(client_id),
            settings_json TEXT NOT NULL, updated_at TEXT NOT NULL)""")
        self.db.commit()

    def get(self, client_id):
        self.profiles._require_client(client_id)
        row = self.db.execute("SELECT settings_json FROM generation_templates WHERE client_id=?", (client_id,)).fetchone()
        value = json.loads(row[0]) if row else {"style": DEFAULT_STYLE, "privacy_rules": "", "local_only": False}
        if value["style"].strip() in {
            """Write professional accountant billing descriptions: action, specific work, entity and period where evidenced.
Use precise accounting terminology and concise invoice-style phrases. Group related correspondence; avoid email-by-email narration.
Keep completed, pending and requested work distinct. Flag possible prior billing overlap. Never invent work, time or fees.""",
            LEGACY_STYLE.strip(),
            LEGACY_STYLE.replace("Do not invent", "Use plain language. Do not invent").strip(),
        }:
            value["style"] = DEFAULT_STYLE
        return value

    def save(self, client_id, *, style, privacy_rules, local_only):
        self.profiles._require_client(client_id)
        if not isinstance(style, str) or len(style) > 8000 or not isinstance(local_only, bool):
            raise ValueError("Use up to 8,000 characters of output preferences and a valid privacy choice.")
        parse_literal_rules(privacy_rules)
        value = {"style": style, "privacy_rules": privacy_rules, "local_only": local_only}
        with self.db:
            self.db.execute("""INSERT INTO generation_templates VALUES (?,?,?)
                ON CONFLICT(client_id) DO UPDATE SET settings_json=excluded.settings_json, updated_at=excluded.updated_at""",
                (client_id, json.dumps(value, ensure_ascii=False), _now()))

