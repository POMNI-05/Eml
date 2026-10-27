"""UI panels around reusable auth, documents and generation services."""

from pathlib import Path
import hashlib
import json

import streamlit as st

from eml_core import GmailMailbox
from eml_core.auth import GmailAuth
from eml_core.ai import OllamaClient, analyse_background, background_candidates
from eml_core.documents import BackgroundStore, explicit_document_candidates
from eml_core.search import build_client_search
from invoice.service import DraftStore, build_inputs, generate_draft, input_digest
from invoice.renderer import render_docx
from workspace_ui import activity_sources


def _clear_account(clear_selection):
    clear_selection()
    for key in ("workspace_account", "workspace_labels", "workspace_labels_choice", "workspace_folder_scope"):
        st.session_state.pop(key, None)


def connection_panel(root: Path, get_service, clear_selection, *, compact=False):
    auth = GmailAuth()
    status = auth.status()
    account = st.session_state.get("workspace_account")
    replace_file = st.session_state.get("gmail_replace_credentials", False)
    needs_file = not (status["credentials_present"] or status["authorization_present"])
    flash = st.session_state.pop("gmail_setup_flash", "")
    if flash:
        st.success(flash)

    if account and not replace_file:
        st.markdown("### Gmail connected")
        st.write(account)
        st.caption("Read-only mailbox access.")
        with st.container() if compact else st.popover("Connection options"):
            if st.button("Disconnect Gmail"):
                auth.disconnect()
                _clear_account(clear_selection)
                st.rerun()
            if st.button("Change Google app file"):
                st.session_state["gmail_replace_credentials"] = True
                st.rerun()
        return

    st.markdown(
        '<div class="eml-login-icon" aria-hidden="true">'
        '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="1.6"><rect x="3" y="5" width="18" height="14" rx="3"/>'
        '<path d="m4 7 8 6 8-6"/></svg></div>', unsafe_allow_html=True,
    )
    st.markdown("## Connect your Gmail")
    if needs_file or replace_file:
        st.caption("Add your Google app file once. Then sign in to your mailbox.")
        uploaded = st.file_uploader(
            "Drop Google credentials JSON here", type=["json"], key="google_credentials_upload",
            help="Use the Desktop app OAuth JSON downloaded from Google Cloud.",
        )
        if st.button("Save and continue", disabled=uploaded is None, type="primary", use_container_width=True):
            try:
                changed = auth.save_credentials(uploaded.getvalue())
                if changed:
                    _clear_account(clear_selection)
                st.session_state.pop("gmail_replace_credentials", None)
                st.session_state["gmail_setup_flash"] = "Ready to connect. Sign in with your Gmail account below."
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
        with st.expander("Where do I get this file?") if compact else st.popover("Where do I get this file?"):
            st.markdown(
                "1. Open [Google Cloud Console](https://console.cloud.google.com/) and enable **Gmail API**.\n"
                "2. Configure the app audience and add your Gmail as a test user.\n"
                "3. Create a **Desktop app** OAuth client and download its JSON file.\n\n"
                "Upload that file here. Your Google password is entered only on Google's sign-in page."
            )
            with st.expander("完整教程 · 中文"):
                tutorial = root / "docs" / "gmail_setup.md"
                if tutorial.exists():
                    st.markdown(tutorial.read_text())
        if replace_file and st.button("Cancel"):
            st.session_state.pop("gmail_replace_credentials", None)
            st.rerun()
        return

    st.caption("Open your saved mailbox or sign in with Google to get started.")
    if st.button("Connect Gmail", type="primary", use_container_width=True):
        try:
            with st.spinner("Complete Google sign-in in your browser…"):
                account = GmailMailbox(get_service()).account_id()
            if st.session_state.get("workspace_account") != account:
                _clear_account(clear_selection)
            st.session_state["workspace_account"] = account
            st.session_state["gmail_setup_flash"] = "Connected mailbox: " + account
            st.rerun()
        except Exception as exc:
            st.error(str(exc))
    st.caption("Read-only access. Email is loaded only when you choose folders and open them.")
    with st.expander("Connection help") if compact else st.popover("Connection help"):
        st.caption("Complete sign-in on this computer. For a test app, add your Gmail address to Google's test users.")
        if status["authorization_present"] and st.button("Reset saved sign-in"):
            auth.disconnect()
            _clear_account(clear_selection)
            st.rerun()
        if st.button("Use a different Google app file"):
            st.session_state["gmail_replace_credentials"] = True
            st.rerun()


