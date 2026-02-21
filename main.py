import argparse
import time
from datetime import datetime, timezone
from typing import Optional

from config import settings
from execution.binance_testnet import BinanceTestnetExecutor
from execution.paper import PaperTradeExecutor
from notifications.telegram_client import TelegramClient
from risk.manager import RiskManager
from strategy.trend_deviation import TrendDeviationStrategy
from utils.market_time import is_market_open
from utils.runtime_state import RuntimeStateStore


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
        return BinanceTestnetExecutor(
            api_key=settings.BINANCE_API_KEY,
            api_secret=settings.BINANCE_API_SECRET,
            symbol=settings.BINANCE_SYMBOL,
            order_size_usdt=settings.BINANCE_ORDER_SIZE_USDT,
            public_api_url=settings.BINANCE_TESTNET_PUBLIC_API,
            private_api_url=settings.BINANCE_TESTNET_PRIVATE_API,
        )

    raise ValueError(f"Unsupported BOT_MODE: {settings.BOT_MODE}")


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


def _parse_symbols() -> list[str]:
    symbols = list(dict.fromkeys(settings.SYMBOLS))
    return symbols if symbols else [settings.SYMBOL]


def _get_selected_symbol(runtime_state: dict, symbols: list[str]) -> str:
    selected = runtime_state.get("selected_symbol") or settings.ACTIVE_SYMBOL
    if selected not in symbols:
        selected = symbols[0]
    runtime_state["selected_symbol"] = selected
    return selected


def run_bot(run_once: bool = False) -> None:
    config_warnings = settings.validate_settings()
    for warning in config_warnings:
        print(f"Config warning: {warning}")

    telegram_client = build_telegram_client()
    executor = build_executor()
    risk_manager = RiskManager()
    symbols = _parse_symbols()
    strategies = {symbol: TrendDeviationStrategy(symbol=symbol) for symbol in symbols}

    state_store = RuntimeStateStore(settings.STATE_DIR)
    runtime_state = state_store.load()

    last_signal_key = runtime_state.get("last_signal_key")
    cycle = int(runtime_state.get("cycles", 0))
    selected_symbol = _get_selected_symbol(runtime_state, symbols)

    startup = (
        f"Bot started | mode={settings.BOT_MODE}, symbols={','.join(symbols)}, "
        f"selected={selected_symbol}, timeframe={settings.TIMEFRAME}, period={settings.PERIOD}"
    )
    send_notification(telegram_client, startup)
    print(f"State file: {state_store.state_file}")
    if last_signal_key:
        print(f"Resuming with last_signal_key={last_signal_key}")

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
                active_signals = 0

                for symbol in symbols:
                    strategy = strategies[symbol]
                    df = strategy.get_data()

                    scan_row = {
                        "symbol": symbol,
                        "updated_at_utc": cycle_time,
                        "data_rows": int(len(df)),
                        "signal": None,
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
                            scan_row["score"] = signal["score"]
                            active_signals += 1

                        if symbol == selected_symbol:
                            selected_signal = signal
                            selected_price = price
                    runtime_state["scanner"][symbol] = scan_row

                print(
                    f"[Cycle {cycle}] {cycle_time} | scanned={len(symbols)} | "
                    f"active_signals={active_signals} | selected={selected_symbol}"
                )

                if selected_signal:
                    signal_key = (
                        f"{selected_symbol}::{selected_signal['timestamp']}::{selected_signal['type']}"
                    )
                    if signal_key != last_signal_key:
                        runtime_state["signals_detected"] = int(runtime_state.get("signals_detected", 0)) + 1

                        equity = risk_manager.current_equity(executor, selected_price)
                        can_trade, blocked_reason = risk_manager.can_trade(runtime_state, equity)

                        message = strategies[selected_symbol].format_alert_message(selected_signal)
                        send_notification(telegram_client, message)

                        if executor:
                            if can_trade:
                                base_order_size = (
                                    settings.BINANCE_ORDER_SIZE_USDT
                                    if settings.BOT_MODE == "binance_testnet"
                                    else settings.PAPER_ORDER_SIZE_USDT
                                )
                                order_size = risk_manager.suggested_order_notional(equity, base_order_size)
                                exec_result = executor.execute_signal(
                                    selected_signal, order_size_usdt=order_size
                                )
                                send_notification(telegram_client, exec_result["message"])
                                if exec_result.get("executed"):
                                    runtime_state["executions_attempted"] = int(
                                        runtime_state.get("executions_attempted", 0)
                                    ) + 1
                                    risk_manager.record_trade(runtime_state, exec_result.get("realized_pnl"))
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
