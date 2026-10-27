import base64
import copy
import re
from email.utils import getaddresses


def matches_search_query(item, query):
    """Evaluate only the quoted any/all/exclusion grammar emitted by Eml."""
    tokens = re.findall(
        r'-?(?:(?:from|to|cc):)?"[^"]*"|-in:(?:spam|trash)|(?:after|before):-?\d+|\b(?:AND|OR)\b|[{}()]',
        query,
    )
    position = 0
    headers = {h["name"].casefold(): h["value"] for h in item["payload"].get("headers", [])}
    data = item["payload"].get("body", {}).get("data", "")
    body = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode() if data else ""
    text = (" ".join(headers.values()) + " " + body).casefold()

    def atom():
        nonlocal position
        token = tokens[position]
        position += 1
        if token in {"(", "{"}:
            return group(")" if token == "(" else "}", "AND" if token == "(" else "OR")
        if token.startswith("-in:"):
            return token[4:].upper() not in item.get("labelIds", [])
        if token.startswith(("after:", "before:")):
            if not item.get("internalDate"):
                return True
            field, value = token.split(":")
            timestamp = int(item["internalDate"])
            return timestamp > int(value) * 1000 if field == "after" else timestamp < int(value) * 1000
        negative = token.startswith("-")
        token = token[1:] if negative else token
        if token.startswith(("from:", "to:", "cc:")):
            field, value = token.split(":", 1)
            addresses = {address.casefold() for _, address in getaddresses([headers.get(field, "")])}
            matched = value.strip('"').casefold() in addresses
        else:
            matched = token.strip('"').casefold() in text
        return not matched if negative else matched

    def group(end=None, default="AND"):
        nonlocal position
        current = atom()
        alternatives = []
        while position < len(tokens) and tokens[position] != end:
            operator = tokens[position] if tokens[position] in {"AND", "OR"} else default
            if tokens[position] in {"AND", "OR"}:
                position += 1
            value = atom()
            if operator == "OR":
                alternatives.append(current)
                current = value
            else:
                current = current and value
        if end:
            if position >= len(tokens) or tokens[position] != end:
                raise AssertionError("Unbalanced generated search query")
            position += 1
        return any([*alternatives, current])

    return group() if tokens else True


def raw_message(mid, *, labels=("L1",), thread="t1", body="Hello",
                sender="Alex <alex@client.example>", to="staff@firm.example",
                timestamp=1790816400000):
    return {
        "id": mid, "threadId": thread, "internalDate": str(timestamp),
        "labelIds": list(labels),
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "From", "value": sender}, {"name": "To", "value": to},
                {"name": "Subject", "value": f"Subject {mid}"},
                {"name": "Date", "value": "Thu, 01 Oct 2026 10:00:00 +1000"},
                {"name": "Message-ID", "value": f"<{mid}@client.example>"},
            ],
            "body": {"data": base64.urlsafe_b64encode(body.encode()).decode().rstrip("=")},
        },
    }


def attach_file(message, filename, content=b"", *, part_id="1", attachment_id="", size=None):
    if message["payload"]["mimeType"] != "multipart/mixed":
        payload = message["payload"]
        message["payload"] = {
            "mimeType": "multipart/mixed", "headers": payload["headers"], "parts": [payload],
        }
    body = {"size": len(content) if size is None else size}
    if attachment_id:
        body["attachmentId"] = attachment_id
    else:
        body["data"] = base64.urlsafe_b64encode(content).decode().rstrip("=")
    message["payload"]["parts"].append({
        "partId": part_id, "filename": filename, "mimeType": "application/octet-stream", "body": body,
    })
    return message


class Request:
    def __init__(self, value):
        self.value = value

    def execute(self):
        return copy.deepcopy(self.value)


class FakeGmail:
    def __init__(self, messages=(), *, page_size=1):
        self.data = {m["id"]: m for m in messages}
        self.page_size = page_size
        self.calls = []
        self.account = "staff@firm.example"
        self.attachment_data = {}
        self.label_data = [
            {"id": "L1", "name": "Clients/Alex", "type": "user"},
            {"id": "L2", "name": "Clients/Alex/Company A", "type": "user"},
            {"id": "L3", "name": "Other client", "type": "user"},
            {"id": "INBOX", "name": "INBOX", "type": "system"},
        ]

    def users(self):
        return self

    def getProfile(self, **kwargs):
        self.calls.append(("profile", kwargs))
        return Request({"emailAddress": self.account})

    def labels(self):
        return Labels(self)

    def messages(self):
        return Messages(self)

    def threads(self):
        return Threads(self)


class Labels:
    def __init__(self, api):
        self.api = api

    def list(self, **kwargs):
        self.api.calls.append(("labels.list", kwargs))
        return Request({"labels": self.api.label_data})


class Messages:
    def __init__(self, api):
        self.api = api

    def list(self, **kwargs):
        self.api.calls.append(("messages.list", kwargs))
        items = list(self.api.data.values())
        for label in kwargs.get("labelIds", []):
            items = [m for m in items if label in m.get("labelIds", [])]
        query = kwargs.get("q", "")
        if query.startswith("rfc822msgid:"):
            term = query.split(":", 1)[1].strip('"<>')
            items = [
                m for m in items
                if any(h["name"].casefold() == "message-id" and h["value"].strip("<>") == term
                       for h in m["payload"].get("headers", []))
            ]
        elif "-in:spam" in query:
            items = [item for item in items if matches_search_query(item, query)]
        index = int(kwargs.get("pageToken", "0"))
        page = items[index:index + self.api.page_size]
        result = {"messages": [{"id": m["id"], "threadId": m["threadId"]} for m in page]}
        if index + self.api.page_size < len(items):
            result["nextPageToken"] = str(index + self.api.page_size)
        return Request(result)

    def get(self, **kwargs):
        self.api.calls.append(("messages.get", kwargs))
        return Request(self.api.data[kwargs["id"]])

    def attachments(self):
        return Attachments(self.api)


class Attachments:
    def __init__(self, api):
        self.api = api

    def get(self, **kwargs):
        self.api.calls.append(("attachments.get", kwargs))
        content = self.api.attachment_data[(kwargs["messageId"], kwargs["id"])]
        return Request({"data": base64.urlsafe_b64encode(content).decode().rstrip("="), "size": len(content)})


class Threads:
    def __init__(self, api):
        self.api = api

    def get(self, **kwargs):
        self.api.calls.append(("threads.get", kwargs))
        return Request({
            "id": kwargs["id"],
            "messages": [m for m in self.api.data.values() if m["threadId"] == kwargs["id"]],
        })
