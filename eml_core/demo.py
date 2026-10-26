"""Offline walkthrough: python -m eml_core.demo (no OAuth, model, or files)."""

import json
from dataclasses import replace

from .mailbox import Email
from .profiles import ProfileStore, RuleExtractor, update_profile


def main():
    mailbox = "staff@firm.example"
    first = Email(
        message_id="demo-1", thread_id="demo-thread",
        sender="Alex <alex@client.example>", to=mailbox, date="2026-10-01",
        body="Company: Example Pty Ltd\nIndustry: Wholesale",
    )
    second = replace(
        first, message_id="demo-2", date="2026-10-15",
        body="Business: Wholesale supply of household goods",
    )
    extractor = RuleExtractor(own_addresses=[mailbox])
    with ProfileStore(":memory:") as store:
        cid = store.create_client("Alex group")
        first_run = update_profile(store, cid, mailbox, [first], extractor)
        before_review = store.context(cid)
        for fact in store.list_facts(cid, "pending"):
            store.review(cid, fact["fact_id"], "confirmed")
        next_run = update_profile(store, cid, mailbox, [first, second], extractor)
        print(json.dumps({
            "first_run": first_run,
            "confirmed_before_review": before_review["confirmed_facts"],
            "next_run": next_run,
            "confirmed_context": store.context(cid),
            "new_pending_suggestions": store.list_facts(cid, "pending"),
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
