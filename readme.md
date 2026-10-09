# Email-to-Invoice Workflow Automation

A Python-based internal workflow for turning selected client email conversations into structured billing inputs for accountant review.

The project is designed around a real operational constraint: the company mailbox is hosted on **Google Workspace Gmail**, while the user works in **Legacy Outlook for Mac**. Outlook is therefore used as the email-selection interface, while Gmail remains the authoritative mailbox source.

## Current Workflow

```text
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
