"""Use approved client context to find mail; leave final selection to the user."""

from __future__ import annotations

import re
from dataclasses import dataclass
from email.utils import getaddresses

from .mailbox import Email


@dataclass(frozen=True)
class ClientSearch:
    query: str
    terms: tuple[str, ...]
    source_fact_ids: tuple[str, ...]
    match_mode: str = "any"
    excluded_terms: tuple[str, ...] = ()
    exclusion_area: str = "anywhere"


def _quoted(value: str) -> str:
    value = " ".join(
        value.replace('"', " ").replace("\\", " ").replace("{", " ").replace("}", " ").split()
    )
    if not value:
        raise ValueError("Search terms cannot be empty.")
    return '"' + value + '"'


def _normalise_terms(values):
    if isinstance(values, str):
        values = [values]
    unique = {}
    for value in values:
        if not isinstance(value, str):
            raise ValueError("Search entries must be text.")
        value = " ".join(value.split())
        if value:
            unique.setdefault(value.casefold(), value)
    return list(unique.values())


def _email_clause(value):
    quoted = _quoted(value)
    return f"(from:{quoted} OR to:{quoted} OR cc:{quoted})"


def _is_email(value):
    return bool(re.fullmatch(r'[^@\s<>:"(){}\\]+@[^@\s<>:"(){}\\]+', value))


def build_client_search(context: dict, additional_terms=(), *, match_mode="any",
                        excluded_terms=(), exclusion_area="anywhere", include_profile=True) -> ClientSearch:
    """Compile literal entries; exclusions always apply outside the any/all group.

    The UI passes include_profile=False because saved identities are already
    visible, removable entries. Other callers keep the original profile default.
    """
    if match_mode not in {"any", "all"}:
        raise ValueError("Choose any or all search entries.")
    if exclusion_area not in {"anywhere", "sender", "recipient", "subject", "body"}:
        raise ValueError("Choose a valid exclusion area.")
    identities, source_lookup = {}, {}
    for fact in context.get("confirmed_facts", []):
        field, value = fact["field"], fact["value"]
        additions = []
        if field == "contacts":
            address = value["email"]
            additions = [(address, _email_clause(address))]
        elif field == "entities":
            additions = [(value["name"], _quoted(value["name"]))]
        elif field == "aliases":
            additions = [(value, _quoted(value))]
        for term, clause in additions:
            key = " ".join(term.split()).casefold()
            identities.setdefault(key, (term, clause))
            source_lookup.setdefault(key, []).append(fact["fact_id"])
    defaults = [value[0] for value in identities.values()] if include_profile else []
    terms = _normalise_terms(defaults + _normalise_terms(additional_terms))
    clauses, source_ids = [], []
    for term in terms:
        key = term.casefold()
        clause = identities[key][1] if key in identities else (
            _email_clause(term) if _is_email(term) else _quoted(term)
        )
        clauses.append(clause)
        source_ids.extend(source_lookup.get(key, []))
    if not clauses:
        raise ValueError(
            "Confirm a contact email, company name or alias first, or enter a search term. "
            "You can also choose Gmail labels without completing the profile."
        )
    positive = "{" + " ".join(clauses) + "}" if match_mode == "any" else (
        "(" + " AND ".join(clauses) + ")"
    )
    exclusions = _normalise_terms(excluded_terms)
    negative = []
    for term in exclusions:
        if _is_email(term):
            fields = {"sender": ("from",), "recipient": ("to", "cc")}.get(
                exclusion_area, ("from", "to", "cc")
            )
            negative.extend(f"-{field}:{_quoted(term)}" for field in fields)
        else:
            field = {"subject": "subject", "body": "body"}.get(exclusion_area, "")
            negative.append("-" + (field + ":" if field else "") + _quoted(term))
    return ClientSearch(
        query=" ".join([positive, *negative, "-in:spam", "-in:trash"]),
        terms=tuple(terms), source_fact_ids=tuple(dict.fromkeys(source_ids)),
        match_mode=match_mode, excluded_terms=tuple(exclusions), exclusion_area=exclusion_area,
    )


def match_reasons(message: Email, context: dict) -> list[str]:
    """Explain matches, not a probability or a decision that work is billable."""
    addresses = {address.casefold() for _, address in getaddresses(
        [message.sender, message.to, message.cc]
    )}
    text = (message.subject + "\n" + message.body).casefold()
    reasons = []
    for fact in context.get("confirmed_facts", []):
        field, value = fact["field"], fact["value"]
        if field == "contacts" and value["email"].casefold() in addresses:
            reasons.append(f"Known contact: {value['email']}")
        elif field == "entities" and value["name"].casefold() in text:
            reasons.append(f"Company mentioned: {value['name']}")
        elif field == "aliases" and value.casefold() in text:
            reasons.append(f"Known alias: {value}")
        elif field in {"engagement_scope", "business_description", "industry"}:
            tokens = re.findall(r"[a-zA-Z]{4,}", value.casefold())
            overlap = [t for t in dict.fromkeys(tokens) if t in text][:4]
            if overlap:
                reasons.append(f"Background terms: {', '.join(overlap)}")
    return list(dict.fromkeys(reasons))
