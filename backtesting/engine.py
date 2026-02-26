from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Any

import numpy as np
import pandas as pd

from config import settings
from strategy.trend_deviation import TrendDeviationStrategy


@dataclass
class BacktestTrade:
    symbol: str
    entry_time: str
    exit_time: str
    entry_price: float
    exit_price: float
    qty: float
    pnl: float
    return_pct: float
    exit_reason: str


def _bars_per_year(timeframe: str) -> int:
    tf = timeframe.lower()
    if tf.endswith("m") and tf[:-1].isdigit():
        minutes = int(tf[:-1])
        return int((365 * 24 * 60) / max(minutes, 1))
    if tf.endswith("h") and tf[:-1].isdigit():
        hours = int(tf[:-1])
        return int((365 * 24) / max(hours, 1))
    if tf == "1d":
        return 252
    return 252


def _max_drawdown(equity_curve: list[float]) -> float:
    if not equity_curve:
        return 0.0
    arr = np.array(equity_curve, dtype=float)
    peak = np.maximum.accumulate(arr)
    drawdowns = (arr - peak) / np.maximum(peak, 1e-12)
    return float(drawdowns.min()) * 100.0


def _execution_price(raw_price: float, side: str) -> float:
    raw = max(float(raw_price), 1e-12)
    spread_bps = max(float(settings.BACKTEST_SPREAD_BPS), 0.0)
    slippage_bps = max(float(settings.BACKTEST_SLIPPAGE_BPS), 0.0)
    cost_bps = (spread_bps / 2.0) + slippage_bps
    cost_pct = cost_bps / 10000.0
    if side == "buy":
        return raw * (1.0 + cost_pct)
    return raw * max(1.0 - cost_pct, 1e-6)


def _profit_factor(pnls: np.ndarray) -> float | None:
    gross_profit = float(np.sum(pnls[pnls > 0])) if pnls.size else 0.0
    gross_loss = abs(float(np.sum(pnls[pnls < 0]))) if pnls.size else 0.0
    if gross_loss <= 0:
        return None
    return gross_profit / gross_loss


def _compute_metrics(
    initial_capital: float,
    final_equity: float,
    trades: list[BacktestTrade],
    equity_curve: list[float],
    timeframe: str,
) -> dict[str, Any]:
    returns = (
        np.diff(np.array(equity_curve, dtype=float)) / np.maximum(np.array(equity_curve[:-1], dtype=float), 1e-12)
        if len(equity_curve) > 1
        else np.array([])
    )
    sharpe = 0.0
    if returns.size > 1 and np.std(returns) > 0:
        sharpe = float(np.mean(returns) / np.std(returns) * sqrt(_bars_per_year(timeframe)))

    pnls = np.array([t.pnl for t in trades], dtype=float) if trades else np.array([])
    wins = int(np.sum(pnls > 0))
    losses = int(np.sum(pnls <= 0))
    win_rate = (wins / len(trades) * 100.0) if trades else 0.0

    return {
        "initial_capital": float(initial_capital),
        "final_equity": float(final_equity),
        "net_profit": float(final_equity - initial_capital),
        "total_return_pct": float(((final_equity / initial_capital) - 1.0) * 100.0) if initial_capital > 0 else 0.0,
        "max_drawdown_pct": _max_drawdown(equity_curve),
        "sharpe": float(sharpe),
        "trades": int(len(trades)),
        "wins": wins,
        "losses": losses,
        "win_rate_pct": float(win_rate),
        "profit_factor": _profit_factor(pnls),
    }


