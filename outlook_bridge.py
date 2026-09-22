from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from fetch_emails import (
    find_gmail_message_by_rfc822_id,
    get_gmail_service,
    get_gmail_thread,
)
from gmail_parser import parse_gmail_thread

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
    print("Internet Message-ID:", email.message_id)
    print("Subject:", email.subject)
    print("Sender:", email.sender_email)
    print("Received:", email.received_at)

    try:
        service = get_gmail_service()
        match = find_gmail_message_by_rfc822_id(
            service,
            email.message_id,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Gmail API error: {exc}",
        ) from exc

    if match is None:
        raise HTTPException(
            status_code=404,
            detail="No matching Gmail message found",
        )

    gmail_message_id = match["id"]
    thread_id = match["threadId"]

    print("\n=== Gmail Match ===")
    print("Gmail message ID:", gmail_message_id)
    print("Gmail thread ID:", thread_id)
    print("Match status: SUCCESS")

    try:
        thread = get_gmail_thread(
            service,
            thread_id,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Gmail thread retrieval error: {exc}",
        ) from exc

    thread_message_count = len(thread.get("messages", []))
    print("Messages in thread:", thread_message_count)

    parsed_thread = parse_gmail_thread(thread)

    print("\n=== Parsed Gmail Thread ===")

    for index, message in enumerate(
        parsed_thread["messages"],
        start=1,
    ):
        print(f"\n--- Message {index} ---")
        print("From:", message["from"])
        print("Date:", message["date"])
        print("Subject:", message["subject"])
        print("Body:", message["body_text"][:500])

    return {
        "ok": True,
        "match_status": "SUCCESS",
        "gmail_message_id": gmail_message_id,
        "thread_id": thread_id,
        "thread_message_count": thread_message_count,
        "parsed_message_count": len(parsed_thread["messages"]),
    }
