"""Synthetic mailbox with the real cloud-package UI. No Google authorization."""
import json
import os
from pathlib import Path
import runpy
import sys
from unittest.mock import patch

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from helpers.windows_trial import trial_environment
from eml_core import ProfileStore
from invoice.exchange import ExchangeStore
from invoice.templates import GenerationTemplateStore
from tests.fakes import FakeGmail, raw_message, attach_file
import workspace_ui

os.environ.update(trial_environment(demo=True))


def mailbox():
    review = raw_message("demo-review", body="I reviewed the Demo Consulting reconciliation and provided the draft for client review.")
    attach_file(review, "reconciliation.txt", b"Draft reconciliation provided for client review. Two transactions remain unresolved.")
    request = raw_message("demo-request", body="Please prepare our company tax return after we send the missing invoices.")
    news = raw_message("demo-news", body="A software newsletter; no professional work recorded.", sender="news@software.example")
    api = FakeGmail([review, request, news], page_size=10)
    api.label_data = [dict(id="L1", name="Clients/Demo Consulting", type="user")]
    return api


if "windows_demo_client" not in st.session_state:
    with ProfileStore(os.environ["EML_PROFILE_DB"]) as store:
        clients = store.list_clients()
        cid = clients[0]["client_id"] if clients else store.create_client("Demo Consulting Pty Ltd · Synthetic")
        if not clients:
            GenerationTemplateStore(store).save(cid, style="Draft concise evidence-backed work records. Do not infer hours, fees or completion.",
                                                privacy_rules="Demo Consulting => ENTITY", local_only=False)
    st.session_state.update(windows_demo_client=cid, workspace_client=cid, workspace_account="staff@firm.example")

original_header = workspace_ui.workspace_header


def demo_header(*args, **kwargs):
    original_header(*args, **kwargs)
    st.info("SYNTHETIC DEMO · No Gmail login. Select Clients/Demo Consulting and turn off Filter by date. After preparing a package, download the scripted response below to test JSON import, review and Word export.")


with patch("fetch_emails.get_gmail_service", return_value=mailbox()), \
        patch("workspace_ui.workspace_header", demo_header):
    runpy.run_path(str(ROOT / "client_workspace.py"), run_name="__main__")

cid = st.session_state.get("workspace_client")
if cid:
    with ProfileStore(os.environ["EML_PROFILE_DB"]) as store:
        exchanges = ExchangeStore(store)
        packages = exchanges.list(cid)
        if packages:
            selected = st.session_state.get(f"cloud_package_{cid}", packages[0]["bundle_id"])
            package = exchanges.get(cid, selected)
            message = package.request["input"]["evidence"]["selected_email_evidence"][0]
            reply = {"bundle_id": package.bundle_id, "evidence_sha256": package.request["input"]["evidence_sha256"],
                     "analysis": {"client_summary": "Synthetic interface test; no model was called.",
                                  "activities": [{"entity": "", "description": message["body"][:1000], "status": "unclear",
                                                  "evidence": [{"message_id": message["message_id"], "quote": message["body"][:1000]}],
                                                  "uncertainties": ["Scripted fixture; confirm the work status manually."]}], "open_questions": []}}
            st.divider()
            st.caption("Demo helper only: this scripted JSON tests the real import/validation/export path. It is not an AI result.")
            st.download_button("Download synthetic response JSON", json.dumps(reply), file_name="synthetic-response.json", mime="application/json")
