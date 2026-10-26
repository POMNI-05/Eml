"""UI panels around reusable auth, documents and generation services."""

from pathlib import Path
import hashlib
import json

import streamlit as st

from eml_core import GmailMailbox
from eml_core.auth import GmailAuth
from eml_core.ai import OllamaClient, analyse_background, background_candidates
from eml_core.documents import BackgroundStore, explicit_document_candidates
from invoice.service import DraftStore, build_inputs, generate_draft, input_digest
from invoice.renderer import render_docx


def _clear_account(clear_selection):
    clear_selection()
    for key in ("workspace_account", "workspace_labels", "workspace_labels_choice"):
        st.session_state.pop(key, None)


def connection_panel(root: Path, get_service, clear_selection):
    auth = GmailAuth()
    status = auth.status()
    with st.expander("Gmail setup", expanded=not status["authorization_present"]):
        flash = st.session_state.pop("gmail_setup_flash", "")
        if flash:
            st.success(flash)
        st.caption("Credentials: " + ("saved" if status["credentials_present"] else "not uploaded"))
        st.caption("Google authorization: " + ("saved" if status["authorization_present"] else "not connected"))
        with st.expander("How to get credentials.json"):
            tutorial = root / "docs" / "gmail_setup.md"
            if tutorial.exists():
                st.markdown(tutorial.read_text())
        uploaded = st.file_uploader(
            "Drop Google credentials JSON here", type=["json"], key="google_credentials_upload",
            help="Use the Desktop app OAuth JSON downloaded from Google Cloud.",
        )
        if st.button("Save Google credentials", disabled=uploaded is None):
            try:
                changed = auth.save_credentials(uploaded.getvalue())
                if changed:
                    _clear_account(clear_selection)
                st.session_state["gmail_setup_flash"] = (
                    "Credentials saved locally. Connect Gmail to authorize the mailbox."
                )
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
        if st.button(
            "Connect Gmail", disabled=not (status["credentials_present"] or status["authorization_present"])
        ):
            try:
                with st.spinner("Complete Google sign-in in the browser on this computer…"):
                    account = GmailMailbox(get_service()).account_id()
                if st.session_state.get("workspace_account") != account:
                    _clear_account(clear_selection)
                st.session_state["workspace_account"] = account
                st.success("Connected mailbox: " + account)
            except Exception as exc:
                st.error(str(exc))
        if status["authorization_present"] and st.button("Forget local Google sign-in"):
            auth.disconnect()
            _clear_account(clear_selection)
            st.rerun()
        st.caption("Run this app on your computer. Credentials and authorization stay in local files.")


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
        st.info("Load a local model in the sidebar to interpret ordinary business documents.")
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
    st.subheader("Generate a work record")
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
        st.info("Choose emails and keep the relevant messages in Include these messages first.")
        return
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
    st.caption(
        f"{len(selected_ids)} chosen emails · {len(chosen_docs)} background documents · "
        f"{len(context['confirmed_facts'])} confirmed profile details."
    )
    st.download_button(
        "Download AI evidence package", json.dumps(payload, ensure_ascii=False, indent=2),
        file_name="ai_evidence_package.json", mime="application/json",
    )
    if not result.complete:
        st.warning("The mailbox fetch is incomplete; the draft will cover only the selected evidence.")
    if model_client is None:
        st.info("Load a local model in the sidebar to generate the draft.")
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
        edited = st.data_editor(
            rows, hide_index=True, disabled=["Item"], width="stretch",
            column_config={"Status": st.column_config.SelectboxColumn(
                options=["completed", "in_progress", "requested", "unclear"], required=True
            )}, key=f"activities_{draft['draft_id']}",
        )
        with st.expander("Check source quotations"):
            for i, activity in enumerate(activities, 1):
                st.write(f"Activity {i}")
                st.json(activity["evidence"])
                for uncertainty in activity["uncertainties"]:
                    st.write("To verify: " + uncertainty)
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
