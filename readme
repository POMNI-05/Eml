# Invoice Automation — Legacy Outlook to Python Backend

## 1. Project Goal

This project automates part of the invoice workflow from email.

The intended user workflow is:

```text
Boss selects an email
→ system identifies the selected message
→ system retrieves the full Gmail thread
→ Python cleans and structures the email content
→ AI extracts billing/invoice information
→ review page opens
→ boss checks and approves
→ PDF invoice and/or Gmail draft is generated
```

The system is **not intended to remove human review**. The boss remains responsible for checking and approving the invoice before it is sent. This matches the original project goal: automate repetitive email collection, information extraction, draft generation, and record keeping while retaining human approval.

---

# 2. Current Architecture

Always keep this architecture in mind when working on the project:

```text
Legacy Outlook
    ↓
AppleScript
    ↓
send_outlook_email.py
    ↓
HTTP / JSON
    ↓
FastAPI
    ↓
Python backend
    ↓
Gmail API
    ↓
Find exact Gmail message
    ↓
Get full Gmail thread
    ↓
Clean / normalize email content
    ↓
AI invoice extraction
    ↓
Review UI
    ↓
Boss approval
    ↓
PDF invoice / Gmail draft
```

The important design principle is **separation of responsibilities**（职责分离）.

Each layer should do one job.

---

# 3. Why We Are Using This Architecture

The company mailbox is actually a **Google Workspace Gmail mailbox**, but the boss uses **Legacy Outlook for Mac** as the desktop email client.

We tested Outlook add-in capability.

Results:

```text
Legacy Outlook
→ Get Add-ins button exists
→ button is disabled / unusable

New Outlook for Mac
→ Get Add-ins works
→ custom add-ins can potentially be added
```

Therefore, we should not make the entire application dependent on an Office.js Outlook add-in.

Instead:

```text
Legacy Outlook
→ AppleScript

New Outlook
→ potentially Office.js later
```

Both can eventually call the same Python backend.

This follows the original project direction: keep Python as the main backend and use a thin integration layer around Outlook.

---

# 4. What AppleScript Is Doing

AppleScript is macOS's built-in scripting language.

For this project, AppleScript is **not the invoice application**.

It is only a bridge:

```text
Outlook
→ AppleScript
→ Python
```

Its responsibility is:

```text
"What email did the boss select?"
```

We already proved that Legacy Outlook exposes the selected email to AppleScript.

From a selected message, AppleScript successfully retrieved:

```text
subject
sender name
sender email
received date
Outlook message ID
raw email source
internet Message-ID
```

This is an important milestone.

Legacy Outlook can therefore act as the boss's selection interface even without an Office.js add-in.

---

# 5. Important Test Result: Raw Email Source Works

AppleScript successfully retrieved the raw MIME source of a selected Outlook message.

The source contained headers such as:

```text
Date: Tue, 25 Aug 2026 11:34:08 +1000
Subject: ...
From: ...
To: ...
Message-ID: <...@post.xero.com>
Content-Type: multipart/alternative
```

It also contained:

```text
text/plain body
HTML body
MIME boundaries
quoted-printable encoding
```

This proves we can access the important internet-level email identifier:

```text
Message-ID
```

For example:

```text
<20260825013408.example@post.xero.com>
```

We should **not normally use AppleScript to parse the entire raw email**.

Instead, we use the Message-ID to locate the real email through Gmail API.

---

# 6. Why Message-ID Is Important

There are several different IDs involved.

Do not confuse them.

## Outlook ID

Outlook may expose its own internal message ID.

Example conceptually:

```text
123456
```

This is Outlook-specific and may not match Gmail.

---

## Internet Message-ID

The raw email contains:

```text
Message-ID: <something@example.com>
```

This is the standard email identifier defined in the email headers.

This is the most useful bridge between Outlook and Gmail.

---

## Gmail Message ID

Gmail API gives its own internal message ID:

```text
198e7abc123...
```

---

## Gmail Thread ID

Gmail also groups messages into conversations using:

```text
threadId
```

So the flow is:

```text
Internet Message-ID
        ↓
Gmail search
        ↓
Gmail message ID
        ↓
Gmail thread ID
        ↓
full conversation
```

---

# 7. Current Local Project Structure

At the moment, the project is approximately:

```text
invoice-auto/
│
├── outlook_bridge.py
├── send_outlook_email.py
├── fetch_emails.py
├── credentials.json
├── token.json
├── venv/
│
└── other existing invoice automation files
```

There is currently no requirement to create a `backend/` directory.

Earlier we tried:

