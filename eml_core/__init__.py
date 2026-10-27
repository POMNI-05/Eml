"""Reusable, framework-independent building blocks for Eml."""

from .mailbox import Email, GmailMailbox, Selection, SelectionResult
from .profiles import ProfileStore, RuleExtractor, update_profile
from .client_methods import ClientSearchMethodStore

__all__ = [
    "Email", "GmailMailbox", "Selection", "SelectionResult",
    "ProfileStore", "RuleExtractor", "update_profile", "ClientSearchMethodStore",
]
