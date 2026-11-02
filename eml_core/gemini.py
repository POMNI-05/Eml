"""Small optional Gemini REST adapter; no SDK, background calls or key file."""

import json
import os
import re
import socket
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from pydantic import ValidationError

from .ai import ModelError


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class GeminiClient:
    provider = "gemini"

    def __init__(self, model: str, api_key: str = "", *, timeout=180):
        if not re.fullmatch(r"gemini-[A-Za-z0-9._-]+", model):
            raise ModelError("Enter a Gemini model ID available to your project, without models/.")
        self.model = model
        self._api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        if not self._api_key or any(ch.isspace() for ch in self._api_key):
            raise ModelError("Enter a Gemini API key or set GEMINI_API_KEY locally.")
        self.timeout = timeout

    def generate(self, schema, system, payload):
        body = json.dumps({
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": json.dumps(payload, ensure_ascii=False)}]}],
            "generationConfig": {
                "temperature": 0, "maxOutputTokens": 8192,
                "responseMimeType": "application/json", "responseJsonSchema": schema.model_json_schema(),
            },
        }, ensure_ascii=False).encode()
        if len(body) > 1_000_000:
            raise ModelError("The outgoing request exceeds 1 MB. Select fewer emails/documents; nothing was sent.")
        request = Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
            data=body, headers={"Content-Type": "application/json", "x-goog-api-key": self._api_key},
            method="POST",
        )
        try:
            # Fixed HTTPS endpoint; don't forward keys on redirects or through
            # an accidentally configured environment proxy. No automatic retries.
            with build_opener(ProxyHandler({}), _NoRedirect()).open(request, timeout=self.timeout) as response:
                data = response.read(4_000_001)
            if len(data) > 4_000_000:
                raise ModelError("Gemini returned an oversized response.")
            result = json.loads(data)
            candidate = result["candidates"][0]
            if candidate.get("finishReason") != "STOP":
                raise ModelError("Gemini did not finish a complete answer. No draft was saved.")
            text = "".join(part.get("text", "") for part in candidate["content"]["parts"] if not part.get("thought"))
            return schema.model_validate_json(text)
        except HTTPError as exc:
            # Provider response bodies may repeat the input or authentication
            # material. Report the status only; don't log the request.
            raise ModelError(f"Gemini returned HTTP {exc.code}. Check the model, billing, key and quota.") from None
        except (URLError, TimeoutError, socket.timeout):
            raise ModelError("Gemini could not be reached. Check the connection; the request was not retried.") from None
        except (KeyError, IndexError, TypeError, ValueError, ValidationError) as exc:
            if isinstance(exc, ModelError):
                raise
            raise ModelError("Gemini returned blocked, incomplete or invalid JSON. No draft was saved.") from None