def _simulate_range(
    df: pd.DataFrame,
    strategy: TrendDeviationStrategy,
    symbol: str,
    timeframe: str,
    start_index: int,
    end_index: int,
    initial_capital: float,
) -> dict[str, Any]:
    fee = max(float(settings.COMMISSION_PCT), 0.0)
    risk_pct = max(float(settings.MAX_TRADE_RISK_PCT) / 100.0, 0.0)
    partial_fill = min(max(float(settings.BACKTEST_PARTIAL_FILL_PCT), 0.01), 1.0)
    latency_bars = max(int(settings.BACKTEST_LATENCY_BARS), 0)
    stop_loss_pct = max(float(settings.STOP_LOSS_PCT), 0.0)
    take_profit_pct = max(float(settings.TAKE_PROFIT_PCT), 0.0)
    trailing_stop_pct = max(float(settings.TRAILING_STOP_PCT), 0.0)
    max_hold_bars = max(int(settings.MAX_HOLD_BARS), 1)

    cash = float(initial_capital)
    qty = 0.0
    entry_price = 0.0
    entry_i: int | None = None
    high_watermark = 0.0

    trades: list[BacktestTrade] = []
    equity_curve: list[float] = []
    timestamps: list[str] = []

    i = max(int(start_index), 1)
    end = min(int(end_index), len(df))
    if i >= end:
        return {
            "trades": [],
            "equity_curve": [],
            "timestamps": [],
            "metrics": _compute_metrics(initial_capital, initial_capital, [], [], timeframe),
        }

    while i < end:
        ts = df.index[i]
        close_price = float(df["Close"].iloc[i])
        signal = strategy.generate_latest_signal(df.iloc[: i + 1])

        exit_reason: str | None = None
        if qty > 0:
            high_watermark = max(high_watermark, close_price)
            stop_price = entry_price * (1.0 - stop_loss_pct)
            tp_price = entry_price * (1.0 + take_profit_pct)
            trail_price = high_watermark * (1.0 - trailing_stop_pct)
            held_bars = (i - entry_i) if entry_i is not None else 0

            if stop_loss_pct > 0 and close_price <= stop_price:
                exit_reason = "stop_loss"
            elif take_profit_pct > 0 and close_price >= tp_price:
                exit_reason = "take_profit"
            elif trailing_stop_pct > 0 and high_watermark > entry_price and close_price <= trail_price:
                exit_reason = "trailing_stop"
            elif held_bars >= max_hold_bars:
                exit_reason = "max_hold"
            elif signal and signal.get("type") == "SHORT":
                exit_reason = "signal_short"

        if qty <= 0 and signal and signal.get("type") == "LONG":
            fill_i = min(i + latency_bars, end - 1)
            fill_raw = float(df["Close"].iloc[fill_i])
            fill_price = _execution_price(fill_raw, side="buy")

            allocation = min(cash, cash * risk_pct) * partial_fill
            if allocation > 0 and fill_price > 0:
                entry_fee = allocation * fee
                net_allocation = max(allocation - entry_fee, 0.0)
                qty = net_allocation / fill_price
                cash -= allocation
                entry_price = fill_price
                entry_i = fill_i
                high_watermark = fill_raw
                i = fill_i

        elif qty > 0 and exit_reason is not None:
            fill_i = min(i + latency_bars, end - 1)
            fill_raw = float(df["Close"].iloc[fill_i])
            fill_price = _execution_price(fill_raw, side="sell")

            qty_to_close = qty * partial_fill
            if qty_to_close <= 0:
                qty_to_close = qty

            gross = qty_to_close * fill_price
            exit_fee = gross * fee
            net = gross - exit_fee
            cash += net
            pnl = (fill_price - entry_price) * qty_to_close - exit_fee
            ret = ((fill_price - entry_price) / entry_price) * 100.0 if entry_price > 0 else 0.0

            trades.append(
                BacktestTrade(
                    symbol=symbol,
                    entry_time=str(df.index[entry_i]) if entry_i is not None else str(ts),
                    exit_time=str(df.index[fill_i]),
                    entry_price=float(entry_price),
                    exit_price=float(fill_price),
                    qty=float(qty_to_close),
                    pnl=float(pnl),
                    return_pct=float(ret),
                    exit_reason=exit_reason,
                )
            )

            qty -= qty_to_close
            if qty <= 1e-12:
                qty = 0.0
                entry_price = 0.0
                entry_i = None
                high_watermark = 0.0

            i = fill_i

        equity = cash + (qty * close_price)
        equity_curve.append(float(equity))
        timestamps.append(str(ts))
        i += 1

    if qty > 0:
        final_i = end - 1
        final_raw = float(df["Close"].iloc[final_i])
        final_price = _execution_price(final_raw, side="sell")
        gross = qty * final_price
        exit_fee = gross * fee
        net = gross - exit_fee
        cash += net
        pnl = (final_price - entry_price) * qty - exit_fee
        ret = ((final_price - entry_price) / entry_price) * 100.0 if entry_price > 0 else 0.0
        trades.append(
            BacktestTrade(
                symbol=symbol,
                entry_time=str(df.index[entry_i]) if entry_i is not None else str(df.index[final_i]),
                exit_time=str(df.index[final_i]),
                entry_price=float(entry_price),
                exit_price=float(final_price),
                qty=float(qty),
                pnl=float(pnl),
                return_pct=float(ret),
                exit_reason="end_of_test",
            )
        )
        qty = 0.0
        if equity_curve:
            equity_curve[-1] = float(cash)

    final_equity = float(cash if not equity_curve else equity_curve[-1])
    metrics = _compute_metrics(initial_capital, final_equity, trades, equity_curve, timeframe)
    return {
        "trades": [t.__dict__ for t in trades],
        "equity_curve": [{"time": t, "equity": e} for t, e in zip(timestamps, equity_curve)],
        "timestamps": timestamps,
        "metrics": metrics,
    }


