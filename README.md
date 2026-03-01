# Trading Bot (ETF/Futures Optimized)

This project is now tuned primarily for:
- US index ETFs (`SPY`, `QQQ`, `IWM`, `DIA`)
- Index futures tickers via Yahoo (`NQ=F`, `ES=F`, `YM=F`, `RTY=F`)

This project is focused on ETF and futures workflows only.

## What Changed For ETF/Futures

- Instrument-aware profiles:
  - Separate thresholds for ETFs and futures (ADX, RSI, volume, mean-reversion score).
- Session-aware execution:
  - ETF RTH window filter (configurable).
  - Futures weekend + daily maintenance window filter.
- Scheduled blackout windows:
  - Time blocks (EST) to avoid known high-noise windows.
- Higher timeframe confirmation:
  - Entry direction must align with higher timeframe trend filter.
- ATR-based protective exits:
  - Dynamic stop-loss / take-profit / trailing distances.
- Symbol-aware risk caps:
  - Separate max trade risk for ETFs vs futures.
- Backtest alignment:
  - Backtests now respect session + blackout filters and ATR-based exits.

## One-Time Setup

From project root:

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
cp .env.example .env
chmod +x install_and_run.sh run.sh
```

Or use:

```bash
./install_and_run.sh
```

## Quick Start (Recommended)

Run the guided launcher:

```bash
./run.sh
```

Recommended first-run inputs:
1. Mode: `2` (`paper`)
2. Symbol: `SPY`
3. Scanner symbols: `SPY,QQQ,NQ=F,ES=F`
4. Active symbol: `SPY`
5. Require market hours: `false`
6. Launch dashboard: `y`
7. Run one cycle only: `y`

Then continuous run:

```bash
./run.sh
```

Use the same settings, but choose `Run one cycle only: n`.

## Dashboard

Start dashboard if not already launched:

```bash
./venv/bin/python dashboard/app.py
```

Open:
- [http://localhost:5001](http://localhost:5001)

You can:
- Change active symbol.
- Monitor scanner signals, model, regime, and symbol type.
- Run backtests and walk-forward validation.
- Track risk and paper account state.

## ETF/Futures Configuration

Main config lives in:
- `/Users/anisimhadri/Developer/trading_bot/.env`

Important sections:

1. Symbols
```env
SYMBOLS=SPY,QQQ,NQ=F,ES=F
ACTIVE_SYMBOL=SPY
ETF_SYMBOLS=SPY,QQQ,IWM,DIA
FUTURES_SYMBOLS=NQ=F,ES=F,YM=F,RTY=F
```

2. Session controls (EST)
```env
ETF_TRADE_RTH_ONLY=true
ETF_SESSION_START_HOUR=9
ETF_SESSION_START_MINUTE=35
ETF_SESSION_END_HOUR=15
ETF_SESSION_END_MINUTE=55
FUTURES_AVOID_DAILY_MAINTENANCE=true
FUTURES_MAINTENANCE_START_HOUR=17
FUTURES_MAINTENANCE_END_HOUR=18
```

3. Blackout windows
```env
ENABLE_SCHEDULED_BLACKOUTS=true
BLACKOUT_WINDOWS_EST=09:25-09:40,09:55-10:05,13:55-14:10
BLACKOUT_WEEKDAYS=0,1,2,3,4
```

4. Higher timeframe filter
```env
ENABLE_HIGHER_TIMEFRAME_CONFIRMATION=true
HIGHER_TIMEFRAME_RESAMPLE_RULE=1h
HIGHER_TIMEFRAME_MIN_BARS=220
```

5. ATR exits
```env
USE_ATR_PROTECTIVE_EXITS=true
ATR_STOP_MULTIPLIER=1.8
ATR_TAKE_PROFIT_MULTIPLIER=3.0
ATR_TRAILING_MULTIPLIER=1.4
ATR_PCT_FLOOR=0.005
ATR_PCT_CAP=0.08
```

6. Symbol-aware risk
```env
MAX_TRADE_RISK_PCT=1
ETF_MAX_TRADE_RISK_PCT=1
FUTURES_MAX_TRADE_RISK_PCT=0.7
```

## Modes

- `signals`: alerts only
- `paper`: local paper execution (recommended for ETF/futures testing)
- `robinhood`: signal-only workflow (manual execution)

## Terminal Output You Should See

Startup:

```text
Bot started | mode=paper, symbols=SPY,QQQ,NQ=F,ES=F, selected=SPY, timeframe=15m, period=60d, execution=paper
State file: data/runtime_state.json
```

Cycle:

```text
[Cycle 12] 2026-03-01T14:30:00+00:00 | scanned=4 | active_signals=1 | selected=SPY
```

No signal case:

```text
[Cycle 12] No new signal for selected symbol (SPY).
```

## Troubleshooting

1. `No data found for this date range`
- Switch symbol (`SPY`, `QQQ`, `NQ=F`, `ES=F`)
- Keep initial `TIMEFRAME=15m` and `PERIOD=60d`
- Refresh dependencies: `./venv/bin/pip install -r requirements.txt`

2. Orders are blocked in session filters
- Check `ETF_TRADE_RTH_ONLY`, futures maintenance window, and `BLACKOUT_WINDOWS_EST`
- For testing only, set `ENABLE_SCHEDULED_BLACKOUTS=false`

3. Telegram errors
- Leave `TELEGRAM_TOKEN` and `TELEGRAM_CHAT_ID` blank if you do not need alerts

## Build Fiverr Bundle

```bash
./scripts/build_release.sh
```

Output:
- `release/trading_bot_bundle_<timestamp>.zip`
