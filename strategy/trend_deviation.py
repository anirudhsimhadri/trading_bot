import time
import pandas as pd
import yfinance as yf

from config import settings
from indicators.technical_indicators import TechnicalIndicators


class TrendDeviationStrategy:
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.required_price_columns = ["Open", "High", "Low", "Close", "Volume"]

    def _fallback_period_for_interval(self, interval: str) -> str | None:
        intraday_limits = {
            "1m": "7d",
            "2m": "60d",
            "5m": "60d",
            "15m": "60d",
            "30m": "60d",
            "60m": "730d",
            "90m": "60d",
            "1h": "730d",
        }
        return intraday_limits.get(interval)

    def _normalize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [
                col[0] if isinstance(col, tuple) and len(col) > 0 else col
                for col in df.columns
            ]
        return df

    def _sanitize_data(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df

        df = self._normalize_columns(df)
        df = df[~df.index.duplicated(keep="last")].sort_index()
        missing = [col for col in self.required_price_columns if col not in df.columns]
        if missing:
            return pd.DataFrame()

        return df.dropna(subset=["Close"])

    def _download_data(self, period: str, timeframe: str) -> pd.DataFrame:
        retries = 3
        for attempt in range(1, retries + 1):
            try:
                df = yf.download(
                    self.symbol,
                    period=period,
                    interval=timeframe,
                    progress=False,
                    auto_adjust=False,
                )
                df = self._sanitize_data(df)
                if not df.empty:
                    return df
            except Exception:
                pass

            if attempt < retries:
                time.sleep(attempt)

        return pd.DataFrame()

    def get_data(self, period: str | None = None, timeframe: str | None = None) -> pd.DataFrame:
        effective_period = period or settings.PERIOD
        effective_timeframe = timeframe or settings.TIMEFRAME

        df = self._download_data(effective_period, effective_timeframe)
        if df.empty:
            fallback_period = self._fallback_period_for_interval(effective_timeframe)
            if fallback_period and fallback_period != effective_period:
                df = self._download_data(fallback_period, effective_timeframe)

        if df.empty:
            return df

        df = TechnicalIndicators.add_indicators(
            df,
            settings.RSI_PERIOD,
            settings.MACD_FAST,
            settings.MACD_SLOW,
            settings.MACD_SIGNAL,
        )

        required_signal_columns = [
            "Close",
            "RSI",
            "MACD",
            "MACD_Signal",
            "Upper_Band",
            "Lower_Band",
            "EMA50",
            "EMA200",
            "ADX",
            "Volume_SMA20",
        ]
        if any(col not in df.columns for col in required_signal_columns):
            return pd.DataFrame()
        return df

    def _signal_payload(self, df: pd.DataFrame, i: int, signal_type: str, score: int) -> dict:
        return {
            "symbol": self.symbol,
            "timestamp": df.index[i],
            "type": signal_type,
            "price": float(df["Close"].iloc[i]),
            "rsi": float(df["RSI"].iloc[i]),
            "macd": float(df["MACD"].iloc[i]),
            "adx": float(df["ADX"].iloc[i]),
            "score": score,
        }

    def _evaluate_long_short(self, df: pd.DataFrame, i: int):
        curr = df.iloc[i]
        prev = df.iloc[i - 1]

        # Regime filters
        uptrend = curr["EMA50"] > curr["EMA200"] and curr["Close"] > curr["EMA200"]
        downtrend = curr["EMA50"] < curr["EMA200"] and curr["Close"] < curr["EMA200"]
        adx_ok = curr["ADX"] >= settings.STRATEGY_MIN_ADX

        # Pullback + momentum confirmation
        long_pullback = curr["Close"] <= curr["EMA20"] or curr["Close"] <= curr["SMA20"]
        short_pullback = curr["Close"] >= curr["EMA20"] or curr["Close"] >= curr["SMA20"]
        long_momentum = bool(curr["MACD_Cross_Up"]) and curr["RSI"] <= settings.STRATEGY_MAX_LONG_RSI
        short_momentum = bool(curr["MACD_Cross_Down"]) and curr["RSI"] >= settings.STRATEGY_MIN_SHORT_RSI

        # Vol/volume filters
        vol_ok = curr["Volume"] >= (curr["Volume_SMA20"] * settings.STRATEGY_MIN_VOLUME_MULTIPLIER)
        band_bias_long = curr["Close"] <= (curr["Upper_Band"] - (curr["Upper_Band"] - curr["Lower_Band"]) * 0.35)
        band_bias_short = curr["Close"] >= (curr["Lower_Band"] + (curr["Upper_Band"] - curr["Lower_Band"]) * 0.65)

        long_score = sum([uptrend, adx_ok, long_pullback, long_momentum, vol_ok, band_bias_long])
        short_score = sum([downtrend, adx_ok, short_pullback, short_momentum, vol_ok, band_bias_short])

        if long_score >= settings.STRATEGY_MIN_SIGNAL_SCORE and prev["RSI"] <= curr["RSI"]:
            return self._signal_payload(df, i, "LONG", long_score)
        if short_score >= settings.STRATEGY_MIN_SIGNAL_SCORE and prev["RSI"] >= curr["RSI"]:
            return self._signal_payload(df, i, "SHORT", short_score)
        return None

    def generate_signals(self, df: pd.DataFrame) -> list[dict]:
        signals: list[dict] = []
        for i in range(1, len(df)):
            signal = self._evaluate_long_short(df, i)
            if signal:
                signals.append(signal)
        return signals

    def generate_latest_signal(self, df: pd.DataFrame):
        if df is None or len(df) < 2:
            return None
        return self._evaluate_long_short(df, len(df) - 1)

    def format_alert_message(self, signal: dict) -> str:
        return (
            f"🚨 {signal['symbol']} ALERT 🚨\n"
            f"Signal: {signal['type']} (score {signal['score']})\n"
            f"Time: {signal['timestamp']}\n"
            f"Price: ${signal['price']:.2f}\n"
            f"RSI: {signal['rsi']:.2f}\n"
            f"MACD: {signal['macd']:.2f}\n"
            f"ADX: {signal['adx']:.2f}"
        )
