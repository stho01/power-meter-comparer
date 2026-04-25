#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  printf "Error: python3 is not installed or not in PATH.\n" >&2
  exit 1
fi

if [[ ! -f "requirements.txt" ]]; then
  printf "Error: requirements.txt not found in %s\n" "$SCRIPT_DIR" >&2
  exit 1
fi

if [[ ! -d ".venv" ]]; then
  printf "[setup] Creating virtual environment...\n"
  python3 -m venv .venv

  printf "[setup] Upgrading pip...\n"
  .venv/bin/python -m pip install --upgrade pip

  printf "[setup] Installing dependencies...\n"
  .venv/bin/pip install -r requirements.txt
fi

printf "[run] Launching PMCompare UI...\n"
exec .venv/bin/python pm_compare.py --ui
