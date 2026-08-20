#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR"

if command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON=python
else
  echo "Error: Python 3.11 or newer is required." >&2
  exit 1
fi

if [ ! -x ".venv/bin/python" ]; then
  echo "Creating virtual environment..."
  if ! "$PYTHON" -m venv ".venv"; then
    echo "Error: Python could not create the virtual environment." >&2
    echo "On Ubuntu/Debian, install it with: sudo apt install python3-venv" >&2
    exit 1
  fi
fi

if ! ".venv/bin/python" -m pip --version >/dev/null 2>&1; then
  echo "Error: .venv is incomplete because it does not contain pip." >&2
  echo "On Ubuntu/Debian, run: sudo apt install python3-venv" >&2
  echo "Then remove .venv and run ./start.sh again." >&2
  exit 1
fi

".venv/bin/python" -m pip install -r "requirements.txt"
exec ".venv/bin/python" -m streamlit run "app.py" "$@"
