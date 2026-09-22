import json
import os
import streamlit as st

from fetch_emails import fetch_threads, filter_threads


CLIENTS_FILE = "clients.json"


def load_clients():
    if not os.path.exists(CLIENTS_FILE):
        return []

    with open(CLIENTS_FILE, "r", encoding="utf-8") as f:
        clients = json.load(f)

    if isinstance(clients, list):
        return [
            client
            for client in clients
            if isinstance(client, dict)
        ]

    if isinstance(clients, dict):
        if isinstance(clients.get("clients"), list):
            return [
                client
                for client in clients["clients"]
                if isinstance(client, dict)
            ]

        return [clients]

    return []


def build_default_keyword(client):
    """
    Pick one useful keyword/search term for the Gmail API query.
    Detailed matching still happens in filter_threads().
    """
    if not client:
        return ""

    candidates = []

    candidates.extend(client.get("emails", []))
    candidates.extend(client.get("domains", []))
    candidates.extend(client.get("aliases", []))
    candidates.extend(client.get("search_keywords", []))

    for item in candidates:
        if item:
            return str(item)

    return ""


st.set_page_config(
    page_title="Invoice Email Finder",
    layout="wide"
)


st.markdown(
    """
    <style>
    .block-container {
        padding-top: 2rem;
    }

    .email-card {
        background-color: white;
        padding: 16px;
        border-radius: 8px;
        margin-bottom: 12px;
        color: black;
        border: 1px solid #e5e5e5;
    }

    .small-label {
        font-weight: 700;
        margin-top: 12px;
    }
    </style>
    """,
    unsafe_allow_html=True
)


st.title("Invoice Email Finder")

left, middle, right = st.columns([1, 1, 1])


# -----------------------------
# LEFT PANEL: Client list
# -----------------------------
with left:
    st.subheader("Clients")

    clients = load_clients()

    selected_client = None

    if not clients:
        st.warning("No clients found. Please create clients.json.")
    else:
        client_labels = ["Manual search"]

        for client in clients:
            label = client.get("display_name") or client.get("client_name") or "Unnamed client"
            client_labels.append(label)

        selected_label = st.selectbox(
            "Select client",
            client_labels
        )

        if selected_label != "Manual search":
            selected_client = next(
                (
                    client for client in clients
                    if (client.get("display_name") or client.get("client_name")) == selected_label
                ),
                None
            )

    if selected_client:
        st.markdown("### Client profile")

        st.write("**Client name:**", selected_client.get("client_name", ""))
        st.write("**Company name:**", selected_client.get("company_name", ""))

        emails = selected_client.get("emails", [])
        if emails:
            st.write("**Emails:**")
            for email in emails:
                st.write("-", email)

        domains = selected_client.get("domains", [])
        if domains:
            st.write("**Domains:**")
            for domain in domains:
                st.write("-", domain)

        aliases = selected_client.get("aliases", [])
        if aliases:
            st.write("**Aliases:**")
            for alias in aliases:
                st.write("-", alias)

        keywords = selected_client.get("search_keywords", [])
        if keywords:
            st.write("**Search keywords:**")
            for keyword_item in keywords:
                st.write("-", keyword_item)

        history_notes = selected_client.get("history_notes", "")
        if history_notes:
            st.write("**History notes:**")
            st.write(history_notes)

    else:
        st.info("Select a client or use manual search.")


# -----------------------------
# MIDDLE PANEL: Filters
# -----------------------------
with middle:
    st.subheader("Filter")

    include_sent = st.checkbox(
        "Include emails I sent",
        value=True
    )

    start_date = st.date_input(
        "Start date",
        value=None
    )

    end_date = st.date_input(
        "End date",
        value=None
    )

    auto_client_name = ""
    auto_company_name = ""
    auto_keyword = ""

    if selected_client:
        auto_client_name = selected_client.get("client_name", "")
        auto_company_name = selected_client.get("company_name", "")
        auto_keyword = build_default_keyword(selected_client)

    client_name = st.text_input(
        "Client name",
        value=auto_client_name
    )

    company_name = st.text_input(
        "Company name",
        value=auto_company_name
    )

    keyword = st.text_input(
        "Keyword for Gmail search",
        value=auto_keyword,
        help="This is used in the Gmail API query. More detailed matching happens after fetching."
    )

    has_attachment = st.checkbox(
        "Only emails with attachment",
        value=False
    )

    max_threads = st.number_input(
        "Search limit",
        min_value=1,
        max_value=500,
        value=50,
        help=(
            "Maximum number of Gmail conversations to load before filtering. "
            "Higher numbers search more broadly but run slower."
        )
    )

    threshold = 0.65

    fetch_button = st.button("Fetch emails")


