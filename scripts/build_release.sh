#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
OUTPUT_DIR="$ROOT_DIR/release"
OUTPUT_FILE="$OUTPUT_DIR/trading_bot_bundle_${TIMESTAMP}.zip"

mkdir -p "$OUTPUT_DIR"

zip -r "$OUTPUT_FILE" . \
  -x ".git/*" \
     "venv/*" \
     ".env" \
     "release/*" \
     "data/*" \
     "data_test/*" \
     "__pycache__/*" \
     "*/__pycache__/*" \
     "*.pyc" \
     ".DS_Store" \
     "backup_trading_bot.zip"

echo "Created release bundle: $OUTPUT_FILE"
