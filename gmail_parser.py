import base64
from email.utils import getaddresses


def get_header(headers, name):
    target = name.lower()

    for header in headers:
        if header.get("name", "").lower() == target:
            return header.get("value", "")

    return ""


def parse_address_list(value):
    addresses = []

    for display_name, email_address in getaddresses([value or ""]):
        if email_address:
            addresses.append(
                {
                    "name": display_name,
                    "email": email_address,
                }
            )

    return addresses


def decode_body_data(data: str) -> str:
    if not data:
        return ""

    padding = "=" * (-len(data) % 4)
    raw = base64.urlsafe_b64decode(data + padding)

    return raw.decode("utf-8", errors="replace")


def extract_plain_text(part):
    mime_type = part.get("mimeType", "")

    if mime_type == "text/plain":
        data = part.get("body", {}).get("data", "")
        return decode_body_data(data)

    for child in part.get("parts", []):
        text = extract_plain_text(child)
        if text:
            return text

    return ""


def parse_gmail_message(message):
    payload = message.get("payload", {})
    headers = payload.get("headers", [])

    sender = get_header(headers, "From")
    to = get_header(headers, "To")
    cc = get_header(headers, "Cc")

    return {
        "gmail_message_id": message.get("id", ""),
        "thread_id": message.get("threadId", ""),
        "from": sender,
        "from_parsed": parse_address_list(sender),
        "to": parse_address_list(to),
        "cc": parse_address_list(cc),
        "date": get_header(headers, "Date"),
        "subject": get_header(headers, "Subject"),
        "body_text": extract_plain_text(payload).strip(),
    }


def parse_gmail_thread(thread):
    messages = [
        parse_gmail_message(message)
        for message in thread.get("messages", [])
    ]

    return {
        "thread_id": thread.get("id", ""),
        "messages": messages,
    }