def run_backtest(symbol: str, period: str | None = None, timeframe: str | None = None) -> dict[str, Any]:
    bt_period = period or settings.PERIOD
    bt_timeframe = timeframe or settings.TIMEFRAME

    strategy = TrendDeviationStrategy(symbol=symbol)
    df = strategy.get_data(period=bt_period, timeframe=bt_timeframe)
    min_bars = max(settings.MIN_SIGNAL_WARMUP_BARS + 10, 60)
    if df.empty or len(df) < min_bars:
        return {
            "symbol": symbol,
            "timeframe": bt_timeframe,
            "period": bt_period,
            "error": "Not enough data for backtest.",
            "trades": [],
            "equity_curve": [],
            "metrics": {},
        }

    simulated = _simulate_range(
        df=df,
        strategy=strategy,
        symbol=symbol,
        timeframe=bt_timeframe,
        start_index=settings.MIN_SIGNAL_WARMUP_BARS,
        end_index=len(df),
        initial_capital=float(settings.INITIAL_CAPITAL),
    )
    return {
        "symbol": symbol,
        "timeframe": bt_timeframe,
        "period": bt_period,
        "trades": simulated["trades"][-200:],
        "equity_curve": simulated["equity_curve"],
        "metrics": simulated["metrics"],
    }