def model_panel(root: Path):
    client = None
    with st.expander("Local AI setup"):
        tutorial = root / "docs" / "ollama_setup.md"
        with st.expander("Install and start Ollama"):
            if tutorial.exists():
                st.markdown(tutorial.read_text())
        address = st.text_input("Local Ollama address", value="http://127.0.0.1:11434")
        context_size = st.selectbox("Model context size", [16384, 32768, 65536], index=1)
        language = st.selectbox("Draft language", ["English", "中文"])
        if st.session_state.get("ollama_model_address") != address:
            st.session_state.pop("ollama_models", None)
            st.session_state.pop("ollama_model_choice", None)
        if st.button("Load local models"):
            try:
                models = OllamaClient(base_url=address).list_models()
                st.session_state["ollama_models"] = models
                st.session_state["ollama_model_address"] = address
                if not models:
                    st.info("No downloaded local models found. See the setup guide above.")
            except ValueError as exc:
                st.error(str(exc))
        models = st.session_state.get("ollama_models", [])
        if models:
            model = st.selectbox("Local model", models, key="ollama_model_choice")
            try:
                client = OllamaClient(model, address, context_size=context_size)
            except ValueError as exc:
                st.error(str(exc))
        st.caption("Selected documents and emails are sent to this local Ollama server only when you request analysis.")
    return client, language


def client_background_panel(store, client_id):
    """Client notes are independent of the selected email dates and folders."""
    st.markdown("### Client background")
    st.caption("Saved context for this client. It is reused across email periods.")
    facts = store.context(client_id)["confirmed_facts"]
    saved_note = next((fact["value"] for fact in facts if fact["field"] == "history_notes"), "")
    with st.form(f"background_note_form_{client_id}", border=False):
        note = st.text_area(
            "Background note", value=saved_note, height=100,
            placeholder="Example: Wholesale business with two related companies. Quarterly bookkeeping review.",
            key=f"background_note_{client_id}",
        )
        save = st.form_submit_button("Save background")
    if save:
        if note.strip():
            if note.strip() != saved_note:
                store.add_manual(
                    client_id, "history_notes", note.strip(), replace_existing=True,
                    note="Client background entered by reviewer",
                )
            st.success("Client background saved.")
        else:
            st.error("Enter a background note before saving.")
    with st.popover("Client details & documents", use_container_width=True):
        return st.tabs(["Client details", "Background documents"])


def _reset_client_search(state_key, widget_prefix, defaults):
    st.session_state[state_key] = {"terms": list(defaults)}
    for field in ("find", "match", "exclude", "prefix", "hide_prefix"):
        st.session_state.pop(widget_prefix + field, None)


