# Earlier interfaces and manual probes

Daily users should open the root `Launch.cmd` (Windows) or `Launch.command` (Mac).
These files are retained for development and reference, and are not started by Launch.

- `app.py`: earlier Streamlit interface. From the project root: `python -m streamlit run legacy/app.py`.
- `outlook_bridge.py`: earlier local HTTP bridge. From the project root: `python -m uvicorn legacy.outlook_bridge:app --host 127.0.0.1`.
- `send_outlook_email.py`: manual bridge client; sends its arguments to that local HTTP bridge, not an email recipient.
- `inspect_outlook_selection.py`, `inspect_outlook_to_gmail.py`, `inspect_outlook_selection.applescript`: manual integration probes.
  Python probes can run as `python -m legacy.inspect_outlook_selection` from the project root. They may print selected mail content;
  use synthetic messages when debugging. They are separate from the automated suite under `tests/`.

Shared Gmail access and parsing now live in `eml_core/`; the current user interface lives in `eml_ui/`.
