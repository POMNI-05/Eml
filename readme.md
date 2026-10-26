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

Open Gmail setup to read the credential tutorial, drag in a Google Desktop app
JSON file, and connect Gmail. Existing local credentials.json and token.json
are also reused. See [Gmail setup](docs/gmail_setup.md).

1. Create a client group, or import an existing clients.json.
2. Load and choose Gmail labels; alternatively use Outlook-selected messages
   or paste Internet Message-IDs.
3. Fetch and preview the exact scope. Dates and nested labels are optional.
4. Exclude irrelevant messages, then request suggested client details.
5. Confirm or reject suggestions; manually enter missing business background.
6. Export confirmed clients in the format understood by the original app.py.

The local rule extractor provides simple suggestions without a model. The
integrated Ollama connection can interpret client background documents and
generate structured work-record drafts from chosen email evidence. Documents
support TXT, Markdown, DOCX, and searchable PDF. Confirmed document-derived
contacts, companies and aliases participate in Client search; the full selected
background also accompanies draft generation. See [Local AI setup](docs/ollama_setup.md).

| File | Responsibility |
| --- | --- |
| eml_core/mailbox.py | Exact label/message/conversation selection, pagination, union/deduplication, Sydney dates, MIME text |
| eml_core/profiles.py | Evidence-backed suggestions, review, persistence, incremental extraction, legacy import/export |
| outlook_adapter.py | Original single-message adapter and added multi-message adapter |
| outlook_trigger_multi.applescript | Read selected Internet Message-IDs in scriptable Mac Outlook |
| helpers/inspect_outlook_dictionary.py | Inspect folder terms in the actual installed scripting dictionary |
| client_workspace.py | Optional Streamlit workspace using the shared modules |
| workspace_panels.py | Credential upload, local AI, background documents and draft review panels |
| eml_core/documents.py | Client-scoped source documents, text extraction and quoted locations |
| eml_core/ai.py | Local Ollama structured output and background analysis |
| eml_core/search.py | Search terms and match explanations from confirmed client context |
| invoice/service.py | Scope-validated background-aware work drafts and saved snapshots |
| invoice/renderer.py | Editable Word records with email evidence appendix |

**Scope:** Gmail labels are supported directly. Outlook-local and Smart Folders
are not automatically mapped to Gmail labels. The added AppleScript must be
tested on the actual Outlook Mac. This is not an Office.js add-in or a completed
billing application. It generates reviewable work-record drafts, without
inferring hours or fees.

## Offline demo and tests

~~~bash
python -m eml_core.demo
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
~~~

Tests use mocked Gmail and model responses, including a local HTTP test server.
The document tests use python-docx, pypdf and ReportLab. They do not contact
real Gmail, Outlook or an Ollama model.
See [中文设计说明与复用示例](docs/client_context.md).

The original app.py still provides Gmail search, conversation review and
TXT/JSON export. The original FastAPI bridge currently returns metadata.
Work-record generation, source validation and Word export are connected in the
new workspace. Issuing invoices, fee calculations, attachment/OCR analysis,
multi-document chunk summarisation and a native Office.js add-in are not included.
