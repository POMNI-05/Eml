import os
import re
import json
import html
import base64
import difflib
from datetime import date
from email.utils import parseaddr, parsedate_to_datetime

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


# -----------------------------
# Gmail authentication
# -----------------------------
def get_gmail_service():
    creds = None

    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json",
                SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open("token.json", "w", encoding="utf-8") as token:
            json.dump(json.loads(creds.to_json()), token)

    return build("gmail", "v1", credentials=creds)

def find_gmail_message_by_rfc822_id(service, internet_message_id: str):
    internet_message_id = str(internet_message_id or "").strip()
    query = f"rfc822msgid:{internet_message_id}"

    result = (
        service.users()
        .messages()
        .list(
            userId="me",
            q=query,
            maxResults=10,
        )
        .execute()
    )

    messages = result.get("messages", [])

    if len(messages) == 0:
        return None

    if len(messages) > 1:
        raise RuntimeError(
            f"Expected exactly one Gmail message, found {len(messages)}"
        )

    return messages[0]


def get_gmail_thread(service, thread_id: str):
    return (
        service.users()
        .threads()
        .get(
            userId="me",
            id=thread_id,
            format="full",
        )
        .execute()
    )

# -----------------------------
# Email body parsing
# -----------------------------
def decode_base64_url(data):
    if not data:
        return ""

    try:
        return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
    except Exception:
        return ""


def clean_html_text(raw_html):
    if not raw_html:
        return ""

    text = html.unescape(raw_html)

    # Remove script/style blocks
    text = re.sub(r"<script.*?</script>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)

    # Replace line-breaking tags with newlines
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</div>", "\n", text, flags=re.IGNORECASE)

    # Remove all remaining tags
    text = re.sub(r"<[^>]+>", " ", text)

    # Clean whitespace
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)

    return text.strip()


def extract_body_from_payload(payload):
    plain_text = ""
    html_text = ""

    def walk(part):
        nonlocal plain_text, html_text

        mime_type = part.get("mimeType", "")
        body_data = part.get("body", {}).get("data", "")

        if mime_type == "text/plain" and body_data:
            plain_text += "\n" + decode_base64_url(body_data)

        elif mime_type == "text/html" and body_data:
            html_text += "\n" + decode_base64_url(body_data)

        for sub_part in part.get("parts", []):
            walk(sub_part)

    walk(payload)

    if plain_text.strip():
        return plain_text.strip()

    if html_text.strip():
        return clean_html_text(html_text)

    return ""


def payload_has_attachment(payload):
    """
    Detect whether a Gmail message payload contains an attachment.
    """
    found = False

    def walk(part):
        nonlocal found

        filename = part.get("filename", "")
        body = part.get("body", {})
        attachment_id = body.get("attachmentId")

        if filename or attachment_id:
            found = True

        for sub_part in part.get("parts", []):
            walk(sub_part)

    walk(payload)
    return found


def get_header(headers, name):
    name = name.lower()

    return next(
        (
            h.get("value", "")
            for h in headers
            if h.get("name", "").lower() == name
        ),
        ""
    )


def parse_email_message(message):
    payload = message.get("payload", {})
    headers = payload.get("headers", [])

    subject = get_header(headers, "Subject")
    sender = get_header(headers, "From")
    recipient = get_header(headers, "To")
    cc = get_header(headers, "Cc")
    date_raw = get_header(headers, "Date")

    sender_name, sender_email = parseaddr(sender)
    sender_domain = sender_email.split("@")[-1] if "@" in sender_email else ""

    label_ids = message.get("labelIds", [])
    direction = "sent" if "SENT" in label_ids else "received"

    body = extract_body_from_payload(payload)
    has_attachment = payload_has_attachment(payload)

    try:
        date_sort = parsedate_to_datetime(date_raw).isoformat()
    except Exception:
        date_sort = ""

    return {
        "id": message.get("id"),
        "thread_id": message.get("threadId"),
        "direction": direction,
        "subject": subject,
        "from": sender,
        "to": recipient,
        "cc": cc,
        "sender_name": sender_name,
        "sender_email": sender_email,
        "sender_domain": sender_domain,
        "date": date_raw,
        "date_sort": date_sort,
        "has_attachment": has_attachment,
        "body": body[:5000],
    }


# -----------------------------
# Gmail query builder
# -----------------------------
def gmail_date(d):
    if not d:
        return ""

    if isinstance(d, date):
        return d.strftime("%Y/%m/%d")

    return str(d).replace("-", "/")


