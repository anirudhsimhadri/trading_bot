import argparse
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from backtesting.engine import run_backtest, run_walk_forward_backtest
from config import settings
from execution.binance_testnet import BinanceTestnetExecutor
from execution.paper import PaperTradeExecutor
from notifications.telegram_client import TelegramClient
from risk.manager import RiskManager
from strategy.trend_deviation import TrendDeviationStrategy
from utils.market_time import is_market_open
from utils.runtime_state import RuntimeStateStore


FEATURE_KEYS = (
    "trend",
    "adx",
    "pullback",
    "momentum",
    "volume",
    "band_bias",
    "rsi_slope",
    "strategy_trend",
    "strategy_mean_reversion",
    "regime_trending",
    "regime_choppy",
    "regime_neutral",
    "zscore_extreme",
    "rsi_reversal",
    "macd_reversal",
    "below_midline",
    "above_midline",
)


def send_notification(telegram_client: Optional[TelegramClient], message: str) -> None:
    print(message)
    if telegram_client:
        telegram_client.send_alert(message)


def build_telegram_client() -> Optional[TelegramClient]:
    if not settings.TELEGRAM_TOKEN or not settings.TELEGRAM_CHAT_ID:
        return None
    return TelegramClient(token=settings.TELEGRAM_TOKEN, chat_id=settings.TELEGRAM_CHAT_ID)


def build_executor():
    if settings.BOT_MODE in {"signals", "robinhood"}:
        return None

    if settings.BOT_MODE == "paper":
        return PaperTradeExecutor(
            state_dir=settings.STATE_DIR,
            initial_balance_usdt=settings.PAPER_INITIAL_BALANCE_USDT,
            order_size_usdt=settings.PAPER_ORDER_SIZE_USDT,
        )

    if settings.BOT_MODE == "binance_testnet":
        try:
            return BinanceTestnetExecutor(
                api_key=settings.BINANCE_API_KEY,
                api_secret=settings.BINANCE_API_SECRET,
                symbol=settings.BINANCE_SYMBOL,
                order_size_usdt=settings.BINANCE_ORDER_SIZE_USDT,
                public_api_url=settings.BINANCE_TESTNET_PUBLIC_API,
                private_api_url=settings.BINANCE_TESTNET_PRIVATE_API,
            )
        except Exception as exc:
            if settings.BINANCE_TESTNET_AUTO_FALLBACK_TO_PAPER:
                print(
                    "Binance testnet unavailable. "
                    "Falling back to local paper execution. "
                    f"Reason: {exc}"
                )
                return PaperTradeExecutor(
                    state_dir=settings.STATE_DIR,
                    initial_balance_usdt=settings.PAPER_INITIAL_BALANCE_USDT,
                    order_size_usdt=settings.PAPER_ORDER_SIZE_USDT,
                )
            raise RuntimeError(
                "Failed to initialize binance_testnet executor. "
                "Set BINANCE_TESTNET_AUTO_FALLBACK_TO_PAPER=true to auto-fallback."
            ) from exc

    raise ValueError(f"Unsupported BOT_MODE: {settings.BOT_MODE}")


def _executor_label(executor) -> str:
    if executor is None:
        return "none"
    if isinstance(executor, PaperTradeExecutor):
        return "paper"
    if isinstance(executor, BinanceTestnetExecutor):
        return "binance_testnet"
    return executor.__class__.__name__


def _to_utc_datetime(value) -> Optional[datetime]:
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _staleness_minutes(df) -> Optional[float]:
    if df is None or df.empty:
        return None
    last_ts = _to_utc_datetime(df.index[-1])
    if not last_ts:
        return None
    age_seconds = (datetime.now(timezone.utc) - last_ts).total_seconds()
    return max(age_seconds / 60.0, 0.0)


def _is_data_stale(stale_minutes: Optional[float]) -> bool:
    if stale_minutes is None:
        return False
    return stale_minutes > float(settings.DATA_STALE_AFTER_MINUTES)


def _timeframe_minutes(timeframe: str) -> Optional[int]:
    tf = timeframe.strip().lower()
    if len(tf) < 2:
        return None
    unit = tf[-1]
    size = tf[:-1]
    if not size.isdigit():
        return None
    n = int(size)
    if unit == "m":
        return max(n, 1)
    if unit == "h":
        return max(n * 60, 1)
    if unit == "d":
        return max(n * 1440, 1)
    return None