```text
backend.outlook_bridge:app
```

but the actual file was placed directly in the project root.

Therefore the correct Uvicorn command is:

```bash
uvicorn outlook_bridge:app --reload --port 8000
```

Or preferably later:

```bash
python -m uvicorn outlook_bridge:app --reload --port 8000
```

---

# 8. Python Environment

The project has a virtual environment:

```text
invoice-auto/venv/
```

Activation currently looks like:

```bash
source /Users/icgtaxinternai/Documents/Code/invoice-auto/venv/bin/activate
```

The terminal prompt has shown:

```text
(venv) (base)
```

This means both the project virtual environment and Conda base appear active.

The project currently works, but this should eventually be cleaned up to avoid dependency confusion.

Useful diagnostic commands:

```bash
which python
which pip
which uvicorn
python --version
```

Ideally, Python and installed dependencies should come from:

```text
invoice-auto/venv/
```

rather than:

```text
miniconda3/
```

Prefer commands like:

```bash
python -m pip install fastapi uvicorn
python -m uvicorn outlook_bridge:app --reload --port 8000
```

because `python -m ...` ensures the selected Python interpreter executes the package.

---

# 9. FastAPI Layer

We created:

```text
outlook_bridge.py
```

Its purpose is to receive selected-email information from the Mac integration layer.

Current basic version:

```python
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()


class OutlookEmail(BaseModel):
    message_id: str
    subject: str
    sender_name: str
    sender_email: str
    received_at: str


@app.post("/outlook/selected-email")
def receive_selected_email(email: OutlookEmail):
    print("\n=== Selected Outlook Email ===")
    print("Message-ID:", email.message_id)
    print("Subject:", email.subject)
    print("Sender:", email.sender_name, f"<{email.sender_email}>")
    print("Received:", email.received_at)

    return {
        "ok": True,
        "message": "Email received by Python"
    }
```

---

# 10. What FastAPI Does

FastAPI exposes a local HTTP endpoint:

```text
http://127.0.0.1:8000/outlook/selected-email
```

The flow is:

```text
external trigger
    ↓
HTTP POST
    ↓
FastAPI
    ↓
Pydantic validation
    ↓
Python function
```

`127.0.0.1` means:

```text
this Mac itself
```

This is also called:

**localhost**（本机地址）

So the current FastAPI server is not automatically exposed to the public internet.

---

# 11. What Uvicorn Does

FastAPI defines the application.

Uvicorn actually runs the web server.

Conceptually:

```text
HTTP request
    ↓
Uvicorn
    ↓
FastAPI
    ↓
Python function
```

Current development command:

```bash
uvicorn outlook_bridge:app --reload --port 8000
```

Meaning:

```text
outlook_bridge
    ↓
outlook_bridge.py

app
    ↓
app = FastAPI()
```

Therefore:

```text
outlook_bridge:app
```

means:

```python
from outlook_bridge import app
```

The `--reload` option watches source files and reloads automatically when code changes.

It is useful during development.

---

# 12. HTTP / JSON Layer

Our components communicate through HTTP.

AppleScript itself does not need to understand FastAPI internals.

It only needs to trigger something that eventually sends data such as:

```json
{
  "message_id": "<example@example.com>",
  "subject": "Documents for invoice",
  "sender_name": "Example Client",
  "sender_email": "client@example.com",
  "received_at": "25 August 2026"
}
```

This is JSON.

JSON is simply a standard data format that different programming languages can understand.

For this project:

```text
AppleScript
→ Python helper
→ JSON
→ FastAPI
```

---

# 13. Initial curl Test

Before connecting real Outlook data, we tested FastAPI using `curl`.

Example:

```bash
curl -X POST \
  http://127.0.0.1:8000/outlook/selected-email \
  -H "Content-Type: application/json" \
  -d '{
    "message_id": "<test@example.com>",
    "subject": "Test invoice email",
    "sender_name": "Test User",
    "sender_email": "test@example.com",
    "received_at": "2026-08-25"
  }'
```

This succeeded.

That proved:

```text
HTTP client
→ FastAPI
→ Python
```

We then tested the same HTTP request from AppleScript.

That also succeeded.

Therefore:

```text
AppleScript
→ HTTP
→ FastAPI
→ Python
```

is confirmed.

---

# 14. What curl Was

`curl` is a command-line HTTP client.

It can send requests such as:

```text
GET
POST
PUT
DELETE
```

We used it only as a debugging/testing tool.

It allowed us to test the HTTP layer without involving Outlook.

Conceptually:

```text
curl
= pretend client
```

Instead of:

