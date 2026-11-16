"""Optional cloud workflow; existing local AI and email selection stay intact."""

import html
import json
import os

import streamlit as st

from eml_core.gemini import GeminiClient
from invoice.exchange import CloudPackage, ExchangeStore, cloud_copy_prompt
from invoice.service import DraftStore
from invoice.templates import GenerationTemplateStore


def generation_settings(store, client_id):
    templates = GenerationTemplateStore(store)
    saved = templates.get(client_id)
    st.subheader("Writing preferences")
    st.caption("Example: Review of bank reconciliations for July–September 2026.")
    style = st.text_area(
        "Output preferences", value=saved["style"], height=240,
        key=f"client_output_style_{client_id}",
    )
    st.markdown("**Extra names to replace before cloud use**")
    st.caption("ANZ → BANK · Leave unused rows blank.")
    rules_key = f"client_privacy_rows_{client_id}"
    if rules_key not in st.session_state:
        count = len(saved["privacy_rules"].splitlines())
        st.session_state[rules_key] = max(3, count)
    existing = [line.rsplit("=>", 1) for line in saved["privacy_rules"].splitlines() if line.strip()]
    left, right = st.columns(2)
    left.markdown("Original")
    right.markdown("Replace with")
    rows = []
    for index in range(st.session_state[rules_key]):
        original, replacement = existing[index] if index < len(existing) else ("", "")
        left, right = st.columns(2)
        source = left.text_input(
            f"Original {index + 1}", value=original.strip(), label_visibility="collapsed",
            placeholder="Original name", key=f"privacy_original_{client_id}_{index}",
        )
        target = right.text_input(
            f"Replace with {index + 1}", value=replacement.strip(), label_visibility="collapsed",
            placeholder="BANK / ENTITY / ADDRESS", key=f"privacy_replacement_{client_id}_{index}",
        )
        rows.append((source.strip(), target.strip()))
    if st.button("＋", key=f"privacy_add_{client_id}", help="Add a replacement row",
                 disabled=st.session_state[rules_key] >= 300):
        st.session_state[rules_key] += 1
        st.rerun()
    local_only = st.checkbox(
        "Keep this client's processing local", value=saved["local_only"],
        key=f"client_local_only_{client_id}",
    )
    if st.button("Save generation preferences", key=f"save_generation_{client_id}"):
        if any(bool(source) != bool(target) for source, target in rows):
            st.error("Fill both cells in each used row, or leave both blank.")
        else:
            rules = "\n".join(f"{source} => {target}" for source, target in rows if source and target)
            try:
                templates.save(client_id, style=style, privacy_rules=rules, local_only=local_only)
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
    st.caption("Use letters and underscores for replacement labels. Names are restored locally; other details may still identify a client.")
    return saved


def _copy_prompt_button(prompt, *, disabled):
    """Copy only the reviewed, masked request; keep clipboard work in the browser."""
    payload = html.escape(prompt, quote=True)
    st.iframe(
        f"""<textarea id="prompt" style="position:fixed;left:-9999px" aria-hidden="true">{payload}</textarea>
<button id="copy" {'disabled' if disabled else ''} style="font:14px sans-serif;padding:10px 16px;
 border:1px solid #ccc;border-radius:8px;background:white;cursor:pointer">Copy prompt + emails for GPT</button>
<span id="status" role="status" style="font:13px sans-serif;margin-left:8px"></span>
<script>
document.getElementById('copy').addEventListener('click', async () => {{
 const text = document.getElementById('prompt');
 const status = document.getElementById('status');
 try {{
   try {{ await navigator.clipboard.writeText(text.value); }}
   catch (_) {{
     text.focus(); text.select();
     if (!document.execCommand('copy')) throw new Error('Clipboard unavailable');
   }}
   status.textContent = 'Copied — paste into GPT.';
 }} catch (_) {{ status.textContent = 'Use the download button to get the request.'; }}
}});
</script>""", height=55,
    )


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
        _copy_prompt_button(cloud_copy_prompt(package.request), disabled=not ready)
        st.download_button(
            "Download prompt + emails", cloud_copy_prompt(package.request),
            file_name="gpt_prompt.txt", mime="text/plain", disabled=not ready,
            key=f"prompt_download_{selected}",
        )
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
        st.info("Cloud preparation is off for this client. Uncheck “Keep this client's processing local” above and save to enable it.")
        return
    st.caption("Bundle the instructions and selected emails into one masked prompt for GPT.")
    if st.button("Prepare prompt + emails for GPT", type="primary"):
        try:
            package = CloudPackage.prepare(
                payload, privacy_rules=settings["privacy_rules"], local_only=settings["local_only"],
            )
            ExchangeStore(store).save(package)
            st.session_state[f"cloud_open_next_{client_id}"] = package.bundle_id
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
