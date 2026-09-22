# the code run applescript, to receive metadata and turn it into python data / or json ? ?
## TODO: remember to add this line to add.py, so that the script can be run from the command line:

import subprocess
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
    output = result.stdout.strip()

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