```text
Outlook
→ AppleScript
```

we temporarily used:

```text
curl
→ FastAPI
```

Once the system works, the boss will never use curl.

---

# 15. Why We Added send_outlook_email.py

Building JSON directly inside AppleScript became messy because AppleScript is very sensitive to:

```text
quotes
backslashes
special characters
new lines
```

We therefore created:

```text
send_outlook_email.py
```

Its responsibility is:

```text
receive command-line arguments
→ construct proper Python dictionary
→ convert dictionary to JSON
→ send HTTP request to FastAPI
```

This gives us:

```text
Legacy Outlook
    ↓
AppleScript
    ↓
send_outlook_email.py
    ↓
HTTP / JSON
    ↓
FastAPI
```

This is cleaner than forcing AppleScript to become a JSON-processing language.

---

# 16. send_outlook_email.py

Current helper:

```python
import json
import sys
from urllib.request import Request, urlopen


def main():
    if len(sys.argv) != 6:
        raise SystemExit(
            "Usage: python send_outlook_email.py "
            "<message_id> <subject> <sender_name> <sender_email> <received_at>"
        )

    message_id = sys.argv[1]
    subject = sys.argv[2]
    sender_name = sys.argv[3]
    sender_email = sys.argv[4]
    received_at = sys.argv[5]

    payload = {
        "message_id": message_id,
        "subject": subject,
        "sender_name": sender_name,
        "sender_email": sender_email,
        "received_at": received_at,
    }

    body = json.dumps(payload).encode("utf-8")

    request = Request(
        "http://127.0.0.1:8000/outlook/selected-email",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urlopen(request) as response:
        response_text = response.read().decode("utf-8")

    print(response_text)


if __name__ == "__main__":
    main()
```

---

# 17. sys.argv

`sys.argv` contains command-line arguments.

If something runs:

```bash
python send_outlook_email.py "123" "Documents" "Chris" "chris@example.com" "25 Aug"
```

Python sees:

```python
sys.argv[0]
# send_outlook_email.py

sys.argv[1]
# 123

sys.argv[2]
# Documents

sys.argv[3]
# Chris
```

This allows AppleScript to pass data into Python without manually constructing JSON.

---

# 18. Current AppleScript Responsibilities

The AppleScript should:

```text
1. Ask Outlook for current selection
2. Check that an email is selected
3. Read subject
4. Read received date
5. Read sender object
6. Extract sender name
7. Extract sender email
8. Read raw message source
9. Extract internet Message-ID
10. Call send_outlook_email.py
```

Conceptual structure:

```applescript
tell application "Microsoft Outlook"

    set selectedMessages to selection

    if selectedMessages is {} then
        display dialog "Please select an email first."
        return
    end if

    set theMessage to item 1 of selectedMessages

    set messageSubject to subject of theMessage
    set messageDate to time received of theMessage

    set senderObject to sender of theMessage
    set senderName to name of senderObject
    set senderAddress to address of senderObject

    set rawSource to source of theMessage

end tell
```

Then extract:

```text
Message-ID:
```

from `rawSource`.

Then call:

```text
send_outlook_email.py
```

---

# 19. AppleScript Sender Error We Already Solved

Initially, this failed:

```text
Can’t make {...sender object...} into type Unicode text.
```

Reason:

```text
sender
```

was not a normal string.

Outlook returned an object containing:

```text
name
address
type
```

The correct solution was:

```applescript
set senderObject to sender of theMessage
set senderName to name of senderObject
set senderAddress to address of senderObject
```

This is an important programming lesson:

```text
object
≠
string
```

You need to inspect the object's properties before converting/displaying it.

---

# 20. Next Major Step: Gmail API Lookup

This is the next task when development resumes.

Current architecture:

```text
Legacy Outlook
    ↓
AppleScript
    ↓
send_outlook_email.py
    ↓
HTTP / JSON
    ↓
FastAPI
    ↓
Python backend
```

Next extension:

```text
Legacy Outlook
    ↓
AppleScript
    ↓
send_outlook_email.py
    ↓
HTTP / JSON
    ↓
FastAPI
    ↓
Python backend
    ↓
Gmail API
    ↓
search by internet Message-ID
    ↓
exact Gmail message
    ↓
threadId
    ↓
full Gmail thread
```

---

# 21. Gmail Search Strategy

If Outlook gives:

```text
<abc123@example.com>
```

Gmail supports searching for the RFC 822 Message-ID using:

```text
rfc822msgid:<abc123@example.com>
```

Conceptual Python:

