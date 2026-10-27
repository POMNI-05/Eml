"""Run with: streamlit run client_workspace.py

The primary work-draft workspace. Reuses the existing Gmail OAuth and reads
mail only after an explicit fetch action.
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
from eml_core.folders import ClientFolderStore
from eml_core.client_methods import ClientSearchMethodStore
from fetch_emails import get_gmail_service
from outlook_adapter import get_selected_outlook_message_ids
from eml_core.search import match_reasons
from workspace_panels import (
    connection_panel, model_panel, client_background_panel, client_search_panel, background_panel, generation_panel,
)
from workspace_ui import (
    apply_theme, workspace_header, disconnected_status, workflow_overview, getting_started, empty_correspondence,
    EMAIL_SOURCE_EXAMPLES,
    email_reader, sender_name, sender_address, message_date,
)


ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("EML_PROFILE_DB", ROOT / "data" / "client_profiles.sqlite3"))
FOLDERS, EMAILS, DRAFT = "1. Client & folders", "2. Review emails", "3. Draft & export"


def go_to_step(step):
    st.session_state["workspace_next_step"] = step


def clear_selection():
    for key in (
        "workspace_result", "workspace_selected_ids", "workspace_preview", "workspace_email_table",
        "workspace_email_baseline_ids", "workspace_sender",
    ):
        st.session_state.pop(key, None)
    go_to_step(FOLDERS)


def show_error(exc):
    st.error(str(exc))


def set_email_inclusion(message_ids, include):
    """Rebase the table after a bulk action while keeping unrelated choices."""
    result = st.session_state.get("workspace_result")
    if result is None:
        return
    current = set(st.session_state.get("workspace_selected_ids", []))
    current = current.union(message_ids) if include else current.difference(message_ids)
    chosen = [message.message_id for message in result.messages if message.message_id in current]
    st.session_state["workspace_selected_ids"] = chosen
    st.session_state["workspace_email_baseline_ids"] = chosen
    st.session_state.pop("workspace_email_table", None)


st.set_page_config(page_title="Eml · Work drafts", page_icon="✉", layout="wide")
apply_theme(ROOT)

with ProfileStore(DB_PATH) as store:
    connected = bool(st.session_state.get("workspace_account"))
    with st.container(
        key="header_connected" if connected else "header_onboarding", horizontal=True,
        horizontal_alignment="distribute", vertical_alignment="center",
    ):
        with st.container(width="content"):
            workspace_header(account=st.session_state.get("workspace_account"))
        with st.container(width="content"):
            if connected:
                with st.popover(
                    "Gmail connected", icon="🟢", key="gmail_status",
                    help="Account and AI settings · " + st.session_state["workspace_account"],
                ):
                    with st.container(key="gmail_settings"):
                        connection_panel(ROOT, get_gmail_service, clear_selection, compact=True)
                        model_client, language = model_panel(ROOT)
                    with st.expander("Import clients"):
                        upload = st.file_uploader("clients.json", type=["json"])
                        if st.button("Import client list", disabled=upload is None):
                            try:
                                count = store.import_legacy(json.loads(upload.getvalue()))
                                st.session_state["client_import_flash"] = f"Imported {count} clients."
                                st.rerun()
                            except (ValueError, TypeError, KeyError) as exc:
                                show_error(exc)
            else:
                disconnected_status()

    with st.container(key="workspace_shell" if connected else "onboarding_shell"):
        if not connected:
            auth_col, next_col = st.columns([1.2, 1], gap="large")
            with auth_col, st.container(border=True, key="gmail_connection"):
                connection_panel(ROOT, get_gmail_service, clear_selection)
            with next_col, st.container(border=True, key="next_steps"):
                workflow_overview()
            st.stop()
        flash = st.session_state.pop("client_import_flash", "")
        if flash:
            st.success(flash)
        client_col, new_col = st.columns([3, 1], gap="small", vertical_alignment="bottom")
        with new_col, st.popover("New client", use_container_width=True):
            with st.form("create_client", border=False):
                new_name = st.text_input("Client name", placeholder="e.g. Example Pty Ltd")
                create = st.form_submit_button("Add client", use_container_width=True)
            if create:
                try:
                    st.session_state["workspace_client"] = store.create_client(new_name)
                except ValueError as exc:
                    show_error(exc)
        clients = store.list_clients()
        names = {client["client_id"]: client["display_name"] for client in clients}
        with client_col:
            client_id = st.selectbox(
                "Client", [""] + list(names),
                format_func=lambda value: names.get(value, "Choose a client"),
                key="workspace_client",
            )
        if st.session_state.get("workspace_active_client") != client_id:
            clear_selection()
            st.session_state["workspace_active_client"] = client_id
            st.session_state["workspace_step"] = FOLDERS
            st.session_state.pop("workspace_next_step", None)
        if "workspace_next_step" in st.session_state:
            st.session_state["workspace_step"] = st.session_state.pop("workspace_next_step")
        if not client_id:
            getting_started()
            workflow_overview(connected=True)
            st.stop()

        with st.container():
            folder_store = ClientFolderStore(store)
            search_store = ClientSearchMethodStore(store)
            folder_tab, mail_tab, generation_tab = st.tabs(
                [FOLDERS, EMAILS, DRAFT], key="workspace_step", on_change="rerun",
            )
            with folder_tab:
                label_ids = []
                internet_ids = []
                include_sub_labels = False
                client_query = ""
                subject_prefix = excluded_subject_prefix = ""
                folder_col, period_col = st.columns([1.6, 1], gap="large")
                with folder_col:
                    source_panel = st.container(border=True, key="email_source_panel")
                with source_panel:
                    st.markdown("### Email source")
                    mode = st.radio(
                        "Email source", list(EMAIL_SOURCE_EXAMPLES),
                        captions=list(EMAIL_SOURCE_EXAMPLES.values()), label_visibility="collapsed",
                    )
                    if mode == "Client folders (IMAP)":
                        if st.button("Load folders"):
                            try:
                                mailbox = GmailMailbox(get_gmail_service())
                                account = mailbox.account_id()
                                labels = mailbox.list_labels()
                                if st.session_state.get("workspace_account") != account:
                                    clear_selection()
                                    st.session_state.pop("workspace_labels_choice", None)
                                st.session_state["workspace_account"] = account
                                st.session_state["workspace_labels"] = labels
                            except Exception as exc:
                                show_error(exc)
                        labels = st.session_state.get("workspace_labels", [])
                        label_names = {label["id"]: label["name"] for label in labels}
                        account = st.session_state.get("workspace_account", "")
                        preference = folder_store.get(client_id, account) if account else None
                        folder_scope = (client_id, account, bool(labels))
                        if (
                            st.session_state.get("workspace_folder_scope") != folder_scope
                            or "workspace_labels_choice" not in st.session_state
                            or "workspace_include_nested" not in st.session_state
                        ):
                            st.session_state["workspace_labels_choice"] = [
                                value for value in (preference or {}).get("label_ids", []) if value in label_names
                            ]
                            st.session_state["workspace_include_nested"] = (preference or {}).get("include_sub_labels", False)
                            st.session_state["workspace_folder_scope"] = folder_scope
                        # A refreshed list may have renamed or removed labels. Match IDs only.
                        st.session_state["workspace_labels_choice"] = [
                            value for value in st.session_state.get("workspace_labels_choice", []) if value in label_names
                        ]
                        if preference:
                            missing = [f["name"] for f in preference["folders"] if f["id"] not in label_names]
                            if missing and labels:
                                st.warning("Saved folders no longer found in this mailbox: " + "; ".join(missing))
                            elif labels:
                                st.caption("Saved folder choice for " + names[client_id] + " · " + account)
                        with st.expander("Standard Gmail folders"):
                            show_standard = st.checkbox("Show Inbox, Sent and other standard folders", value=False)
                        visible_ids = [
                            label["id"] for label in labels
                            if label.get("type") == "user" or show_standard
                            or label["id"] in st.session_state["workspace_labels_choice"]
                        ]
                        label_ids = st.multiselect(
                            "Client folders", visible_ids, format_func=lambda value: "📁 " + label_names[value],
                            key="workspace_labels_choice", placeholder="Search folder paths and select this client's folders",
                        )
                        include_sub_labels = st.checkbox("Include subfolders", key="workspace_include_nested")
                        remember_folders = st.checkbox("Remember these folders for this client", value=True)
                        if st.button("Save folder choice", disabled=not account or not labels):
                            folder_store.save(
                                client_id, account, [{"id": value, "name": label_names[value]} for value in label_ids],
                                include_sub_labels,
                            )
                            st.success("Folder choice saved for " + names[client_id] + ".")
                        if label_ids:
                            paths = [label_names[value] for value in label_ids]
                            included_paths = [
                                label["name"] for label in labels if label["id"] in label_ids or (
                                    include_sub_labels and any(label["name"].startswith(path + "/") for path in paths)
                                )
                            ]
                            st.caption(f"{len(included_paths)} folders in scope · duplicates will appear once")
                            with st.expander("Check the full folder scope"):
                                for path in included_paths:
                                    st.text(path)
                        elif not labels:
                            st.info("Load folders from Gmail, then choose the client's folder paths. No email is read by loading the folder list.")
                        st.caption("Outlook On My Computer and Smart Folders are separate from Gmail-synced folders.")
                    elif mode == "Client search":
                        plan, subject_prefix, excluded_subject_prefix = client_search_panel(store.context(client_id), search_store, st.session_state.get("workspace_account", ""))
                        client_query = plan.query if plan else ""
                    elif mode == "Internet Message-IDs":
                        text = st.text_area("Paste one Internet Message-ID per line")
                        internet_ids = [line.strip() for line in text.splitlines() if line.strip()]
                    else:
                        st.caption(
                            "Select messages in Legacy Outlook, then fetch. "
                            "The Mac AppleScript connection needs testing on that Outlook installation."
                        )

                with period_col, st.container(border=True, key="period_scope_panel"):
                    st.markdown("### Period & scope")
                    st.caption("Applies only to the selected emails.")
                    use_dates = st.checkbox("Filter by date", value=True)
                    start = end = None
                    if use_dates:
                        left, right = st.columns(2)
                        start = left.date_input("From", value=date.today().replace(day=1))
                        end = right.date_input("Through", value=date.today())
                        st.caption("Includes both dates in Australia/Sydney time.")
                    cap = st.checkbox("Limit the number of messages", value=True)
                    limit = int(st.number_input("Message limit", min_value=1, value=50)) if cap else None
                    st.caption("The limit applies only to this email fetch.")

                with period_col, st.container(border=True, key="client_background_panel"):
                    profile_tab, documents_tab = client_background_panel(store, client_id)

                signature = hashlib.sha256(json.dumps(
                    [client_id, mode, st.session_state.get("workspace_account"),
                     label_ids, internet_ids, client_query, include_sub_labels, start, end, limit,
                     subject_prefix, excluded_subject_prefix],
                    default=str,
                ).encode()).hexdigest()
                if st.session_state.get("workspace_scope") != signature:
                    had_result = st.session_state.get("workspace_result") is not None
                    clear_selection()
                    st.session_state["workspace_scope"] = signature
                    if had_result:
                        go_to_step(FOLDERS)
                        st.rerun()

                fetch_label = "Open selected folders →" if mode == "Client folders (IMAP)" else "Find emails →"
                ready = bool(label_ids) if mode == "Client folders (IMAP)" else (
                    bool(client_query) if mode == "Client search" else (
                        bool(internet_ids) if mode == "Internet Message-IDs" else True
                    )
                )
                with source_panel:
                    if st.button(fetch_label, type="primary", disabled=not ready):
                        clear_selection()
                        try:
                            if mode == "Outlook selection (Mac)":
                                internet_ids = get_selected_outlook_message_ids()
                            selection = Selection(
                                label_ids=tuple(label_ids) if mode == "Client folders (IMAP)" else (),
                                internet_message_ids=tuple(internet_ids) if mode != "Client folders (IMAP)" else (),
                                client_query=client_query,
                                include_sub_labels=include_sub_labels,
                                start_date=start, end_date=end, max_messages=limit,
                                subject_prefix=subject_prefix, excluded_subject_prefix=excluded_subject_prefix,
                            )
                            with st.spinner("Reading chosen emails…"):
                                result = GmailMailbox(get_gmail_service()).select(selection)
                            expected = st.session_state.get("workspace_account")
                            if mode == "Client folders (IMAP)" and expected != result.account_id:
                                raise ValueError("Gmail account changed. Reload its labels and choose again.")
                            if mode == "Client folders (IMAP)" and remember_folders:
                                folder_store.save(
                                    client_id, result.account_id,
                                    [{"id": value, "name": label_names[value]} for value in label_ids], include_sub_labels,
                                )
                            st.session_state["workspace_result"] = result
                            go_to_step(EMAILS)
                            st.rerun()
                        except Exception as exc:
                            show_error(exc)

            with mail_tab:
                st.subheader("Review the correspondence")
                st.caption("Read each message, keep the relevant evidence, then use the selection for your draft.")
                st.button("← Change client folders", on_click=go_to_step, args=(FOLDERS,))

                result = st.session_state.get("workspace_result")
                if result is None:
                    empty_correspondence()
                else:
                    for warning in result.warnings:
                        st.warning(warning)
                    if not result.complete:
                        st.warning("This selection is incomplete. It must not be described as all matching mail.")
                    by_id = {m.message_id: m for m in result.messages}
                    attachment_count = sum(len(m.attachment_contents) for m in result.messages)
                    if attachment_count:
                        unread = sum(not a.parts for m in result.messages for a in m.attachment_contents)
                        st.caption(f"Attachments: {attachment_count - unread} with extracted text · {unread} not read. Open an email to review its files.")
                    if not by_id:
                        st.info("No emails matched. Try another name or label, or widen the date range.")
                    selection_col, preview_col = st.columns([1.15, 1], gap="large")
                    with selection_col:
                        st.markdown("#### Relevant correspondence")
                        st.caption("Tick the messages that should support this draft.")
                        sender_groups = {}
                        for message in result.messages:
                            sender_groups.setdefault(sender_address(message.sender), []).append(message.message_id)
                        if by_id:
                            sender = st.selectbox(
                                "Sender", [""] + sorted(sender_groups), key="workspace_sender",
                                format_func=lambda value: (
                                    f"{value} · {len(sender_groups[value])} emails" if value else "All senders"
                                ),
                            )
                            targets = sender_groups[sender] if sender else list(by_id)
                            select_col, exclude_col = st.columns(2)
                            select_col.button(
                                "Select sender" if sender else "Select all", use_container_width=True,
                                on_click=set_email_inclusion, args=(targets, True),
                            )
                            exclude_col.button(
                                "Exclude sender" if sender else "Exclude all", use_container_width=True,
                                on_click=set_email_inclusion, args=(targets, False),
                            )
                        baseline = set(st.session_state.get("workspace_email_baseline_ids", list(by_id)))
                        rows = [
                            {"Include": m.message_id in baseline, "From": sender_name(m.sender), "Subject": m.subject or "(no subject)",
                             "Date": message_date(m), "Message ID": m.message_id}
                            for m in result.messages
                        ]
                        if rows:
                            edited_rows = st.data_editor(
                                rows, hide_index=True, height=min(400, 38 * len(rows) + 40), width="stretch",
                                disabled=["From", "Subject", "Date", "Message ID"],
                                column_config={"Include": st.column_config.CheckboxColumn("Use", width="small"),
                                               "From": st.column_config.TextColumn(width="small"),
                                               "Subject": st.column_config.TextColumn(width="medium"),
                                               "Date": st.column_config.TextColumn(width="small"), "Message ID": None},
                                key="workspace_email_table",
                            )
                            chosen_ids = [row["Message ID"] for row in edited_rows if row["Include"]]
                        else:
                            chosen_ids = []
                        st.session_state["workspace_selected_ids"] = chosen_ids
                        st.caption(f"{len(chosen_ids)} selected · {len(by_id)} loaded · {len(by_id) - len(chosen_ids)} excluded")
                        if st.button("Use selected emails →", type="primary", disabled=not chosen_ids, use_container_width=True):
                            go_to_step(DRAFT)
                            st.rerun()
                    with preview_col:
                        with st.container(border=True):
                            st.markdown("#### Reading pane")
                            if by_id:
                                mid = st.selectbox(
                                    "Preview email", list(by_id), format_func=lambda value: by_id[value].subject or value,
                                    key="workspace_preview",
                                )
                                email_reader(by_id[mid])
                            else:
                                st.caption("Your selected email will appear here.")
                    chosen = [by_id[mid] for mid in chosen_ids]
                    if chosen:
                        with st.expander("Matches with confirmed client background"):
                            st.dataframe([
                                {"Subject": m.subject, "Message ID": m.message_id,
                                 "Why it may relate": "; ".join(match_reasons(m, store.context(client_id)))
                                 or "No explicit profile match; review the email itself"}
                                for m in chosen
                            ], hide_index=True, width="stretch")
                    with st.expander("Build reusable client context from these emails"):
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
                                summary = update_profile(store, client_id, result.account_id, chosen, extractor)
                                st.success(
                                    f"{summary['new_suggestions']} new suggestions; "
                                    f"{summary['processed_messages']} messages processed; "
                                    f"{summary['skipped_messages']} already processed."
                                )
                            except Exception as exc:
                                show_error(exc)
                        st.caption("Optional. Review suggestions under Client & folders → Client background before confirming them.")
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

            with documents_tab:
                background_panel(store, client_id, model_client, language)
            with generation_tab:
                st.button("← Back to email review", on_click=go_to_step, args=(EMAILS,))
                generation_panel(store, client_id, model_client, language)
