"""Reversible local substitutions, not a guarantee of anonymisation.

Mappings are per package. Never send ``mapping`` to a model. Literal rules
are supplied by the reviewer; built-in regexes are deliberately inspectable.
"""

from __future__ import annotations

import re
import uuid
from email.utils import getaddresses

from .ai import ModelError


TOKEN = re.compile(r"\[\[EML_[^\[\]\r\n]{1,180}\]\]", re.I)
PATTERNS = (
    ("EMAIL", r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])"),
    ("URL", r"https?://[^\s<>\"\[\]]+"),
    ("ABN", r"(?<!\d)\d{2}[ -]\d{3}[ -]\d{3}[ -]\d{3}(?!\d)"),
    ("TFN", r"(?<!\d)\d{3}[ -]\d{3}[ -]\d{3}(?!\d)"),
    ("PHONE", r"(?<!\w)(?:\+61[ -]?|0)(?:4\d{2}[ -]?\d{3}[ -]?\d{3}|[2378][ -]?\d{4}[ -]?\d{4})(?!\d)"),
    # Includes compact TFN/account/phone-like numbers. False positives are
    # preferable here, but this is not an exhaustive tax identifier detector.
    ("NUMBER", r"(?<![\w])\d{8,16}(?![\w])"),
    ("BSB", r"(?<!\d)\d{3}-\d{3}(?!\d)"),
)


def parse_literal_rules(text: str) -> list[tuple[str, str]]:
    """One exact phrase => semantic type per line; no executable regex UI."""
    rules = []
    for line in text.splitlines():
        if not line.strip():
            continue
        source, separator, kind = line.rpartition("=>")
        source, kind = source.strip(), kind.strip().upper()
        if not separator or not source or len(source) > 500 or not re.fullmatch(r"[A-Z][A-Z_]{0,23}", kind):
            raise ModelError("Use one phrase => TYPE per line, for example ANZ => BANK.")
        rules.append((source, kind))
    if len(rules) > 300:
        raise ModelError("Use at most 300 literal privacy rules.")
    return rules


def profile_literals(payload: dict) -> list[tuple[str, str]]:
    context = payload["client_profile"]
    rules = [(context["display_name"], "CLIENT")]
    for fact in context.get("confirmed_facts", []):
        value, field = fact["value"], fact["field"]
        if field == "contacts":
            rules.extend((value.get(k, ""), kind) for k, kind in (("name", "PERSON"), ("email", "EMAIL")))
        elif field == "entities":
            rules.append((value["name"], "ENTITY"))
        elif field in {"aliases", "domains"}:
            rules.append((value, "ENTITY" if field == "aliases" else "DOMAIN"))
    for message in payload["selected_email_evidence"]:
        for name, email in getaddresses([message.get(k, "") for k in ("sender", "to", "cc")]):
            rules.extend(((name, "PERSON"), (email, "EMAIL")))
    return [(text, kind) for text, kind in rules if isinstance(text, str) and text.strip()]


class Pseudonymizer:
    def __init__(self, literals=(), *, namespace=None, mapping=None):
        self.namespace = namespace or uuid.uuid4().hex[:12]
        if not re.fullmatch(r"[a-f0-9]{12}", self.namespace):
            raise ModelError("Invalid local mapping namespace.")
        self.mapping = dict(mapping or {})  # token -> exact original spelling
        self._reverse = {(original, token.rsplit("_", 1)[0]): token for token, original in self.mapping.items()}
        unique = {}
        for source, kind in literals:
            if not isinstance(source, str) or not source.strip() or not re.fullmatch(r"[A-Z][A-Z_]{0,23}", kind):
                raise ModelError("Invalid literal privacy rule.")
            unique.setdefault(source, kind)
        self.rules = sorted(unique.items(), key=lambda rule: -len(rule[0]))
        self.patterns = [re.compile(pattern, re.I) for _, pattern in PATTERNS]

    def token(self, original: str, kind: str) -> str:
        prefix = f"[[EML_{self.namespace}_{kind}"
        key = (original, prefix)
        if key not in self._reverse:
            token = f"{prefix}_{len(self.mapping) + 1:04d}]]"
            self.mapping[token] = original
            self._reverse[key] = token
        return self._reverse[key]

    def mask_text(self, text: str) -> str:
        if TOKEN.search(text):
            raise ModelError("Source text already contains reserved Eml tokens. Remove them or use local AI.")
        spans = []
        # Discover on the original string; never run later rules over tokens.
        for source, kind in self.rules:
            left = r"(?<!\w)" if source[0].isalnum() else ""
            right = r"(?!\w)" if source[-1].isalnum() else ""
            for match in re.finditer(left + re.escape(source) + right, text, re.I):
                spans.append((match.start(), match.end(), kind))
        for (kind, _), pattern in zip(PATTERNS, self.patterns):
            spans.extend((m.start(), m.end(), kind) for m in pattern.finditer(text))
        # Longest overlap wins (a URL/email must not become a partly hidden
        # address just because a company alias matches inside it).
        chosen = []
        for start, end, kind in sorted(spans, key=lambda span: (-(span[1] - span[0]), span[0])):
            if not any(start < b and end > a for a, b, _ in chosen):
                chosen.append((start, end, kind))
        output, offset = [], 0
        for start, end, kind in sorted(chosen):
            output.extend((text[offset:start], self.token(text[start:end], kind)))
            offset = end
        return "".join(output) + text[offset:]

    def mask(self, value):
        if isinstance(value, str):
            return self.mask_text(value)
        if isinstance(value, dict):
            # Schema keys remain unchanged; identifiers in this application
            # occur in values, not arbitrary user-provided keys.
            return {key: self.mask(item) for key, item in value.items()}
        if isinstance(value, (tuple, list)):
            return [self.mask(item) for item in value]
        return value

    def restore(self, value):
        if isinstance(value, str):
            def replace(match):
                if match[0] not in self.mapping:
                    raise ModelError("The response contains an unknown privacy token. No draft was saved.")
                return self.mapping[match[0]]
            # One pass: substituted originals are never interpreted as tokens.
            return TOKEN.sub(replace, value)
        if isinstance(value, dict):
            return {key: self.restore(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self.restore(item) for item in value]
        return value
