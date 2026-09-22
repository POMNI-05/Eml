from pprint import pprint

from outlook_adapter import get_selected_outlook_email

from fetch_emails import (
    get_gmail_service,
    find_gmail_message_by_rfc822_id,
    get_gmail_thread,
)

from gmail_parser import parse_gmail_thread


def main():
    # Step 1: ask AppleScript which Outlook email is selected
    selected_email = get_selected_outlook_email()

    print("\n=== Outlook Selection ===")
    pprint(selected_email)

    # Step 2: Connect to Gmail API
    service = get_gmail_service()

    # Step 3: Use the Outlook Internet Message-ID to find the exact same message in Gmail
    match = find_gmail_message_by_rfc822_id(
        service,
        selected_email["message_id"],
    )

    if match is None:
        raise RuntimeError(
            "Could not find the selected Outlook email in Gmail."
        )

    print("\n=== Gmail Match ===")
    print("Gmail message ID:", match["id"])
    print("Thread ID:", match["threadId"])

    # Step 4: Fetch the entire Gmail conversation
    thread = get_gmail_thread(
        service,
        match["threadId"],
    )

    print(
        "Raw messages in thread:",
        len(thread.get("messages", [])),
    )

    # Step 5:
    # Convert Gmail's ugly/raw format
    # into your clean internal email format
    parsed_thread = parse_gmail_thread(thread)

    print("\n=== Clean Thread ===")
    print(
        "Parsed messages:",
        len(parsed_thread["messages"]),
    )

    for index, message in enumerate(
        parsed_thread["messages"],
        start=1,
    ):
        print(f"\n--- Message {index} ---")
        print("From:", message.get("from"))
        print("To:", message.get("to"))
        print("Date:", message.get("date"))
        print("Subject:", message.get("subject"))

        body = message.get("body_text", "")
        print("Body preview:", body[:300])


if __name__ == "__main__":
    main()