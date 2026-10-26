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


def _quoted(value: str) -> str:
    value = " ".join(
        value.replace('"', " ").replace("\\", " ").replace("{", " ").replace("}", " ").split()
    )
    if not value:
        raise ValueError("Search terms cannot be empty.")
    return '"' + value + '"'


def build_client_search(context: dict, additional_terms=()) -> ClientSearch:
    terms, clauses, source_ids = [], [], []
    for fact in context.get("confirmed_facts", []):
        field, value = fact["field"], fact["value"]
        additions = []
        if field == "contacts":
            address = value["email"]
            q = _quoted(address)
            additions = [(address, f"from:{q} to:{q} cc:{q}")]
        elif field == "entities":
            additions = [(value["name"], _quoted(value["name"]))]
        elif field == "aliases":
            additions = [(value, _quoted(value))]
        if additions:
            source_ids.append(fact["fact_id"])
        for term, clause in additions:
            if term.casefold() not in {t.casefold() for t in terms}:
                terms.append(term)
                clauses.append(clause)
    for term in additional_terms:
        if term.strip() and term.casefold() not in {t.casefold() for t in terms}:
            terms.append(term.strip())
            clauses.append(_quoted(term))
    if not clauses:
        raise ValueError(
            "Confirm a contact email, company name or alias first, or enter a search term. "
            "You can also choose Gmail labels without completing the profile."
        )
    return ClientSearch(
        query="{" + " ".join(clauses) + "} -in:spam -in:trash",
        terms=tuple(terms), source_fact_ids=tuple(dict.fromkeys(source_ids)),
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
