"""Start the existing workspace on this computer; no remote host or auto-update.

Use .venv/bin/python helpers/launch_local.py --help for options.
"""

import argparse
import importlib.util
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import threading
from urllib.request import ProxyHandler, build_opener
import webbrowser

ROOT = Path(__file__).resolve().parents[1]


def default_data_directory():
    if os.environ.get("EML_DATA_DIR"):
        return Path(os.environ["EML_DATA_DIR"]).expanduser().resolve()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Eml"
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Eml"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "eml"


def runtime_environment(directory):
    directory = Path(directory).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        directory.chmod(0o700)
    env = os.environ.copy()
    env.setdefault("EML_AUTH_DIR", str(directory / "auth"))
    env.setdefault("EML_PROFILE_DB", str(directory / "client_profiles.sqlite3"))
    return env


def migrate_project_data(env):
    """Explicit first-use COPY; never replace an existing destination."""
    copies = [(ROOT / name, Path(env["EML_AUTH_DIR"]) / name) for name in ("credentials.json", "token.json")]
    source_db = ROOT / "data" / "client_profiles.sqlite3"
    target_db = Path(env["EML_PROFILE_DB"])
    plan = [(source, target) for source, target in copies if source.is_file()]
    if source_db.is_file():
        plan.append((source_db, target_db))
    if any(target.exists() and source.resolve() != target.resolve() for source, target in plan):
        raise ValueError("Migration destination already contains data. No files were copied; use the existing data or a new directory.")
    for source, target in plan:
        if source.resolve() == target.resolve():
            continue
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if source == source_db:
            with sqlite3.connect(source) as original, sqlite3.connect(target) as destination:
                original.backup(destination)
        else:
            with target.open("xb") as stream:
                stream.write(source.read_bytes())
        if os.name != "nt":
            target.chmod(0o600)


def launch_command(port):
    if not 1024 <= port <= 65535:
        raise ValueError("Choose a local port from 1024 to 65535.")
    return [
        sys.executable, "-m", "streamlit", "run", str(ROOT / "client_workspace.py"),
        "--server.address=127.0.0.1", f"--server.port={port}", "--server.headless=true",
        "--browser.gatherUsageStats=false", "--server.enableXsrfProtection=true",
    ]


def _open_when_ready(port, stopped):
    # Headless suppresses Streamlit's first-run email prompt. Open the browser
    # ourselves only after the local server is ready. Never use an HTTP proxy.
    opener = build_opener(ProxyHandler({}))
    for _ in range(80):
        if stopped.is_set():
            return
        try:
            with opener.open(f"http://127.0.0.1:{port}/_stcore/health", timeout=0.5) as response:
                if response.read(32) == b"ok" and not stopped.is_set():
                    webbrowser.open(f"http://127.0.0.1:{port}")
                    return
        except OSError:
            pass
        if stopped.wait(0.25):
            return


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=default_data_directory())
    parser.add_argument("--port", type=int, default=8501)
    parser.add_argument("--migrate-from-project", action="store_true")
    args = parser.parse_args()
    if not importlib.util.find_spec("streamlit"):
        parser.error("Run Setup.command or Setup.cmd once before launching.")
    if os.name != "nt":
        os.umask(0o077)
    try:
        command = launch_command(args.port)
        env = runtime_environment(args.data_dir)
        if args.migrate_from_project:
            migrate_project_data(env)
        with socket.socket() as check:
            check.bind(("127.0.0.1", args.port))
    except (ValueError, OSError) as exc:
        parser.error(f"{exc} If the app is already running, use its window; otherwise choose --port 8502.")
    print(f"Local address: http://127.0.0.1:{args.port}", flush=True)
    print(f"Local client database: {env['EML_PROFILE_DB']}", flush=True)
    print("Keep this window open while using Eml. Ctrl+C stops the local app.", flush=True)
    stopped = threading.Event()
    threading.Thread(target=_open_when_ready, args=(args.port, stopped), daemon=True).start()
    try:
        return subprocess.call(command, cwd=ROOT, env=env)
    except KeyboardInterrupt:
        return 0
    finally:
        stopped.set()


if __name__ == "__main__":
    raise SystemExit(main())