# -----------------------------
# RIGHT PANEL: Email display
# -----------------------------
with right:
    st.subheader("Email display")

    if fetch_button:
        with st.spinner("Fetching Gmail conversations..."):
            threads = fetch_threads(
                max_threads=int(max_threads),
                include_sent=include_sent,
                keyword=keyword,
                start_date=start_date,
                end_date=end_date,
                has_attachment=has_attachment
            )

            filtered_threads = filter_threads(
                threads,
                client_name=client_name,
                company_name=company_name,
                client_profile=selected_client,
                threshold=threshold
            )

            st.session_state["threads"] = filtered_threads

    threads = st.session_state.get("threads", [])

    st.write(f"Found **{len(threads)}** matching conversations.")

    if threads:
        with st.expander("DEBUG: First thread structure"):
            st.write(list(threads[0].keys()))
            st.json(threads[0])

        selected_indices = st.multiselect(
            "Choose relevant conversations",
            options=range(len(threads)),
            format_func=lambda i: (
                f"{threads[i].get('subject', 'No subject')} "
                f"({threads[i].get('message_count', 0)} messages)"
            ),
        )

        selected_threads = [
            threads[i]
            for i in selected_indices
        ]

        use_selected = st.button(
            "Use selected conversations",
            disabled=not selected_indices,
        )

        if use_selected:
            st.session_state["selected_threads"] = selected_threads

        committed_threads = st.session_state.get("selected_threads", [])

        if selected_threads:
            st.markdown("### Current checkbox selection")
            st.write(f"Selected **{len(selected_threads)}** conversation(s).")
            st.json(selected_threads)

        if committed_threads:
            st.markdown("### Committed selected conversations")
            st.write(f"Using **{len(committed_threads)}** conversation(s).")

            combined_text = "\n\n--- THREAD BREAK ---\n\n".join(
                thread.get("full_text", "")
                for thread in committed_threads
            )

            st.download_button(
                label="Download selected conversations as TXT",
                data=combined_text,
                file_name="selected_conversations.txt",
                mime="text/plain"
            )

            st.download_button(
                label="Download selected conversations as JSON",
                data=json.dumps(committed_threads, ensure_ascii=False, indent=2),
                file_name="selected_conversations.json",
                mime="application/json"
            )

            for thread_index, selected in enumerate(committed_threads, start=1):
                st.markdown(f"### Conversation {thread_index}")
                st.write("**Subject:**", selected.get("subject"))
                st.write("**Thread ID:**", selected.get("thread_id"))
                st.write("**Messages in thread:**", selected.get("message_count"))
                st.write("**First date:**", selected.get("first_date"))
                st.write("**Last date:**", selected.get("last_date"))
                st.write("**Match score:**", selected.get("match_score", "N/A"))

                st.write("**Match reasons:**")
                for reason in selected.get("match_reasons", []):
                    st.write("-", reason)

                st.write("**Participants:**")
                for person in selected.get("participants", []):
                    st.write("-", person)

                with st.expander("Copy conversation"):
                    st.code(selected.get("full_text", ""), language="text")

                st.markdown("#### Thread messages")

                for message in selected.get("messages", []):
                    expander_title = (
                        f"{message.get('direction', '').upper()} | "
                        f"{message.get('date', '')} | "
                        f"{message.get('subject', '')}"
                    )

                    with st.expander(expander_title):
                        st.write("**From:**", message.get("from"))
                        st.write("**To:**", message.get("to"))
                        st.write("**Date:**", message.get("date"))
                        st.write("**Direction:**", message.get("direction"))
                        st.write("**Has attachment:**", message.get("has_attachment"))
                        st.code(message.get("body", ""), language="text")

    else:
        st.write("Use the filter panel, then click **Fetch emails**.")
