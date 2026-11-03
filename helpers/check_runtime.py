"""Read-only Eml startup diagnostics; never refresh tokens or read mailbox data."""

import argparse
from contextlib import closing
from importlib import metadata
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener

ROOT = Path(__file__).resolve().parents[1]
GOOGLE_HOSTS = ("oauth2.googleapis.com", "gmail.googleapis.com")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def dns_check(hostname):
    try:
        response = subprocess.run(
            [sys.executable, "-c", "import socket,sys; socket.getaddrinfo(sys.argv[1],443,type=socket.SOCK_STREAM)", hostname],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5,
        )
    except subprocess.TimeoutExpired:
        return "error", "System DNS lookup exceeded five seconds."
    except OSError:
        return "error", "Could not start the system DNS check."
    if response.returncode:
        return "error", "System DNS lookup failed; compare with this command in your normal Mac Terminal."
    return "ok", "System DNS lookup succeeded."


def https_check():
    try:
        with build_opener(_NoRedirect()).open("https://oauth2.googleapis.com/token", timeout=5) as response:
            status = response.status
    except HTTPError as error:
        status = error.code
    except (URLError, OSError, ValueError):
        return "error", "Google HTTPS failed; certificate verification remains enabled. No credentials were sent."
    if status >= 500:
        return "warning", f"Google was reachable over verified HTTPS but returned HTTP {status}."
    return "ok", f"Google was reachable over verified HTTPS (HTTP {status}); no credentials were sent."


def workspace_check(port):
    try:
        with build_opener(ProxyHandler({}), _NoRedirect()).open(
            f"http://127.0.0.1:{port}/_stcore/health", timeout=2,
        ) as response:
            if response.read(32) == b"ok":
                return "ok", "A Streamlit server answers on the selected local port; this does not verify Gmail access."
    except (URLError, OSError, ValueError):
        pass
    return "warning", "No healthy Streamlit server was found on the selected local port."


def diagnose(*, auth_directory=None, database=None, port=8503, network=True):
    if not 1024 <= port <= 65535:
        raise ValueError("Choose a local port from 1024 to 65535.")
    auth_directory = Path(auth_directory or os.environ.get("EML_AUTH_DIR") or ROOT).expanduser().resolve()
    database = Path(database or os.environ.get("EML_PROFILE_DB") or ROOT / "data/client_profiles.sqlite3").expanduser().resolve()
    checks = []

    def record(name, status, detail):
        checks.append({"name": name, "status": status, "detail": detail})

    if os.environ.get("CODEX_SANDBOX_NETWORK_DISABLED") == "1":
        record("execution_context", "warning", "Executor network-disabled marker is present. Use normal Mac Terminal for app hosting; removing a marker does not remove sandbox restrictions.")
    else:
        record("execution_context", "ok", "No executor network-disabled marker was detected; DNS and HTTPS still need verification.")
    for package in ("streamlit", "google-auth", "google-auth-oauthlib", "google-api-python-client"):
        try:
            record(package, "ok", f"Installed version: {metadata.version(package)}")
        except metadata.PackageNotFoundError:
            record(package, "error", "Required package is missing from this Python environment.")
    configuration = None
    credentials_path = auth_directory / "credentials.json"
    if credentials_path.is_file():
        try:
            configuration = json.loads(credentials_path.read_text())
            installed = configuration.get("installed", {})
            if not isinstance(installed, dict) or not all(
                isinstance(installed.get(name), str) and installed[name].strip()
                for name in ("client_id", "client_secret", "auth_uri", "token_uri")
            ) or installed["token_uri"] != "https://oauth2.googleapis.com/token" or installed["auth_uri"] not in {
                "https://accounts.google.com/o/oauth2/auth", "https://accounts.google.com/o/oauth2/v2/auth",
            }:
                raise ValueError("Invalid Desktop OAuth configuration")
            record("oauth_configuration", "ok", "Desktop OAuth configuration is readable and uses Google endpoints; secrets are not displayed.")
        except (OSError, ValueError, AttributeError):
            configuration = None
            record("oauth_configuration", "error", "Desktop OAuth configuration is unreadable or invalid; file contents were not logged.")
    else:
        record("oauth_configuration", "warning", "No Desktop OAuth configuration was found in the selected auth directory.")
    token_path = auth_directory / "token.json"
    if token_path.is_file():
        try:
            token = json.loads(token_path.read_text())
            if not isinstance(token, dict):
                raise ValueError("Invalid saved authorization")
            if configuration and token.get("client_id") != configuration["installed"]["client_id"]:
                record("saved_authorization", "error", "Saved authorization belongs to a different OAuth app.")
            elif token.get("refresh_token"):
                record("saved_authorization", "ok", "A refresh token is saved; its validity was not tested or changed.")
            else:
                record("saved_authorization", "warning", "No refresh token is saved; unattended reconnection may require Google approval.")
            if os.name != "nt" and token_path.stat().st_mode & 0o077:
                record("token_permissions", "warning", "Saved authorization is accessible beyond the file owner; review its permissions.")
        except (OSError, ValueError):
            record("saved_authorization", "error", "Saved authorization could not be inspected; file contents were not logged.")
    else:
        record("saved_authorization", "warning", "No saved authorization exists; sign in interactively once before unattended use.")
    if database.is_file():
        try:
            with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=2)) as connection:
                valid = connection.execute("PRAGMA quick_check").fetchone() == ("ok",)
            record("profile_database", "ok" if valid else "error", "Read-only SQLite integrity check passed." if valid else "SQLite reported an integrity problem; restore only from a verified backup.")
        except sqlite3.Error:
            record("profile_database", "error", "The profile database could not be checked read-only; no database was created or modified.")
    else:
        record("profile_database", "warning", "No profile database exists at the selected path; check the data directory before launching.")
    record("local_workspace", *workspace_check(port))
    if network:
        dns_ok = True
        for hostname in GOOGLE_HOSTS:
            status, detail = dns_check(hostname)
            record("dns:" + hostname, status, detail)
            dns_ok = dns_ok and status == "ok"
        if dns_ok:
            record("google_https", *https_check())
        else:
            record("google_https", "skipped", "DNS must work first; no alternate resolver, hardcoded Google IP, or certificate bypass was used.")
    else:
        record("google_network", "skipped", "External DNS and HTTPS checks were disabled.")
    return {"python": sys.version.split()[0], "auth_directory": str(auth_directory), "database": str(database), "port": port, "checks": checks}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--auth-dir", type=Path)
    parser.add_argument("--database", type=Path)
    parser.add_argument("--port", type=int, default=8503)
    parser.add_argument("--offline", action="store_true", help="Skip external Google DNS/HTTPS checks; still check the local app.")
    args = parser.parse_args(argv)
    try:
        report = diagnose(auth_directory=args.auth_dir, database=args.database, port=args.port, network=not args.offline)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return int(any(check["status"] == "error" for check in report["checks"]))


if __name__ == "__main__":
    raise SystemExit(main())