def _executor_snapshot(executor, mark_price: float | None) -> Optional[dict]:
    if not executor or not hasattr(executor, "get_account_snapshot"):
        return None
    try:
        snapshot = executor.get_account_snapshot(mark_price)
    except Exception:
        return None
    return snapshot if isinstance(snapshot, dict) else None


def _sync_position_meta(
    runtime_state: dict,
    symbol: str,
    snapshot: Optional[dict],
    mark_price: Optional[float],
    now_utc_iso: str,
) -> Optional[dict]:
    positions = runtime_state.setdefault("positions", {})
    meta = positions.get(symbol)
    asset_qty = float((snapshot or {}).get("asset_qty", 0.0) or 0.0)

    if asset_qty <= 1e-12:
        positions.pop(symbol, None)
        return None

    if not meta:
        inferred_entry = float((snapshot or {}).get("avg_entry_price", 0.0) or mark_price or 0.0)
        if inferred_entry <= 0:
            inferred_entry = float(mark_price or 0.0)
        meta = {
            "entry_price": inferred_entry,
            "entry_time_utc": now_utc_iso,
            "high_watermark": float(mark_price or inferred_entry),
            "qty": asset_qty,
            "inferred": True,
        }
        positions[symbol] = meta
        return meta

    entry_price = float(meta.get("entry_price", 0.0) or 0.0)
    if entry_price <= 0:
        entry_price = float((snapshot or {}).get("avg_entry_price", 0.0) or mark_price or 0.0)
        meta["entry_price"] = entry_price
    high = float(meta.get("high_watermark", 0.0) or 0.0)
    if mark_price is not None:
        meta["high_watermark"] = max(high, float(mark_price))
    meta["qty"] = asset_qty
    return meta


def _build_protective_exit_signal(
    symbol: str,
    mark_price: Optional[float],
    position_meta: Optional[dict],
    now_utc_iso: str,
) -> Optional[dict]:
    if not position_meta or mark_price is None:
        return None

    entry_price = float(position_meta.get("entry_price", 0.0) or 0.0)
    high_watermark = float(position_meta.get("high_watermark", 0.0) or 0.0)
    if entry_price <= 0 or mark_price <= 0:
        return None

    stop_price = entry_price * (1.0 - float(settings.STOP_LOSS_PCT))
    take_profit_price = entry_price * (1.0 + float(settings.TAKE_PROFIT_PCT))
    trailing_price = high_watermark * (1.0 - float(settings.TRAILING_STOP_PCT))
    reason = None

    if settings.STOP_LOSS_PCT > 0 and mark_price <= stop_price:
        reason = "stop_loss"
    elif settings.TAKE_PROFIT_PCT > 0 and mark_price >= take_profit_price:
        reason = "take_profit"
    elif (
        settings.TRAILING_STOP_PCT > 0
        and high_watermark > entry_price
        and mark_price <= trailing_price
    ):
        reason = "trailing_stop"
    else:
        tf_minutes = _timeframe_minutes(settings.TIMEFRAME)
        if tf_minutes is not None and settings.MAX_HOLD_BARS > 0:
            entry_raw = position_meta.get("entry_time_utc")
            try:
                entry_dt = datetime.fromisoformat(str(entry_raw))
                if entry_dt.tzinfo is None:
                    entry_dt = entry_dt.replace(tzinfo=timezone.utc)
                age_minutes = (datetime.now(timezone.utc) - entry_dt.astimezone(timezone.utc)).total_seconds() / 60.0
                if age_minutes >= (settings.MAX_HOLD_BARS * tf_minutes):
                    reason = "max_hold"
            except (ValueError, TypeError):
                pass

    if not reason:
        return None

    return {
        "symbol": symbol,
        "timestamp": now_utc_iso,
        "type": "SHORT",
        "price": float(mark_price),
        "rsi": 0.0,
        "macd": 0.0,
        "adx": 0.0,
        "score": settings.STRATEGY_MIN_SIGNAL_SCORE,
        "features": [f"protective_{reason}"],
        "reason": reason,
    }


