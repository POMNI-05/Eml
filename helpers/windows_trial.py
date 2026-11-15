"""Isolated Windows trial entry point; never reuse production auth/data overrides."""
import argparse
from datetime import datetime
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def trial_environment(*, demo=False):
    env = os.environ.copy()
    base = Path(env.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Eml-Windows-Test"
    directory = base / ("demo" if demo else "workspace")
    env.update(EML_DATA_DIR=str(directory), EML_AUTH_DIR=str(directory / "auth"),
               EML_PROFILE_DB=str(directory / "client_profiles.sqlite3"), EML_ENABLE_LOCAL_LLM="0")
    # Keys configured for another installation must not silently enter the trial.
    for name in ("GEMINI_API_KEY", "GEMINI_MODEL"):
        env.pop(name, None)
    return env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["launch", "demo", "check", "backup"])
    parser.add_argument("--port", type=int)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("Use Launch.command for the Mac handoff; this entry point is the Windows trial.")
    env = trial_environment(demo=args.action == "demo")
    if args.action == "backup":
        folder = Path(env["EML_DATA_DIR"]).parent / "backups"
        folder.mkdir(parents=True, exist_ok=True)
        output = folder / ("eml-test-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".zip")
        command = [sys.executable, str(ROOT / "helpers/backup_local.py"), "--output", str(output)]
    else:
        port = args.port or (8522 if args.action == "demo" else 8521)
        command = [sys.executable, str(ROOT / "helpers/launch_local.py"), "--port", str(port)]
        if args.action == "demo":
            command.extend(["--entrypoint", "helpers/windows_demo.py"])
        if args.action == "check":
            command.append("--check")
        if args.no_browser:
            command.append("--no-browser")
    print("Windows test data: " + env["EML_DATA_DIR"], flush=True)
    try:
        return subprocess.call(command, cwd=ROOT, env=env)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
