"""One-time per-checkout setup. Launching never installs or updates code."""

from pathlib import Path
import subprocess
import sys
import venv


def main():
    if sys.version_info < (3, 11):
        raise SystemExit("Install Python 3.11 or newer, then run setup again.")
    root = Path(__file__).resolve().parents[1]
    directory = root / ".venv"
    python = directory / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if not python.exists():
        venv.EnvBuilder(with_pip=True).create(directory)
    subprocess.check_call([str(python), "-m", "pip", "install", "-r", str(root / "requirements.txt")])
    print("Setup complete. Launch.command (Mac) or Launch.cmd (Windows) opens Eml on this computer.")


if __name__ == "__main__":
    main()
