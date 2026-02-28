# Trading Bot (Signals + Paper + Binance Testnet)

This bot now includes:
- Hybrid regime-switching strategy:
  - Trend model in trending markets
  - Mean reversion model in choppy/ranging markets
  - Regime confirmation filter to avoid one-bar regime flips
- Risk controls (daily loss cap, trade risk cap, max trades/day, cooldown, loss streak cap)
- Multi-symbol scanner with active-symbol selection
- Backtesting engine (for internal testing)
- Web dashboard for monitoring + symbol switch + backtest visualization
- Adaptive learning: symbol bias + confluence feature weights are adjusted from realized outcomes (logged in `data/learn_log.csv`).
- Walk-forward preflight gate: execution can be blocked unless out-of-sample validation passes.
- Realistic backtesting assumptions: spread, slippage, order latency, partial fill factor.
- Protective exits: stop loss, take profit, trailing stop, and max-hold controls.
- Stale-data protection + indicator warmup gate to avoid trading on incomplete/low-quality inputs.
- Position-scaling guard (disabled by default) to avoid repeated entries while a position is already open.

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

## Preflight Checklist (Run Before Live Session)

Use this quick check to avoid startup hiccups:

1. Verify dependencies and env file:

```bash
./install_and_run.sh
```

2. Keep first run simple in `.env`:
   - `BOT_MODE=paper`
   - `REQUIRE_MARKET_HOURS=false`
   - `TELEGRAM_TOKEN=` and `TELEGRAM_CHAT_ID=` (leave blank unless you want alerts)
   - Optional for first validation run: `REQUIRE_BACKTEST_PASS=false`

3. Use symbols Yahoo supports reliably (examples):
   - `BTC-USD`, `ETH-USD`, `SPY`, `QQQ`, `NQ=F`

4. Run one cycle smoke test:

```bash
./venv/bin/python main.py --once
```

5. Confirm expected terminal output:
   - `Bot started | ...`
   - `State file: data/runtime_state.json`
   - `[Cycle X] ... scanned=...`

6. If you see `No data found for this date range`:
   - Switch to a different symbol from the list above.
   - Keep `TIMEFRAME=15m` and `PERIOD=60d` for first check.

7. Start dashboard and verify interaction:

```bash
./venv/bin/python dashboard/app.py
```

Open [http://localhost:5001](http://localhost:5001), then confirm scanner rows and risk panel update.

8. After all checks pass, enable stricter safety back:
   - `REQUIRE_BACKTEST_PASS=true`

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
- Run out-of-sample validation from dashboard (`Run Walk-Forward`).
- Monitor paper account, risk controls, and live scanner state.

### Minimal Buyer Setup Promise

- No brokerage connection is required for `paper` mode.
- Telegram is optional.
- Leave `TELEGRAM_TOKEN` / `TELEGRAM_CHAT_ID` blank unless you want alerts.
- Only Python + this folder are required.

## Modes

- `signals`: alerts only
- `paper`: local paper execution (`data/paper_state.json`, `data/paper_trades.csv`)
- `binance_testnet`: paper-money orders via Binance Spot Testnet
- `robinhood`: signal-only workflow

If Binance testnet is blocked in your region (HTTP 451), the bot can auto-fallback to local paper execution:

```env
BINANCE_TESTNET_AUTO_FALLBACK_TO_PAPER=true
```

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
DATA_STALE_AFTER_MINUTES=240
MIN_SIGNAL_WARMUP_BARS=220
ALLOW_POSITION_SCALING=false
STOP_LOSS_PCT=0.02
TAKE_PROFIT_PCT=0.04
TRAILING_STOP_PCT=0.015
MAX_HOLD_BARS=96
```

Regime + strategy settings:

```env
ALLOW_NEUTRAL_REGIME_TRADES=false
REGIME_LOOKBACK_BARS=24
REGIME_CONFIRM_BARS=2
REGIME_TREND_ADX_HIGH=22
REGIME_CHOPPY_ADX_LOW=16
REGIME_TREND_EMA_GAP_PCT=0.0025
REGIME_CHOPPY_EMA_GAP_PCT=0.0012
REGIME_TREND_BANDWIDTH_PCT=0.018
REGIME_CHOPPY_BANDWIDTH_PCT=0.012
MEANREV_ZSCORE_ENTRY=1.1
MEANREV_RSI_LONG_MAX=38
MEANREV_RSI_SHORT_MIN=62
MEANREV_MIN_VOLUME_MULTIPLIER=0.8
MEANREV_MIN_SIGNAL_SCORE=4
```

The bot blocks execution when limits are hit.
Risk rationale and references are in:
- `docs/risk_guidelines.md`

Backtest gate settings:

```env
REQUIRE_BACKTEST_PASS=true
BACKTEST_LOOKBACK_PERIOD=6mo
BACKTEST_MIN_TRADES=20
BACKTEST_MIN_WIN_RATE_PCT=45
BACKTEST_MIN_PROFIT_FACTOR=1.1
USE_WALK_FORWARD_PRECHECK=true
WALK_FORWARD_SPLITS=4
WALK_FORWARD_MIN_BARS_PER_SPLIT=120
WALK_FORWARD_MIN_TRADES=8
WALK_FORWARD_MIN_WIN_RATE_PCT=42
WALK_FORWARD_MIN_PROFIT_FACTOR=1.05
BACKTEST_SPREAD_BPS=2
BACKTEST_SLIPPAGE_BPS=2
BACKTEST_LATENCY_BARS=1
BACKTEST_PARTIAL_FILL_PCT=1.0
SYMBOL_LEARNING_RATE=0.2
FEATURE_LEARNING_RATE=0.06
FEATURE_WEIGHT_CLAMP=0.5
```

For `binance_testnet` mode, install `ccxt` first:

```bash
./venv/bin/pip install ccxt
```

If Binance returns `restricted location` errors, keep using `paper` mode or leave
`BINANCE_TESTNET_AUTO_FALLBACK_TO_PAPER=true` so the app does not crash.

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

Walk-forward API:

```bash
curl -X POST http://localhost:5001/api/walkforward \
  -H "Content-Type: application/json" \
  -d '{"symbol":"BTC-USD","period":"6mo","timeframe":"15m"}'
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
- Scanner table for all symbols (model, regime, signal, score, stale data, price)
- Risk block (trades today, realized PnL, cooldown, loss streak)
- Paper account snapshot
- Backtest metrics + equity chart + trade table
- Learning log: `data/learn_log.csv` captures signals, adjusted score, active features, and bias updates.

## Build Fiverr Zip

```bash
./scripts/build_release.sh
```

Output:
- `release/trading_bot_bundle_<timestamp>.zip`

## Notes

- Backtesting is currently included for your testing phase.
- When ready for Fiverr delivery, you can remove `backtesting/` and dashboard backtest endpoint if desired.
