from __future__ import annotations

from datetime import datetime

import pytz

from config import settings


EST = pytz.timezone("US/Eastern")


def _now_est() -> datetime:
    return datetime.now(EST)


def _minutes_of_day(dt: datetime) -> int:
    return (dt.hour * 60) + dt.minute


def _in_time_window(current_minute: int, start_minute: int, end_minute: int) -> bool:
    if start_minute == end_minute:
        return False
    if start_minute < end_minute:
        return start_minute <= current_minute < end_minute
    return current_minute >= start_minute or current_minute < end_minute


def is_market_open(now_est: datetime | None = None) -> bool:
    current_time = now_est or _now_est()
    if current_time.weekday() >= 5:
        return False
    if current_time.hour < settings.MARKET_OPEN_HOUR or current_time.hour > settings.MARKET_CLOSE_HOUR:
        return False
    if current_time.hour == settings.MARKET_OPEN_HOUR and current_time.minute < settings.MARKET_OPEN_MINUTE:
        return False
    return True


def is_symbol_session_open(symbol: str, now_est: datetime | None = None) -> tuple[bool, str | None]:
    now_est = now_est or _now_est()
    sec_type = settings.get_security_type(symbol)
    weekday = now_est.weekday()  # Mon=0 ... Sun=6
    minute_now = _minutes_of_day(now_est)

    if sec_type == "etf" and settings.ETF_TRADE_RTH_ONLY:
        if weekday >= 5:
            return False, "ETF session closed (weekend)."
        start = (settings.ETF_SESSION_START_HOUR * 60) + settings.ETF_SESSION_START_MINUTE
        end = (settings.ETF_SESSION_END_HOUR * 60) + settings.ETF_SESSION_END_MINUTE
        if not _in_time_window(minute_now, start, end):
            return False, "ETF session filter blocked trade (outside configured RTH window)."
        return True, None

    if sec_type == "futures":
        # CME index futures: closed Fri 17:00 ET -> Sun 18:00 ET
        if weekday == 5:
            return False, "Futures session closed (Saturday)."
        if weekday == 4 and minute_now >= (17 * 60):
            return False, "Futures session closed after Friday settlement."
        if weekday == 6 and minute_now < (18 * 60):
            return False, "Futures session closed before Sunday reopen."

        if settings.FUTURES_AVOID_DAILY_MAINTENANCE:
            maint_start = (settings.FUTURES_MAINTENANCE_START_HOUR * 60) + settings.FUTURES_MAINTENANCE_START_MINUTE
            maint_end = (settings.FUTURES_MAINTENANCE_END_HOUR * 60) + settings.FUTURES_MAINTENANCE_END_MINUTE
            if _in_time_window(minute_now, maint_start, maint_end):
                return False, "Futures maintenance window block is active."
        return True, None

    return True, None


def is_in_blackout_window(now_est: datetime | None = None) -> tuple[bool, str | None]:
    if not settings.ENABLE_SCHEDULED_BLACKOUTS:
        return False, None

    now_est = now_est or _now_est()
    weekday = now_est.weekday()
    minute_now = _minutes_of_day(now_est)
    allowed_days = {int(str(d).strip()) for d in settings.BLACKOUT_WEEKDAYS if str(d).strip().isdigit()}
    if weekday not in allowed_days:
        return False, None

    for token in settings.BLACKOUT_WINDOWS_EST:
        raw = str(token).strip()
        if "-" not in raw:
            continue
        start_raw, end_raw = raw.split("-", 1)
        try:
            sh, sm = [int(x) for x in start_raw.split(":", 1)]
            eh, em = [int(x) for x in end_raw.split(":", 1)]
        except ValueError:
            continue
        start_min = (sh * 60) + sm
        end_min = (eh * 60) + em
        if _in_time_window(minute_now, start_min, end_min):
            return True, f"Scheduled blackout active ({raw} ET)."
    return False, None
