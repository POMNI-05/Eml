"""Client context: evidence-backed suggestions, explicit review, local persistence.

The baseline extractor uses headers and explicit labelled lines only. It does
not infer company ownership, industry from a domain, tax needs, or completed
billable work. A future local model can implement the same Extractor protocol.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email.utils import getaddresses, parseaddr
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Protocol

if TYPE_CHECKING:
    from .mailbox import Email


FIELDS = {
    "contacts", "entities", "aliases", "domains", "industry",
    "business_description", "engagement_scope", "history_notes", "potential_need",
    "relationships",
}
SCALAR_FIELDS = {"industry", "business_description", "engagement_scope", "history_notes"}


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _value(field: str, value: Any) -> Any:
    if field not in FIELDS:
        raise ValueError(f"Unsupported profile field: {field}")
    if field == "contacts":
        if not isinstance(value, dict):
            raise ValueError("A contact needs a name/email object.")
        email = str(value.get("email", "")).strip().casefold()
        if parseaddr(email)[1] != email or not re.fullmatch(r"[^@\s]+@[^@\s]+", email):
            raise ValueError("A contact needs a valid email address.")
        return {"email": email, "name": str(value.get("name", "")).strip()}
    if field == "entities":
        if (
            not isinstance(value, dict) or not isinstance(value.get("name"), str)
            or not value["name"].strip()
        ):
            raise ValueError("An entity needs a name.")
        return {"name": str(value["name"]).strip()}
    if field == "relationships":
        if not isinstance(value, dict) or not all(
            isinstance(value.get(k), str) and value[k].strip()
            for k in ("from_entity", "to_entity", "relationship")
        ):
            raise ValueError("A relationship needs two entities and a relationship description.")
        return {k: value[k].strip() for k in ("from_entity", "to_entity", "relationship")}
    if not isinstance(value, str) or not value.strip():
        raise ValueError("A profile value must be non-empty text.")
    return value.strip().casefold() if field == "domains" else value.strip()


@dataclass(frozen=True)
class Evidence:
    source_type: str
    excerpt: str
    mailbox_id: str = ""
    message_id: str = ""
    date: str = ""
    document_id: str = ""
    location: str = ""

    def __post_init__(self):
        if self.source_type not in {
            "email_header", "email_body", "manual", "import", "background_document",
        }:
            raise ValueError("Unknown evidence type.")
        if not self.excerpt.strip():
            raise ValueError("Evidence must include an excerpt or manual note.")
        if self.source_type.startswith("email_") and not (
            self.mailbox_id and self.message_id
        ):
            raise ValueError("Email evidence needs mailbox and message IDs.")
        if self.source_type == "background_document" and not (self.document_id and self.location):
            raise ValueError("Document evidence needs document ID and location.")


@dataclass(frozen=True)
class Candidate:
    field: str
    value: Any
    evidence: tuple[Evidence, ...]

    def __post_init__(self):
        _value(self.field, self.value)
        if not self.evidence:
            raise ValueError("A suggestion must have evidence.")


class Extractor(Protocol):
    version: str

    def extract(self, message: Email, mailbox_id: str) -> Iterable[Candidate]: ...


def _new_body(text: str) -> str:
    """Conservative quote boundary heuristic; not a full email quote parser."""
    lines = []
    for line in text.splitlines():
        if re.match(r"^\s*(>|On .+wrote:|[-_]+\s*Original Message)", line, re.I):
            break
        lines.append(line)
    return "\n".join(lines)


class RuleExtractor:
    """Suggest external header contacts and explicit Company:/Industry: lines."""

    def __init__(self, own_addresses=(), excluded_domains=()):
        self.own_addresses = {s.strip().casefold() for s in own_addresses if s.strip()}
        self.excluded_domains = {
            s.strip().casefold().lstrip("@") for s in excluded_domains if s.strip()
        }
        config = _json([sorted(self.own_addresses), sorted(self.excluded_domains)])
        self.version = "explicit-fields-v1:" + hashlib.sha256(config.encode()).hexdigest()[:12]

    def extract(self, message: Email, mailbox_id: str) -> Iterable[Candidate]:
        # All recipients are suggestions, not automatically assigned clients.
        for label, raw in (
            ("From", message.sender), ("To", message.to), ("Cc", message.cc)
        ):
            for name, address in getaddresses([raw]):
                address = address.casefold().strip()
                if not re.fullmatch(r"[^@\s]+@[^@\s]+", address):
                    continue
                if address in self.own_addresses or address.split("@")[-1] in self.excluded_domains:
                    continue
                yield Candidate(
                    "contacts", {"name": name, "email": address},
                    (Evidence("email_header", f"{label}: {raw}",
                              mailbox_id, message.message_id, message.date),),
                )
        mapping = {
            "company": "entities", "entity": "entities", "legal entity": "entities",
            "industry": "industry", "business": "business_description",
            "business description": "business_description",
            "agreed services": "engagement_scope",
        }
        for line in _new_body(message.body).splitlines():
            match = re.match(
                r"^\s*(Company|Entity|Legal entity|Industry|Business|"
                r"Business description|Agreed services)\s*:\s*(.{2,500})\s*$",
                line, re.I,
            )
            if match:
                field = mapping[match[1].casefold()]
                value = {"name": match[2].strip()} if field == "entities" else match[2].strip()
                yield Candidate(
                    field, value,
                    (Evidence("email_body", line.strip(), mailbox_id,
                              message.message_id, message.date),),
                )


class ProfileStore:
    """A small SQLite store. Confirmed facts and unreviewed suggestions are separate."""

    def __init__(self, path: str | Path):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(path), timeout=15)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS clients (
                client_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS facts (
                fact_id TEXT PRIMARY KEY,
                client_id TEXT NOT NULL REFERENCES clients(client_id),
                field TEXT NOT NULL,
                value_json TEXT NOT NULL,
                status TEXT NOT NULL CHECK (
                    status IN ('pending','confirmed','rejected','superseded')
                ),
                evidence_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS facts_client ON facts(client_id, status);
            CREATE TABLE IF NOT EXISTS processed (
                client_id TEXT NOT NULL REFERENCES clients(client_id),
                mailbox_id TEXT NOT NULL,
                message_id TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                extractor_version TEXT NOT NULL,
                processed_at TEXT NOT NULL,
                PRIMARY KEY(client_id, mailbox_id, message_id)
            );
        """)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        self.connection.close()

    def create_client(self, display_name: str, client_id: str | None = None) -> str:
        if not display_name.strip():
            raise ValueError("Client name is required.")
        client_id = client_id or str(uuid.uuid4())
        if not client_id.strip():
            raise ValueError("Client ID is required.")
        with self.connection:
            self.connection.execute(
                "INSERT INTO clients VALUES (?, ?, ?)",
                (client_id, display_name.strip(), _now()),
            )
        return client_id

    def _require_client(self, client_id: str):
        if not self.connection.execute(
            "SELECT 1 FROM clients WHERE client_id=?", (client_id,)
        ).fetchone():
            raise ValueError("Unknown client group.")

    def list_clients(self) -> list[dict]:
        return [dict(row) for row in self.connection.execute(
            "SELECT * FROM clients ORDER BY display_name, client_id"
        )]

    def list_facts(self, client_id: str, status: str | None = None) -> list[dict]:
        self._require_client(client_id)
        query = "SELECT * FROM facts WHERE client_id=?"
        params = [client_id]
        if status is not None:
            query += " AND status=?"
            params.append(status)
        query += " ORDER BY field, fact_id"
        output = []
        for row in self.connection.execute(query, params):
            value = dict(row)
            value["value"] = json.loads(value.pop("value_json"))
            value["evidence"] = json.loads(value.pop("evidence_json"))
            output.append(value)
        return output

    def _write_candidate(self, client_id: str, candidate: Candidate) -> tuple[str, bool]:
        value = _value(candidate.field, candidate.value)
        key = _json([client_id, candidate.field, value])
        fact_id = hashlib.sha256(key.encode()).hexdigest()
        old = self.connection.execute(
            "SELECT evidence_json FROM facts WHERE fact_id=?", (fact_id,)
        ).fetchone()
        evidence = json.loads(old[0]) if old else []
        for source in candidate.evidence:
            encoded = asdict(source)
            if encoded not in evidence:
                evidence.append(encoded)
        if old:
            # More evidence never re-approves rejected facts or overwrites review.
            self.connection.execute(
                "UPDATE facts SET evidence_json=?, updated_at=? WHERE fact_id=?",
                (_json(evidence), _now(), fact_id),
            )
        else:
            self.connection.execute(
                "INSERT INTO facts VALUES (?, ?, ?, ?, 'pending', ?, ?)",
                (fact_id, client_id, candidate.field, _json(value),
                 _json(evidence), _now()),
            )
        return fact_id, old is None

    def is_processed(self, client_id: str, mailbox_id: str, message: Email, version: str) -> bool:
        row = self.connection.execute(
            "SELECT fingerprint, extractor_version FROM processed "
            "WHERE client_id=? AND mailbox_id=? AND message_id=?",
            (client_id, mailbox_id.casefold(), message.message_id),
        ).fetchone()
        return bool(row and row[0] == message.fingerprint() and row[1] == version)

    def ingest(self, client_id: str, mailbox_id: str, message: Email,
               version: str, candidates: Iterable[Candidate]) -> int:
        self._require_client(client_id)
        mailbox_id = mailbox_id.casefold()
        if not message.message_id or not mailbox_id:
            raise ValueError("Message and mailbox IDs are required.")
        candidates = list(candidates)
        for candidate in candidates:
            for evidence in candidate.evidence:
                if (
                    not evidence.source_type.startswith("email_")
                    or evidence.mailbox_id.casefold() != mailbox_id
                    or evidence.message_id != message.message_id
                ):
                    raise ValueError("Extractor evidence is outside this input message.")
                if evidence.source_type == "email_body" and evidence.excerpt not in message.body:
                    raise ValueError("Quoted body evidence is not present in this message.")
                headers = f"From: {message.sender}\nTo: {message.to}\nCc: {message.cc}"
                if evidence.source_type == "email_header" and evidence.excerpt not in headers:
                    raise ValueError("Quoted header evidence is not present in this message.")
        with self.connection:
            count = sum(self._write_candidate(client_id, c)[1] for c in candidates)
            self.connection.execute(
                "INSERT INTO processed VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(client_id, mailbox_id, message_id) DO UPDATE SET "
                "fingerprint=excluded.fingerprint, "
                "extractor_version=excluded.extractor_version, "
                "processed_at=excluded.processed_at",
                (client_id, mailbox_id, message.message_id,
                 message.fingerprint(), version, _now()),
            )
        return count

    def review(self, client_id: str, fact_id: str, decision: str,
               *, replace_existing: bool = False):
        if decision not in {"confirmed", "rejected"}:
            raise ValueError("Review decision must be confirmed or rejected.")
        row = self.connection.execute(
            "SELECT field, value_json FROM facts WHERE fact_id=? AND client_id=?",
            (fact_id, client_id),
        ).fetchone()
        if row is None:
            raise ValueError("Suggestion does not belong to this client.")
        with self.connection:
            if decision == "confirmed" and row["field"] in SCALAR_FIELDS:
                other = self.connection.execute(
                    "SELECT fact_id FROM facts WHERE client_id=? AND field=? "
                    "AND status='confirmed' AND fact_id<>?",
                    (client_id, row["field"], fact_id),
                ).fetchall()
                if other and not replace_existing:
                    raise ValueError("A confirmed value exists; explicitly choose replacement.")
                if other:
                    self.connection.execute(
                        "UPDATE facts SET status='superseded', updated_at=? "
                        "WHERE client_id=? AND field=? AND status='confirmed' AND fact_id<>?",
                        (_now(), client_id, row["field"], fact_id),
                    )
            self.connection.execute(
                "UPDATE facts SET status=?, updated_at=? WHERE fact_id=?",
                (decision, _now(), fact_id),
            )

    def add_background_candidates(self, client_id: str, documents, candidates) -> int:
        """Validate all sources before adding any candidate."""
        self._require_client(client_id)
        lookup = {}
        for doc in documents:
            if doc.client_id != client_id:
                raise ValueError("Background document belongs to another client.")
            lookup[doc.document_id] = {p.location: p.text for p in doc.parts}
        candidates = list(candidates)
        for candidate in candidates:
            for source in candidate.evidence:
                text = lookup.get(source.document_id, {}).get(source.location, "")
                if (
                    source.source_type != "background_document"
                    or not source.excerpt.strip()
                    or " ".join(source.excerpt.split()) not in " ".join(text.split())
                ):
                    raise ValueError("Background citation is outside the chosen documents.")
        with self.connection:
            return sum(self._write_candidate(client_id, c)[1] for c in candidates)

    def add_manual(self, client_id: str, field: str, value: Any,
                   *, note: str = "Entered by reviewer", replace_existing: bool = False) -> str:
        self._require_client(client_id)
        candidate = Candidate(field, value, (Evidence("manual", note, date=_now()),))
        with self.connection:
            fact_id, _ = self._write_candidate(client_id, candidate)
        self.review(client_id, fact_id, "confirmed", replace_existing=replace_existing)
        return fact_id

    def context(self, client_id: str) -> dict:
        self._require_client(client_id)
        facts = self.list_facts(client_id, "confirmed")
        name = self.connection.execute(
            "SELECT display_name FROM clients WHERE client_id=?", (client_id,)
        ).fetchone()[0]
        return {
            "client_id": client_id, "display_name": name,
            "confirmed_facts": [f for f in facts if f["field"] != "potential_need"],
            "possible_needs": [f for f in facts if f["field"] == "potential_need"],
            "note": "Possible needs are hypotheses. This profile is not evidence of completed work.",
        }

    def import_legacy(self, data: dict | list) -> int:
        """Import existing clients.json; existing client IDs are left unchanged."""
        if not isinstance(data, (dict, list)):
            raise ValueError("Expected a client object or list.")
        rows = data if isinstance(data, list) else data.get("clients", [data])
        if not isinstance(rows, list):
            raise ValueError("Expected a client object, list, or {'clients': [...]} file.")
        plan = []
        existing = {c["client_id"] for c in self.list_clients()}
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("Each client must be an object.")
            name = row.get("display_name") or row.get("client_name") or row.get("company_name")
            if not name or not isinstance(name, str):
                raise ValueError("Each client needs a display_name or client_name.")
            cid = row.get("client_id") or "legacy-" + hashlib.sha256(name.encode()).hexdigest()[:16]
            if not isinstance(cid, str):
                raise ValueError("Client IDs must be strings.")
            if cid in existing:
                continue
            values = []
            contacts = row.get("primary_contacts", [])
            by_email = {}
            for contact in contacts:
                if isinstance(contact, dict) and contact.get("email"):
                    normal = _value("contacts", contact)
                    by_email[normal["email"]] = normal
            for address in row.get("emails", []):
                normal = _value("contacts", {"email": address})
                by_email.setdefault(normal["email"], normal)
            values.extend(("contacts", c) for c in by_email.values())
            entities = list(row.get("entities", []))
            if row.get("company_name"):
                entities.append({"name": row["company_name"]})
            for entity in entities:
                values.append(("entities", {"name": entity} if isinstance(entity, str) else entity))
            for field in ("aliases", "domains"):
                values.extend((field, v) for v in row.get(field, []))
            for field in SCALAR_FIELDS:
                if row.get(field):
                    values.append((field, row[field]))
            for field, value in values:
                _value(field, value)
            plan.append((cid, name, values))
            existing.add(cid)
        with self.connection:
            for cid, name, values in plan:
                self.connection.execute("INSERT INTO clients VALUES (?, ?, ?)", (cid, name, _now()))
                for field, value in values:
                    candidate = Candidate(
                        field, value, (Evidence("import", "Existing client list", date=_now()),)
                    )
                    fid, _ = self._write_candidate(cid, candidate)
                    self.connection.execute(
                        "UPDATE facts SET status='confirmed' WHERE fact_id=?", (fid,)
                    )
        return len(plan)

    def export_legacy(self) -> list[dict]:
        """Confirmed facts in the format understood by Eml's existing app.py."""
        result = []
        for client in self.list_clients():
            values: dict[str, list] = {}
            for fact in self.list_facts(client["client_id"], "confirmed"):
                values.setdefault(fact["field"], []).append(fact["value"])
            contacts = values.get("contacts", [])
            entities = values.get("entities", [])
            item = {
                "client_id": client["client_id"], "display_name": client["display_name"],
                "client_name": client["display_name"],
                "company_name": entities[0]["name"] if len(entities) == 1 else "",
                "primary_contacts": contacts, "emails": sorted({c["email"] for c in contacts}),
                "entities": entities, "aliases": values.get("aliases", []),
                "domains": values.get("domains", []),
            }
            for field in SCALAR_FIELDS:
                if values.get(field):
                    item[field] = values[field][0]
            result.append(item)
        return result


def update_profile(store: ProfileStore, client_id: str, mailbox_id: str,
                   messages: Iterable[Email], extractor: Extractor) -> dict:
    """Incremental extraction for this chosen input, not an entire-mailbox scan.

    Each successful message and its checkpoint commit together. A failed
    extraction is retryable. Changed content or an extractor version/config
    change is processed again; previous reviewer decisions are retained.
    """
    store._require_client(client_id)
    processed = skipped = added = 0
    for message in messages:
        if store.is_processed(client_id, mailbox_id, message, extractor.version):
            skipped += 1
            continue
        candidates = list(extractor.extract(message, mailbox_id))
        added += store.ingest(client_id, mailbox_id, message, extractor.version, candidates)
        processed += 1
    return {"processed_messages": processed, "skipped_messages": skipped,
            "new_suggestions": added}
