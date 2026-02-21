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

echo "Select mode:"
echo "  1) signals (alerts only)"
echo "  2) paper (local paper account)"
echo "  3) binance_testnet (paper-money exchange)"
echo "  4) robinhood (signal workflow)"
read -r -p "Enter choice [1-4] (default: 1): " mode_choice
mode_choice="${mode_choice:-1}"

case "$mode_choice" in
  1)
    BOT_MODE="signals"
    DEFAULT_SYMBOL="NQ=F"
    DEFAULT_MARKET_HOURS="true"
    ;;
  2)
    BOT_MODE="paper"
    DEFAULT_SYMBOL="BTC-USD"
    DEFAULT_MARKET_HOURS="false"
    ;;
  3)
    BOT_MODE="binance_testnet"
    DEFAULT_SYMBOL="BTC-USD"
    DEFAULT_MARKET_HOURS="false"
    ;;
  4)
    BOT_MODE="robinhood"
    DEFAULT_SYMBOL="BTC-USD"
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

read -r -p "Data symbol for signals (default: ${current_symbol:-$DEFAULT_SYMBOL}): " user_symbol
user_symbol="${user_symbol:-${current_symbol:-$DEFAULT_SYMBOL}}"

read -r -p "Scanner symbols (comma-separated, default: ${current_symbols:-$user_symbol}): " user_symbols
user_symbols="${user_symbols:-${current_symbols:-$user_symbol}}"

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
  current_paper_balance="$(read_env_var "PAPER_INITIAL_BALANCE_USDT")"
  current_paper_size="$(read_env_var "PAPER_ORDER_SIZE_USDT")"
  read -r -p "Paper initial balance USDT (default: ${current_paper_balance:-10000}): " paper_balance
  read -r -p "Paper order size USDT (default: ${current_paper_size:-250}): " paper_size
  set_env_var "PAPER_INITIAL_BALANCE_USDT" "${paper_balance:-${current_paper_balance:-10000}}"
  set_env_var "PAPER_ORDER_SIZE_USDT" "${paper_size:-${current_paper_size:-250}}"
fi

if [[ "$BOT_MODE" == "binance_testnet" ]]; then
  if ! "$PYTHON_BIN" - <<'PY' >/dev/null 2>&1
import ccxt
PY
  then
    read -r -p "ccxt is required for Binance mode. Install it now? [Y/n]: " install_ccxt_choice
    if [[ -z "${install_ccxt_choice}" || "${install_ccxt_choice,,}" == "y" || "${install_ccxt_choice,,}" == "yes" ]]; then
      ./venv/bin/pip install ccxt
    else
      echo "Cannot continue in binance_testnet mode without ccxt."
      exit 1
    fi
  fi

  current_binance_symbol="$(read_env_var "BINANCE_SYMBOL")"
  current_binance_size="$(read_env_var "BINANCE_ORDER_SIZE_USDT")"
  current_binance_key="$(read_env_var "BINANCE_API_KEY")"
  current_binance_secret="$(read_env_var "BINANCE_API_SECRET")"

  read -r -p "Binance symbol (default: ${current_binance_symbol:-BTC/USDT}): " binance_symbol
  read -r -p "Binance order size USDT (default: ${current_binance_size:-50}): " binance_size
  read -r -p "Binance API key (leave blank to keep existing): " binance_key
  read -r -p "Binance API secret (leave blank to keep existing): " binance_secret

  set_env_var "BINANCE_SYMBOL" "${binance_symbol:-${current_binance_symbol:-BTC/USDT}}"
  set_env_var "BINANCE_ORDER_SIZE_USDT" "${binance_size:-${current_binance_size:-50}}"
  set_env_var "BINANCE_API_KEY" "${binance_key:-$current_binance_key}"
  set_env_var "BINANCE_API_SECRET" "${binance_secret:-$current_binance_secret}"

  final_key="$(read_env_var "BINANCE_API_KEY")"
  final_secret="$(read_env_var "BINANCE_API_SECRET")"
  if [[ -z "$final_key" || -z "$final_secret" ]]; then
    echo "BINANCE_API_KEY and BINANCE_API_SECRET are required for binance_testnet mode."
    exit 1
  fi
fi

current_tg_token="$(read_env_var "TELEGRAM_TOKEN")"
current_tg_chat="$(read_env_var "TELEGRAM_CHAT_ID")"
read -r -p "Telegram token (leave blank to keep existing): " tg_token
read -r -p "Telegram chat id (leave blank to keep existing): " tg_chat
set_env_var "TELEGRAM_TOKEN" "${tg_token:-$current_tg_token}"
set_env_var "TELEGRAM_CHAT_ID" "${tg_chat:-$current_tg_chat}"

read -r -p "Launch dashboard in background on http://localhost:5001 ? [y/N]: " launch_dashboard_choice
if [[ "${launch_dashboard_choice,,}" == "y" || "${launch_dashboard_choice,,}" == "yes" ]]; then
  echo "Starting dashboard in background..."
  "$PYTHON_BIN" dashboard/app.py >/tmp/trading_bot_dashboard.log 2>&1 &
  echo "Dashboard PID: $! (logs: /tmp/trading_bot_dashboard.log)"
fi

read -r -p "Run one cycle only? [y/N]: " run_once_choice
if [[ "${run_once_choice,,}" == "y" || "${run_once_choice,,}" == "yes" ]]; then
  echo "Starting bot in one-cycle mode..."
  "$PYTHON_BIN" main.py --once
else
  echo "Starting bot..."
  "$PYTHON_BIN" main.py
fi
