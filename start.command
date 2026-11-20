#!/usr/bin/env bash
cd "$(dirname "$0")" || exit 1
PY=$(command -v python3 || command -v python)
[ -z "$PY" ] && { echo "Python 3.8+ not found: https://www.python.org/downloads/"; read -r -p "Enter to close"; exit 1; }
exec "$PY" server.py
