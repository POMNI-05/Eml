"""Exercise the legacy HTTP route with synthetic data; never open Gmail OAuth."""
from contextlib import redirect_stdout
import io
import json
import unittest
from unittest.mock import patch

from outlook_bridge import app


class OutlookBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def request(self, payload=None):
        if payload is None:
            payload = dict(message_id="<synthetic@example.test>", subject="private-subject",
                           sender_name="Demo", sender_email="demo@example.test", received_at="2026-11-15")
        events = []
        async def receive():
            return {"type": "http.request", "body": json.dumps(payload).encode(), "more_body": False}
        async def send(event):
            events.append(event)
        await app({"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                   "method": "POST", "scheme": "http", "path": "/outlook/selected-email",
                   "raw_path": b"/outlook/selected-email", "query_string": b"",
                   "headers": [(b"content-type", b"application/json")],
                   "server": ("127.0.0.1", 8000), "client": ("127.0.0.1", 1234)}, receive, send)
        status = next(e["status"] for e in events if e["type"] == "http.response.start")
        body = b"".join(e.get("body", b"") for e in events if e["type"] == "http.response.body")
        return status, json.loads(body)

    async def test_success_does_not_print_correspondence(self):
        output = io.StringIO()
        with patch("outlook_bridge.get_gmail_service"), \
                patch("outlook_bridge.find_gmail_message_by_rfc822_id", return_value={"id": "m1", "threadId": "t1"}), \
                patch("outlook_bridge.get_gmail_thread", return_value={"messages": [{}]}), \
                patch("outlook_bridge.parse_gmail_thread", return_value={"messages": [{"body_text": "private-body"}]}), \
                redirect_stdout(output):
            status, body = await self.request()
        self.assertEqual(status, 200)
        self.assertEqual(body["parsed_message_count"], 1)
        self.assertEqual(output.getvalue(), "")
        self.assertNotIn("private", json.dumps(body))

    async def test_missing_message_is_404(self):
        with patch("outlook_bridge.get_gmail_service"), \
                patch("outlook_bridge.find_gmail_message_by_rfc822_id", return_value=None):
            self.assertEqual((await self.request())[0], 404)

    async def test_connection_errors_are_actionable_without_private_details(self):
        for error, expected in [(RuntimeError("private-token"), 409), (OSError("private-token"), 502)]:
            with self.subTest(error=type(error).__name__), \
                    patch("outlook_bridge.get_gmail_service", side_effect=error):
                status, body = await self.request()
                self.assertEqual(status, expected)
                self.assertNotIn("private-token", json.dumps(body))

    async def test_thread_failure_is_502_without_provider_details(self):
        with patch("outlook_bridge.get_gmail_service"), \
                patch("outlook_bridge.find_gmail_message_by_rfc822_id", return_value={"id": "m1", "threadId": "t1"}), \
                patch("outlook_bridge.get_gmail_thread", side_effect=OSError("private-body")):
            status, body = await self.request()
        self.assertEqual(status, 502)
        self.assertNotIn("private-body", json.dumps(body))

    async def test_invalid_request_is_rejected_before_authorization(self):
        with patch("outlook_bridge.get_gmail_service") as connect:
            self.assertEqual((await self.request({}))[0], 422)
            connect.assert_not_called()
