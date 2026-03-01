#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

ENV_FILE=".env"
ENV_EXAMPLE_FILE=".env.example"
PYTHON_BIN="./venv/bin/python"

if [[ ! -f "$ENV_FILE" ]]; then
  if [[ -f "$ENV_EXAMPLE_FILE" ]]; then
    cp "$ENV_EXAMPLE_FILE" "$ENV_FILE"
    echo "Created .env from .env.example"
  else
    touch "$ENV_FILE"
    echo "Created empty .env"
  fi
fi

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Virtual environment not found at ./venv."
  echo "Run:"
  echo "  python -m venv venv"
  echo "  source venv/bin/activate"
  echo "  pip install -r requirements.txt"
  exit 1
fi

set_env_var() {
  local key="$1"
  local value="$2"
  local tmp_file
  tmp_file="$(mktemp)"

  awk -v key="$key" -v value="$value" '
    BEGIN { updated = 0 }
    $0 ~ ("^" key "=") {
      print key "=" value
      updated = 1
      next
    }
    { print }
    END {
      if (!updated) {
        print key "=" value
      }
    }
  ' "$ENV_FILE" > "$tmp_file"

  mv "$tmp_file" "$ENV_FILE"
}

read_env_var() {
  local key="$1"
  local val
  val="$(grep -E "^${key}=" "$ENV_FILE" | head -n1 | cut -d'=' -f2- || true)"
  echo "${val}"
}

is_yes() {
  case "$1" in
    [Yy]|[Yy][Ee][Ss]) return 0 ;;
    *) return 1 ;;
  esac
}

echo "Select mode:"
echo "  1) signals (alerts only)"
echo "  2) paper (local paper account)"
echo "  3) robinhood (signal workflow)"
read -r -p "Enter choice [1-3] (default: 1): " mode_choice
mode_choice="${mode_choice:-1}"

case "$mode_choice" in
  1)
    BOT_MODE="signals"
    DEFAULT_SYMBOL="SPY"
    DEFAULT_SYMBOLS="SPY,QQQ,NQ=F,ES=F"
    DEFAULT_MARKET_HOURS="false"
    ;;
  2)
    BOT_MODE="paper"
    DEFAULT_SYMBOL="SPY"
    DEFAULT_SYMBOLS="SPY,QQQ,NQ=F,ES=F"
    DEFAULT_MARKET_HOURS="false"
    ;;
  3)
    BOT_MODE="robinhood"
    DEFAULT_SYMBOL="SPY"
    DEFAULT_SYMBOLS="SPY,QQQ,NQ=F,ES=F"
    DEFAULT_MARKET_HOURS="false"
    ;;
  *)
    echo "Invalid choice: $mode_choice"
    exit 1
    ;;
esac

current_symbol="$(read_env_var "SYMBOL")"
current_symbols="$(read_env_var "SYMBOLS")"
current_active_symbol="$(read_env_var "ACTIVE_SYMBOL")"
current_market_hours="$(read_env_var "REQUIRE_MARKET_HOURS")"
current_interval="$(read_env_var "CHECK_INTERVAL_SECONDS")"

if [[ -z "$current_symbol" ]]; then
  current_symbol="$DEFAULT_SYMBOL"
fi
if [[ -z "$current_symbols" ]]; then
  current_symbols="$DEFAULT_SYMBOLS"
fi
if [[ -z "$current_active_symbol" ]]; then
  current_active_symbol="$DEFAULT_SYMBOL"
fi

read -r -p "Data symbol (ETF/Futures recommended) (default: ${current_symbol:-$DEFAULT_SYMBOL}): " user_symbol
user_symbol="${user_symbol:-${current_symbol:-$DEFAULT_SYMBOL}}"

read -r -p "Scanner symbols (comma-separated, default: ${current_symbols:-$DEFAULT_SYMBOLS}): " user_symbols
user_symbols="${user_symbols:-${current_symbols:-$DEFAULT_SYMBOLS}}"

read -r -p "Active symbol to trade (default: ${current_active_symbol:-$user_symbol}): " user_active_symbol
user_active_symbol="${user_active_symbol:-${current_active_symbol:-$user_symbol}}"

read -r -p "Require market hours? true/false (default: ${current_market_hours:-$DEFAULT_MARKET_HOURS}): " user_market_hours
user_market_hours="${user_market_hours:-${current_market_hours:-$DEFAULT_MARKET_HOURS}}"

read -r -p "Loop interval in seconds (default: ${current_interval:-300}): " user_interval
user_interval="${user_interval:-${current_interval:-300}}"

set_env_var "BOT_MODE" "$BOT_MODE"
set_env_var "SYMBOL" "$user_symbol"
set_env_var "SYMBOLS" "$user_symbols"
set_env_var "ACTIVE_SYMBOL" "$user_active_symbol"
set_env_var "REQUIRE_MARKET_HOURS" "$user_market_hours"
set_env_var "CHECK_INTERVAL_SECONDS" "$user_interval"

if [[ "$BOT_MODE" == "paper" ]]; then
  current_paper_balance="$(read_env_var "PAPER_INITIAL_BALANCE_USD")"
  current_paper_size="$(read_env_var "PAPER_ORDER_SIZE_USD")"
  read -r -p "Paper initial balance USD (default: ${current_paper_balance:-10000}): " paper_balance
  read -r -p "Paper order size USD (default: ${current_paper_size:-250}): " paper_size
  set_env_var "PAPER_INITIAL_BALANCE_USD" "${paper_balance:-${current_paper_balance:-10000}}"
  set_env_var "PAPER_ORDER_SIZE_USD" "${paper_size:-${current_paper_size:-250}}"
fi

current_tg_token="$(read_env_var "TELEGRAM_TOKEN")"
current_tg_chat="$(read_env_var "TELEGRAM_CHAT_ID")"
read -r -p "Telegram token (leave blank to keep existing): " tg_token
read -r -p "Telegram chat id (leave blank to keep existing): " tg_chat
set_env_var "TELEGRAM_TOKEN" "${tg_token:-$current_tg_token}"
set_env_var "TELEGRAM_CHAT_ID" "${tg_chat:-$current_tg_chat}"

read -r -p "Launch dashboard in background on http://localhost:5001 ? [y/N]: " launch_dashboard_choice
if is_yes "${launch_dashboard_choice}"; then
  echo "Starting dashboard in background..."
  "$PYTHON_BIN" dashboard/app.py >/tmp/trading_bot_dashboard.log 2>&1 &
  echo "Dashboard PID: $! (logs: /tmp/trading_bot_dashboard.log)"
fi

read -r -p "Run one cycle only? [y/N]: " run_once_choice
if is_yes "${run_once_choice}"; then
  echo "Starting bot in one-cycle mode..."
  "$PYTHON_BIN" main.py --once
else
  echo "Starting bot..."
  "$PYTHON_BIN" main.py
fi