def sanitize_gmail_search_text(text):
    """
    Keep Gmail query input simple.
    Avoid breaking Gmail search syntax with unexpected quotes/braces.
    """
    text = str(text or "").strip()
    text = text.replace('"', "")
    text = text.replace("{", "")
    text = text.replace("}", "")
    return text


def build_gmail_query(
    include_sent=True,
    keyword="",
    start_date=None,
    end_date=None,
    has_attachment=False
):
    parts = []

    if include_sent:
        # Gmail search syntax: inbox OR sent
        parts.append("{in:inbox in:sent}")
    else:
        parts.append("in:inbox")

    keyword = sanitize_gmail_search_text(keyword)
    if keyword:
        parts.append(f'"{keyword}"')

    if start_date:
        parts.append(f"after:{gmail_date(start_date)}")

    if end_date:
        parts.append(f"before:{gmail_date(end_date)}")

    if has_attachment:
        parts.append("has:attachment")

    return " ".join(parts)


# -----------------------------
# Fetch Gmail threads
# -----------------------------
def fetch_threads(
    max_threads=50,
    include_sent=True,
    keyword="",
    start_date=None,
    end_date=None,
    has_attachment=False
):
    service = get_gmail_service()

    query = build_gmail_query(
        include_sent=include_sent,
        keyword=keyword,
        start_date=start_date,
        end_date=end_date,
        has_attachment=has_attachment
    )

    results = service.users().threads().list(
        userId="me",
        q=query,
        maxResults=max_threads
    ).execute()

    thread_refs = results.get("threads", [])
    threads = []

    for thread_ref in thread_refs:
        thread_detail = service.users().threads().get(
            userId="me",
            id=thread_ref["id"],
            format="full"
        ).execute()

        messages = [
            parse_email_message(msg)
            for msg in thread_detail.get("messages", [])
        ]

        messages.sort(key=lambda x: x.get("date_sort", ""))

        if not messages:
            continue

        thread_has_attachment = any(
            m.get("has_attachment", False) for m in messages
        )

        full_text = "\n\n".join(
            [
                f"{m.get('direction', '').upper()} | {m.get('date', '')}\n"
                f"From: {m.get('from', '')}\n"
                f"To: {m.get('to', '')}\n"
                f"Cc: {m.get('cc', '')}\n"
                f"Subject: {m.get('subject', '')}\n"
                f"Has attachment: {m.get('has_attachment', False)}\n\n"
                f"{m.get('body', '')}"
                for m in messages
            ]
        )

        participants = sorted(
            set(
                [m.get("from", "") for m in messages if m.get("from")]
                + [m.get("to", "") for m in messages if m.get("to")]
                + [m.get("cc", "") for m in messages if m.get("cc")]
            )
        )

        threads.append({
            "thread_id": thread_detail.get("id"),
            "subject": messages[0].get("subject", "No subject"),
            "message_count": len(messages),
            "first_date": messages[0].get("date", ""),
            "last_date": messages[-1].get("date", ""),
            "last_date_sort": messages[-1].get("date_sort", ""),
            "participants": participants,
            "has_attachment": thread_has_attachment,
            "messages": messages,
            "full_text": full_text,
        })

    threads.sort(key=lambda x: x.get("last_date_sort", ""), reverse=True)
    return threads


# -----------------------------
# Matching / filtering
# -----------------------------
def normalize_text(text):
    return str(text or "").lower().strip()


def fuzzy_score(search_term, target_text):
    search_term = normalize_text(search_term)
    target_text = normalize_text(target_text)

    if not search_term or not target_text:
        return 0

    if search_term in target_text:
        return 1

    return difflib.SequenceMatcher(None, search_term, target_text).ratio()


def thread_text_for_matching(thread):
    parts = []

    parts.append(thread.get("subject", ""))
    parts.append(thread.get("full_text", ""))
    parts.extend(thread.get("participants", []))

    for message in thread.get("messages", []):
        parts.append(message.get("from", ""))
        parts.append(message.get("to", ""))
        parts.append(message.get("cc", ""))
        parts.append(message.get("sender_email", ""))
        parts.append(message.get("sender_domain", ""))
        parts.append(message.get("subject", ""))
        parts.append(message.get("body", ""))

    return normalize_text(" ".join(parts))


