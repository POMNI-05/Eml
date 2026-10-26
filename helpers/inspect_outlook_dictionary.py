"""Print actual folder-related terms from the installed Mac Outlook dictionary.

Usage: python helpers/inspect_outlook_dictionary.py
This reads scripting definitions, not mailbox contents. No guessed AppleScript
folder enumeration is executed.
"""

import argparse
import json
import shutil
import subprocess
import xml.etree.ElementTree as ET


def folder_terms(xml_text: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    output = []
    for suite in root.findall(".//suite"):
        for definition in suite:
            kind = definition.tag
            if kind not in {"class", "class-extension", "command", "record-type"}:
                continue
            members = []
            for child in definition:
                if child.tag in {"property", "element", "parameter", "result", "direct-parameter"}:
                    members.append({"kind": child.tag, **child.attrib})
            text = json.dumps([definition.attrib, members], ensure_ascii=False)
            if "folder" in text.casefold():
                output.append({
                    "suite": suite.get("name"), "kind": kind,
                    **definition.attrib, "members": members,
                })
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", default="/Applications/Microsoft Outlook.app")
    args = parser.parse_args()
    sdef = shutil.which("sdef")
    if not sdef:
        parser.exit(1, "sdef is unavailable. Run this helper on the Outlook Mac.\n")
    try:
        result = subprocess.run(
            [sdef, args.app], capture_output=True, text=True, check=True, timeout=30
        )
        terms = folder_terms(result.stdout)
    except (subprocess.SubprocessError, ET.ParseError) as exc:
        parser.exit(1, f"Could not read Outlook scripting definitions: {exc}\n")
    print(json.dumps(terms, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
