# Trading Bot (Signals + Paper + Binance Testnet)

This bot now includes:
- Refined confluence strategy (trend + momentum + strength + volume filters)
- Risk controls (daily loss cap, trade risk cap, max trades/day, cooldown, loss streak cap)
- Multi-symbol scanner with active-symbol selection
- Backtesting engine (for internal testing)
- Web dashboard for monitoring + symbol switch + backtest visualization

Optional dependency for Binance mode only:
- `ccxt` (install with `./venv/bin/pip install ccxt`)

## One-Time Setup

From project root:

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
cp .env.example .env
chmod +x run.sh install_and_run.sh
```

Or use one-command bootstrap:

```bash
./install_and_run.sh
```

## Quick Start

### Easiest for testing (no external accounts)

```bash
BOT_MODE=paper REQUIRE_MARKET_HOURS=false SYMBOLS=BTC-USD,ETH-USD ACTIVE_SYMBOL=BTC-USD ./venv/bin/python main.py
```

### Start dashboard

```bash
./venv/bin/python dashboard/app.py
```

Open:
- [http://localhost:5001](http://localhost:5001)

## Fiverr Client Experience (Recommended Flow)

Use this exact flow for the easiest buyer experience:

1. Open terminal in project folder.
2. Run:

```bash
./install_and_run.sh
```

3. In prompts:
   - Mode: `paper`
   - Symbols: `BTC-USD,ETH-USD`
   - Active symbol: `BTC-USD`
   - Require market hours: `false`
   - Launch dashboard: `y`
   - Run one cycle only: `y` (first check)

4. Confirm success:
   - You see startup logs and cycle status in terminal.
   - Dashboard opens at [http://localhost:5001](http://localhost:5001).
   - Scanner table and risk panel populate.

5. Start continuous run:

```bash
./run.sh
```

Use the same settings, then select `Run one cycle only: n`.

### What Buyers Can Interact With

- Change active traded symbol from dashboard (`Set Active`).
- Run backtests from dashboard (`Run Backtest`) with custom period/timeframe.
- Monitor paper account, risk controls, and live scanner state.

### Minimal Buyer Setup Promise

- No brokerage connection is required for `paper` mode.
- Telegram is optional.
- Only Python + this folder are required.

## Modes

- `signals`: alerts only
- `paper`: local paper execution (`data/paper_state.json`, `data/paper_trades.csv`)
- `binance_testnet`: paper-money orders via Binance Spot Testnet
- `robinhood`: signal-only workflow

## Multi-Symbol Scanner

Configure symbols in `.env`:

```env
SYMBOLS=BTC-USD,ETH-USD,SPY,NQ=F
ACTIVE_SYMBOL=BTC-USD
```

Behavior:
- Bot scans all symbols each cycle.
- Bot executes trades only for `selected_symbol`.
- `selected_symbol` can be changed from dashboard (`Set Active`).

## Risk Controls

Configured in `.env`:

```env
MAX_DAILY_LOSS_PCT=2
MAX_TRADE_RISK_PCT=1
MAX_TRADES_PER_DAY=6
COOLDOWN_AFTER_LOSS_MINUTES=30
MAX_CONSECUTIVE_LOSSES=3
```

The bot blocks execution when limits are hit.
Risk rationale and references are in:
- `docs/risk_guidelines.md`

For `binance_testnet` mode, install `ccxt` first:

```bash
./venv/bin/pip install ccxt
```

## Backtesting Engine (Internal Use)

Dashboard:
- Use `Run Backtest` button.
- Shows equity curve, drawdown-aware metrics, trade table.

API:

```bash
curl -X POST http://localhost:5001/api/backtest \
  -H "Content-Type: application/json" \
  -d '{"symbol":"BTC-USD","period":"60d","timeframe":"15m"}'
```

## Terminal Output You Should See

On start:

```text
Bot started | mode=paper, symbols=BTC-USD,ETH-USD, selected=BTC-USD, timeframe=15m, period=60d
State file: data/runtime_state.json
```

Each cycle:

```text
[Cycle 14] 2026-02-21T20:00:00+00:00 | scanned=2 | active_signals=1 | selected=BTC-USD
[Cycle 14] No new signal for selected symbol (BTC-USD).
```

Heartbeat:

```text
Heartbeat | cycles=24 | signals=2 | executions=1 | errors=0 | trades_today=1
```

## Dashboard Overview

The dashboard shows:
- Mode, cycles, selected symbol
- Scanner table for all symbols (signal, score, stale data, price)
- Risk block (trades today, realized PnL, cooldown, loss streak)
- Paper account snapshot
- Backtest metrics + equity chart + trade table

## Build Fiverr Zip

```bash
./scripts/build_release.sh
```

Output:
- `release/trading_bot_bundle_<timestamp>.zip`

## Notes

- Backtesting is currently included for your testing phase.
- When ready for Fiverr delivery, you can remove `backtesting/` and dashboard backtest endpoint if desired.