def client_search_panel(context):
    """Plain-language search controls; selected entries define the full scope."""
    try:
        defaults = list(build_client_search(context).terms)
    except ValueError:
        defaults = []
    state_key = f"client_search_state_{context['client_id']}"
    widget_prefix = f"client_search_{context['client_id']}_"
    state = st.session_state.get(state_key, {"terms": defaults})
    terms = st.multiselect(
        "Find", list(dict.fromkeys(defaults + state.get("terms", []))),
        default=state.get("terms", defaults), accept_new_options=True,
        placeholder="Type a name, email or phrase, then press Enter",
        help="Each entry is one name, email address or phrase. Remove any saved client details you do not want to search.",
        key=widget_prefix + "find",
    )
    choices = ["Match ANY of those written", "Match ALL of those written"]
    saved_mode = state.get("match_mode", "all" if "all" in state.get("match", "").casefold() else "any")
    match = choices[1] if saved_mode == "all" else choices[0]
    if len(terms) > 1:
        match = st.radio(
            "Match", choices, index=choices.index(match), horizontal=True,
            key=widget_prefix + "match",
        )
    with st.popover("Exclusion filters"):
        excluded = st.multiselect(
            "Leave out", state.get("excluded", []), default=state.get("excluded", []),
            accept_new_options=True, placeholder="e.g. newsletter, meeting invitation",
            key=widget_prefix + "exclude",
        )
        prefix = st.text_input(
            "Subject begins with", value=state.get("prefix", ""), placeholder="e.g. Tax advice",
            help="Matches the actual beginning of the subject, including Re: or Fwd:.",
            key=widget_prefix + "prefix",
        )
        hide_prefix = st.text_input(
            "Hide subjects beginning with", value=state.get("hide_prefix", ""), placeholder="e.g. Re:",
            key=widget_prefix + "hide_prefix",
        )
        st.button(
            "Reset search", on_click=_reset_client_search,
            args=(state_key, widget_prefix, defaults),
            help="Restore saved client names and emails, and clear the extra filters.",
        )
    st.session_state[state_key] = {
        "terms": terms, "match": match, "match_mode": "all" if match == choices[1] else "any", "excluded": excluded,
        "prefix": prefix, "hide_prefix": hide_prefix,
    }
    try:
        plan = build_client_search(
            context, terms, include_profile=False,
            match_mode="all" if match == choices[1] else "any", excluded_terms=excluded,
        )
    except ValueError as exc:
        st.caption("Add a name, email address or phrase to start." if not terms else str(exc))
        return None, prefix.strip(), hide_prefix.strip()
    summary = (
        f"Match {plan.match_mode} of these {len(plan.terms)} entries."
        if len(plan.terms) > 1 else "Find emails matching this entry."
    )
    if plan.excluded_terms:
        summary += " Leave out: " + "; ".join(plan.excluded_terms) + "."
    if prefix.strip():
        summary += f" Subject begins with: {prefix.strip()}."
    if hide_prefix.strip():
        summary += f" Hide subjects beginning with: {hide_prefix.strip()}."
    st.caption(summary)
    return plan, prefix.strip(), hide_prefix.strip()


def background_panel(store, client_id, model_client, language):
    background = BackgroundStore(store)
    st.subheader("Client background documents")
    st.write("Add client notes, company structure, engagement scope or other business background.")
    roles = {
        "Client background": "client_background",
        "Agreed engagement scope": "engagement_scope",
        "Reference material": "reference",
    }
    role = st.selectbox("Document purpose", list(roles), key=f"document_role_{client_id}")
    uploads = st.file_uploader(
        "Drop background documents here", type=["txt", "md", "docx", "pdf"],
        accept_multiple_files=True, key=f"background_upload_{client_id}",
    )
    st.caption("Up to 20 MB per file. PDFs need searchable text; images and scanned pages are not OCR-processed.")
    if st.button("Save background documents", disabled=not uploads):
        results = []
        for upload in uploads:
            try:
                doc = background.save(client_id, upload.name, upload.getvalue(), roles[role])
                count = store.add_background_candidates(
                    client_id, [doc], explicit_document_candidates(doc)
                )
                results.append(("success", f"{doc.filename}: saved, {count} explicit profile suggestions."))
            except Exception as exc:
                results.append(("error", f"{upload.name}: {exc}"))
        st.session_state[f"document_flash_{client_id}"] = results
        st.rerun()
    for kind, message in st.session_state.pop(f"document_flash_{client_id}", []):
        getattr(st, kind)(message)
    documents = background.list(client_id)
    if not documents:
        st.info("Save a background document, or enter known details in Client context.")
        return
    by_id = {d.document_id: d for d in documents}
    selected = st.multiselect(
        "Documents to understand", list(by_id), default=list(by_id),
        format_func=lambda value: by_id[value].filename,
        key=f"analyse_documents_{client_id}",
    )
    chosen = [by_id[value] for value in selected]
    if chosen:
        with st.expander("Preview document text"):
            did = st.selectbox(
                "Document", selected, format_func=lambda value: by_id[value].filename,
                key=f"document_preview_{client_id}",
            )
            doc = by_id[did]
            for warning in doc.warnings:
                st.warning(warning)
            st.text("\n\n".join(f"{p.location}\n{p.text}" for p in doc.parts))
            st.download_button(
                "Download original document", background.original(client_id, did),
                file_name=doc.filename, key=f"download_source_{did}",
            )
    st.caption(
        "AI can interpret ordinary prose and propose companies, contacts, relationships and service scope. "
        "Confirm suggestions in Client context before they are used for Client search."
    )
    if st.button("Analyse documents with AI", disabled=not chosen or model_client is None):
        try:
            with st.spinner("Reading the selected client background…"):
                analysis = analyse_background(model_client, store.context(client_id), chosen, language)
                count = store.add_background_candidates(
                    client_id, chosen, background_candidates(analysis)
                )
            st.session_state[f"background_overview_{client_id}"] = {
                "document_ids": selected, "analysis": analysis.model_dump(),
                "new_suggestions": count,
            }
            st.rerun()
        except Exception as exc:
            st.error(str(exc))
    if model_client is None:
        st.info("Open Gmail connected → Local AI setup to choose a model for these documents.")
    overview = st.session_state.get(f"background_overview_{client_id}")
    if overview and overview["document_ids"] == selected:
        st.write("AI overview for review")
        st.write(overview["analysis"]["overview"])
        for question in overview["analysis"]["questions"]:
            st.write("To clarify: " + question)
        st.success(f"{overview['new_suggestions']} new profile suggestions. Review them in Client context.")


