# the code run applescript, to receive metadata and turn it into python data / or json ? ?
# KEY RULEEEE: Inside Python, prefer Python-native data; At system boundaries, serialize it.
## TODO: remember to add this line to add.py, so that the script can be run from the command line:

import subprocess
import json
import re
import sys
from pathlib import Path

# in Apple: use an assigned field-separator in email 'ASCII 31 = Unit Separator' 
#   map to "\x1f" in Python, to separate the fields in the output of the AppleScript

FIELD_SEPARATOR = "\x1f"

# aviod hardcoding the path to the AppleScript
#   instead use Path to get the path of the script relative to this file
SCRIPT_PATH = Path(__file__).with_name(
    "outlook_trigger.applescript"
)

class OutlookSelectionError(RuntimeError):
    pass


def get_selected_outlook_email():
    # handshake with the AppleScript to get the selected email's metadata
    result = subprocess.run(
        [
            # Python runs Terminal command：osascript outlook_trigger.applescript
            "osascript",
            str(SCRIPT_PATH),
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        error_message = result.stderr.strip()

        raise OutlookSelectionError(
            error_message or "Could not read selected Outlook email."
        )
    # stdout is the output of the AppleScript (return outputText)
    #   a string with fields separated by FIELD_SEPARATOR
    # strip() also removes ASCII 31, losing an empty trailing folder field.
    output = result.stdout.rstrip("\r\n")

    # after split, py gives a list 
    parts = output.split(FIELD_SEPARATOR)

    if len(parts) != 6:
        raise OutlookSelectionError(
            f"Unexpected AppleScript output: expected 6 fields, "
            f"got {len(parts)}."
        )
    # the = parts are unpacked into variables
    (
        message_id,
        subject,
        sender_name,
        sender_email,
        received_at,
        folder_name,
    ) = parts

    # then returned as a dictionary
    return {
        "message_id": message_id,
        "subject": subject,
        "sender_name": sender_name,
        "sender_email": sender_email,
        "received_at": received_at,
        "folder_name": folder_name or None,
    }


def get_selected_outlook_message_ids():
    """Read multiple selections in Legacy Outlook on Mac.

    Returns Internet Message-IDs, not Outlook or Gmail internal IDs. Resolve
    them with GmailMailbox.select(Selection(internet_message_ids=...)).
    Requires an on-device test against the installed Outlook dictionary.
    """
    if sys.platform == "win32":
        return _windows_selected_message_ids()
    script = Path(__file__).with_name("outlook_trigger_multi.applescript")
    try:
        result = subprocess.run(
            ["osascript", str(script)], capture_output=True, text=True, timeout=60
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise OutlookSelectionError(
            "Could not read Outlook selection. Run on a Mac with scriptable Outlook."
        ) from exc
    if result.returncode:
        raise OutlookSelectionError(
            result.stderr.strip() or "Could not read selected Outlook messages."
        )
    ids = list(dict.fromkeys(line.strip() for line in result.stdout.splitlines() if line.strip()))
    if not ids:
        raise OutlookSelectionError("Please select at least one Outlook email.")
    return ids


def _windows_selected_message_ids():
    """Read selection from an already running Classic Outlook, without pywin32."""
    script = Path(__file__).with_name("helpers") / "outlook_selection_windows.ps1"
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script.read_text(encoding="utf-8")],
            capture_output=True, text=True, encoding="utf-8", timeout=60,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise OutlookSelectionError("Could not read Windows Outlook. Open Classic Outlook, or use Gmail folders/search.") from None
    try:
        payload = json.loads(result.stdout.lstrip("\ufeff"))
    except (ValueError, TypeError):
        raise OutlookSelectionError("Outlook did not return a readable selection. Use Classic Outlook or Gmail folders/search.") from None
    messages = {
        "unavailable": "Open Classic Outlook with the same Windows user and permission level, then select emails. New Outlook is not supported; use Gmail folders/search.",
        "empty": "Select at least one individual email in the Classic Outlook message list.",
        "too_many": "Select at most 500 Outlook emails at once.",
        "not_mail": "The selection includes a non-email item. Select individual emails only.",
        "missing_id": "A selected email has no Internet Message-ID. No partial selection was used; use Gmail folders/search.",
    }
    if not isinstance(payload, dict) or result.returncode or "error" in payload:
        code = payload.get("error") if isinstance(payload, dict) else None
        raise OutlookSelectionError(messages.get(code, "Could not read the Outlook selection. Use Gmail folders/search."))
    ids = payload.get("ids")
    if not isinstance(ids, list) or not 1 <= len(ids) <= 500 or any(
        not isinstance(value, str) or len(value) > 998 or value.startswith("<") != value.endswith(">")
        or not re.fullmatch(r'<?[^\s<>"{}]+@[^\s<>"{}]+>?', value)
        for value in ids
    ):
        raise OutlookSelectionError("Outlook returned invalid message identifiers. No emails were fetched.")
    return list(dict.fromkeys(ids))
