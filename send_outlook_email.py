# send the email data to the FastAPI server

import json
import sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

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

    try:
        with urlopen(request) as response:
            response_text = response.read().decode("utf-8")
            print(response_text)

    except HTTPError as exc:
        error_body = exc.read().decode("utf-8")
        print(f"HTTP {exc.code}: {exc.reason}")
        print(error_body)
        raise

    except URLError as exc:
        print(f"Connection error: {exc.reason}")
        raise


if __name__ == "__main__":
    main()