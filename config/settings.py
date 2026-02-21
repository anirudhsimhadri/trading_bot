import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _get_list(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    values = [item.strip() for item in raw.split(",") if item.strip()]
    return values or default


# Runtime configuration
BOT_MODE = os.getenv("BOT_MODE", "signals").strip().lower()
CHECK_INTERVAL_SECONDS = _get_int("CHECK_INTERVAL_SECONDS", 300)
REQUIRE_MARKET_HOURS = _get_bool("REQUIRE_MARKET_HOURS", True)
STATE_DIR = os.getenv("STATE_DIR", "data")
HEARTBEAT_CYCLES = _get_int("HEARTBEAT_CYCLES", 12)
DATA_STALE_AFTER_MINUTES = _get_int("DATA_STALE_AFTER_MINUTES", 240)

# Notification configuration
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Bot link format (you can access this via f-string)
BOT_LINK = f"https://t.me/ani_tradingbot"

# Trading pairs configuration
SYMBOL = os.getenv("SYMBOL", "NQ=F")
SYMBOLS = _get_list("SYMBOLS", [SYMBOL])
ACTIVE_SYMBOL = os.getenv("ACTIVE_SYMBOL", SYMBOLS[0] if SYMBOLS else SYMBOL)
TIMEFRAME = os.getenv("TIMEFRAME", "15m")
# Yahoo Finance intraday limits mean 15m data is only available for shorter windows.
PERIOD = os.getenv("PERIOD", "60d")

# Technical indicators parameters
RSI_PERIOD = _get_int("RSI_PERIOD", 14)
RSI_OVERBOUGHT = _get_int("RSI_OVERBOUGHT", 70)
RSI_OVERSOLD = _get_int("RSI_OVERSOLD", 30)
MACD_FAST = _get_int("MACD_FAST", 12)
MACD_SLOW = _get_int("MACD_SLOW", 26)
MACD_SIGNAL = _get_int("MACD_SIGNAL", 9)
STRATEGY_MIN_ADX = _get_float("STRATEGY_MIN_ADX", 18.0)
STRATEGY_MIN_VOLUME_MULTIPLIER = _get_float("STRATEGY_MIN_VOLUME_MULTIPLIER", 1.0)
STRATEGY_MAX_LONG_RSI = _get_float("STRATEGY_MAX_LONG_RSI", 55.0)
STRATEGY_MIN_SHORT_RSI = _get_float("STRATEGY_MIN_SHORT_RSI", 45.0)
STRATEGY_MIN_SIGNAL_SCORE = _get_int("STRATEGY_MIN_SIGNAL_SCORE", 4)

# Market hours (EST)
MARKET_OPEN_HOUR = _get_int("MARKET_OPEN_HOUR", 9)
MARKET_OPEN_MINUTE = _get_int("MARKET_OPEN_MINUTE", 30)
MARKET_CLOSE_HOUR = _get_int("MARKET_CLOSE_HOUR", 16)

# Trading parameters
POSITION_SIZE = _get_float("POSITION_SIZE", 1)
MAX_POSITIONS = _get_int("MAX_POSITIONS", 5)
STOP_LOSS_PCT = _get_float("STOP_LOSS_PCT", 0.02)
TAKE_PROFIT_PCT = _get_float("TAKE_PROFIT_PCT", 0.04)

# Backtesting parameters
INITIAL_CAPITAL = 100000  # $100,000 initial capital
COMMISSION_PCT = 0.001  # 0.1% commission per trade

# Paper trading configuration
PAPER_INITIAL_BALANCE_USDT = _get_float("PAPER_INITIAL_BALANCE_USDT", 10000.0)
PAPER_ORDER_SIZE_USDT = _get_float("PAPER_ORDER_SIZE_USDT", 250.0)

# Risk management configuration
MAX_DAILY_LOSS_PCT = _get_float("MAX_DAILY_LOSS_PCT", 2.0)
MAX_TRADE_RISK_PCT = _get_float("MAX_TRADE_RISK_PCT", 1.0)
MAX_TRADES_PER_DAY = _get_int("MAX_TRADES_PER_DAY", 6)
COOLDOWN_AFTER_LOSS_MINUTES = _get_int("COOLDOWN_AFTER_LOSS_MINUTES", 30)
MAX_CONSECUTIVE_LOSSES = _get_int("MAX_CONSECUTIVE_LOSSES", 3)

# Binance testnet configuration
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET")
BINANCE_SYMBOL = os.getenv("BINANCE_SYMBOL", "BTC/USDT")
BINANCE_ORDER_SIZE_USDT = _get_float("BINANCE_ORDER_SIZE_USDT", 50.0)
BINANCE_TESTNET_PUBLIC_API = os.getenv("BINANCE_TESTNET_PUBLIC_API", "https://testnet.binance.vision/api")
BINANCE_TESTNET_PRIVATE_API = os.getenv("BINANCE_TESTNET_PRIVATE_API", "https://testnet.binance.vision/api")


def validate_settings() -> list[str]:
    warnings: list[str] = []
    allowed_modes = {"signals", "paper", "binance_testnet", "robinhood"}

    if BOT_MODE not in allowed_modes:
        raise ValueError(f"Invalid BOT_MODE '{BOT_MODE}'. Allowed: {sorted(allowed_modes)}")
    if CHECK_INTERVAL_SECONDS < 1:
        raise ValueError("CHECK_INTERVAL_SECONDS must be >= 1.")
    if HEARTBEAT_CYCLES < 0:
        raise ValueError("HEARTBEAT_CYCLES must be >= 0.")
    if DATA_STALE_AFTER_MINUTES < 1:
        raise ValueError("DATA_STALE_AFTER_MINUTES must be >= 1.")
    if PAPER_INITIAL_BALANCE_USDT <= 0:
        raise ValueError("PAPER_INITIAL_BALANCE_USDT must be > 0.")
    if PAPER_ORDER_SIZE_USDT <= 0:
        raise ValueError("PAPER_ORDER_SIZE_USDT must be > 0.")
    if BINANCE_ORDER_SIZE_USDT <= 0:
        raise ValueError("BINANCE_ORDER_SIZE_USDT must be > 0.")
    if not SYMBOLS:
        raise ValueError("SYMBOLS must include at least one symbol.")
    if ACTIVE_SYMBOL not in SYMBOLS:
        warnings.append(f"ACTIVE_SYMBOL '{ACTIVE_SYMBOL}' is not in SYMBOLS. Runtime will default to first symbol.")
    if MAX_DAILY_LOSS_PCT <= 0 or MAX_DAILY_LOSS_PCT > 20:
        raise ValueError("MAX_DAILY_LOSS_PCT must be > 0 and <= 20.")
    if MAX_TRADE_RISK_PCT <= 0 or MAX_TRADE_RISK_PCT > 10:
        raise ValueError("MAX_TRADE_RISK_PCT must be > 0 and <= 10.")
    if MAX_TRADES_PER_DAY < 1:
        raise ValueError("MAX_TRADES_PER_DAY must be >= 1.")
    if COOLDOWN_AFTER_LOSS_MINUTES < 0:
        raise ValueError("COOLDOWN_AFTER_LOSS_MINUTES must be >= 0.")
    if MAX_CONSECUTIVE_LOSSES < 1:
        raise ValueError("MAX_CONSECUTIVE_LOSSES must be >= 1.")

    if bool(TELEGRAM_TOKEN) != bool(TELEGRAM_CHAT_ID):
        warnings.append(
            "Only one Telegram variable is set. Set both TELEGRAM_TOKEN and TELEGRAM_CHAT_ID to enable alerts."
        )

    if BOT_MODE == "binance_testnet":
        if not BINANCE_API_KEY or not BINANCE_API_SECRET:
            raise ValueError("BINANCE_API_KEY and BINANCE_API_SECRET are required for binance_testnet mode.")
        if not BINANCE_SYMBOL:
            raise ValueError("BINANCE_SYMBOL is required for binance_testnet mode.")

    return warnings
