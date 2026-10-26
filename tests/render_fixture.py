"""Synthetic layout fixture, not a model-quality demo.

Run: python -m tests.render_fixture /tmp/billing_layout.docx
"""

from pathlib import Path
import sys

from eml_core import Email, ProfileStore, Selection, SelectionResult
from eml_core.documents import BackgroundStore
from invoice.models import BillingAnalysis
from invoice.service import generate_draft
from invoice.renderer import render_docx


def sample_draft():
    messages = [
        Email("demo-mail-1", "demo-thread-1", sender="Accountant <staff@firm.example>",
              to="Alex <alex@client.example>", subject="Bookkeeping records reviewed",
              date="Thu, 1 Oct 2026 10:00:00 +1000",
              body="I have reviewed the bookkeeping records and sent the reconciliation schedule."),
        Email("demo-mail-2", "demo-thread-2", sender="Alex <alex@client.example>",
              to="staff@firm.example", subject="October records",
              date="Mon, 5 Oct 2026 11:00:00 +1100",
              body="Please prepare the October BAS after I provide the missing invoices."),
        Email("demo-mail-3", "demo-thread-3", sender="staff@firm.example",
              to="alex@client.example", subject="往来账核对进展",
              date="Tue, 6 Oct 2026 09:00:00 +1100",
              body="我们已经核对了往来账，并列出了仍需客户确认的两笔交易。"),
    ]

    class FixtureModel:
        model = "synthetic-layout-fixture"
        context_size = 32768

        def generate(self, schema, system, payload):
            return BillingAnalysis(
                client_summary=(
                    "The client group contains Example Pty Ltd and Example Trading Pty Ltd. "
                    "The correspondence concerns bookkeeping review, a request for BAS preparation "
                    "and outstanding transaction queries. 客户背景用于区分相关公司，活动状态须按邮件核对。"
                ),
                activities=[
                    {
                        "entity": "Example Pty Ltd",
                        "description": (
                            "Reviewed bookkeeping records and supplied a reconciliation schedule. "
                            "The record groups correspondence relating to this review into one activity "
                            "so that repeated emails do not become separate descriptions of the same work."
                        ),
                        "status": "completed",
                        "evidence": [{"message_id": messages[0].message_id, "quote": messages[0].body}],
                        "uncertainties": ["Verify whether this work has already appeared on a previous bill."],
                    },
                    {
                        "entity": "Example Pty Ltd",
                        "description": "Received a request to prepare the October BAS after missing invoices are supplied.",
                        "status": "requested",
                        "evidence": [{"message_id": messages[1].message_id, "quote": messages[1].body}],
                        "uncertainties": ["The selected correspondence does not establish completion."],
                    },
                    {
                        "entity": "Example Trading Pty Ltd",
                        "description": "核对往来账并整理两笔待客户确认的交易。保留未决事项，后续根据客户补充资料继续处理。",
                        "status": "in_progress",
                        "evidence": [{"message_id": messages[2].message_id, "quote": messages[2].body}],
                        "uncertainties": ["仍需客户确认交易性质。"],
                    },
                ],
                open_questions=["Confirm time spent and check these activities against prior bills."],
            )

    with ProfileStore(":memory:") as store:
        cid = store.create_client("Example client group")
        store.add_manual(cid, "business_description", "Wholesale supply with two related companies.")
        document = BackgroundStore(store).save(
            cid, "client_background.txt",
            b"The group includes Example Pty Ltd and Example Trading Pty Ltd. Bookkeeping support is in scope.",
        )
        selection = SelectionResult(
            "staff@firm.example",
            Selection(message_ids=tuple(m.message_id for m in messages)), messages,
        )
        return generate_draft(
            FixtureModel(), store.context(cid), [document], selection,
            [m.message_id for m in messages],
        )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Provide an output .docx path.")
    Path(sys.argv[1]).write_bytes(render_docx(sample_draft()))
