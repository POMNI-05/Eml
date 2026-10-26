# Eml · Email-to-Work-Draft Assistant

A Python-based internal workspace for turning selected client correspondence into
source-backed professional work drafts. Invoice preparation is the first use case:
identify proposed work activities, review their evidence, and export an editable
work record for preparing invoice descriptions.

The mailbox is hosted on **Google Workspace Gmail**, which remains the
authoritative email source. The primary workflow runs in the web workspace.
**Legacy Outlook for Mac** selection is an optional alternative entry point.

## Current Workflow

~~~text
Web workspace: client + optional dates + relevant email selection
    ↓
Gmail API
    ↓
Exact selected messages + reusable client background
    ↓
Structured evidence package
    ↓
Local AI work-record draft with source quotations and open questions
    ↓
Human review, corrections, and Word / JSON export
~~~

The Streamlit workspace calls shared Python services directly. The existing
FastAPI bridge remains available for Outlook integration.

## Run the workspace

The workspace shares the existing read-only Gmail OAuth login. Client profiles,
background documents and draft snapshots are saved locally in an ignored SQLite
database.

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

1. Create or choose a client group, or import an existing clients.json.
2. Add or update client background when needed. Review suggested profile details
   before confirming them; a complete profile is not required to select emails.
3. Search using confirmed client identities or additional terms, or choose Gmail
   labels. Optionally set dates, then fetch, preview and exclude irrelevant mail.
4. In Generate draft, choose the relevant background documents. Download the AI
   evidence package, or use a local Ollama model to generate a work-record draft.
5. Check the quoted emails, correct descriptions and activity status, and exclude
   unsupported items. Save a reviewed snapshot and export Word or JSON.

The structured evidence package contains the client profile, selected documents,
selected email content and source IDs, and selection scope. The AI proposes work
activities and gaps from that evidence; a request for work does not establish
completion. Hours and fees are entered separately. Other professional document
types and email attachment analysis are future extensions.

Outlook-selected messages and pasted Internet Message-IDs are also supported.
Confirmed profiles can be exported for use with the original app.py.

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
| client_workspace.py | Primary Streamlit workspace using the shared modules |
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
