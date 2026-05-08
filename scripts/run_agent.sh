#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
PYTHON_BIN="${PYTHON_BIN:-$APP_DIR/venv/bin/python}"
AGENT_MODE="${AGENT_MODE:-start}"
LOG_DIR="${LOG_DIR:-$APP_DIR/logs}"
LOG_TO_FILE="${LOG_TO_FILE:-false}"

cd "$APP_DIR"
mkdir -p "$LOG_DIR"

if [[ "$LOG_TO_FILE" == "true" ]]; then
  exec >> "$LOG_DIR/agent.log" 2>> "$LOG_DIR/agent-error.log"
fi

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Python executable not found: $PYTHON_BIN" >&2
  echo "Create venv and install dependencies: python -m venv venv && ./venv/bin/python -m pip install -r requirements.txt" >&2
  exit 1
fi

exec "$PYTHON_BIN" agent.py "$AGENT_MODE"