def client_profile_text(client_profile):
    if not client_profile:
        return ""

    parts = []

    for key in [
        "display_name",
        "client_name",
        "company_name",
        "history_notes"
    ]:
        value = client_profile.get(key)
        if value:
            parts.append(str(value))

    for key in [
        "emails",
        "domains",
        "aliases",
        "search_keywords"
    ]:
        values = client_profile.get(key, [])
        if isinstance(values, list):
            parts.extend([str(v) for v in values if v])
        elif values:
            parts.append(str(values))

    return " ".join(parts)


def thread_match_score(
    thread,
    client_name="",
    company_name="",
    client_profile=None,
    threshold=0.55
):
    thread_text = thread_text_for_matching(thread)

    client_name = normalize_text(client_name)
    company_name = normalize_text(company_name)

    scores = []
    reasons = []

    # Manual client name filter
    if client_name:
        score = fuzzy_score(client_name, thread_text)
        scores.append(score)

        if score >= threshold:
            reasons.append(f"client name matched, score={score:.2f}")

    # Manual company name filter
    if company_name:
        score = fuzzy_score(company_name, thread_text)
        scores.append(score)

        if score >= threshold:
            reasons.append(f"company matched, score={score:.2f}")

    # Client profile filter
    if client_profile:
        profile_scores = []

        # Exact email match: strongest
        for email_address in client_profile.get("emails", []):
            email_norm = normalize_text(email_address)

            if email_norm and email_norm in thread_text:
                profile_scores.append(1.0)
                reasons.append(f"client email matched: {email_address}")

        # Exact domain match: also strong
        for domain in client_profile.get("domains", []):
            domain_norm = normalize_text(domain)

            if domain_norm and domain_norm in thread_text:
                profile_scores.append(0.95)
                reasons.append(f"client domain matched: {domain}")

        # Alias matching
        for alias in client_profile.get("aliases", []):
            alias_norm = normalize_text(alias)

            if not alias_norm:
                continue

            if alias_norm in thread_text:
                profile_scores.append(0.90)
                reasons.append(f"alias matched: {alias}")
            else:
                score = fuzzy_score(alias_norm, thread_text)
                profile_scores.append(score)

                if score >= threshold:
                    reasons.append(f"alias fuzzy matched: {alias}, score={score:.2f}")

        # Keyword matching
        for keyword in client_profile.get("search_keywords", []):
            keyword_norm = normalize_text(keyword)

            if not keyword_norm:
                continue

            if keyword_norm in thread_text:
                profile_scores.append(0.85)
                reasons.append(f"keyword matched: {keyword}")
            else:
                score = fuzzy_score(keyword_norm, thread_text)
                profile_scores.append(score)

                if score >= threshold:
                    reasons.append(f"keyword fuzzy matched: {keyword}, score={score:.2f}")

        # History note matching is weaker because it can be long and vague
        history_notes = client_profile.get("history_notes", "")
        if history_notes:
            score = fuzzy_score(history_notes, thread_text)
            profile_scores.append(score)

            if score >= threshold:
                reasons.append(f"client history matched, score={score:.2f}")

        if profile_scores:
            scores.append(max(profile_scores))

    # No filter means allow all
    if not client_name and not company_name and not client_profile:
        return 1, ["no client/company/client-profile filter"]

    best_score = max(scores) if scores else 0
    return best_score, reasons


def filter_threads(
    threads,
    client_name="",
    company_name="",
    client_profile=None,
    threshold=0.55
):
    filtered = []

    for thread in threads:
        score, reasons = thread_match_score(
            thread,
            client_name=client_name,
            company_name=company_name,
            client_profile=client_profile,
            threshold=threshold
        )

        if reasons:
            item = thread.copy()
            item["match_score"] = round(score, 2)
            item["match_reasons"] = reasons
            filtered.append(item)

    filtered.sort(key=lambda x: x.get("match_score", 0), reverse=True)
    return filtered


# -----------------------------
# Optional local test
# -----------------------------
if __name__ == "__main__":
    threads = fetch_threads(
        max_threads=10,
        include_sent=True,
        keyword="",
        start_date=None,
        end_date=None,
        has_attachment=False
    )

    with open("threads_raw.json", "w", encoding="utf-8") as f:
        json.dump(threads, f, ensure_ascii=False, indent=2)

    print(f"Fetched {len(threads)} threads.")
    print("Saved to threads_raw.json")
