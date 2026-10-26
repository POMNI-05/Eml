"""Client-scoped background documents. Originals and extracted text stay local."""

from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path

from .profiles import Candidate, Evidence, ProfileStore, _now

MAX_BYTES = 20 * 1024 * 1024
MAX_TEXT = 200_000
ROLES = {"client_background", "engagement_scope", "reference"}


class DocumentError(ValueError):
    pass


@dataclass(frozen=True)
class DocumentPart:
    location: str
    text: str


@dataclass(frozen=True)
class BackgroundDocument:
    document_id: str
    client_id: str
    filename: str
    role: str
    sha256: str
    parts: tuple[DocumentPart, ...]
    warnings: tuple[str, ...] = ()

    def for_ai(self) -> dict:
        return asdict(self)


def extract_document(filename: str, content: bytes) -> tuple[list[DocumentPart], list[str]]:
    if not content or len(content) > MAX_BYTES:
        raise DocumentError("Upload a non-empty document of at most 20 MB.")
    suffix = Path(filename).suffix.casefold()
    parts = []
    warnings = []
    try:
        if suffix in {".txt", ".md"}:
            encoding = "utf-16" if content.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
            parts = [DocumentPart("text", content.decode(encoding).strip())]
        elif suffix == ".docx":
            from docx import Document
            from docx.table import Table
            from docx.text.paragraph import Paragraph
            from docx.oxml.ns import qn
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                entries = archive.infolist()
                if len(entries) > 2000 or sum(p.file_size for p in entries) > 60 * 1024 * 1024:
                    raise DocumentError("The expanded Word document is too large.")
            doc = Document(io.BytesIO(content))
            for index, child in enumerate(doc.element.body, 1):
                if child.tag == qn("w:p"):
                    text = Paragraph(child, doc).text
                elif child.tag == qn("w:tbl"):
                    table = Table(child, doc)
                    text = "\n".join(" | ".join(cell.text for cell in row.cells) for row in table.rows)
                else:
                    continue
                if text.strip():
                    parts.append(DocumentPart(f"block {index}", text.strip()))
        elif suffix == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(content))
            if reader.is_encrypted:
                raise DocumentError("Upload an unlocked PDF.")
            if len(reader.pages) > 150:
                raise DocumentError("Choose a PDF of at most 150 pages.")
            for index, page in enumerate(reader.pages, 1):
                text = (page.extract_text() or "").strip()
                if text:
                    parts.append(DocumentPart(f"page {index}", text))
                else:
                    warnings.append(f"Page {index} has no searchable text and was not read.")
        else:
            raise DocumentError("Supported documents: TXT, Markdown, DOCX, and searchable PDF.")
    except DocumentError:
        raise
    except Exception as exc:
        raise DocumentError("This document could not be read. Check its format and text encoding.") from exc
    if not parts or not any(p.text for p in parts):
        raise DocumentError("No searchable text found. For scanned files, upload OCR text or an editable document.")
    if sum(len(p.text) for p in parts) > MAX_TEXT:
        raise DocumentError("The document text exceeds 200,000 characters. Split it into relevant documents.")
    return parts, warnings


class BackgroundStore:
    def __init__(self, profiles: ProfileStore):
        self.profiles = profiles
        self.db = profiles.connection
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS background_documents (
                document_id TEXT PRIMARY KEY,
                client_id TEXT NOT NULL REFERENCES clients(client_id),
                filename TEXT NOT NULL, role TEXT NOT NULL,
                sha256 TEXT NOT NULL, parts_json TEXT NOT NULL,
                warnings_json TEXT NOT NULL, original BLOB NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        self.db.commit()

    def save(self, client_id: str, filename: str, content: bytes,
             role: str = "client_background") -> BackgroundDocument:
        self.profiles._require_client(client_id)
        if role not in ROLES:
            raise DocumentError("Unknown document role.")
        filename = Path(filename.replace("\\", "/")).name[:240]
        digest = hashlib.sha256(content).hexdigest()
        document_id = hashlib.sha256(f"{client_id}:{digest}".encode()).hexdigest()[:32]
        existing = self.db.execute(
            "SELECT document_id FROM background_documents WHERE document_id=?", (document_id,)
        ).fetchone()
        if existing:
            return self.get(client_id, document_id)
        parts, warnings = extract_document(filename, content)
        with self.db:
            self.db.execute(
                "INSERT INTO background_documents VALUES (?,?,?,?,?,?,?,?,?)",
                (document_id, client_id, filename, role, digest,
                 json.dumps([asdict(p) for p in parts], ensure_ascii=False),
                 json.dumps(warnings), content, _now()),
            )
        return self.get(client_id, document_id)

    def get(self, client_id: str, document_id: str) -> BackgroundDocument:
        row = self.db.execute(
            "SELECT * FROM background_documents WHERE client_id=? AND document_id=?",
            (client_id, document_id),
        ).fetchone()
        if not row:
            raise DocumentError("Document does not belong to this client group.")
        return BackgroundDocument(
            row["document_id"], row["client_id"], row["filename"], row["role"],
            row["sha256"], tuple(DocumentPart(**p) for p in json.loads(row["parts_json"])),
            tuple(json.loads(row["warnings_json"])),
        )

    def list(self, client_id: str) -> list[BackgroundDocument]:
        self.profiles._require_client(client_id)
        ids = self.db.execute(
            "SELECT document_id FROM background_documents WHERE client_id=? "
            "ORDER BY created_at, document_id", (client_id,),
        )
        return [self.get(client_id, row[0]) for row in ids]

    def original(self, client_id: str, document_id: str) -> bytes:
        self.get(client_id, document_id)
        return self.db.execute(
            "SELECT original FROM background_documents WHERE document_id=?", (document_id,)
        ).fetchone()[0]

    def remove(self, client_id: str, document_id: str):
        self.get(client_id, document_id)
        used = any(
            source.get("document_id") == document_id
            for fact in self.profiles.list_facts(client_id)
            for source in fact["evidence"]
        )
        if used:
            raise DocumentError("This document supports saved profile facts. Keep it for their source history.")
        with self.db:
            self.db.execute(
                "DELETE FROM background_documents WHERE client_id=? AND document_id=?",
                (client_id, document_id),
            )


def explicit_document_candidates(document: BackgroundDocument) -> list[Candidate]:
    """A local fallback for clearly labelled facts; AI can analyse ordinary prose."""
    fields = {
        "company": "entities", "entity": "entities", "公司": "entities",
        "公司名称": "entities", "industry": "industry", "行业": "industry",
        "business": "business_description", "业务描述": "business_description",
        "agreed services": "engagement_scope", "合作范围": "engagement_scope",
        "email": "contacts", "邮箱": "contacts",
    }
    output = []
    for part in document.parts:
        for line in part.text.splitlines():
            match = re.match(r"^\s*([^:：]{2,30})\s*[:：]\s*(.{2,500})\s*$", line)
            if not match or match[1].casefold().strip() not in fields:
                continue
            field = fields[match[1].casefold().strip()]
            value = match[2].strip()
            if field == "entities":
                value = {"name": value}
            elif field == "contacts":
                value = {"name": "", "email": value}
            try:
                output.append(Candidate(
                    field, value,
                    (Evidence("background_document", line.strip(),
                              document_id=document.document_id, location=part.location),),
                ))
            except ValueError:
                continue
    return output
