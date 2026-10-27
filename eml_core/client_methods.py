"""Persistent client-to-search-method mappings."""
import json
from .profiles import _now

class ClientSearchMethodStore:
    def __init__(self, profiles):
        self.profiles, self.db = profiles, profiles.connection
        self.db.execute("CREATE TABLE IF NOT EXISTS client_search_methods (client_id TEXT NOT NULL REFERENCES clients(client_id), account_id TEXT NOT NULL, methods_json TEXT NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY(client_id, account_id))")
        self.db.commit()
    def get(self, client_id, account_id):
        self.profiles._require_client(client_id)
        row = self.db.execute("SELECT methods_json FROM client_search_methods WHERE client_id=? AND account_id=?", (client_id, (account_id or '').strip().casefold())).fetchone()
        return json.loads(row[0]) if row else []

    def for_client(self, client_id):
        self.profiles._require_client(client_id)
        rows = self.db.execute(
            "SELECT account_id, methods_json FROM client_search_methods WHERE client_id=? ORDER BY account_id",
            (client_id,),
        )
        return [{"account_id": row[0], "methods": json.loads(row[1])} for row in rows]
    def save(self, client_id, account_id, method):
        self.profiles._require_client(client_id)
        if not isinstance(account_id, str) or not account_id.strip() or not method.get('terms'):
            raise ValueError("A connected mailbox and at least one search entry are required.")
        fields = ("terms", "match_mode", "excluded_terms", "exclusion_area", "subject_prefix", "excluded_subject_prefix")
        value = {field: method.get(field, [] if field.endswith('terms') else '') for field in fields}
        methods = [old for old in self.get(client_id, account_id) if old != value]
        methods.insert(0, value)
        with self.db:
            self.db.execute("INSERT INTO client_search_methods VALUES (?,?,?,?) ON CONFLICT(client_id, account_id) DO UPDATE SET methods_json=excluded.methods_json, updated_at=excluded.updated_at", (client_id, account_id.strip().casefold(), json.dumps(methods[:12], ensure_ascii=False), _now()))
        return methods[:12]
