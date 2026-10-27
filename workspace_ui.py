"""Shared presentation for the local work-draft workspace."""

from dataclasses import asdict, is_dataclass
from datetime import datetime
from email.utils import parseaddr, parsedate_to_datetime
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

import streamlit as st


EMAIL_SOURCE_EXAMPLES = {
    "Client folders (IMAP)": (
        "Use Gmail folders synced into Outlook. "
        "Example: select `Clients/Alex/Tax` for this client's correspondence."
    ),
    "Client search": (
        "Find mail using a client name or email address. "
        "Example: search for `alex@example.com` or `Example Pty Ltd`."
    ),
    "Outlook selection (Mac)": (
        "Start with messages selected in Legacy Outlook for Mac. "
        "Example: select three client emails there, then open them here."
    ),
    "Internet Message-IDs": (
        "Find specific messages using their Internet Message-IDs. "
        "Example: paste `<review-123@example.com>` from an email header."
    ),
}


def apply_theme(root: Path):
    st.markdown(f"<style>{(root / 'assets' / 'workspace.css').read_text()}</style>", unsafe_allow_html=True)


def brand():
    st.markdown(
        '<div class="eml-brand"><span class="eml-mark">e</span>'
        '<span>eml<span class="eml-dot">.</span></span></div>'
        '<div class="eml-brand-note">CORRESPONDENCE → WORK PRODUCT</div>',
        unsafe_allow_html=True,
    )


def workspace_header(client_name=None, account=None):
    st.markdown(
        f'<div class="eml-appbar {"" if account else "eml-appbar-onboarding"}">'
        '<div class="eml-brand"><span class="eml-mark">e</span>'
        '<span>eml<span class="eml-dot">.</span></span></div>'
        '<span class="eml-app-label">Work drafts</span></div>',
        unsafe_allow_html=True,
    )


def disconnected_status():
    st.markdown(
        '<div class="eml-connection-pill disconnected" role="status">'
        '<span class="eml-status-light" aria-hidden="true"></span>Gmail not connected</div>',
        unsafe_allow_html=True,
    )


def workflow_overview(connected=False):
    st.markdown("#### Your next steps")
    st.caption("Choose a client to begin." if connected else "Available after Gmail is connected.")
    for key, title, description in (
        ("folders", "1. Client & folders", "Choose the client and their synced folders."),
        ("emails", "2. Review emails", "Keep the correspondence relevant to this work."),
        ("draft", "3. Draft & export", "Prepare a draft, check its sources and export."),
    ):
        st.button(title, key=f"onboarding_{key}", disabled=True, use_container_width=True)
        st.caption(description)


def getting_started(account=None):
    st.caption("Choose a client above, or add one with New client. Folder choices are remembered for each client and mailbox.")


def sender_name(value):
    name, address = parseaddr(value)
    return name or address or "Unknown sender"


def sender_address(value):
    return parseaddr(value)[1].strip().casefold() or value.strip().casefold() or "Unknown sender"


def message_date(message):
    try:
        if message.timestamp_ms is not None:
            value = datetime.fromtimestamp(message.timestamp_ms / 1000, ZoneInfo("Australia/Sydney"))
        else:
            value = parsedate_to_datetime(message.date)
        return value.strftime("%d %b %Y")
    except (ValueError, TypeError, OverflowError):
        return message.date or "No date"


def email_reader(message, *, show_body=True):
    data = asdict(message) if is_dataclass(message) else message
    subject = escape(data.get("subject") or "(no subject)")
    sender = escape(data.get("sender") or "Unknown sender")
    recipient = escape(data.get("to") or "—")
    date = escape(data.get("date") or "No date")
    st.markdown(
        f'<div class="eml-message-head"><h3>{subject}</h3>'
        f'<p><strong>From</strong> {sender}<br><strong>To</strong> {recipient}</p>'
        f'<span>{date}</span></div>', unsafe_allow_html=True,
    )
    if show_body:
        st.markdown(
            f'<div class="eml-email-body">{escape(data.get("body") or "This email has no readable text body.")}</div>',
            unsafe_allow_html=True,
        )
    if data.get("attachments"):
        st.caption("Attachments: " + ", ".join(data["attachments"]))
        contents = data.get("attachment_contents", [])
        if not contents:
            st.caption("Attachment content was not loaded in this evidence snapshot. Fetch the emails again to read it.")
        for attachment in contents:
            parts = attachment.get("parts", [])
            label = attachment["filename"] + (" · text extracted" if parts else " · not read")
            with st.expander(label):
                st.caption("Source part: " + attachment["part_id"])
                for warning in attachment.get("warnings", []):
                    st.warning(warning)
                for part in parts:
                    st.caption(part["location"])
                    st.text(part["text"])
    with st.expander("Source reference"):
        st.text("Gmail message ID: " + data["message_id"])
        if data.get("internet_message_id"):
            st.text("Internet Message-ID: " + data["internet_message_id"])


def empty_correspondence():
    st.markdown(
        '<div class="eml-empty"><div class="eml-empty-icon">↗</div>'
        '<h3>A little correspondence. A clearer picture.</h3>'
        '<p>Open a client’s folders in the first step.<br>'
        'Their correspondence will appear here, ready to read and select.</p></div>', unsafe_allow_html=True,
    )


def activity_sources(draft):
    activities = draft["analysis"]["activities"]
    st.markdown("#### Supporting correspondence")
    index = st.selectbox(
        "Activity to verify", range(len(activities)),
        format_func=lambda value: f"{value + 1}. {activities[value]['description'][:75]}",
        key=f"verify_activity_{draft['draft_id']}",
    )
    activity = activities[index]
    messages = {m["message_id"]: m for m in draft["inputs"]["selected_email_evidence"]}
    sources = list(dict.fromkeys(source["message_id"] for source in activity["evidence"]))
    mid = st.selectbox(
        "Source email", sources, format_func=lambda value: messages[value]["subject"] or value,
        key=f"verify_source_{draft['draft_id']}_{index}",
    )
    email_reader(messages[mid], show_body=False)
    st.caption("QUOTED EVIDENCE")
    for source in activity["evidence"]:
        if source["message_id"] == mid:
            if source.get("attachment_part_id"):
                attachment = next(
                    a for a in messages[mid].get("attachment_contents", [])
                    if a["part_id"] == source["attachment_part_id"]
                )
                st.caption(attachment["filename"] + " · " + source["location"])
            st.markdown(f'<blockquote class="eml-quote">{escape(source["quote"])}</blockquote>', unsafe_allow_html=True)
    for uncertainty in activity["uncertainties"]:
        st.warning(uncertainty)
    with st.expander("Read the full email"):
        st.text(messages[mid]["body"])
