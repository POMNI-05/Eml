"""Read an explicitly chosen Gmail scope without expanding it to other mail.

The service is injected: GmailMailbox(get_gmail_service()) reuses Eml's OAuth.
There are no Google SDK imports or network calls at module import time.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from dataclasses import asdict, dataclass, field, replace
from datetime import date, datetime, time, timedelta, timezone
from email.message import Message
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .attachments import EmailAttachment, SUPPORTED_SUFFIXES, extract_attachment
from .documents import MAX_BYTES

MAX_FETCH_ATTACHMENT_BYTES = 50 * 1024 * 1024


def header(payload: dict, name: str) -> str:
    return next(
        (h.get("value", "") for h in payload.get("headers", [])
         if h.get("name", "").casefold() == name.casefold()), ""
    )


class _HTMLText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        if not self.hidden and tag in {"br", "p", "div", "tr", "li"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)
        elif not self.hidden and tag in {"p", "div", "tr", "li"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def _decode(part: dict) -> str:
    data = part.get("body", {}).get("data", "")
    if not data:
        if part.get("body", {}).get("attachmentId"):
            raise ValueError(
                "Gmail stored a text body externally; this reader cannot load it yet."
            )
        return ""
    raw = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
    content_type = Message()
    content_type["content-type"] = header(part, "Content-Type")
    charset = content_type.get_content_charset() or "utf-8"
    try:
        return raw.decode(charset, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


def body_text(part: dict) -> str:
    """Prefer the plain alternative, fall back to HTML, skip file attachments."""
    if part.get("filename"):
        return ""
    mime = part.get("mimeType", "")
    children = part.get("parts", [])
    if mime == "multipart/alternative":
        plain = [p for p in children if p.get("mimeType") == "text/plain"]
        for child in plain + [p for p in children if p not in plain]:
            text = body_text(child)
            if text.strip():
                return text
        return ""
    if children:
        return "\n\n".join(filter(None, (body_text(p) for p in children)))
    if mime == "text/plain":
        return _decode(part).strip()
    if mime == "text/html":
        parser = _HTMLText()
        parser.feed(_decode(part))
        return re.sub(r"\n[ \t]*\n+", "\n\n", "".join(parser.parts)).strip()
    return ""


def attachment_names(part: dict) -> tuple[str, ...]:
    names = [part["filename"]] if part.get("filename") else []
    for child in part.get("parts", []):
        names.extend(attachment_names(child))
    return tuple(dict.fromkeys(names))


@dataclass(frozen=True)
class Email:
    message_id: str
    thread_id: str
    sender: str = ""
    to: str = ""
    cc: str = ""
    subject: str = ""
    date: str = ""
    timestamp_ms: int | None = None
    body: str = ""
    internet_message_id: str = ""
    label_ids: tuple[str, ...] = ()
    attachments: tuple[str, ...] = ()
    attachment_contents: tuple[EmailAttachment, ...] = ()

    @classmethod
    def from_gmail(cls, raw: dict) -> "Email":
        payload = raw.get("payload", {})
        timestamp = raw.get("internalDate")
        if timestamp is None:
            try:
                parsed = parsedate_to_datetime(header(payload, "Date"))
                timestamp = int(parsed.timestamp() * 1000) if parsed.tzinfo else None
            except (ValueError, TypeError, OverflowError):
                timestamp = None
        return cls(
            message_id=raw["id"], thread_id=raw.get("threadId", ""),
            sender=header(payload, "From"), to=header(payload, "To"),
            cc=header(payload, "Cc"), subject=header(payload, "Subject"),
            date=header(payload, "Date"),
            timestamp_ms=int(timestamp) if timestamp is not None else None,
            body=body_text(payload),
            internet_message_id=header(payload, "Message-ID"),
            label_ids=tuple(raw.get("labelIds", [])),
            attachments=attachment_names(payload),
        )

    def fingerprint(self) -> str:
        # Label membership can change without changing the content to extract.
        values = asdict(self)
        values.pop("label_ids")
        return hashlib.sha256(
            json.dumps(values, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()


@dataclass(frozen=True)
class Selection:
    """Exactly one source; dates are inclusive calendar dates in timezone_name.

    Multiple label IDs mean UNION, implemented as separate Gmail requests.
    Gmail's labelIds parameter itself means intersection, so it is not used
    to represent this union. Parent labels do not imply descendants.
    """

    label_ids: tuple[str, ...] = ()
    message_ids: tuple[str, ...] = ()
    internet_message_ids: tuple[str, ...] = ()
    thread_ids: tuple[str, ...] = ()
    client_query: str = ""
    include_sub_labels: bool = False
    start_date: date | None = None
    end_date: date | None = None
    timezone_name: str = "Australia/Sydney"
    max_messages: int | None = None
    subject_prefix: str = ""
    excluded_subject_prefix: str = ""

    def __post_init__(self):
        if sum(bool(v) for v in (
            self.label_ids, self.message_ids, self.internet_message_ids,
            self.thread_ids, self.client_query.strip(),
        )) != 1:
            raise ValueError("Choose exactly one non-empty message source.")
        for values in (
            self.label_ids, self.message_ids, self.internet_message_ids,
            self.thread_ids,
        ):
            if any(not isinstance(v, str) or not v.strip() for v in values):
                raise ValueError("Message and label IDs must be non-empty strings.")
        ZoneInfo(self.timezone_name)
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("Start date must not be after end date.")
        if self.max_messages is not None and self.max_messages < 1:
            raise ValueError("max_messages must be positive or None.")
        if self.include_sub_labels and not self.label_ids:
            raise ValueError("Sub-labels apply only to label selections.")
        if not isinstance(self.subject_prefix, str) or not isinstance(self.excluded_subject_prefix, str):
            raise ValueError("Subject prefixes must be text.")

    def bounds(self) -> tuple[int | None, int | None]:
        tz = ZoneInfo(self.timezone_name)
        lower = (
            int(datetime.combine(self.start_date, time.min, tz).timestamp() * 1000)
            if self.start_date else None
        )
        upper = (
            int(datetime.combine(self.end_date + timedelta(days=1), time.min, tz)
                .timestamp() * 1000)
            if self.end_date else None
        )
        return lower, upper

    def query(self) -> str:
        lower, upper = self.bounds()
        # Fetch a one-second superset at the lower edge, then filter exactly.
        terms = [f"after:{lower // 1000 - 1}"] if lower is not None else []
        if upper is not None:
            terms.append(f"before:{upper // 1000}")
        return " ".join(terms)

    def matches_subject(self, message: Email) -> bool:
        subject = message.subject.lstrip().casefold()
        return (
            (not self.subject_prefix.strip() or subject.startswith(self.subject_prefix.strip().casefold()))
            and (not self.excluded_subject_prefix.strip()
                 or not subject.startswith(self.excluded_subject_prefix.strip().casefold()))
        )

    def contains(self, message: Email) -> bool:
        if not self.matches_subject(message):
            return False
        lower, upper = self.bounds()
        if lower is None and upper is None:
            return True
        ts = message.timestamp_ms
        return ts is not None and (lower is None or ts >= lower) and (
            upper is None or ts < upper
        )


@dataclass
class SelectionResult:
    account_id: str
    selection: Selection
    messages: list[Email]
    complete: bool = True
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return json.loads(json.dumps(asdict(self), default=str, ensure_ascii=False))


class GmailMailbox:
    def __init__(self, service: Any, user_id: str = "me"):
        self.service = service
        self.user_id = user_id
        self._account_id: str | None = None

    def account_id(self) -> str:
        if self._account_id is None:
            profile = self.service.users().getProfile(userId=self.user_id).execute()
            self._account_id = profile["emailAddress"].casefold()
        return self._account_id

    def list_labels(self, *, user_only: bool = False) -> list[dict]:
        labels = self.service.users().labels().list(
            userId=self.user_id
        ).execute().get("labels", [])
        return sorted(
            [l for l in labels if not user_only or l.get("type") == "user"],
            key=lambda l: l["name"].casefold(),
        )

    def _message_refs(self, **kwargs):
        token = None
        seen_tokens = set()
        while True:
            params = {
                "userId": self.user_id, "maxResults": 500,
                "includeSpamTrash": True, **kwargs,
            }
            if token:
                params["pageToken"] = token
            result = self.service.users().messages().list(**params).execute()
            yield from result.get("messages", [])
            token = result.get("nextPageToken")
            if not token:
                return
            if token in seen_tokens:
                raise RuntimeError("Gmail repeated a page token; selection incomplete.")
            seen_tokens.add(token)

    def _label_ids(self, selection: Selection) -> list[str]:
        ids = list(dict.fromkeys(selection.label_ids))
        labels = self.list_labels()
        by_id = {label["id"]: label for label in labels}
        unknown = set(ids) - by_id.keys()
        if unknown:
            raise ValueError(f"Unknown Gmail label IDs: {', '.join(sorted(unknown))}")
        if selection.include_sub_labels:
            prefixes = [by_id[label_id]["name"] + "/" for label_id in ids]
            ids.extend(label["id"] for label in labels
                       if any(label["name"].startswith(p) for p in prefixes))
        return list(dict.fromkeys(ids))

    def _resolve_internet_id(self, value: str) -> str:
        value = value.strip()
        if value.startswith("<") and value.endswith(">"):
            value = value[1:-1]
        if "@" not in value or re.search(r'[\s<>{}"]', value):
            raise ValueError(f"Invalid Internet Message-ID: {value!r}")
        refs = []
        for ref in self._message_refs(q=f'rfc822msgid:"{value}"'):
            if ref["id"] not in refs:
                refs.append(ref["id"])
            if len(refs) > 1:
                raise ValueError(f"Internet Message-ID has multiple matches: {value}")
        if not refs:
            raise ValueError(f"Internet Message-ID not found in this Gmail account: {value}")
        return refs[0]

    def _read_attachments(self, raw, budget):
        def files(part, location="0"):
            if part.get("filename"):
                yield part, location
            else:
                for index, child in enumerate(part.get("parts", [])):
                    yield from files(child, f"{location}.{index}")

        output = []
        for part, location in files(raw.get("payload", {})):
            filename = part["filename"]
            body = part.get("body", {})
            size = int(body.get("size", 0))
            source = EmailAttachment(
                part_id=part.get("partId") or location, filename=filename,
                mime_type=part.get("mimeType", ""), size=size,
            )
            try:
                if Path(filename).suffix.casefold() not in SUPPORTED_SUFFIXES:
                    raise ValueError("Not read: unsupported file type. Images and scanned files need OCR text.")
                if size > MAX_BYTES:
                    raise ValueError("Not read: attachment exceeds the 20 MB limit.")
                if size > budget[0] or budget[0] <= 0:
                    raise ValueError("Not read: attachments exceed the 50 MB limit for this fetch.")
                content_body = body
                if body.get("attachmentId"):
                    content_body = self.service.users().messages().attachments().get(
                        userId=self.user_id, messageId=raw["id"], id=body["attachmentId"],
                    ).execute()
                data = content_body.get("data", "")
                content = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
                budget[0] -= len(content)
                if len(content) > MAX_BYTES or budget[0] < 0:
                    raise ValueError("Not read: attachment exceeds the file or fetch size limit.")
                parts, warnings = extract_attachment(filename, content)
                source = replace(
                    source, size=len(content), sha256=hashlib.sha256(content).hexdigest(),
                    parts=tuple(parts), warnings=tuple(warnings),
                )
            except Exception as exc:
                # One unavailable or unreadable file must not discard the email.
                # Avoid including service errors, URLs or credentials in evidence.
                reason = str(exc) if isinstance(exc, ValueError) else "Not read: attachment download or extraction failed."
                source = replace(source, warnings=(reason,))
            output.append(source)
        return tuple(output)

    def select(self, selection: Selection) -> SelectionResult:
        """Read only selected messages. API failures propagate; never report success."""
        raw_threads: dict[str, dict] = {}
        seen_ids: set[str] = set()

        def refs():
            if selection.label_ids:
                for label_id in self._label_ids(selection):
                    yield from self._message_refs(
                        labelIds=[label_id], q=selection.query()
                    )
            elif selection.message_ids:
                yield from ({"id": mid} for mid in selection.message_ids)
            elif selection.internet_message_ids:
                for mid in selection.internet_message_ids:
                    yield {"id": self._resolve_internet_id(mid)}
            elif selection.client_query:
                yield from self._message_refs(
                    q=f"({selection.client_query}) {selection.query()}".strip()
                )
            else:
                for thread_id in dict.fromkeys(selection.thread_ids):
                    raw = self.service.users().threads().get(
                        userId=self.user_id, id=thread_id, format="full"
                    ).execute()
                    for msg in raw.get("messages", []):
                        raw_threads[msg["id"]] = msg
                        yield {"id": msg["id"]}

        messages = []
        warnings = []
        complete = True
        attachment_budget = [MAX_FETCH_ATTACHMENT_BYTES]
        lower, upper = selection.bounds()
        for ref in refs():
            mid = ref["id"]
            if mid in seen_ids:
                continue
            seen_ids.add(mid)
            raw = raw_threads.get(mid)
            if raw is None:
                raw = self.service.users().messages().get(
                    userId=self.user_id, id=mid, format="full"
                ).execute()
            message = Email.from_gmail(raw)
            # Gmail has no reliable starts-with operator. Filter the actual
            # subject before date warnings and before counting the message cap.
            if not selection.matches_subject(message):
                continue
            if message.timestamp_ms is None and (lower is not None or upper is not None):
                warnings.append(f"Excluded {mid}: cannot establish its date.")
                complete = False
            if not selection.contains(message):
                continue
            if selection.max_messages is not None and len(messages) >= selection.max_messages:
                complete = False
                warnings.append(
                    f"Stopped at {selection.max_messages} messages; this is a partial selection."
                )
                break
            messages.append(replace(message, attachment_contents=self._read_attachments(raw, attachment_budget)))
        messages.sort(key=lambda m: (m.timestamp_ms or 0, m.message_id))
        return SelectionResult(
            account_id=self.account_id(), selection=selection, messages=messages,
            complete=complete, warnings=warnings,
        )
