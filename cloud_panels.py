"""Optional cloud workflow; existing local AI and email selection stay intact."""

import json
import os

import streamlit as st

from eml_core.gemini import GeminiClient
from invoice.exchange import CloudPackage, ExchangeStore
from invoice.service import DraftStore
from invoice.templates import GenerationTemplateStore


def generation_settings(store, client_id):
    templates = GenerationTemplateStore(store)
    saved = templates.get(client_id)
    with st.expander("Client generation preferences"):
        st.caption("Saved for this client across periods. These preferences do not prove that work was performed.")
        with st.form(f"generation_preferences_{client_id}"):
            local_only = st.checkbox(
                "Keep this client's processing local", value=saved["local_only"],
                key=f"client_local_only_{client_id}",
            )
            style = st.text_area(
                "Output preferences", value=saved["style"], height=140,
                key=f"client_output_style_{client_id}",
            )
            rules = st.text_area(
                "Extra names to replace before cloud use", value=saved["privacy_rules"],
                placeholder="ANZ => BANK\nExample Pty Ltd => ENTITY\n12 Example Street => ADDRESS",
                help="One exact phrase => TYPE per line. Contacts, confirmed names, email addresses and common identifiers are also masked.",
                key=f"client_privacy_rules_{client_id}",
            )
            if st.form_submit_button("Save generation preferences"):
                try:
                    templates.save(client_id, style=style, privacy_rules=rules, local_only=local_only)
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
        st.caption("Name replacement is reversible pseudonymisation. Distinctive business facts can still identify a client.")
    return saved


def pending_cloud_panel(store, client_id, settings):
    exchanges = ExchangeStore(store)
    saved = exchanges.list(client_id)
    if not saved:
        return
    with st.expander("Pending cloud packages — preview or restore a response", expanded=True):
        widget_key = f"cloud_package_{client_id}"
        deferred = st.session_state.pop(f"cloud_open_next_{client_id}", None)
        if deferred:
            st.session_state[widget_key] = deferred
        ids = [item["bundle_id"] for item in saved]
        if st.session_state.get(widget_key) not in ids:
            st.session_state.pop(widget_key, None)
        selected = st.selectbox(
            "Evidence package", ids,
            format_func=lambda value: next(item["created_at"] for item in saved if item["bundle_id"] == value),
            key=widget_key,
        )
        package = exchanges.get(client_id, selected)
        st.caption("This saved snapshot has its own emails and background. Current selections do not change it.")
        st.caption(f"{len(package.mapping)} local token mappings. Originals and mappings are excluded from this request.")
        with st.expander("Inspect the complete outgoing request"):
            st.code(json.dumps(package.request, ensure_ascii=False, indent=2), language="json")
        if settings["local_only"]:
            st.info("This client is set to local processing. You can restore an earlier response here; cloud sending is disabled.")
        st.caption(
            "For real client email use a firm-approved service with suitable data terms. "
            "Gemini unpaid services must not receive confidential/personal information and may use inputs to improve models."
        )
        reviewed = st.checkbox(
            "I reviewed this outgoing package and the firm permits its cloud use",
            key=f"cloud_review_{selected}_{package.request_sha256}",
            disabled=settings["local_only"],
        )
        ready = reviewed and not settings["local_only"]
        st.download_button(
            "Download masked request for an approved cloud service",
            json.dumps(package.request, ensure_ascii=False, indent=2),
            file_name="eml_cloud_request.json", mime="application/json", disabled=not ready,
            key=f"masked_download_{selected}",
        )
        st.caption("Ask for JSON matching response_schema, including the supplied package ID and evidence digest.")
        with st.expander("Or generate with Gemini API"):
            model = st.text_input(
                "Gemini model ID", value=os.environ.get("GEMINI_MODEL", ""),
                placeholder="Model ID enabled for your Google project", key=f"gemini_model_{client_id}",
            )
            key = st.text_input(
                "Gemini API key", type="password", key=f"gemini_key_{client_id}",
                help="Kept in this app session only. Alternatively set GEMINI_API_KEY on this computer.",
            )
            paid = st.checkbox(
                "This key uses an approved Google project with active Cloud Billing",
                key=f"gemini_paid_{selected}",
            )
            if st.button("Send reviewed package to Gemini", disabled=not ready or not paid or not model):
                try:
                    with st.spinner("Sending the reviewed package and checking the response…"):
                        draft = package.generate(
                            GeminiClient(model, key), reviewed_request_sha256=package.request_sha256,
                            paid_project_confirmed=paid, local_only=settings["local_only"],
                        )
                    DraftStore(store).save(draft)
                    st.session_state[f"work_draft_{client_id}"] = draft
                    st.success("Draft restored locally and saved. Check the proposed work below or open Saved drafts.")
                except ValueError as exc:
                    st.error(str(exc))
        reply = st.file_uploader(
            "Upload cloud response JSON to restore locally", type=["json"], key=f"cloud_response_{selected}",
        )
        if st.button("Restore and save response", disabled=reply is None):
            try:
                if reply.size > 4_000_000:
                    raise ValueError("Use a response JSON of at most 4 MB.")
                draft = package.accept(reply.getvalue())
                DraftStore(store).save(draft)
                st.session_state[f"work_draft_{client_id}"] = draft
                st.success("Draft restored locally and saved. Check the proposed work below or open Saved drafts.")
            except ValueError as exc:
                st.error(str(exc))
        if st.button("Delete this pending package", key=f"delete_package_{selected}"):
            exchanges.delete(client_id, selected)
            st.rerun()


def prepare_cloud_panel(store, client_id, payload, settings):
    if settings["local_only"]:
        st.info("Cloud preparation is off for this client. Change and save Client generation preferences to enable it.")
        return
    st.write("Prepare a masked snapshot, inspect it, then download it or send it to Gemini.")
    st.caption("No model is needed for preparation. Keep only the emails and background needed for this work record.")
    if st.button("Prepare cloud evidence package", type="primary"):
        try:
            package = CloudPackage.prepare(
                payload, privacy_rules=settings["privacy_rules"], local_only=settings["local_only"],
            )
            ExchangeStore(store).save(package)
            st.session_state[f"cloud_open_next_{client_id}"] = package.bundle_id
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