```python
def find_gmail_message_by_rfc822_id(service, internet_message_id):
    query = f"rfc822msgid:{internet_message_id}"

    result = service.users().messages().list(
        userId="me",
        q=query,
        maxResults=10,
    ).execute()

    messages = result.get("messages", [])

    if not messages:
        return None

    return messages[0]
```

Expected result:

```python
{
    "id": "gmail-message-id",
    "threadId": "gmail-thread-id"
}
```

---

# 22. Fetch the Full Gmail Thread

After obtaining:

```text
threadId
```

call:

```python
def get_gmail_thread(service, thread_id):
    return service.users().threads().get(
        userId="me",
        id=thread_id,
        format="full",
    ).execute()
```

Then the system can retrieve:

```text
message 1
message 2
message 3
...
```

instead of only the currently selected Outlook email.

This is important for billing because invoice information may be distributed throughout a conversation.

---

# 23. Why Gmail API Should Be the Authoritative Source

**authoritative source**（权威数据源） means the source we trust for the official/complete data.

For this project:

```text
Outlook
= selection interface

Gmail
= authoritative mailbox source
```

Outlook answers:

```text
"What did the boss click?"
```

Gmail answers:

```text
"What is the real email/thread and what data does it contain?"
```

This avoids relying on Outlook's rendering or MIME handling for downstream processing.

---

# 24. After Gmail API: Cleaning Layer

Raw Gmail API data still needs processing.

The next layer should eventually convert:

```text
MIME
HTML
quoted replies
signatures
encoded headers
attachments
```

into structured conversation data.

Target structure:

```text
Thread ID: ...

Message 1
From:
To:
Date:
Subject:
Body:

Message 2
From:
To:
Date:
Subject:
Body:

Message 3
...
```

Potential JSON representation:

```json
{
  "thread_id": "...",
  "messages": [
    {
      "from": "...",
      "to": ["..."],
      "date": "...",
      "subject": "...",
      "body_text": "..."
    }
  ]
}
```

Do not send huge raw MIME blobs directly to the AI unless necessary.

---

# 25. AI Layer

Only after email retrieval and cleaning are stable should AI processing be added.

Architecture:

```text
Gmail thread
    ↓
clean structured text
    ↓
AI extraction
```

The AI should ideally return structured output such as:

```json
{
  "client": "...",
  "work_description": "...",
  "billing_amount": null,
  "billing_basis": "...",
  "missing_information": [],
  "confidence": "..."
}
```

The exact schema still needs to be designed based on the company's real invoice workflow.

The AI should not automatically send invoices.

It should prepare information for human review.

---

# 26. Review Layer

Current likely choice:

```text
Streamlit
```

because the existing project already uses Python and Streamlit is quick for internal tools.

Possible boss workflow:

```text
Select email
→ run Create Invoice action
→ browser automatically opens
→ review page displays:

Client
Matter/work
Email thread summary
Extracted billing information
Warnings
Draft invoice
```

Boss can then:

```text
Approve
Edit
Reject
```

---

# 27. Final Output Layer

After approval:

```text
approved invoice data
    ↓
PDF generator
    ↓
invoice PDF
```

and potentially:

```text
approved invoice
    ↓
Gmail API
    ↓
create draft email
```

Important:

```text
Draft
≠
Send automatically
```

Human approval should remain part of the workflow unless requirements change.

---

# 28. Future Boss User Experience

The boss should **never need to open Script Editor**.

The current Script Editor workflow is only for development.

Final Legacy Outlook UX should be approximately:

```text
1. Boss selects email
2. Boss presses keyboard shortcut
   OR clicks macOS Shortcut/menu-bar action
3. Everything else runs automatically
4. Review screen opens
5. Boss approves
```

AppleScript should execute invisibly.

Possible final trigger methods:

```text
macOS Shortcut
keyboard shortcut
menu-bar utility
small desktop launcher
```

---

# 29. New Outlook Future Path

If the boss eventually switches to **New Outlook for Mac**, we can potentially create an Office.js add-in.

Then:

```text
New Outlook
    ↓
Office.js button
    ↓
HTTP / JSON
    ↓
FastAPI
    ↓
same Python backend
```

Compare:

```text
Legacy Outlook
    ↓
AppleScript
    ↓
send_outlook_email.py
    ↓
FastAPI
```

versus:

```text
New Outlook
    ↓
Office.js
    ↓
FastAPI
```

The backend remains unchanged.

This is the benefit of **decoupling**（解耦）.

---

# 30. Development Philosophy

Do not build the entire system at once.

Test one **handshake**（层与层之间的连接） at a time.

Already completed:

