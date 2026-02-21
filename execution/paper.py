import csv
import json
import os
from datetime import datetime, timezone
from typing import Dict, Any


class PaperTradeExecutor:
    def __init__(self, state_dir: str, initial_balance_usdt: float, order_size_usdt: float):
        self.state_dir = state_dir
        self.state_file = os.path.join(state_dir, "paper_state.json")
        self.trade_log_file = os.path.join(state_dir, "paper_trades.csv")
        self.order_size_usdt = order_size_usdt
        self.initial_balance_usdt = initial_balance_usdt
        self._ensure_state()

    def _ensure_state(self) -> None:
        os.makedirs(self.state_dir, exist_ok=True)
        if not os.path.exists(self.state_file):
            state = {
                "cash_usdt": self.initial_balance_usdt,
                "asset_qty": 0.0,
                "avg_entry_price": 0.0,
                "realized_pnl_total": 0.0,
                "created_at_utc": datetime.now(timezone.utc).isoformat(),
                "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            }
            self._save_state(state)

        if not os.path.exists(self.trade_log_file):
            with open(self.trade_log_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(
                    [
                        "timestamp_utc",
                        "action",
                        "price",
                        "qty",
                        "notional_usdt",
                        "cash_usdt",
                        "asset_qty",
                    ]
                )

    def _load_state(self) -> Dict[str, Any]:
        with open(self.state_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_state(self, state: Dict[str, Any]) -> None:
        state["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)

    def _append_trade(self, action: str, price: float, qty: float, notional: float, state: Dict[str, Any]) -> None:
        with open(self.trade_log_file, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    datetime.now(timezone.utc).isoformat(),
                    action,
                    round(price, 8),
                    round(qty, 8),
                    round(notional, 8),
                    round(state["cash_usdt"], 8),
                    round(state["asset_qty"], 8),
                ]
            )

    def get_account_snapshot(self, mark_price: float | None = None) -> Dict[str, Any]:
        state = self._load_state()
        if mark_price is None:
            mark_price = state.get("avg_entry_price", 0.0)
        equity = float(state["cash_usdt"]) + float(state["asset_qty"]) * float(mark_price or 0.0)
        return {
            "cash_usdt": float(state["cash_usdt"]),
            "asset_qty": float(state["asset_qty"]),
            "avg_entry_price": float(state.get("avg_entry_price", 0.0)),
            "realized_pnl_total": float(state.get("realized_pnl_total", 0.0)),
            "equity_usdt": float(equity),
        }

    def execute_signal(self, signal: Dict[str, Any], order_size_usdt: float | None = None) -> Dict[str, Any]:
        price = float(signal["price"])
        signal_type = signal["type"].upper()
        state = self._load_state()
        size = self.order_size_usdt if order_size_usdt is None else float(order_size_usdt)

        if signal_type == "LONG":
            notional = min(size, float(state["cash_usdt"]))
            if notional <= 0:
                return {"executed": False, "message": "Paper trade skipped: no USDT cash available.", "realized_pnl": None}
            qty = notional / price

            prev_qty = float(state["asset_qty"])
            prev_avg = float(state.get("avg_entry_price", 0.0))
            new_qty = prev_qty + qty
            if new_qty > 0:
                weighted_avg = ((prev_qty * prev_avg) + (qty * price)) / new_qty
            else:
                weighted_avg = 0.0

            state["cash_usdt"] -= notional
            state["asset_qty"] = new_qty
            state["avg_entry_price"] = weighted_avg
            action = "BUY"
            self._append_trade(action, price, qty, notional, state)
            self._save_state(state)
            return {
                "executed": True,
                "side": action,
                "qty": qty,
                "notional_usdt": notional,
                "price": price,
                "realized_pnl": 0.0,
                "message": (
                f"Paper BUY filled | price={price:.2f}, qty={qty:.6f}, "
                f"cash={state['cash_usdt']:.2f}, asset={state['asset_qty']:.6f}"
                ),
            }

        if signal_type == "SHORT":
            if float(state["asset_qty"]) <= 0:
                return {
                    "executed": False,
                    "message": "Paper SELL skipped: no asset inventory to sell.",
                    "realized_pnl": None,
                }
            max_notional = float(state["asset_qty"]) * price
            notional = min(size, max_notional)
            qty = notional / price
            avg_entry = float(state.get("avg_entry_price", 0.0))
            realized_pnl = (price - avg_entry) * qty
            state["cash_usdt"] += notional
            state["asset_qty"] -= qty
            if float(state["asset_qty"]) <= 1e-12:
                state["asset_qty"] = 0.0
                state["avg_entry_price"] = 0.0
            state["realized_pnl_total"] = float(state.get("realized_pnl_total", 0.0)) + realized_pnl
            action = "SELL"
            self._append_trade(action, price, qty, notional, state)
            self._save_state(state)
            return {
                "executed": True,
                "side": action,
                "qty": qty,
                "notional_usdt": notional,
                "price": price,
                "realized_pnl": realized_pnl,
                "message": (
                f"Paper SELL filled | price={price:.2f}, qty={qty:.6f}, "
                f"cash={state['cash_usdt']:.2f}, asset={state['asset_qty']:.6f}, "
                f"realized_pnl={realized_pnl:.2f}"
                ),
            }

        return {
            "executed": False,
            "message": f"Paper trade skipped: unsupported signal type '{signal_type}'.",
            "realized_pnl": None,
        }
