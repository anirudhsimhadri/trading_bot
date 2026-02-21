#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if command -v python3 >/dev/null 2>&1; then
  PYTHON_CMD="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_CMD="python"
else
  echo "Python is not installed. Please install Python 3.10+ and try again."
  exit 1
fi

if [[ ! -d "venv" || ! -x "./venv/bin/python" ]]; then
  echo "Creating virtual environment..."
  "$PYTHON_CMD" -m venv venv
fi

echo "Installing dependencies..."
./venv/bin/python -m pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

if [[ ! -f ".env" && -f ".env.example" ]]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

if [[ ! -f "run.sh" ]]; then
  echo "run.sh not found in project root."
  exit 1
fi

chmod +x run.sh

echo "Starting guided launcher..."
exec ./run.sh
