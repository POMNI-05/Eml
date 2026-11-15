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
    try:
        service = get_gmail_service()
        match = find_gmail_message_by_rfc822_id(
            service,
            email.message_id,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=409,
            detail="Gmail authorization or message matching needs attention. Check the local workspace connection.",
        ) from None
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Gmail could not be queried. Check the local workspace connection.",
        ) from None

    if match is None:
        raise HTTPException(
            status_code=404,
            detail="No matching Gmail message found",
        )

    gmail_message_id = match["id"]
    thread_id = match["threadId"]

    try:
        thread = get_gmail_thread(
            service,
            thread_id,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="The matching Gmail thread could not be retrieved.",
        ) from None

    thread_message_count = len(thread.get("messages", []))
    parsed_thread = parse_gmail_thread(thread)

    return {
        "ok": True,
        "match_status": "SUCCESS",
        "gmail_message_id": gmail_message_id,
        "thread_id": thread_id,
        "thread_message_count": thread_message_count,
        "parsed_message_count": len(parsed_thread["messages"]),
    }