def _current_position_state(executor, mark_price: float | None) -> str | None:
    if not executor or not hasattr(executor, "get_account_snapshot"):
        return None
    try:
        snapshot = executor.get_account_snapshot(mark_price)
    except Exception:
        return None

    if not snapshot:
        return None

    asset_qty = float(snapshot.get("asset_qty", 0.0) or 0.0)
    return "LONG" if asset_qty > 1e-12 else "FLAT"


def _parse_symbols() -> list[str]:
    symbols = list(dict.fromkeys(settings.SYMBOLS))
    return symbols if symbols else [settings.SYMBOL]


def _get_selected_symbol(runtime_state: dict, symbols: list[str]) -> str:
    selected = runtime_state.get("selected_symbol") or settings.ACTIVE_SYMBOL
    if selected not in symbols:
        selected = symbols[0]
    runtime_state["selected_symbol"] = selected
    return selected


def _get_bias(runtime_state: dict, symbol: str) -> float:
    learning = runtime_state.setdefault("learning", {})
    return float(learning.get(symbol, 0.0))


def _update_bias(runtime_state: dict, symbol: str, realized_pnl: float | None) -> float:
    if realized_pnl is None or abs(float(realized_pnl)) < 1e-12:
        return _get_bias(runtime_state, symbol)
    lr = float(settings.SYMBOL_LEARNING_RATE)
    learning = runtime_state.setdefault("learning", {})
    bias = float(learning.get(symbol, 0.0))
    delta = lr if realized_pnl > 0 else -lr
    bias = max(-1.5, min(1.5, bias + delta))
    learning[symbol] = bias
    return bias


def _get_feature_weights(runtime_state: dict, symbol: str) -> dict[str, float]:
    root = runtime_state.setdefault("feature_learning", {})
    raw = root.get(symbol)
    if not isinstance(raw, dict):
        raw = {}
    weights: dict[str, float] = {}
    for key in FEATURE_KEYS:
        weights[key] = float(raw.get(key, 0.0) or 0.0)
    for key, value in raw.items():
        if key not in weights:
            weights[str(key)] = float(value or 0.0)
    root[symbol] = weights
    return weights


def _signal_features(signal: dict) -> list[str]:
    raw = signal.get("features", [])
    if not isinstance(raw, list):
        return []
    features: list[str] = []
    for item in raw:
        key = str(item).strip()
        if key and key not in features:
            features.append(key)
    return features


def _feature_adjustment(runtime_state: dict, symbol: str, features: list[str]) -> float:
    weights = _get_feature_weights(runtime_state, symbol)
    return float(sum(float(weights.get(name, 0.0)) for name in features))


def _update_feature_weights(
    runtime_state: dict,
    symbol: str,
    features: list[str],
    realized_pnl: float | None,
) -> dict[str, float]:
    weights = _get_feature_weights(runtime_state, symbol)
    if realized_pnl is None or abs(float(realized_pnl)) < 1e-12 or not features:
        return weights

    lr = float(settings.FEATURE_LEARNING_RATE)
    clamp = float(settings.FEATURE_WEIGHT_CLAMP)
    delta = lr if realized_pnl > 0 else -lr

    for name in features:
        current = float(weights.get(name, 0.0))
        weights[name] = max(-clamp, min(clamp, current + delta))
    return weights


def _log_learning_event(
    state_dir: str,
    symbol: str,
    signal: dict,
    pnl: float | None,
    bias_before: float,
    bias_after: float,
    feature_adj_before: float,
):
    path = Path(state_dir) / "learn_log.csv"
    score = float(signal.get("score", 0.0))
    adj_score = score + float(bias_before) + float(feature_adj_before)
    features = ";".join(_signal_features(signal))
    strategy_name = str(signal.get("strategy", "unknown"))
    regime_name = str(signal.get("regime", "unknown"))
    regime_conf = float(signal.get("regime_confidence", 0.0))
    header = (
        "timestamp,symbol,strategy,regime,regime_conf,type,score,adj_score,feature_adj,features,price,rsi,adx,pnl,bias_before,bias_after\n"
    )
    line = (
        f"{signal['timestamp']},{symbol},{strategy_name},{regime_name},{regime_conf},{signal['type']},"
        f"{score},{adj_score},{feature_adj_before},{features},"
        f"{signal.get('price', '')},{signal.get('rsi', '')},{signal.get('adx', '')},"
        f"{pnl if pnl is not None else ''},{bias_before},{bias_after}\n"
    )
    if not path.exists():
        path.write_text(header, encoding="utf-8")
    with path.open("a", encoding="utf-8") as f:
        f.write(line)


