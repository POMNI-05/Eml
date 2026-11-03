"""Local Gmail desktop OAuth files shared by both Eml entry points."""

from __future__ import annotations

import json
import logging
import os
import socket
import tempfile
from pathlib import Path

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOGGER = logging.getLogger(__name__)


class CredentialError(ValueError):
    pass


def _dns_failure(error):
    pending, seen = [error], set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, socket.gaierror):
            return True
        pending.extend(related for related in (
            getattr(current, "__cause__", None), getattr(current, "__context__", None),
            getattr(current, "reason", None), *getattr(current, "args", ()),
        ) if isinstance(related, BaseException))
    return False


def _dns_error_message():
    return (
        "Eml cannot resolve Google's server address (DNS lookup failed). "
        "Browser approval may have finished, but Eml could not obtain a Gmail token. "
        "Check the network/DNS on the computer running Eml, then click Connect Gmail again."
    )


def validate_credentials(content: bytes) -> dict:
    if len(content) > 100_000:
        raise CredentialError("The credentials file is too large.")
    try:
        data = json.loads(content.decode("utf-8-sig"))
    except (UnicodeError, ValueError) as exc:
        raise CredentialError("Upload the JSON downloaded from Google Cloud.") from exc
    if not isinstance(data, dict) or not isinstance(data.get("installed"), dict):
        raise CredentialError("Create a Desktop app OAuth client, not a web client or service account.")
    config = data["installed"]
    if not all(isinstance(config.get(k), str) and config[k].strip()
               for k in ("client_id", "client_secret", "auth_uri", "token_uri")):
        raise CredentialError("The Desktop app credentials are missing required fields.")
    if not config["client_id"].endswith(".apps.googleusercontent.com"):
        raise CredentialError("This does not look like a Google OAuth client ID.")
    if config["auth_uri"] not in {
        "https://accounts.google.com/o/oauth2/auth",
        "https://accounts.google.com/o/oauth2/v2/auth",
    } or config["token_uri"] != "https://oauth2.googleapis.com/token":
        raise CredentialError("The credentials must use Google's OAuth endpoints.")
    return data


def _save_private(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".eml-oauth-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as target:
            json.dump(data, target, ensure_ascii=False)
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class GmailAuth:
    def __init__(self, directory: str | Path | None = None):
        self.directory = Path(directory or os.environ.get("EML_AUTH_DIR", PROJECT_ROOT))
        self.credentials_path = self.directory / "credentials.json"
        self.token_path = self.directory / "token.json"

    def status(self) -> dict:
        # Return presence only: never send secrets to the UI, logs, or exports.
        return {"credentials_present": self.credentials_path.is_file(),
                "authorization_present": self.token_path.is_file()}

    def save_credentials(self, content: bytes) -> bool:
        data = validate_credentials(content)
        new = data["installed"]
        changed = True
        if self.credentials_path.exists():
            try:
                old = json.loads(self.credentials_path.read_text())["installed"]
                changed = any(old.get(k) != new.get(k) for k in ("client_id", "client_secret"))
            except (ValueError, KeyError, TypeError):
                pass
        _save_private(self.credentials_path, data)
        if changed:
            self.token_path.unlink(missing_ok=True)
        return changed

    def disconnect(self):
        """Forget local authorization; does not revoke consent at Google."""
        self.token_path.unlink(missing_ok=True)

    def get_service(self, *, on_authorization_url=None):
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow, WSGITimeoutError
        from googleapiclient.discovery import build

        credentials = None
        if self.token_path.exists():
            try:
                credentials = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)
            except (ValueError, KeyError) as exc:
                raise CredentialError("Saved authorization is unreadable. Disconnect and sign in again.") from exc
        if not credentials or not credentials.valid:
            if credentials and credentials.expired and credentials.refresh_token:
                try:
                    credentials.refresh(Request())
                except Exception as exc:
                    if _dns_failure(exc):
                        LOGGER.warning("Gmail authorization refresh failed (dns_resolution_failed).")
                        raise CredentialError(_dns_error_message()) from exc
                    LOGGER.warning("Gmail authorization refresh failed (%s).", type(exc).__name__)
                    raise CredentialError("Google authorization could not refresh. Disconnect and sign in again.") from exc
            else:
                if not self.credentials_path.exists():
                    raise CredentialError("Upload Google Desktop app credentials in Gmail setup first.")
                validate_credentials(self.credentials_path.read_bytes())
                flow_class = InstalledAppFlow
                if on_authorization_url is not None:
                    class LinkedInstalledAppFlow(InstalledAppFlow):
                        def authorization_url(self, **kwargs):
                            url, state = super().authorization_url(**kwargs)
                            on_authorization_url(url)
                            return url, state
                    flow_class = LinkedInstalledAppFlow
                flow = flow_class.from_client_secrets_file(str(self.credentials_path), SCOPES)
                try:
                    credentials = flow.run_local_server(
                        host="localhost", bind_addr="127.0.0.1", port=0,
                        open_browser=on_authorization_url is None,
                        authorization_prompt_message=None if on_authorization_url is not None else "Open this URL to sign in: {url}",
                        success_message="Google's response was received. Return to Eml to check whether Gmail connected. You can close this tab.",
                        timeout_seconds=180,
                    )
                except WSGITimeoutError as exc:
                    LOGGER.warning("Gmail sign-in timed out waiting for the local Google callback.")
                    raise CredentialError(
                        "Google sign-in timed out. Click Connect Gmail again, then Continue to Google sign-in. "
                        "Finish in the new tab within three minutes and leave Eml open."
                    ) from exc
                except Exception as exc:
                    if _dns_failure(exc):
                        LOGGER.warning("Gmail sign-in failed (dns_resolution_failed).")
                        raise CredentialError(_dns_error_message()) from exc
                    LOGGER.warning("Gmail sign-in failed (%s).", type(exc).__name__)
                    raise CredentialError(
                        "Google sign-in did not finish. Retry and check the Gmail setup guide."
                    ) from exc
            _save_private(self.token_path, json.loads(credentials.to_json()))
        return build("gmail", "v1", credentials=credentials)
