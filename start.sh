#!/usr/bin/env sh
set -eu
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR"
if [ ! -x ".venv/bin/python" ]; then
  if command -v python3 >/dev/null 2>&1; then python3 -m venv .venv; else python -m venv .venv; fi
fi
".venv/bin/python" -m pip install -r requirements.txt
exec ".venv/bin/python" -m reflex run
