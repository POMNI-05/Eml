"""Validate source quotations and reviewer edits before saving or exporting."""

from eml_core.ai import ModelError
import re


def validate_activity_evidence(analysis, messages):
    by_id = {message.message_id: message for message in messages}
    for activity in analysis.activities:
        for source in activity.evidence:
            message = by_id.get(source.message_id)
            if message is None:
                raise ModelError("A generated activity cites an email outside the chosen evidence.")
            quote = " ".join(source.quote.split())
            text = message.body
            if source.attachment_part_id:
                attachment = next((a for a in message.attachment_contents
                                   if a.part_id == source.attachment_part_id), None)
                part = next((p for p in attachment.parts if p.location == source.location), None) if attachment else None
                if part is None:
                    raise ModelError("A generated activity cites an attachment or location outside the chosen evidence.")
                text = part.text
            elif source.location:
                raise ModelError("An attachment location needs its source attachment part ID.")
            if not quote or quote not in " ".join(text.split()):
                raise ModelError("A generated quotation is not present in its cited email. No draft was saved.")
        if activity.status == "completed":
            quotes = [source.quote.strip() for source in activity.evidence]
            request_only = all(
                re.match(r"^(please\b|could you\b|can you\b|would you\b|请|麻烦)", q, re.I)
                and not re.search(r"\b(completed|lodged|submitted|finished)\b|已完成|已提交|已递交", q, re.I)
                for q in quotes
            )
            if request_only:
                activity.status = "unclear"
                activity.uncertainties.append("The quoted evidence is a request; completion is not established.")
    # This checks source fidelity, not whether an interpretation is substantively
    # correct. Completion and billability still require the reviewer's judgment.


def validate_review_edits(activities, edits):
    """Excluded rows may stay unfinished; included rows must be exportable."""
    if edits is None:
        return
    if not isinstance(edits, list) or any(not isinstance(row, dict) for row in edits):
        raise ValueError("Activity edits must be a list of rows.")
    for row in edits:
        if not row.get("Include", True):
            continue
        try:
            index = int(row["Item"]) - 1
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Edited activity does not exist.") from exc
        if index < 0 or index >= len(activities):
            raise ValueError("Edited activity does not exist.")
        if not str(row.get("Description") or "").strip() or row.get("Status") not in {
            "completed", "in_progress", "requested", "unclear",
        }:
            raise ValueError("Included activities need a description and valid status.")