def _backtest_gate(result: dict) -> tuple[bool, str]:
    if result.get("error"):
        return False, f"Backtest unavailable: {result.get('error')}"

    metrics = result.get("metrics", {})
    trades = int(metrics.get("trades", 0) or 0)
    win_rate = float(metrics.get("win_rate_pct", 0.0) or 0.0)
    validation_mode = str(metrics.get("validation_mode", "backtest"))
    pf_raw = metrics.get("profit_factor")
    if pf_raw is None:
        wins = int(metrics.get("wins", 0) or 0)
        losses = int(metrics.get("losses", 0) or 0)
        profit_factor = float("inf") if wins > 0 and losses == 0 else 0.0
    else:
        profit_factor = float(pf_raw)

    if validation_mode == "walk_forward":
        split_pass_rate = float(metrics.get("split_pass_rate_pct", 0.0) or 0.0)
        if trades < settings.WALK_FORWARD_MIN_TRADES:
            return (
                False,
                f"Walk-forward trades below threshold ({trades} < {settings.WALK_FORWARD_MIN_TRADES})",
            )
        if win_rate < settings.WALK_FORWARD_MIN_WIN_RATE_PCT:
            return (
                False,
                f"Walk-forward win-rate below threshold "
                f"({win_rate:.2f}% < {settings.WALK_FORWARD_MIN_WIN_RATE_PCT:.2f}%)",
            )
        if profit_factor < settings.WALK_FORWARD_MIN_PROFIT_FACTOR:
            return (
                False,
                f"Walk-forward profit-factor below threshold "
                f"({profit_factor:.2f} < {settings.WALK_FORWARD_MIN_PROFIT_FACTOR:.2f})",
            )
        if split_pass_rate < 50.0:
            return (
                False,
                f"Walk-forward split pass-rate too low ({split_pass_rate:.2f}% < 50.00%)",
            )
        return True, "Walk-forward gate passed"

    if trades < settings.BACKTEST_MIN_TRADES:
        return False, f"Backtest trades below threshold ({trades} < {settings.BACKTEST_MIN_TRADES})"
    if win_rate < settings.BACKTEST_MIN_WIN_RATE_PCT:
        return False, f"Backtest win-rate below threshold ({win_rate:.2f}% < {settings.BACKTEST_MIN_WIN_RATE_PCT:.2f}%)"
    if profit_factor < settings.BACKTEST_MIN_PROFIT_FACTOR:
        return (
            False,
            f"Backtest profit-factor below threshold "
            f"({profit_factor:.2f} < {settings.BACKTEST_MIN_PROFIT_FACTOR:.2f})",
        )
    return True, "Backtest gate passed"


