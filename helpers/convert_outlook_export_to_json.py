import zipfile
import json
import html
import re
import xml.etree.ElementTree as ET
from pathlib import Path

EXPORT_PATH = "2026-05-29_Strathdee_Outlook for Mac Archive.mbox"
JSON_OUT = "emails_readable.json"


def strip_html(value):
    if not value:
        return ""

    value = html.unescape(value)

    # Remove script/style blocks
    value = re.sub(r"<(script|style).*?</\1>", " ", value, flags=re.I | re.S)

    # Convert some block tags to newlines
    value = re.sub(r"</?(br|p|div|tr|li|h[1-6])[^>]*>", "\n", value, flags=re.I)

    # Remove all remaining tags
    value = re.sub(r"<[^>]+>", " ", value)

    # Clean whitespace
    value = re.sub(r"\r\n|\r", "\n", value)
    value = re.sub(r"\n\s*\n\s*\n+", "\n\n", value)
    value = re.sub(r"[ \t]+", " ", value)

    return value.strip()


def get_attr_or_child(email_el, name):
    """
    Outlook export fields may appear as XML attributes or child elements.
    This checks both.
    """
    if name in email_el.attrib:
        return email_el.attrib.get(name, "")

    child = email_el.find(name)
    if child is not None and child.text:
        return child.text

    return ""


def email_element_to_dict(email_el, source_file):
    body_html = get_attr_or_child(email_el, "OPFMessageCopyBody")

    item = {
        "source_file": source_file,

        # Common Outlook OPF fields
        "subject": get_attr_or_child(email_el, "OPFMessageCopySubject"),
        "from": get_attr_or_child(email_el, "OPFMessageCopySenderAddress"),
        "from_name": get_attr_or_child(email_el, "OPFMessageCopySenderName"),
        "to": get_attr_or_child(email_el, "OPFMessageCopyDisplayTo"),
        "cc": get_attr_or_child(email_el, "OPFMessageCopyDisplayCc"),
        "bcc": get_attr_or_child(email_el, "OPFMessageCopyDisplayBcc"),
        "date_sent": get_attr_or_child(email_el, "OPFMessageCopySentTime"),
        "date_received": get_attr_or_child(email_el, "OPFMessageCopyReceivedTime"),
        "message_id": get_attr_or_child(email_el, "OPFMessageCopyInternetMessageId"),

        # Body
        "body_html": html.unescape(body_html or ""),
        "body_text": strip_html(body_html or ""),
    }

    # Keep all raw OPF fields too, in case Outlook uses unexpected names.
    raw_fields = {}
    for key, value in email_el.attrib.items():
        raw_fields[key] = value

    for child in list(email_el):
        raw_fields[child.tag] = child.text or ""

    item["raw_fields"] = raw_fields

    return item


emails = []

export = Path(EXPORT_PATH)

print(f"Reading ZIP-style Outlook export: {export}")

with zipfile.ZipFile(export, "r") as z:
    names = z.namelist()
    print(f"Files inside archive: {len(names):,}")

    possible_xml_files = [
        name for name in names
        if not name.endswith("/")
        and (
            name.lower().endswith(".xml")
            or "/com.microsoft.__messages/" in name.lower()
            or "com.microsoft.__messages" in name.lower()
        )
    ]

    print(f"Possible XML/message files: {len(possible_xml_files):,}")

    for idx, name in enumerate(possible_xml_files, start=1):
        if idx % 1000 == 0:
            print(f"Scanned {idx:,} files... extracted {len(emails):,} emails")

        try:
            with z.open(name) as f:
                data = f.read()
        except Exception as e:
            print(f"Skipped unreadable file: {name} — {e}")
            continue

        # Fast skip if it does not contain email XML.
        if b"<email" not in data and b"<emails" not in data:
            continue

        try:
            root = ET.fromstring(data)
        except Exception as e:
            print(f"Skipped bad XML: {name} — {e}")
            continue

        # The root may be <emails>, or emails may be nested.
        for email_el in root.iter():
            tag = email_el.tag.split("}")[-1].lower()
            if tag == "email":
                emails.append(email_element_to_dict(email_el, name))

print(f"Extracted emails: {len(emails):,}")

with open(JSON_OUT, "w", encoding="utf-8") as f:
    json.dump(emails, f, ensure_ascii=False, indent=2)

print(f"Saved JSON to: {JSON_OUT}")