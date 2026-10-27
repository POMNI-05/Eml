"""AI output describes proposed activities, not hours, fees, or an issued invoice."""

from typing import Literal
from pydantic import Field
from eml_core.ai import StrictModel


class MailCitation(StrictModel):
    message_id: str = Field(min_length=1)
    quote: str = Field(min_length=1, max_length=1600)
    attachment_part_id: str = ""
    location: str = ""


class WorkActivity(StrictModel):
    entity: str
    description: str = Field(min_length=1, max_length=1500)
    status: Literal["completed", "in_progress", "requested", "unclear"]
    evidence: list[MailCitation] = Field(min_length=1)
    uncertainties: list[str]


class BillingAnalysis(StrictModel):
    client_summary: str
    activities: list[WorkActivity]
    open_questions: list[str]
