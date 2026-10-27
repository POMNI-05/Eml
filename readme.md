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

The opening screen focuses on Gmail sign-in, with the following steps on the
right. If no credentials or saved sign-in exist, upload a Google Desktop app
JSON file once. Existing credentials.json and token.json are reused without
showing the upload form again. See [Gmail setup](docs/gmail_setup.md).

After connecting, Gmail and local AI controls collapse into the green
**Gmail connected** status pill. The full-width workspace shows email sources
and examples on the left, with independent **Period & scope** and
**Client background** cards on the right. Background notes are saved per client
and reused across date ranges. Open the status pill to manage the account or model.

For a personal `@gmail.com` account, follow [Test with your own Gmail](docs/gmail_testing.md).
The first-time upload includes setup help. Start with a few familiar messages; the
workspace starts with the client's Gmail folders, the current month and a
50-message limit. Full folder paths are shown, with subfolders included only
when chosen. Folder choices are saved per client and mailbox using Gmail label
IDs, so a renamed folder can still be recognised.

1. Connect Gmail, then choose a **Client** or use **Client management → Add client**.
   An existing clients.json can also be imported.
2. In **Client & folders**, load folders, choose the client's paths and optional
   subfolders, and click **Open selected folders →** to load mail and advance.
3. In **Review emails**, read correspondence beside the checkbox list, exclude
   irrelevant messages, and click **Use selected emails →** to continue.
4. In **Draft & export**, choose relevant background documents, download an AI
   evidence package or generate a local-model work-record draft.
5. Check the quoted emails beside the draft, correct descriptions and status, and exclude
   unsupported items. Save a reviewed snapshot and export Word or JSON.

Client details and documents are available from the **Client background** card. Client
search, Outlook selection and Internet Message-IDs remain alternative sources.
Client search accepts separate names, email addresses or phrases, with **Match ANY
of those written** or **Match ALL of those written** matching. **Exclusion filters** adds exclusions and subject
prefixes without requiring Gmail query syntax. Saved search entries can be removed;
they are not silently added back. Subject prefixes are checked locally before
counting the message limit.
Saved searches are stored in the local user profile per client and Gmail account.
They are included as client background metadata when preparing a draft, so the
draft records how the correspondence was found without treating the search
criteria as proof that work was performed.
Changing the client, folders, search filters or date scope clears the previous email selection
and returns the workflow to the first step.

The structured evidence package contains the client profile, selected documents,
selected email content and source IDs, and selection scope. The AI proposes work
activities and gaps from that evidence; a request for work does not establish
completion. Hours and fees are entered separately. Other professional document
types are future extensions.

Email attachments are read locally when mail is fetched: searchable PDF, DOCX,
TXT, Markdown, CSV and XLSX. Stage 2 shows extracted text and unread/partial-file
notices in the reading pane. Only attachments belonging to included emails enter
the draft. Citations retain the Gmail message ID, attachment part ID and page,
block or sheet/row location; quotations are checked against that exact source.
Excel formulas are preserved rather than calculated. Files over 20 MB, combined
attachments over 50 MB per fetch, unsupported files and files requiring OCR are
flagged, not silently treated as read. Re-fetch existing email sets to load attachments.

In stage 2, **Sender** groups messages by email address. Choose a sender and use
**Select sender** or **Exclude sender**, or choose **All senders** for **Select all**
and **Exclude all**. Other senders' individual checkbox choices are preserved.

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
| eml_core/folders.py | Client folder preferences isolated by mailbox, retaining Gmail IDs and full paths |
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
new workspace. Issuing invoices, fee calculations, image/scanned-file OCR,
multi-document chunk summarisation and a native Office.js add-in are not included.
