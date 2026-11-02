#!/bin/bash
set -eu
cd -- "$(dirname -- "$0")"
if [ ! -x .venv/bin/python ]; then
  echo 'Run Setup.command once, then open Launch.command again.'
  read -r -p 'Press Enter to close.'
  exit 1
fi
exec .venv/bin/python helpers/launch_local.py
