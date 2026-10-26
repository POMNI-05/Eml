"""Run with: streamlit run client_workspace.py

An optional client-context workspace alongside the original app.py. Reuses
the existing Gmail OAuth. It reads mail only after an explicit fetch action.
"""

import hashlib
import json
import os
from dataclasses import asdict
from datetime import date
from pathlib import Path

import streamlit as st

from eml_core import GmailMailbox, ProfileStore, RuleExtractor, Selection, update_profile
from eml_core.profiles import SCALAR_FIELDS
from fetch_emails import get_gmail_service
from outlook_adapter import get_selected_outlook_message_ids


ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("EML_PROFILE_DB", ROOT / "data" / "client_profiles.sqlite3"))


def clear_selection():
    for key in ("workspace_result", "workspace_selected_ids", "workspace_preview"):
        st.session_state.pop(key, None)


def show_error(exc):
    st.error(str(exc))


st.set_page_config(page_title="Eml · Client workspace", layout="wide")
st.title("Client workspace")
st.caption("Choose email evidence, review suggested client details, and keep confirmed context.")

with ProfileStore(DB_PATH) as store:
    with st.sidebar:
        st.subheader("Client groups")
        with st.form("create_client"):
            new_name = st.text_input("New client group name")
            create = st.form_submit_button("Create client group")
        if create:
            try:
                st.session_state["workspace_client"] = store.create_client(new_name)
            except ValueError as exc:
                show_error(exc)

        clients = store.list_clients()
        names = {c["client_id"]: c["display_name"] for c in clients}
        client_id = st.selectbox(
            "Client group", [""] + list(names),
            format_func=lambda value: names.get(value, "Choose a client group"),
            key="workspace_client",
        )
        st.caption("A client group can contain several companies and contacts.")
        with st.expander("Import existing client list"):
            upload = st.file_uploader("clients.json", type=["json"])
            if st.button("Import client list", disabled=upload is None):
                try:
                    count = store.import_legacy(json.loads(upload.getvalue()))
                    st.success(f"Imported {count} new client groups.")
                    st.rerun()
                except (ValueError, TypeError, KeyError) as exc:
                    show_error(exc)

    if st.session_state.get("workspace_active_client") != client_id:
        clear_selection()
        st.session_state["workspace_active_client"] = client_id
    if not client_id:
        st.info("Create or choose a client group to begin. Background details can be added later.")
        st.stop()

    mail_tab, profile_tab = st.tabs(["Choose emails", "Client context"])
    with mail_tab:
        mode = st.radio(
            "Email source",
            ["Gmail labels", "Outlook selection (Mac)", "Internet Message-IDs"],
            horizontal=True,
        )
        label_ids = []
        internet_ids = []
        include_sub_labels = False
        if mode == "Gmail labels":
            if st.button("Load Gmail labels"):
                try:
                    mailbox = GmailMailbox(get_gmail_service())
                    account = mailbox.account_id()
                    if st.session_state.get("workspace_account") != account:
                        clear_selection()
                        st.session_state.pop("workspace_labels_choice", None)
                    st.session_state["workspace_account"] = account
                    st.session_state["workspace_labels"] = mailbox.list_labels()
                except Exception as exc:
                    show_error(exc)
            labels = st.session_state.get("workspace_labels", [])
            label_names = {label["id"]: label["name"] for label in labels}
            label_ids = st.multiselect(
                "Labels", list(label_names), format_func=label_names.get,
                key="workspace_labels_choice",
            )
            include_sub_labels = st.checkbox("Also include nested labels", value=False)
            if st.session_state.get("workspace_account"):
                st.caption(f"Mailbox: {st.session_state['workspace_account']}")
            st.caption("Multiple labels are combined. Duplicate messages appear once.")
        elif mode == "Internet Message-IDs":
            text = st.text_area("Paste one Internet Message-ID per line")
            internet_ids = [line.strip() for line in text.splitlines() if line.strip()]
        else:
            st.caption(
                "Select messages in Legacy Outlook, then fetch. "
                "The Mac AppleScript connection needs testing on that Outlook installation."
            )

        use_dates = st.checkbox("Filter by date", value=False)
        start = end = None
        if use_dates:
            left, right = st.columns(2)
            start = left.date_input("From", value=date.today().replace(day=1))
            end = right.date_input("Through", value=date.today())
            st.caption("Includes both dates in Australia/Sydney time.")
        cap = st.checkbox("Limit the number of messages", value=False)
        limit = int(st.number_input("Message limit", min_value=1, value=500)) if cap else None

        signature = hashlib.sha256(json.dumps(
            [client_id, mode, st.session_state.get("workspace_account"),
             label_ids, internet_ids, include_sub_labels, start, end, limit],
            default=str,
        ).encode()).hexdigest()
        if st.session_state.get("workspace_scope") != signature:
            clear_selection()
            st.session_state["workspace_scope"] = signature

        if st.button("Fetch chosen emails", type="primary"):
            clear_selection()
            try:
                if mode == "Outlook selection (Mac)":
                    internet_ids = get_selected_outlook_message_ids()
                selection = Selection(
                    label_ids=tuple(label_ids) if mode == "Gmail labels" else (),
                    internet_message_ids=tuple(internet_ids) if mode != "Gmail labels" else (),
                    include_sub_labels=include_sub_labels,
                    start_date=start, end_date=end, max_messages=limit,
                )
                with st.spinner("Reading chosen emails…"):
                    result = GmailMailbox(get_gmail_service()).select(selection)
                expected = st.session_state.get("workspace_account")
                if mode == "Gmail labels" and expected != result.account_id:
                    raise ValueError("Gmail account changed. Reload its labels and choose again.")
                st.session_state["workspace_result"] = result
            except Exception as exc:
                show_error(exc)

        result = st.session_state.get("workspace_result")
        if result is not None:
            st.write(f"Loaded **{len(result.messages)}** messages for **{names[client_id]}**.")
            for warning in result.warnings:
                st.warning(warning)
            if not result.complete:
                st.warning("This selection is incomplete. It must not be described as all matching mail.")
            by_id = {m.message_id: m for m in result.messages}
            chosen_ids = st.multiselect(
                "Include these messages",
                list(by_id), default=list(by_id),
                format_func=lambda mid: (
                    f"{by_id[mid].date or 'No date'} · {by_id[mid].subject or '(no subject)'} · {mid}"
                ),
                key="workspace_selected_ids",
            )
            chosen = [by_id[mid] for mid in chosen_ids]
            if chosen:
                with st.expander("Preview a message"):
                    mid = st.selectbox(
                        "Message", chosen_ids, format_func=lambda mid: by_id[mid].subject or mid,
                        key="workspace_preview",
                    )
                    message = by_id[mid]
                    st.write("From:", message.sender)
                    st.write("To:", message.to)
                    st.write("Gmail ID:", message.message_id)
                    st.text(message.body)
                    if message.attachments:
                        st.write("Attachments (names only):", list(message.attachments))
            own_text = st.text_input(
                "Additional firm email addresses to exclude", help="Separate addresses with commas."
            )
            excluded_text = st.text_input(
                "Firm domains to exclude", help="For example: yourfirm.example"
            )
            if st.button("Suggest client details", disabled=not chosen):
                try:
                    extractor = RuleExtractor(
                        own_addresses=[result.account_id] + own_text.split(","),
                        excluded_domains=excluded_text.split(","),
                    )
                    summary = update_profile(
                        store, client_id, result.account_id, chosen, extractor
                    )
                    st.success(
                        f"{summary['new_suggestions']} new suggestions; "
                        f"{summary['processed_messages']} messages processed; "
                        f"{summary['skipped_messages']} already processed."
                    )
                except Exception as exc:
                    show_error(exc)
            st.caption(
                "Suggestions use sender/recipient headers and explicit Company:, Industry:, "
                "Business: or Agreed services: lines. Broader background can be entered below."
            )
            export = result.to_dict()
            export["messages"] = [asdict(message) for message in chosen]
            export["excluded_message_ids"] = [mid for mid in by_id if mid not in chosen_ids]
            st.download_button(
                "Download chosen evidence as JSON",
                json.dumps(export, ensure_ascii=False, indent=2),
                file_name="selected_messages.json", mime="application/json",
            )

    with profile_tab:
        context = store.context(client_id)
        st.subheader("Confirmed context")
        confirmed = context["confirmed_facts"]
        if confirmed:
            st.dataframe([
                {"Field": f["field"], "Value": json.dumps(f["value"], ensure_ascii=False)}
                for f in confirmed
            ], width="stretch", hide_index=True)
        else:
            st.info("No confirmed context yet. You can use email selection before completing a profile.")
        if context["possible_needs"]:
            st.write("Possible needs · hypotheses for review")
            st.json(context["possible_needs"])

        pending = store.list_facts(client_id, "pending")
        st.subheader(f"Suggestions to review · {len(pending)}")
        if pending:
            by_fact = {f["fact_id"]: f for f in pending}
            fid = st.selectbox(
                "Suggestion", list(by_fact),
                format_func=lambda key: (
                    f"{by_fact[key]['field']}: {json.dumps(by_fact[key]['value'], ensure_ascii=False)}"
                ),
            )
            fact = by_fact[fid]
            st.json(fact["evidence"])
            replace = st.checkbox(
                "Replace the previous confirmed value",
                disabled=fact["field"] not in SCALAR_FIELDS,
                key=f"replace_{fid}",
            )
            left, right = st.columns(2)
            if left.button("Confirm suggestion"):
                try:
                    store.review(client_id, fid, "confirmed", replace_existing=replace)
                    st.rerun()
                except ValueError as exc:
                    show_error(exc)
            if right.button("Reject suggestion"):
                store.review(client_id, fid, "rejected")
                st.rerun()

        with st.expander("Add or update background"):
            fields = {
                "Company / entity name": "entities", "Contact email": "contacts",
                "Industry": "industry", "Business description": "business_description",
                "Known engagement scope": "engagement_scope", "Alias": "aliases",
                "Background note": "history_notes", "Possible need (hypothesis)": "potential_need",
            }
            field_label = st.selectbox("Detail type", list(fields))
            field = fields[field_label]
            with st.form(f"manual_fact_{client_id}_{field}"):
                value = st.text_area("Value")
                contact_name = st.text_input("Contact name (for contact email)")
                note = st.text_input("Source / reason", value="Entered by reviewer")
                replace = st.checkbox("Replace an existing value for this detail", value=False)
                save = st.form_submit_button("Save confirmed detail")
            if save:
                try:
                    data = {"name": value} if field == "entities" else (
                        {"name": contact_name, "email": value} if field == "contacts" else value
                    )
                    store.add_manual(
                        client_id, field, data, note=note, replace_existing=replace
                    )
                    st.rerun()
                except ValueError as exc:
                    show_error(exc)

        st.download_button(
            "Download this client context",
            json.dumps(context, ensure_ascii=False, indent=2),
            file_name="profile_export.json", mime="application/json",
        )
        st.download_button(
            "Export confirmed clients for the original Eml app",
            json.dumps(store.export_legacy(), ensure_ascii=False, indent=2),
            file_name="clients.json", mime="application/json",
        )
