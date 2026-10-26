"""Local Gmail desktop OAuth files shared by both Eml entry points."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
PROJECT_ROOT = Path(__file__).resolve().parents[1]


class CredentialError(ValueError):
    pass


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

    def get_service(self):
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
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
                    raise CredentialError("Google authorization could not refresh. Disconnect and sign in again.") from exc
            else:
                if not self.credentials_path.exists():
                    raise CredentialError("Upload Google Desktop app credentials in Gmail setup first.")
                validate_credentials(self.credentials_path.read_bytes())
                flow = InstalledAppFlow.from_client_secrets_file(str(self.credentials_path), SCOPES)
                try:
                    credentials = flow.run_local_server(
                        host="localhost", port=0, open_browser=True, timeout_seconds=180
                    )
                except Exception as exc:
                    raise CredentialError(
                        "Google sign-in did not finish. Retry and check the Gmail setup guide."
                    ) from exc
            _save_private(self.token_path, json.loads(credentials.to_json()))
        return build("gmail", "v1", credentials=credentials)
