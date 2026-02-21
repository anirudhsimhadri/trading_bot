from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Tuple

from config import settings


class RiskManager:
    def _today_key(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _ensure_risk_state(self, runtime_state: Dict[str, Any], equity: float) -> Dict[str, Any]:
        risk = runtime_state.get("risk", {})
        today = self._today_key()
        if risk.get("date") != today:
            risk = {
                "date": today,
                "day_start_equity": equity,
                "trades_today": 0,
                "realized_pnl_today": 0.0,
                "consecutive_losses": 0,
                "cooldown_until_utc": None,
                "blocked_reason": None,
            }
            runtime_state["risk"] = risk
        return risk

    def current_equity(self, executor, mark_price: float | None) -> float | None:
        if executor and hasattr(executor, "get_account_snapshot"):
            snapshot = executor.get_account_snapshot(mark_price)
            if snapshot and isinstance(snapshot.get("equity_usdt"), (float, int)):
                return float(snapshot["equity_usdt"])
        return None

    def suggested_order_notional(self, equity: float | None, configured_order_size: float) -> float:
        if equity is None:
            return configured_order_size
        capped = equity * (settings.MAX_TRADE_RISK_PCT / 100.0)
        if capped <= 0:
            return configured_order_size
        return min(configured_order_size, capped)

    def can_trade(self, runtime_state: Dict[str, Any], equity: float | None) -> Tuple[bool, str | None]:
        effective_equity = equity if equity is not None else settings.PAPER_INITIAL_BALANCE_USDT
        risk = self._ensure_risk_state(runtime_state, effective_equity)
        now = datetime.now(timezone.utc)

        cooldown_until = risk.get("cooldown_until_utc")
        if cooldown_until:
            try:
                until = datetime.fromisoformat(cooldown_until)
                if now < until:
                    return False, f"Cooldown active until {cooldown_until}"
            except ValueError:
                pass

        if risk.get("trades_today", 0) >= settings.MAX_TRADES_PER_DAY:
            return False, f"Max trades/day reached ({settings.MAX_TRADES_PER_DAY})"

        day_start = float(risk.get("day_start_equity", effective_equity))
        if day_start > 0 and equity is not None:
            drawdown_pct = ((equity - day_start) / day_start) * 100.0
            if drawdown_pct <= -settings.MAX_DAILY_LOSS_PCT:
                return False, (
                    f"Daily loss limit hit ({drawdown_pct:.2f}% <= -{settings.MAX_DAILY_LOSS_PCT:.2f}%)"
                )

        if int(risk.get("consecutive_losses", 0)) >= settings.MAX_CONSECUTIVE_LOSSES:
            return False, f"Max consecutive losses reached ({settings.MAX_CONSECUTIVE_LOSSES})"

        return True, None

    def record_trade(self, runtime_state: Dict[str, Any], realized_pnl: float | None) -> None:
        effective_equity = settings.PAPER_INITIAL_BALANCE_USDT
        risk = self._ensure_risk_state(runtime_state, effective_equity)
        risk["trades_today"] = int(risk.get("trades_today", 0)) + 1

        if realized_pnl is None:
            return

        risk["realized_pnl_today"] = float(risk.get("realized_pnl_today", 0.0)) + float(realized_pnl)
        if realized_pnl < 0:
            risk["consecutive_losses"] = int(risk.get("consecutive_losses", 0)) + 1
            if settings.COOLDOWN_AFTER_LOSS_MINUTES > 0:
                until = datetime.now(timezone.utc) + timedelta(minutes=settings.COOLDOWN_AFTER_LOSS_MINUTES)
                risk["cooldown_until_utc"] = until.isoformat()
        else:
            risk["consecutive_losses"] = 0
            risk["cooldown_until_utc"] = None

