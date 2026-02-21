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


def _bars_per_year(timeframe: str) -> int:
    tf = timeframe.lower()
    if tf.endswith("m"):
        minutes = int(tf[:-1])
        return int((365 * 24 * 60) / max(minutes, 1))
    if tf.endswith("h"):
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
    drawdowns = (arr - peak) / peak
    return float(drawdowns.min()) * 100.0


def run_backtest(symbol: str, period: str | None = None, timeframe: str | None = None) -> dict[str, Any]:
    bt_period = period or settings.PERIOD
    bt_timeframe = timeframe or settings.TIMEFRAME

    strategy = TrendDeviationStrategy(symbol=symbol)
    df = strategy.get_data(period=bt_period, timeframe=bt_timeframe)
    if df.empty or len(df) < 50:
        return {
            "symbol": symbol,
            "timeframe": bt_timeframe,
            "period": bt_period,
            "error": "Not enough data for backtest.",
            "trades": [],
            "equity_curve": [],
            "metrics": {},
        }

    initial_capital = float(settings.INITIAL_CAPITAL)
    fee = float(settings.COMMISSION_PCT)
    risk_pct = float(settings.MAX_TRADE_RISK_PCT) / 100.0

    cash = initial_capital
    qty = 0.0
    entry_price = 0.0
    entry_time = None

    trades: list[BacktestTrade] = []
    equity_curve: list[float] = []
    timestamps: list[str] = []

    for i in range(1, len(df)):
        ts = df.index[i]
        price = float(df["Close"].iloc[i])
        slice_df = df.iloc[: i + 1]
        signal = strategy.generate_latest_signal(slice_df)

        if signal and signal["type"] == "LONG" and qty == 0:
            allocation = min(cash, cash * risk_pct)
            if allocation > 0:
                fee_cost = allocation * fee
                net = max(allocation - fee_cost, 0.0)
                qty = net / price
                cash -= allocation
                entry_price = price
                entry_time = ts

        elif signal and signal["type"] == "SHORT" and qty > 0:
            gross = qty * price
            fee_cost = gross * fee
            net = gross - fee_cost
            cash += net
            pnl = (price - entry_price) * qty - fee_cost
            ret = ((price - entry_price) / entry_price) * 100.0 if entry_price else 0.0
            trades.append(
                BacktestTrade(
                    symbol=symbol,
                    entry_time=str(entry_time),
                    exit_time=str(ts),
                    entry_price=entry_price,
                    exit_price=price,
                    qty=qty,
                    pnl=pnl,
                    return_pct=ret,
                )
            )
            qty = 0.0
            entry_price = 0.0
            entry_time = None

        equity = cash + (qty * price)
        equity_curve.append(float(equity))
        timestamps.append(str(ts))

    if qty > 0:
        final_price = float(df["Close"].iloc[-1])
        ts = df.index[-1]
        gross = qty * final_price
        fee_cost = gross * fee
        net = gross - fee_cost
        cash += net
        pnl = (final_price - entry_price) * qty - fee_cost
        ret = ((final_price - entry_price) / entry_price) * 100.0 if entry_price else 0.0
        trades.append(
            BacktestTrade(
                symbol=symbol,
                entry_time=str(entry_time),
                exit_time=str(ts),
                entry_price=entry_price,
                exit_price=final_price,
                qty=qty,
                pnl=pnl,
                return_pct=ret,
            )
        )
        equity_curve[-1] = float(cash)

    final_equity = float(equity_curve[-1]) if equity_curve else initial_capital
    returns = np.diff(np.array(equity_curve)) / np.array(equity_curve[:-1]) if len(equity_curve) > 1 else np.array([])
    sharpe = 0.0
    if returns.size > 1 and np.std(returns) > 0:
        sharpe = float(np.mean(returns) / np.std(returns) * sqrt(_bars_per_year(bt_timeframe)))

    pnls = np.array([t.pnl for t in trades], dtype=float) if trades else np.array([])
    wins = int(np.sum(pnls > 0))
    losses = int(np.sum(pnls <= 0))
    win_rate = (wins / len(trades) * 100.0) if trades else 0.0
    gross_profit = float(np.sum(pnls[pnls > 0])) if trades else 0.0
    gross_loss = abs(float(np.sum(pnls[pnls < 0]))) if trades else 0.0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else None

    metrics = {
        "initial_capital": initial_capital,
        "final_equity": final_equity,
        "net_profit": final_equity - initial_capital,
        "total_return_pct": ((final_equity / initial_capital) - 1) * 100.0,
        "max_drawdown_pct": _max_drawdown(equity_curve),
        "sharpe": sharpe,
        "trades": len(trades),
        "wins": wins,
        "losses": losses,
        "win_rate_pct": win_rate,
        "profit_factor": profit_factor,
    }

    return {
        "symbol": symbol,
        "timeframe": bt_timeframe,
        "period": bt_period,
        "trades": [t.__dict__ for t in trades[-200:]],
        "equity_curve": [{"time": t, "equity": e} for t, e in zip(timestamps, equity_curve)],
        "metrics": metrics,
    }
