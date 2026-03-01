import csv
import json
import os
from datetime import datetime, timezone
from typing import Dict, Any


class PaperTradeExecutor:
    def __init__(self, state_dir: str, initial_balance_usd: float, order_size_usd: float):
        self.state_dir = state_dir
        self.state_file = os.path.join(state_dir, "paper_state.json")
        self.trade_log_file = os.path.join(state_dir, "paper_trades.csv")
        self.order_size_usd = order_size_usd
        self.initial_balance_usd = initial_balance_usd
        self._ensure_state()

    def _default_state(self) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        return {
            "cash_usd": self.initial_balance_usd,
            "asset_qty": 0.0,
            "avg_entry_price": 0.0,
            "realized_pnl_total": 0.0,
            "created_at_utc": now,
            "updated_at_utc": now,
        }

    def _ensure_state(self) -> None:
        os.makedirs(self.state_dir, exist_ok=True)
        if not os.path.exists(self.state_file):
            state = self._default_state()
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
                        "notional_usd",
                        "cash_usd",
                        "asset_qty",
                    ]
                )

    def _load_state(self) -> Dict[str, Any]:
        defaults = self._default_state()
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                state = json.load(f)
        except (OSError, json.JSONDecodeError):
            self._save_state(defaults)
            return defaults

        if not isinstance(state, dict):
            self._save_state(defaults)
            return defaults

        if "cash_usd" not in state:
            legacy_cash = state.get("cash")
            if not isinstance(legacy_cash, (int, float)):
                for key, value in state.items():
                    if str(key).startswith("cash_") and isinstance(value, (int, float)):
                        legacy_cash = value
                        break
            if isinstance(legacy_cash, (int, float)):
                state["cash_usd"] = float(legacy_cash)

        defaults.update(state)
        return defaults

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
                    round(state["cash_usd"], 8),
                    round(state["asset_qty"], 8),
                ]
            )

    def get_account_snapshot(self, mark_price: float | None = None) -> Dict[str, Any]:
        state = self._load_state()
        if mark_price is None:
            mark_price = state.get("avg_entry_price", 0.0)
        equity = float(state["cash_usd"]) + float(state["asset_qty"]) * float(mark_price or 0.0)
        return {
            "cash_usd": float(state["cash_usd"]),
            "asset_qty": float(state["asset_qty"]),
            "avg_entry_price": float(state.get("avg_entry_price", 0.0)),
            "realized_pnl_total": float(state.get("realized_pnl_total", 0.0)),
            "equity_usd": float(equity),
        }

    def execute_signal(
        self,
        signal: Dict[str, Any],
        order_size_usd: float | None = None,
        close_position: bool = False,
    ) -> Dict[str, Any]:
        price = float(signal["price"])
        signal_type = signal["type"].upper()
        state = self._load_state()
        size = self.order_size_usd if order_size_usd is None else float(order_size_usd)

        if signal_type == "LONG":
            notional = min(size, float(state["cash_usd"]))
            if notional <= 0:
                return {"executed": False, "message": "Paper trade skipped: no USD cash available.", "realized_pnl": None}
            qty = notional / price

            prev_qty = float(state["asset_qty"])
            prev_avg = float(state.get("avg_entry_price", 0.0))
            new_qty = prev_qty + qty
            if new_qty > 0:
                weighted_avg = ((prev_qty * prev_avg) + (qty * price)) / new_qty
            else:
                weighted_avg = 0.0

            state["cash_usd"] -= notional
            state["asset_qty"] = new_qty
            state["avg_entry_price"] = weighted_avg
            action = "BUY"
            self._append_trade(action, price, qty, notional, state)
            self._save_state(state)
            return {
                "executed": True,
                "side": action,
                "qty": qty,
                "notional_usd": notional,
                "price": price,
                "realized_pnl": 0.0,
                "message": (
                f"Paper BUY filled | price={price:.2f}, qty={qty:.6f}, "
                f"cash={state['cash_usd']:.2f}, asset={state['asset_qty']:.6f}"
                ),
            }

        if signal_type == "SHORT":
            if float(state["asset_qty"]) <= 0:
                return {
                    "executed": False,
                    "message": "Paper SELL skipped: no asset inventory to sell.",
                    "realized_pnl": None,
                }
            max_qty = float(state["asset_qty"])
            if close_position:
                qty = max_qty
                notional = qty * price
            else:
                max_notional = max_qty * price
                notional = min(size, max_notional)
                qty = notional / price
            avg_entry = float(state.get("avg_entry_price", 0.0))
            realized_pnl = (price - avg_entry) * qty
            state["cash_usd"] += notional
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
                "notional_usd": notional,
                "price": price,
                "realized_pnl": realized_pnl,
                "message": (
                f"Paper SELL filled | price={price:.2f}, qty={qty:.6f}, "
                f"cash={state['cash_usd']:.2f}, asset={state['asset_qty']:.6f}, "
                f"realized_pnl={realized_pnl:.2f}"
                ),
            }

        return {
            "executed": False,
            "message": f"Paper trade skipped: unsupported signal type '{signal_type}'.",
            "realized_pnl": None,
        }