def run_walk_forward_backtest(
    symbol: str,
    period: str | None = None,
    timeframe: str | None = None,
) -> dict[str, Any]:
    bt_period = period or settings.PERIOD
    bt_timeframe = timeframe or settings.TIMEFRAME
    strategy = TrendDeviationStrategy(symbol=symbol)
    df = strategy.get_data(period=bt_period, timeframe=bt_timeframe)
    if df.empty:
        return {
            "symbol": symbol,
            "timeframe": bt_timeframe,
            "period": bt_period,
            "error": "Not enough data for walk-forward backtest.",
            "splits": [],
            "metrics": {},
        }

    warmup = settings.MIN_SIGNAL_WARMUP_BARS
    available = len(df) - warmup
    if available < settings.WALK_FORWARD_MIN_BARS_PER_SPLIT * 2:
        return {
            "symbol": symbol,
            "timeframe": bt_timeframe,
            "period": bt_period,
            "error": "Not enough data for walk-forward splits.",
            "splits": [],
            "metrics": {},
        }

    max_splits = available // settings.WALK_FORWARD_MIN_BARS_PER_SPLIT
    splits = min(settings.WALK_FORWARD_SPLITS, max_splits)
    if splits < 2:
        return {
            "symbol": symbol,
            "timeframe": bt_timeframe,
            "period": bt_period,
            "error": "Not enough data for walk-forward splits.",
            "splits": [],
            "metrics": {},
        }

    split_size = available // splits
    split_rows: list[dict[str, Any]] = []
    all_trades: list[dict[str, Any]] = []
    combined_equity_curve: list[dict[str, Any]] = []

    for idx in range(splits):
        start_i = warmup + (idx * split_size)
        end_i = warmup + ((idx + 1) * split_size) if idx < splits - 1 else len(df)
        if (end_i - start_i) < settings.WALK_FORWARD_MIN_BARS_PER_SPLIT:
            continue

        sim = _simulate_range(
            df=df,
            strategy=strategy,
            symbol=symbol,
            timeframe=bt_timeframe,
            start_index=start_i,
            end_index=end_i,
            initial_capital=float(settings.INITIAL_CAPITAL),
        )

        m = sim["metrics"]
        split_row = {
            "split": idx + 1,
            "start_time": str(df.index[start_i]),
            "end_time": str(df.index[end_i - 1]),
            "metrics": m,
        }
        split_rows.append(split_row)
        all_trades.extend(sim["trades"])
        combined_equity_curve.extend(sim["equity_curve"])

    if not split_rows:
        return {
            "symbol": symbol,
            "timeframe": bt_timeframe,
            "period": bt_period,
            "error": "No valid walk-forward splits were generated.",
            "splits": [],
            "metrics": {},
        }

    pnls = np.array([float(t["pnl"]) for t in all_trades], dtype=float) if all_trades else np.array([])
    wins = int(np.sum(pnls > 0))
    losses = int(np.sum(pnls <= 0))
    trade_count = int(len(all_trades))
    win_rate = (wins / trade_count * 100.0) if trade_count > 0 else 0.0
    pf = _profit_factor(pnls)
    gross_profit = float(np.sum(pnls[pnls > 0])) if pnls.size else 0.0
    gross_loss = abs(float(np.sum(pnls[pnls < 0]))) if pnls.size else 0.0

    split_passes = 0
    for row in split_rows:
        sm = row["metrics"]
        spf = sm.get("profit_factor")
        if spf is None:
            spf = 0.0
        if (
            int(sm.get("trades", 0) or 0) >= settings.WALK_FORWARD_MIN_TRADES
            and float(sm.get("win_rate_pct", 0.0) or 0.0) >= settings.WALK_FORWARD_MIN_WIN_RATE_PCT
            and float(spf) >= settings.WALK_FORWARD_MIN_PROFIT_FACTOR
        ):
            split_passes += 1

    aggregate_initial = float(settings.INITIAL_CAPITAL) * len(split_rows)
    aggregate_final = aggregate_initial + float(np.sum(pnls)) if pnls.size else aggregate_initial
    metrics = {
        "validation_mode": "walk_forward",
        "splits": len(split_rows),
        "split_passes": split_passes,
        "split_pass_rate_pct": (split_passes / len(split_rows)) * 100.0 if split_rows else 0.0,
        "initial_capital": aggregate_initial,
        "final_equity": aggregate_final,
        "net_profit": aggregate_final - aggregate_initial,
        "total_return_pct": ((aggregate_final / aggregate_initial) - 1.0) * 100.0 if aggregate_initial > 0 else 0.0,
        "max_drawdown_pct": _max_drawdown([p["equity"] for p in combined_equity_curve]),
        "trades": trade_count,
        "wins": wins,
        "losses": losses,
        "win_rate_pct": win_rate,
        "profit_factor": pf,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
    }

    return {
        "symbol": symbol,
        "timeframe": bt_timeframe,
        "period": bt_period,
        "splits": split_rows,
        "trades": all_trades[-200:],
        "equity_curve": combined_equity_curve,
        "metrics": metrics,
    }