def run_bot(run_once: bool = False) -> None:
    config_warnings = settings.validate_settings()
    for warning in config_warnings:
        print(f"Config warning: {warning}")

    telegram_client = build_telegram_client()
    executor = build_executor()
    risk_manager = RiskManager()
    symbols = _parse_symbols()
    strategies = {symbol: TrendDeviationStrategy(symbol=symbol) for symbol in symbols}
    preflight: dict[str, dict] = {}

    state_store = RuntimeStateStore(settings.STATE_DIR)
    runtime_state = state_store.load()

    last_signal_key = runtime_state.get("last_signal_key")
    cycle = int(runtime_state.get("cycles", 0))
    selected_symbol = _get_selected_symbol(runtime_state, symbols)

    startup = (
        f"Bot started | mode={settings.BOT_MODE}, symbols={','.join(symbols)}, "
        f"selected={selected_symbol}, timeframe={settings.TIMEFRAME}, period={settings.PERIOD}, "
        f"execution={_executor_label(executor)}"
    )
    send_notification(telegram_client, startup)
    print(f"State file: {state_store.state_file}")
    if last_signal_key:
        print(f"Resuming with last_signal_key={last_signal_key}")

    if settings.REQUIRE_BACKTEST_PASS:
        validation_label = "walk-forward" if settings.USE_WALK_FORWARD_PRECHECK else "single backtest"
        print(
            f"Running preflight {validation_label} checks..."
        )
        for symbol in symbols:
            if settings.USE_WALK_FORWARD_PRECHECK:
                result = run_walk_forward_backtest(
                    symbol=symbol,
                    period=settings.BACKTEST_LOOKBACK_PERIOD,
                    timeframe=settings.TIMEFRAME,
                )
            else:
                result = run_backtest(
                    symbol=symbol,
                    period=settings.BACKTEST_LOOKBACK_PERIOD,
                    timeframe=settings.TIMEFRAME,
                )
            passed, reason = _backtest_gate(result)
            preflight[symbol] = {
                "passed": passed,
                "reason": reason,
                "validation_mode": "walk_forward" if settings.USE_WALK_FORWARD_PRECHECK else "backtest",
                "checked_at_utc": datetime.now(timezone.utc).isoformat(),
                "metrics": result.get("metrics", {}),
                "error": result.get("error"),
            }
            status = "PASS" if passed else "BLOCK"
            print(f"Preflight {status} {symbol}: {reason}")
        runtime_state["preflight"] = preflight
        state_store.save(runtime_state)

    if settings.BOT_MODE == "robinhood":
        send_notification(
            telegram_client,
            "Robinhood mode is signal-only. No orders are placed automatically.",
        )

    try:
        while True:
            try:
                cycle += 1
                cycle_time = datetime.now(timezone.utc).isoformat()
                external_state = state_store.load()
                external_selected = external_state.get("selected_symbol")
                if external_selected in symbols:
                    runtime_state["selected_symbol"] = external_selected
                runtime_state["cycles"] = cycle
                runtime_state["last_cycle_at_utc"] = cycle_time
                runtime_state.setdefault("scanner", {})
                selected_symbol = _get_selected_symbol(runtime_state, symbols)

                market_is_open = is_market_open() if settings.REQUIRE_MARKET_HOURS else True
                if not market_is_open:
                    print(f"[Cycle {cycle}] {cycle_time} | Market closed. Waiting for next cycle...")
                    state_store.save(runtime_state)
                    if run_once:
                        return
                    time.sleep(settings.CHECK_INTERVAL_SECONDS)
                    continue

                selected_signal = None
                selected_price = None
                selected_stale = None
                active_signals = 0

                for symbol in symbols:
                    strategy = strategies[symbol]
                    df = strategy.get_data()

                    scan_row = {
                        "symbol": symbol,
                        "updated_at_utc": cycle_time,
                        "data_rows": int(len(df)),
                        "signal": None,
                        "strategy": None,
                        "regime": None,
                        "regime_confidence": None,
                        "score": None,
                        "last_close": None,
                        "stale_minutes": None,
                    }

                    if not df.empty:
                        price = float(df["Close"].iloc[-1])
                        scan_row["last_close"] = price
                        scan_row["stale_minutes"] = _staleness_minutes(df)
                        signal = strategy.generate_latest_signal(df)
                        if signal:
                            scan_row["signal"] = signal["type"]
                            scan_row["strategy"] = signal.get("strategy")
                            scan_row["regime"] = signal.get("regime")
                            scan_row["regime_confidence"] = signal.get("regime_confidence")
                            scan_row["score"] = signal["score"]
                            active_signals += 1

                        if symbol == selected_symbol:
                            selected_signal = signal
                            selected_price = price
                            selected_stale = scan_row["stale_minutes"]
                    runtime_state["scanner"][symbol] = scan_row

                print(
                    f"[Cycle {cycle}] {cycle_time} | scanned={len(symbols)} | "
                    f"active_signals={active_signals} | selected={selected_symbol}"
                )

                selected_snapshot = _executor_snapshot(executor, selected_price)
                selected_position_meta = _sync_position_meta(
                    runtime_state,
                    selected_symbol,
                    selected_snapshot,
                    selected_price,
                    cycle_time,
                )
                protective_signal = _build_protective_exit_signal(
                    selected_symbol,
                    selected_price,
                    selected_position_meta,
                    cycle_time,
                )
                trade_signal = protective_signal if protective_signal else selected_signal

                if trade_signal:
                    is_protective = bool(trade_signal.get("reason"))
                    if not is_protective and _is_data_stale(selected_stale):
                        reason = (
                            f"Data stale for {selected_symbol} "
                            f"({selected_stale:.1f}m > {settings.DATA_STALE_AFTER_MINUTES}m)."
                        )
                        print(f"[Cycle {cycle}] Execution blocked: {reason}")
                        runtime_state.setdefault("risk", {})["blocked_reason"] = reason
                        state_store.save(runtime_state)
                        if run_once:
                            return
                        time.sleep(settings.CHECK_INTERVAL_SECONDS)
                        continue

                    signal_features = _signal_features(trade_signal)
                    bias_before = _get_bias(runtime_state, selected_symbol)
                    feature_adj_before = _feature_adjustment(runtime_state, selected_symbol, signal_features)
                    adjusted_score = float(trade_signal.get("score", 0.0)) + bias_before + feature_adj_before
                    if not is_protective and adjusted_score < settings.STRATEGY_MIN_SIGNAL_SCORE:
                        print(
                            f"[Cycle {cycle}] Skipping signal; adjusted score {adjusted_score:.2f} "
                            f"< min {settings.STRATEGY_MIN_SIGNAL_SCORE}"
                        )
                        state_store.save(runtime_state)
                        if run_once:
                            return
                        time.sleep(settings.CHECK_INTERVAL_SECONDS)
                        continue

                    signal_key = (
                        f"{selected_symbol}::{trade_signal['timestamp']}::"
                        f"{trade_signal['type']}::{trade_signal.get('reason', 'signal')}"
                    )
                    if signal_key != last_signal_key:
                        runtime_state["signals_detected"] = int(runtime_state.get("signals_detected", 0)) + 1

                        equity = risk_manager.current_equity(executor, selected_price)
                        can_trade, blocked_reason = risk_manager.can_trade(runtime_state, equity)

                        if is_protective:
                            message = (
                                f"Protective exit triggered for {selected_symbol} | "
                                f"reason={trade_signal.get('reason')} | price={trade_signal.get('price')}"
                            )
                        else:
                            message = strategies[selected_symbol].format_alert_message(trade_signal)
                        send_notification(telegram_client, message)

                        if executor:
                            symbol_preflight = preflight.get(selected_symbol) if settings.REQUIRE_BACKTEST_PASS else None
                            if symbol_preflight and not symbol_preflight.get("passed", False):
                                reason = symbol_preflight.get("reason", "Backtest gate blocked execution.")
                                print(f"[Cycle {cycle}] Execution blocked by backtest gate: {reason}")
                                runtime_state.setdefault("risk", {})["blocked_reason"] = reason
                                last_signal_key = signal_key
                                runtime_state["last_signal_key"] = last_signal_key
                                state_store.save(runtime_state)
                                if run_once:
                                    return
                                time.sleep(settings.CHECK_INTERVAL_SECONDS)
                                continue

                            position_block_reason = None
                            position_state = _current_position_state(executor, selected_price)
                            if not settings.ALLOW_POSITION_SCALING:
                                if trade_signal["type"] == "LONG" and position_state == "LONG":
                                    position_block_reason = "Position already open; scaling is disabled."
                                elif trade_signal["type"] == "SHORT" and position_state == "FLAT":
                                    position_block_reason = "No open position to close on SHORT signal."

                            close_position = trade_signal["type"] == "SHORT"
                            if position_block_reason:
                                print(f"[Cycle {cycle}] Execution blocked: {position_block_reason}")
                                runtime_state.setdefault("risk", {})["blocked_reason"] = position_block_reason
                            elif can_trade or close_position:
                                runtime_state.setdefault("risk", {})["blocked_reason"] = None
                                base_order_size = (
                                    settings.BINANCE_ORDER_SIZE_USDT
                                    if settings.BOT_MODE == "binance_testnet"
                                    else settings.PAPER_ORDER_SIZE_USDT
                                )
                                order_size = (
                                    None
                                    if close_position
                                    else risk_manager.suggested_order_notional(equity, base_order_size)
                                )
                                try:
                                    try:
                                        exec_result = executor.execute_signal(
                                            trade_signal,
                                            order_size_usdt=order_size,
                                            close_position=close_position,
                                        )
                                    except TypeError:
                                        exec_result = executor.execute_signal(
                                            trade_signal,
                                            order_size_usdt=order_size,
                                        )
                                except Exception as exec_exc:
                                    exec_result = {
                                        "executed": False,
                                        "message": f"Execution error: {exec_exc}",
                                        "realized_pnl": None,
                                    }

                                send_notification(telegram_client, exec_result["message"])
                                if exec_result.get("executed"):
                                    runtime_state["executions_attempted"] = int(
                                        runtime_state.get("executions_attempted", 0)
                                    ) + 1
                                    realized = exec_result.get("realized_pnl")
                                    equity_after = risk_manager.current_equity(executor, selected_price)
                                    risk_manager.record_trade(
                                        runtime_state,
                                        realized,
                                        current_equity=equity_after,
                                    )

                                    if trade_signal["type"] == "LONG":
                                        runtime_state.setdefault("positions", {})[selected_symbol] = {
                                            "entry_price": float(exec_result.get("price", selected_price or 0.0)),
                                            "entry_time_utc": cycle_time,
                                            "high_watermark": float(exec_result.get("price", selected_price or 0.0)),
                                            "qty": float(exec_result.get("qty", 0.0)),
                                            "inferred": False,
                                        }
                                    elif trade_signal["type"] == "SHORT":
                                        runtime_state.setdefault("positions", {}).pop(selected_symbol, None)

                                    bias_after = _update_bias(runtime_state, selected_symbol, realized)
                                    _update_feature_weights(runtime_state, selected_symbol, signal_features, realized)
                                    _log_learning_event(
                                        settings.STATE_DIR,
                                        selected_symbol,
                                        trade_signal,
                                        realized,
                                        bias_before,
                                        bias_after,
                                        feature_adj_before,
                                    )
                                else:
                                    _log_learning_event(
                                        settings.STATE_DIR,
                                        selected_symbol,
                                        trade_signal,
                                        exec_result.get("realized_pnl"),
                                        bias_before,
                                        bias_before,
                                        feature_adj_before,
                                    )
                            else:
                                reason = blocked_reason or "Risk control blocked execution."
                                print(f"[Cycle {cycle}] Execution blocked: {reason}")
                                runtime_state.setdefault("risk", {})["blocked_reason"] = reason

                        last_signal_key = signal_key
                        runtime_state["last_signal_key"] = last_signal_key
                    else:
                        print(f"[Cycle {cycle}] Duplicate signal for selected symbol. Skipping.")
                else:
                    print(f"[Cycle {cycle}] No new signal for selected symbol ({selected_symbol}).")

                if settings.HEARTBEAT_CYCLES > 0 and cycle % settings.HEARTBEAT_CYCLES == 0:
                    risk_state = runtime_state.get("risk", {})
                    heartbeat = (
                        "Heartbeat | "
                        f"cycles={runtime_state.get('cycles', 0)} | "
                        f"signals={runtime_state.get('signals_detected', 0)} | "
                        f"executions={runtime_state.get('executions_attempted', 0)} | "
                        f"errors={runtime_state.get('errors', 0)} | "
                        f"trades_today={risk_state.get('trades_today', 0)}"
                    )
                    send_notification(telegram_client, heartbeat)

                state_store.save(runtime_state)
                if run_once:
                    return
                time.sleep(settings.CHECK_INTERVAL_SECONDS)
            except Exception as exc:
                runtime_state["errors"] = int(runtime_state.get("errors", 0)) + 1
                runtime_state["last_error"] = str(exc)
                state_store.save(runtime_state)
                send_notification(telegram_client, f"⚠️ Trading Bot Error ⚠️\n{exc}")
                if run_once:
                    raise
                time.sleep(60)
    except KeyboardInterrupt:
        state_store.save(runtime_state)
        print("Bot stopped by user.")


def parse_args():
    parser = argparse.ArgumentParser(description="Trend Deviation Trading Bot")
    parser.add_argument("--once", action="store_true", help="Run one evaluation cycle and exit.")
    return parser.parse_args()


if __name__ == "__main__":
    cli_args = parse_args()
    run_bot(run_once=cli_args.once)
