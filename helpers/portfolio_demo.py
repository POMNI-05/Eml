"""Actual workspace with synthetic dependencies. Run via Streamlit, loopback only.

No credentials or existing client database are read. Model output is scripted.
"""
import os
import runpy
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from eml_core import ProfileStore
from invoice.templates import GenerationTemplateStore
from tests.fakes import FakeGmail, raw_message, attach_file


class DemoModel:
    model = "scripted-demo-response"
    context_size = 32768

    def __init__(self, *args, **kwargs):
        pass

    def list_models(self):
        return [self.model]

    def generate(self, schema, system, payload):
        selected = payload["selected_email_evidence"]
        activities = []
        for mid, description, status in [
            ("demo-review", "Reviewed October bookkeeping records and supplied the reconciliation schedule.", "completed"),
            ("demo-request", "Received a request for October BAS preparation; missing invoices remain outstanding.", "requested"),
        ]:
            message = next((m for m in selected if m["message_id"] == mid), None)
            if message:
                activities.append(dict(entity="Northstar Imports", description=description, status=status,
                    evidence=[dict(message_id=mid, quote=message["body"])], uncertainties=[]))
        return schema.model_validate(dict(
            client_summary="SYNTHETIC DEMO / scripted response. Northstar Imports Pty Ltd | October 2026. Bookkeeping review is documented; BAS preparation is requested but not confirmed complete.",
            activities=activities, open_questions=["Confirm receipt of missing invoices and check for prior billing overlap."]))


def mailbox():
    specs = [
        ("demo-review", "Re: October records — review completed", "I have reviewed the October bookkeeping records and sent the reconciliation schedule. Two transactions still need your confirmation.", "Sam Taylor <reviewer@firm.example>"),
        ("demo-request", "October BAS — missing invoices", "Please prepare the October BAS after I provide the missing invoices.", "Olivia Chen <olivia@northstar.example>"),
        ("demo-reply", "Re: October records — documents supplied", "Attached are the October records. Please let me know if you need anything else for the review.", "Olivia Chen <olivia@northstar.example>"),
        ("demo-news", "Monthly software newsletter", "Product news and webinar invitations. No client work is recorded in this message.", "Newsletter <news@software.example>"),
    ]
    messages = []
    for mid, subject, body, sender in specs:
        m = raw_message(mid, body=body, sender=sender, to="Accounts <accounts@northstar.example>")
        next(h for h in m["payload"]["headers"] if h["name"] == "Subject")["value"] = subject
        if mid == "demo-review":
            attach_file(m, "October-reconciliation.txt", b"October reconciliation schedule\nBookkeeping records reviewed.\nTwo transactions await client clarification.")
        messages.append(m)
    api = FakeGmail(messages, page_size=10)
    api.label_data = [dict(id="L1", name="Clients/Northstar Imports", type="user")]
    return api


if "portfolio_temp" not in st.session_state:
    st.session_state["portfolio_temp"] = tempfile.TemporaryDirectory(prefix="eml-portfolio-")
directory = Path(st.session_state["portfolio_temp"].name)
os.environ["EML_PROFILE_DB"] = str(directory / "demo.sqlite3")
os.environ["EML_AUTH_DIR"] = str(directory / "auth")
if "portfolio_client" not in st.session_state:
    with ProfileStore(os.environ["EML_PROFILE_DB"]) as store:
        cid = store.create_client("Northstar Imports Pty Ltd · Demo")
        store.add_manual(cid, "history_notes", "Fictional wholesale business. Monthly bookkeeping and BAS support. Previous invoice wording guides style only.")
        GenerationTemplateStore(store).save(cid, style="Use concise invoice-style descriptions. Group related work; distinguish completed and requested activities. Never invent hours or fees.", privacy_rules="Northstar Imports => ENTITY", local_only=True)
    st.session_state.update(portfolio_client=cid, workspace_client=cid,
        workspace_account="reviewer@firm.example", ollama_model_address="http://127.0.0.1:11434",
        ollama_models=[DemoModel.model], ollama_model_choice=DemoModel.model)

import workspace_ui
if not hasattr(workspace_ui, "_portfolio_header_original"):
    workspace_ui._portfolio_header_original = workspace_ui.workspace_header
original_header = workspace_ui._portfolio_header_original
def demo_header(*args, **kwargs):
    original_header(*args, **kwargs)
    st.caption("SYNTHETIC DEMO · Fictional correspondence · Scripted model response")

with patch("fetch_emails.get_gmail_service", return_value=mailbox()), \
     patch("workspace_panels.OllamaClient", DemoModel), \
     patch("workspace_ui.workspace_header", demo_header):
    runpy.run_path(str(ROOT / "client_workspace.py"), run_name="__main__")
