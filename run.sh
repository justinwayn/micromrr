#!/bin/bash
# MicroMRR launcher — creates venv on first run, then starts the server.
set -e
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo "Creating virtualenv..."
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi
PORT="${MICROMRR_PORT:-8787}"
echo "MicroMRR on http://127.0.0.1:$PORT/  (mode: ${MICROMRR_MODE:-demo})"
exec .venv/bin/uvicorn main:app --host 127.0.0.1 --port "$PORT"