def _draft_downloads(draft, edits=None, reviewed=False, reviewer="", prefix="current"):
    st.download_button(
        "Download Word record",
        render_docx(draft, edits, reviewed=reviewed, reviewer=reviewer),
        file_name="billing_work_record.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        key=f"{prefix}_word_{draft['draft_id']}",
    )
    exported = {**draft, "review_edits": edits, "reviewed": reviewed, "reviewer": reviewer}
    st.download_button(
        "Download draft and source snapshot", json.dumps(exported, ensure_ascii=False, indent=2),
        file_name="billing_draft.json", mime="application/json",
        key=f"{prefix}_json_{draft['draft_id']}",
    )


def generation_panel(store, client_id, model_client, language):
    drafts = DraftStore(store)
    background = BackgroundStore(store)
    st.subheader("Prepare, review and export")
    st.caption("Build a work record from your selected emails. Check the source before confirming each activity.")
    saved = drafts.list(client_id)
    if saved:
        with st.expander("Saved drafts"):
            chosen_draft = st.selectbox(
                "Saved draft", [d["draft_id"] for d in saved],
                format_func=lambda value: next(d["created_at"] for d in saved if d["draft_id"] == value),
                key=f"saved_draft_{client_id}",
            )
            if st.button("Open saved draft"):
                st.session_state[f"open_saved_draft_{client_id}"] = chosen_draft
            if st.session_state.get(f"open_saved_draft_{client_id}") == chosen_draft:
                previous = drafts.get(client_id, chosen_draft)
                st.caption("This is the saved evidence snapshot, independent of the current selection.")
                st.write(previous["analysis"]["client_summary"])
                try:
                    _draft_downloads(
                        previous, previous.get("review_edits"),
                        previous.get("reviewed", False), previous.get("reviewer", ""), "saved",
                    )
                except (ValueError, TypeError, KeyError) as exc:
                    st.error("This saved draft contains invalid activity edits: " + str(exc))

    result = st.session_state.get("workspace_result")
    selected_ids = st.session_state.get("workspace_selected_ids", [])
    if result is None or not selected_ids:
        st.info("Choose a client's folders, open them, then use the relevant emails to prepare a draft.")
        return
    has_draft = bool(st.session_state.get(f"work_draft_{client_id}"))
    with st.expander("Draft inputs", expanded=not has_draft, key=f"draft_inputs_{client_id}_{has_draft}"):
        docs = background.list(client_id)
        by_id = {doc.document_id: doc for doc in docs}
        doc_ids = st.multiselect(
            "Background documents sent to AI", list(by_id), default=list(by_id),
            format_func=lambda value: by_id[value].filename,
            key=f"generation_documents_{client_id}",
        )
        chosen_docs = [by_id[value] for value in doc_ids]
        context = store.context(client_id)
        payload, _ = build_inputs(context, chosen_docs, result, selected_ids, language)
        if payload["selection_scope"]["attachment_warnings"]:
            st.warning("Some attachments were only partly read or could not be read. Check their notices in the email reading pane.")
        for column, label, value in zip(
            st.columns(3), ["Selected emails", "Background documents", "Confirmed details"],
            [len(selected_ids), len(chosen_docs), len(context["confirmed_facts"])],
        ):
            column.metric(label, value)
        st.download_button(
            "Download AI evidence package", json.dumps(payload, ensure_ascii=False, indent=2),
            file_name="ai_evidence_package.json", mime="application/json",
        )
    if not result.complete:
        st.warning("The mailbox fetch is incomplete; the draft will cover only the selected evidence.")
    if model_client is None:
        st.info("Open Gmail connected → Local AI setup to choose a model for the draft.")
        return
    signature = input_digest(payload, model_client.model, model_client.context_size)
    key = f"work_draft_{client_id}"
    if st.button("Generate work record draft", type="primary"):
        try:
            with st.spinner("Generating activities from email evidence and client background…"):
                draft = generate_draft(
                    model_client, context, chosen_docs, result, selected_ids, language
                )
                drafts.save(draft)
            st.session_state[key] = draft
            st.rerun()
        except Exception as exc:
            st.error(str(exc))
    draft = st.session_state.get(key)
    if not draft:
        return
    if draft["input_digest"] != signature:
        st.info("The emails, background, profile or model changed. Generate a fresh draft for these inputs.")
        return
    with st.container(border=True):
        st.markdown("#### Client & work summary")
        st.write(draft["analysis"]["client_summary"])
        for question in draft["analysis"]["open_questions"]:
            st.write("To clarify: " + question)
    activities = draft["analysis"]["activities"]
    rows = draft.get("review_edits") or [
        {"Item": i + 1, "Include": True, "Entity": a["entity"],
         "Description": a["description"], "Status": a["status"], "Reviewer note": ""}
        for i, a in enumerate(activities)
    ]
    if activities:
        edit_col, evidence_col = st.columns([1.35, 1], gap="large")
        with edit_col:
            st.markdown("#### Proposed work activities")
            st.caption("Edit descriptions and status. Untick any activity that should be left out.")
            edited = st.data_editor(
                rows, hide_index=True, disabled=["Item"], width="stretch", row_height=80,
                column_config={
                    "Item": None,
                    "Include": st.column_config.CheckboxColumn("Use", width="small"),
                    "Entity": st.column_config.TextColumn(width="small"),
                    "Description": st.column_config.TextColumn(width="medium", required=True),
                    "Status": st.column_config.SelectboxColumn(
                        options=["completed", "in_progress", "requested", "unclear"], required=True, width="small",
                    ),
                }, column_order=["Include", "Description", "Status", "Entity", "Reviewer note"],
                key=f"activities_{draft['draft_id']}",
            )
        with evidence_col:
            with st.container(border=True):
                activity_sources(draft)
    else:
        edited = []
        st.info("The model did not identify a supported work activity in the chosen emails.")
    reviewer = st.text_input(
        "Reviewer name", value=draft.get("reviewer", ""), key=f"reviewer_{draft['draft_id']}"
    )
    reviewed = st.checkbox(
        "I have checked the included activities against the email evidence",
        value=bool(draft.get("reviewed", False)),
        key=f"reviewed_{draft['draft_id']}",
    )
    edits_valid = True
    try:
        _draft_downloads(draft, edited, reviewed, reviewer)
    except (ValueError, TypeError, KeyError) as exc:
        edits_valid = False
        st.error("Check the edited activity fields before exporting: " + str(exc))
    if st.button("Save edited draft", disabled=not edits_valid):
        import copy
        import uuid
        from eml_core.profiles import _now
        revised = copy.deepcopy(draft)
        revised.update(
            draft_id=str(uuid.uuid4()), parent_draft_id=draft["draft_id"], created_at=_now(),
            review_edits=edited, reviewed=reviewed, reviewer=reviewer,
        )
        try:
            drafts.save(revised)
        except (ValueError, TypeError, KeyError) as exc:
            st.error("Check the edited activity fields before saving: " + str(exc))
        else:
            st.session_state[key] = revised
            st.rerun()
