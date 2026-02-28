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


def _get_optional_secret(name: str) -> str | None:
    raw = os.getenv(name)
    if raw is None:
        return None
    value = raw.strip()
    if not value:
        return None
    normalized = value.lower()
    if normalized in {"none", "null", "changeme"} or normalized.startswith("your_"):
        return None
    return value


# Runtime configuration
BOT_MODE = os.getenv("BOT_MODE", "signals").strip().lower()
CHECK_INTERVAL_SECONDS = _get_int("CHECK_INTERVAL_SECONDS", 300)
REQUIRE_MARKET_HOURS = _get_bool("REQUIRE_MARKET_HOURS", True)
STATE_DIR = os.getenv("STATE_DIR", "data")
HEARTBEAT_CYCLES = _get_int("HEARTBEAT_CYCLES", 12)
DATA_STALE_AFTER_MINUTES = _get_int("DATA_STALE_AFTER_MINUTES", 240)
USE_LAST_CLOSED_CANDLE = _get_bool("USE_LAST_CLOSED_CANDLE", True)
MIN_SIGNAL_WARMUP_BARS = _get_int("MIN_SIGNAL_WARMUP_BARS", 220)
ALLOW_POSITION_SCALING = _get_bool("ALLOW_POSITION_SCALING", False)

# Notification configuration
TELEGRAM_TOKEN = _get_optional_secret("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = _get_optional_secret("TELEGRAM_CHAT_ID")

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
ALLOW_NEUTRAL_REGIME_TRADES = _get_bool("ALLOW_NEUTRAL_REGIME_TRADES", False)
REGIME_LOOKBACK_BARS = _get_int("REGIME_LOOKBACK_BARS", 24)
REGIME_CONFIRM_BARS = _get_int("REGIME_CONFIRM_BARS", 2)
REGIME_TREND_ADX_HIGH = _get_float("REGIME_TREND_ADX_HIGH", 22.0)
REGIME_CHOPPY_ADX_LOW = _get_float("REGIME_CHOPPY_ADX_LOW", 16.0)
REGIME_TREND_EMA_GAP_PCT = _get_float("REGIME_TREND_EMA_GAP_PCT", 0.0025)
REGIME_CHOPPY_EMA_GAP_PCT = _get_float("REGIME_CHOPPY_EMA_GAP_PCT", 0.0012)
REGIME_TREND_BANDWIDTH_PCT = _get_float("REGIME_TREND_BANDWIDTH_PCT", 0.018)
REGIME_CHOPPY_BANDWIDTH_PCT = _get_float("REGIME_CHOPPY_BANDWIDTH_PCT", 0.012)
MEANREV_ZSCORE_ENTRY = _get_float("MEANREV_ZSCORE_ENTRY", 1.1)
MEANREV_RSI_LONG_MAX = _get_float("MEANREV_RSI_LONG_MAX", 38.0)
MEANREV_RSI_SHORT_MIN = _get_float("MEANREV_RSI_SHORT_MIN", 62.0)
MEANREV_MIN_VOLUME_MULTIPLIER = _get_float("MEANREV_MIN_VOLUME_MULTIPLIER", 0.8)
MEANREV_MIN_SIGNAL_SCORE = _get_int("MEANREV_MIN_SIGNAL_SCORE", 4)

# Market hours (EST)
MARKET_OPEN_HOUR = _get_int("MARKET_OPEN_HOUR", 9)
MARKET_OPEN_MINUTE = _get_int("MARKET_OPEN_MINUTE", 30)
MARKET_CLOSE_HOUR = _get_int("MARKET_CLOSE_HOUR", 16)

# Trading parameters
POSITION_SIZE = _get_float("POSITION_SIZE", 1)
STOP_LOSS_PCT = _get_float("STOP_LOSS_PCT", 0.02)
TAKE_PROFIT_PCT = _get_float("TAKE_PROFIT_PCT", 0.04)
TRAILING_STOP_PCT = _get_float("TRAILING_STOP_PCT", 0.015)
MAX_HOLD_BARS = _get_int("MAX_HOLD_BARS", 96)

# Backtesting parameters
INITIAL_CAPITAL = 100000  # $100,000 initial capital
COMMISSION_PCT = 0.001  # 0.1% commission per trade
BACKTEST_SPREAD_BPS = _get_float("BACKTEST_SPREAD_BPS", 2.0)
BACKTEST_SLIPPAGE_BPS = _get_float("BACKTEST_SLIPPAGE_BPS", 2.0)
BACKTEST_LATENCY_BARS = _get_int("BACKTEST_LATENCY_BARS", 1)
BACKTEST_PARTIAL_FILL_PCT = _get_float("BACKTEST_PARTIAL_FILL_PCT", 1.0)
REQUIRE_BACKTEST_PASS = _get_bool("REQUIRE_BACKTEST_PASS", True)
BACKTEST_LOOKBACK_PERIOD = os.getenv("BACKTEST_LOOKBACK_PERIOD", "6mo")
BACKTEST_MIN_TRADES = _get_int("BACKTEST_MIN_TRADES", 20)
BACKTEST_MIN_WIN_RATE_PCT = _get_float("BACKTEST_MIN_WIN_RATE_PCT", 45.0)
BACKTEST_MIN_PROFIT_FACTOR = _get_float("BACKTEST_MIN_PROFIT_FACTOR", 1.1)
USE_WALK_FORWARD_PRECHECK = _get_bool("USE_WALK_FORWARD_PRECHECK", True)
WALK_FORWARD_SPLITS = _get_int("WALK_FORWARD_SPLITS", 4)
WALK_FORWARD_MIN_BARS_PER_SPLIT = _get_int("WALK_FORWARD_MIN_BARS_PER_SPLIT", 120)
WALK_FORWARD_MIN_TRADES = _get_int("WALK_FORWARD_MIN_TRADES", 8)
WALK_FORWARD_MIN_WIN_RATE_PCT = _get_float("WALK_FORWARD_MIN_WIN_RATE_PCT", 42.0)
WALK_FORWARD_MIN_PROFIT_FACTOR = _get_float("WALK_FORWARD_MIN_PROFIT_FACTOR", 1.05)

# Data quality controls
MAX_MISSING_BARS_PCT = _get_float("MAX_MISSING_BARS_PCT", 5.0)
MAX_ALLOWED_GAP_MULTIPLIER = _get_float("MAX_ALLOWED_GAP_MULTIPLIER", 3.5)
MAX_ZERO_VOLUME_PCT = _get_float("MAX_ZERO_VOLUME_PCT", 20.0)

# Adaptive learning controls
SYMBOL_LEARNING_RATE = _get_float("SYMBOL_LEARNING_RATE", 0.2)
FEATURE_LEARNING_RATE = _get_float("FEATURE_LEARNING_RATE", 0.06)
FEATURE_WEIGHT_CLAMP = _get_float("FEATURE_WEIGHT_CLAMP", 0.5)

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
BINANCE_API_KEY = _get_optional_secret("BINANCE_API_KEY")
BINANCE_API_SECRET = _get_optional_secret("BINANCE_API_SECRET")
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
    if not isinstance(USE_LAST_CLOSED_CANDLE, bool):
        raise ValueError("USE_LAST_CLOSED_CANDLE must be a boolean.")
    if MIN_SIGNAL_WARMUP_BARS < 50:
        raise ValueError("MIN_SIGNAL_WARMUP_BARS must be >= 50.")
    if not isinstance(ALLOW_POSITION_SCALING, bool):
        raise ValueError("ALLOW_POSITION_SCALING must be a boolean.")
    if not isinstance(ALLOW_NEUTRAL_REGIME_TRADES, bool):
        raise ValueError("ALLOW_NEUTRAL_REGIME_TRADES must be a boolean.")
    if REGIME_LOOKBACK_BARS < 5 or REGIME_LOOKBACK_BARS > 500:
        raise ValueError("REGIME_LOOKBACK_BARS must be between 5 and 500.")
    if REGIME_CONFIRM_BARS < 1 or REGIME_CONFIRM_BARS > 20:
        raise ValueError("REGIME_CONFIRM_BARS must be between 1 and 20.")
    if REGIME_CONFIRM_BARS > REGIME_LOOKBACK_BARS:
        raise ValueError("REGIME_CONFIRM_BARS must be <= REGIME_LOOKBACK_BARS.")
    if REGIME_CHOPPY_ADX_LOW < 1 or REGIME_CHOPPY_ADX_LOW > 40:
        raise ValueError("REGIME_CHOPPY_ADX_LOW must be between 1 and 40.")
    if REGIME_TREND_ADX_HIGH < 1 or REGIME_TREND_ADX_HIGH > 60:
        raise ValueError("REGIME_TREND_ADX_HIGH must be between 1 and 60.")
    if REGIME_CHOPPY_ADX_LOW >= REGIME_TREND_ADX_HIGH:
        raise ValueError("REGIME_CHOPPY_ADX_LOW must be lower than REGIME_TREND_ADX_HIGH.")
    if REGIME_CHOPPY_EMA_GAP_PCT < 0 or REGIME_CHOPPY_EMA_GAP_PCT > 0.05:
        raise ValueError("REGIME_CHOPPY_EMA_GAP_PCT must be between 0 and 0.05.")
    if REGIME_TREND_EMA_GAP_PCT <= 0 or REGIME_TREND_EMA_GAP_PCT > 0.1:
        raise ValueError("REGIME_TREND_EMA_GAP_PCT must be > 0 and <= 0.1.")
    if REGIME_CHOPPY_EMA_GAP_PCT >= REGIME_TREND_EMA_GAP_PCT:
        raise ValueError("REGIME_CHOPPY_EMA_GAP_PCT must be lower than REGIME_TREND_EMA_GAP_PCT.")
    if REGIME_CHOPPY_BANDWIDTH_PCT < 0 or REGIME_CHOPPY_BANDWIDTH_PCT > 0.2:
        raise ValueError("REGIME_CHOPPY_BANDWIDTH_PCT must be between 0 and 0.2.")
    if REGIME_TREND_BANDWIDTH_PCT <= 0 or REGIME_TREND_BANDWIDTH_PCT > 0.4:
        raise ValueError("REGIME_TREND_BANDWIDTH_PCT must be > 0 and <= 0.4.")
    if REGIME_CHOPPY_BANDWIDTH_PCT >= REGIME_TREND_BANDWIDTH_PCT:
        raise ValueError("REGIME_CHOPPY_BANDWIDTH_PCT must be lower than REGIME_TREND_BANDWIDTH_PCT.")
    if MEANREV_ZSCORE_ENTRY <= 0 or MEANREV_ZSCORE_ENTRY > 5:
        raise ValueError("MEANREV_ZSCORE_ENTRY must be > 0 and <= 5.")
    if MEANREV_RSI_LONG_MAX < 5 or MEANREV_RSI_LONG_MAX > 60:
        raise ValueError("MEANREV_RSI_LONG_MAX must be between 5 and 60.")
    if MEANREV_RSI_SHORT_MIN < 40 or MEANREV_RSI_SHORT_MIN > 95:
        raise ValueError("MEANREV_RSI_SHORT_MIN must be between 40 and 95.")
    if MEANREV_RSI_LONG_MAX >= MEANREV_RSI_SHORT_MIN:
        raise ValueError("MEANREV_RSI_LONG_MAX must be lower than MEANREV_RSI_SHORT_MIN.")
    if MEANREV_MIN_VOLUME_MULTIPLIER <= 0 or MEANREV_MIN_VOLUME_MULTIPLIER > 5:
        raise ValueError("MEANREV_MIN_VOLUME_MULTIPLIER must be > 0 and <= 5.")
    if MEANREV_MIN_SIGNAL_SCORE < 1 or MEANREV_MIN_SIGNAL_SCORE > 8:
        raise ValueError("MEANREV_MIN_SIGNAL_SCORE must be between 1 and 8.")
    if STOP_LOSS_PCT <= 0 or STOP_LOSS_PCT >= 0.5:
        raise ValueError("STOP_LOSS_PCT must be > 0 and < 0.5.")
    if TAKE_PROFIT_PCT <= 0 or TAKE_PROFIT_PCT >= 1.0:
        raise ValueError("TAKE_PROFIT_PCT must be > 0 and < 1.")
    if TRAILING_STOP_PCT < 0 or TRAILING_STOP_PCT >= 0.5:
        raise ValueError("TRAILING_STOP_PCT must be >= 0 and < 0.5.")
    if MAX_HOLD_BARS < 1:
        raise ValueError("MAX_HOLD_BARS must be >= 1.")
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
    if BACKTEST_MIN_TRADES < 1:
        raise ValueError("BACKTEST_MIN_TRADES must be >= 1.")
    if BACKTEST_MIN_WIN_RATE_PCT < 0 or BACKTEST_MIN_WIN_RATE_PCT > 100:
        raise ValueError("BACKTEST_MIN_WIN_RATE_PCT must be between 0 and 100.")
    if BACKTEST_MIN_PROFIT_FACTOR <= 0:
        raise ValueError("BACKTEST_MIN_PROFIT_FACTOR must be > 0.")
    if BACKTEST_SPREAD_BPS < 0 or BACKTEST_SPREAD_BPS > 100:
        raise ValueError("BACKTEST_SPREAD_BPS must be between 0 and 100.")
    if BACKTEST_SLIPPAGE_BPS < 0 or BACKTEST_SLIPPAGE_BPS > 100:
        raise ValueError("BACKTEST_SLIPPAGE_BPS must be between 0 and 100.")
    if BACKTEST_LATENCY_BARS < 0 or BACKTEST_LATENCY_BARS > 10:
        raise ValueError("BACKTEST_LATENCY_BARS must be between 0 and 10.")
    if BACKTEST_PARTIAL_FILL_PCT <= 0 or BACKTEST_PARTIAL_FILL_PCT > 1:
        raise ValueError("BACKTEST_PARTIAL_FILL_PCT must be > 0 and <= 1.")
    if WALK_FORWARD_SPLITS < 2:
        raise ValueError("WALK_FORWARD_SPLITS must be >= 2.")
    if WALK_FORWARD_MIN_BARS_PER_SPLIT < 30:
        raise ValueError("WALK_FORWARD_MIN_BARS_PER_SPLIT must be >= 30.")
    if WALK_FORWARD_MIN_TRADES < 1:
        raise ValueError("WALK_FORWARD_MIN_TRADES must be >= 1.")
    if WALK_FORWARD_MIN_WIN_RATE_PCT < 0 or WALK_FORWARD_MIN_WIN_RATE_PCT > 100:
        raise ValueError("WALK_FORWARD_MIN_WIN_RATE_PCT must be between 0 and 100.")
    if WALK_FORWARD_MIN_PROFIT_FACTOR <= 0:
        raise ValueError("WALK_FORWARD_MIN_PROFIT_FACTOR must be > 0.")
    if MAX_MISSING_BARS_PCT < 0 or MAX_MISSING_BARS_PCT > 50:
        raise ValueError("MAX_MISSING_BARS_PCT must be between 0 and 50.")
    if MAX_ALLOWED_GAP_MULTIPLIER < 1.0 or MAX_ALLOWED_GAP_MULTIPLIER > 20:
        raise ValueError("MAX_ALLOWED_GAP_MULTIPLIER must be between 1 and 20.")
    if MAX_ZERO_VOLUME_PCT < 0 or MAX_ZERO_VOLUME_PCT > 100:
        raise ValueError("MAX_ZERO_VOLUME_PCT must be between 0 and 100.")
    if SYMBOL_LEARNING_RATE < 0 or SYMBOL_LEARNING_RATE > 1:
        raise ValueError("SYMBOL_LEARNING_RATE must be between 0 and 1.")
    if FEATURE_LEARNING_RATE < 0 or FEATURE_LEARNING_RATE > 1:
        raise ValueError("FEATURE_LEARNING_RATE must be between 0 and 1.")
    if FEATURE_WEIGHT_CLAMP <= 0 or FEATURE_WEIGHT_CLAMP > 5:
        raise ValueError("FEATURE_WEIGHT_CLAMP must be > 0 and <= 5.")

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
