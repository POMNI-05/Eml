import base64
import copy


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
        index = int(kwargs.get("pageToken", "0"))
        page = items[index:index + self.api.page_size]
        result = {"messages": [{"id": m["id"], "threadId": m["threadId"]} for m in page]}
        if index + self.api.page_size < len(items):
            result["nextPageToken"] = str(index + self.api.page_size)
        return Request(result)

    def get(self, **kwargs):
        self.api.calls.append(("messages.get", kwargs))
        return Request(self.api.data[kwargs["id"]])


class Threads:
    def __init__(self, api):
        self.api = api

    def get(self, **kwargs):
        self.api.calls.append(("threads.get", kwargs))
        return Request({
            "id": kwargs["id"],
            "messages": [m for m in self.api.data.values() if m["threadId"] == kwargs["id"]],
        })
