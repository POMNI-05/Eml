# Email-to-Invoice Workflow Automation

A Python-based internal workflow for turning selected client email conversations into structured billing inputs for accountant review.

The project is designed around a real operational constraint: the company mailbox is hosted on **Google Workspace Gmail**, while the user works in **Legacy Outlook for Mac**. Outlook is therefore used as the email-selection interface, while Gmail remains the authoritative mailbox source.

## Current Workflow

~~~text
Legacy Outlook
    ↓
AppleScript
    ↓
Python / FastAPI bridge
    ↓
Internet Message-ID
    ↓
Gmail API
    ↓
Full Gmail thread
    ↓
Parse and normalise email content
    ↓
Client / thread matching
    ↓
Streamlit review and selection
~~~

## Client context workspace

The optional workspace adds reusable selection and client-profile modules.
It shares the existing read-only Gmail OAuth login. Profiles are saved locally
in an ignored SQLite database.

From the repository directory, with Python 3.11 or later:

~~~bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
streamlit run client_workspace.py
~~~

Use the existing local credentials.json. The first explicit Gmail action starts
the existing OAuth flow if a valid token.json is unavailable.

1. Create a client group, or import an existing clients.json.
2. Load and choose Gmail labels; alternatively use Outlook-selected messages
   or paste Internet Message-IDs.
3. Fetch and preview the exact scope. Dates and nested labels are optional.
4. Exclude irrelevant messages, then request suggested client details.
5. Confirm or reject suggestions; manually enter missing business background.
6. Export confirmed clients in the format understood by the original app.py.

The baseline extractor suggests contacts from headers and details from explicit
Company:, Industry:, Business:, and Agreed services: lines. It does not perform
broad semantic analysis or determine completed billable work. No commercial
model API is called. A local-model extractor can implement the same protocol.

| File | Responsibility |
| --- | --- |
| eml_core/mailbox.py | Exact label/message/conversation selection, pagination, union/deduplication, Sydney dates, MIME text |
| eml_core/profiles.py | Evidence-backed suggestions, review, persistence, incremental extraction, legacy import/export |
| outlook_adapter.py | Original single-message adapter and added multi-message adapter |
| outlook_trigger_multi.applescript | Read selected Internet Message-IDs in scriptable Mac Outlook |
| helpers/inspect_outlook_dictionary.py | Inspect folder terms in the actual installed scripting dictionary |
| client_workspace.py | Optional Streamlit workspace using the shared modules |

**Scope:** Gmail labels are supported directly. Outlook-local and Smart Folders
are not automatically mapped to Gmail labels. The added AppleScript must be
tested on the actual Outlook Mac. This is not an Office.js add-in or a completed
billing-report generator.

## Offline demo and tests

~~~bash
python -m eml_core.demo
python -m unittest discover -s tests -v
~~~

Core tests use the standard library and mocked Gmail responses. UI integration
tests run when Streamlit is installed; they do not contact Gmail or Outlook.
See [中文设计说明与复用示例](docs/client_context.md).

The original app.py still provides Gmail search, conversation review and
TXT/JSON export. The original FastAPI bridge currently returns metadata.
The files in invoice/ remain placeholders; service-activity extraction,
approved billing items and Word reports are future work.