```text
Legacy Outlook
→ AppleScript
✅
```

Completed:

```text
AppleScript
→ selected email metadata
✅
```

Completed:

```text
AppleScript
→ raw source
→ Message-ID
✅
```

Completed:

```text
AppleScript
→ HTTP
→ FastAPI
✅
```

Current / next:

```text
FastAPI
→ Gmail API
→ exact Gmail message
```

Then:

```text
Gmail message
→ full thread
```

Then:

```text
thread
→ cleaner
```

Then:

```text
clean thread
→ AI
```

Then:

```text
AI
→ review UI
```

Then:

```text
approval
→ PDF / Gmail draft
```

This approach makes debugging much easier because when something breaks, we know which boundary caused it.

---

# 31. Where We Stopped — 25 August 2026

Current working state:

```text
Legacy Outlook
    ↓
selected real email
    ↓
AppleScript can read:
    - subject
    - sender
    - date
    - Outlook ID
    - raw source
    - internet Message-ID
    ↓
AppleScript can call local HTTP
    ↓
FastAPI receives JSON
    ↓
Python prints received metadata
```

The FastAPI server successfully starts with:

```bash
uvicorn outlook_bridge:app --reload --port 8000
```

and reports:

```text
Uvicorn running on http://127.0.0.1:8000
Application startup complete.
```

---

# 32. NEXT WEEK — Start Here

Do not restart from Outlook research.

The Outlook → AppleScript question is already sufficiently validated for development.

Start with:

```text
CURRENT ARCHITECTURE

Legacy Outlook
    ↓
AppleScript
    ↓
send_outlook_email.py
    ↓
HTTP / JSON
    ↓
FastAPI
    ↓
Python backend
```

Then implement:

```text
NEXT HANDSHAKE

Python backend
    ↓
Gmail API
    ↓
rfc822msgid search
    ↓
find exact Gmail message
```

First target:

```text
Select an Outlook email
→ run AppleScript
→ FastAPI receives internet Message-ID
→ Gmail API finds exactly one matching message
→ terminal prints Gmail message ID + thread ID
```

Success output should look approximately like:

```text
Outlook Internet Message-ID:
<abc@example.com>

Matched Gmail message:
198e7abc123

Gmail thread:
198e7def456

Match status:
SUCCESS
```

Do not add AI until this works reliably.

---

# 33. Next-Week Development Order

Follow this sequence:

```text
1. Clean Python environment if necessary

2. Confirm FastAPI still starts

3. Confirm AppleScript → FastAPI still works

4. Reuse existing Gmail authentication

5. Add Message-ID Gmail search

6. Fail clearly if:
   - zero matches
   - multiple ambiguous matches
   - Gmail API unavailable

7. Retrieve threadId

8. Fetch complete Gmail thread

9. Print thread metadata for inspection

10. Only then build cleaning/parsing

11. Only then connect AI

12. Only then build the boss-facing review workflow
```

---

# 34. Useful English / Engineering Vocabulary

Since this project is also being used for English practice:

**bridge**
桥接层
A component connecting two otherwise separate systems.

**handshake**
接口握手 / 两层成功建立连接
A successful initial exchange between components.

**backend**
后端
The application logic behind the user-facing interface.

**endpoint**
接口地址
A specific HTTP URL exposed by an API.

**payload**
请求数据 / 载荷
The data being sent in an HTTP request.

**schema**
数据结构规范
Definition of what fields/types a piece of data should contain.

**authoritative source**
权威数据源
The source treated as the correct/original data source.

**decoupling**
解耦
Designing components so one can change without rewriting everything else.

**dependency**
依赖
Another library/service/component required by your code.

**virtual environment**
虚拟环境
An isolated Python installation/dependency environment for one project.

**sideload**
旁加载
Installing an add-in directly for development rather than through the public store.

**fallback**
备用方案
The alternative used when the preferred solution does not work.

**legacy**
旧版 / 遗留系统
An older technology or application version that remains in use.

---

# 35. One-Sentence Project Summary

The project currently uses **Legacy Outlook as the email-selection interface, AppleScript as the Mac integration bridge, FastAPI as the local communication layer, and Python/Gmail API as the real backend**, with the eventual goal of retrieving the selected email thread, extracting invoice information with AI, and presenting a human-reviewed invoice draft.

```text
Legacy Outlook
    ↓
AppleScript
    ↓
send_outlook_email.py
    ↓
HTTP / JSON
    ↓
FastAPI
    ↓
Python backend
    ↓
Gmail API
    ↓
full thread
    ↓
AI
    ↓
review
    ↓
invoice
```
