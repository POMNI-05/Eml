# Portfolio screenshot checklist

## Reproduce the included captures

The three included PNGs are browser captures of the actual workspace with mocked
Gmail and model dependencies. The demo uses a temporary SQLite database and
fictional correspondence, including an extracted text attachment. Model responses
are scripted and pass through the production evidence validator. They are not a
measurement of model quality. The third screenshot is scrolled to the review area.

From the repository root, after installing `requirements.txt`, start:

```bash
python -m streamlit run helpers/portfolio_demo.py --server.address 127.0.0.1 --server.port 8517 --server.headless true
```

In a second terminal, with Google Chrome installed:

```bash
python -m pip install playwright
python helpers/capture_portfolio.py
```

The script selects October 2026, opens the synthetic client folder, excludes the
newsletter, previews the completed review email and generates a scripted draft.
It fills a fictional reviewer name and checks the review box before capturing the
draft, quotations and export controls. PNGs are saved in `docs/assets/screenshots/`.
Stop Streamlit after the capture. Run this isolated demo separately from any live workspace: its mocks
are process-wide and intended only for one local demonstration session.

Use this checklist to capture the real Eml interface without exposing client,
employee or employer-confidential information. The screenshots should demonstrate
the workflow and its controls, not claim that the synthetic example is real work.

## Prepare one coherent synthetic case

Use the same fictional client and reporting period in all three screenshots so the
sequence reads as one story.

- Client: `Northstar Imports Pty Ltd`
- Contact: `Olivia Chen <olivia.chen@example.com>`
- Firm user: `Reviewer <reviewer@firm.example>`
- Period: `1 October 2026` to `31 October 2026`
- Completed evidence: “Reviewed the October bookkeeping records and supplied the
  reconciliation schedule.”
- Requested-only evidence: “Please prepare the October BAS after the missing
  invoices are supplied.”
- Open question: “Confirm whether the missing invoices were received.”

Use `example.com` or another reserved example domain. Do not alter a real client’s
name while leaving their dates, transactions, addresses or relationships intact.

## Capture order

Save images under `docs/assets/screenshots/` using the filenames below. A 16:10
browser viewport such as 1600 × 1000 works well; keep the same zoom for all images.

### 01 · Client & Scope

Filename: `01-client-scope.png`

Show the fictional client, email source and reporting period together. Avoid open
credential dialogs, local file paths and account identifiers.

README caption:

> Select a client, relevant correspondence and reporting period.

### 02 · Email Review

Filename: `02-email-review.png`

Show the selection table and reading pane. Include at least one selected email and
one excluded or requested-only message so the reviewer’s judgment is visible.

README caption:

> Review and filter source correspondence before generating a draft.

### 03 · Draft & Export

Filename: `03-draft-export.png`

This is the strongest portfolio image. In one frame, show a proposed activity, its
quoted supporting email, editable status or description, reviewer confirmation and
the Word/JSON export actions. If the page is too tall, collapse saved drafts and
cloud configuration before capturing it.

README caption:

> Generate evidence-backed work records for human review and editable export.

If only two screenshots are possible, capture Email Review and Draft & Export.

## Final disclosure check

Before committing or sharing each image, confirm all of the following:

- The case, people, domains, message IDs, document names and email bodies are synthetic.
- No OAuth details, API keys, browser profiles, local paths or notification previews appear.
- No real client facts survive through dates, amounts, addresses, relationships or unusual events.
- The repository, interface and system design are authorised for public portfolio use.
- The README describes a prototype and does not imply production deployment or legal/tax advice.

Public GitHub visibility is not evidence of employer authorisation. Keep the images
out of Git history until that permission and this checklist are both satisfied.
