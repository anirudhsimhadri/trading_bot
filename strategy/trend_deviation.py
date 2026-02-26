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

    def _interval_to_seconds(self, interval: str) -> int | None:
        val = interval.strip().lower()
        if len(val) < 2:
            return None
        unit = val[-1]
        size = val[:-1]
        if not size.isdigit():
            return None
        n = int(size)
        if unit == "m":
            return n * 60
        if unit == "h":
            return n * 3600
        if unit == "d":
            return n * 86400
        if unit == "w":
            return n * 604800
        return None

    def _sanitize_data(self, df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
        if df.empty:
            return df

        df = self._normalize_columns(df)
        df = df[~df.index.duplicated(keep="last")].sort_index()
        missing = [col for col in self.required_price_columns if col not in df.columns]
        if missing:
            return pd.DataFrame()

        if isinstance(df.index, pd.DatetimeIndex):
            if df.index.tz is None:
                df.index = df.index.tz_localize("UTC")
            else:
                df.index = df.index.tz_convert("UTC")

        for col in self.required_price_columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=self.required_price_columns)

        # Reject rows that violate basic OHLC consistency.
        ohlc_ok = (
            (df["Open"] > 0)
            & (df["High"] > 0)
            & (df["Low"] > 0)
            & (df["Close"] > 0)
            & (df["Volume"] >= 0)
            & (df["High"] >= df[["Open", "Close", "Low"]].max(axis=1))
            & (df["Low"] <= df[["Open", "Close", "High"]].min(axis=1))
        )
        df = df[ohlc_ok]
        if df.empty:
            return pd.DataFrame()

        # Reject datasets with excessive bar gaps.
        expected_seconds = self._interval_to_seconds(timeframe)
        if expected_seconds and len(df) > 1:
            diffs = df.index.to_series().diff().dropna().dt.total_seconds()
            large_gaps = diffs[diffs > (expected_seconds * settings.MAX_ALLOWED_GAP_MULTIPLIER)]
            if not large_gaps.empty:
                missing_estimate = int(((large_gaps / expected_seconds) - 1).clip(lower=0).sum())
                expected_total = max(len(df) + missing_estimate, 1)
                missing_pct = (missing_estimate / expected_total) * 100.0
                if missing_pct > settings.MAX_MISSING_BARS_PCT:
                    print(
                        f"Data quality warning for {self.symbol}: "
                        f"missing bars estimate {missing_pct:.2f}% exceeds "
                        f"{settings.MAX_MISSING_BARS_PCT:.2f}%."
                    )
                    return pd.DataFrame()

        if "Volume" in df.columns and len(df) > 0:
            zero_volume_pct = float((df["Volume"] <= 0).mean() * 100.0)
            if zero_volume_pct > settings.MAX_ZERO_VOLUME_PCT:
                print(
                    f"Data quality warning for {self.symbol}: "
                    f"zero-volume bars {zero_volume_pct:.2f}% exceeds "
                    f"{settings.MAX_ZERO_VOLUME_PCT:.2f}%."
                )
                return pd.DataFrame()

        return df

    def _download_data(self, period: str, timeframe: str) -> pd.DataFrame:
        retries = 3
        last_exception: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                df = yf.download(
                    self.symbol,
                    period=period,
                    interval=timeframe,
                    progress=False,
                    auto_adjust=False,
                )
                df = self._sanitize_data(df, timeframe)
                if not df.empty:
                    return df
            except Exception as exc:
                last_exception = exc

            if attempt < retries:
                time.sleep(attempt)

        if last_exception is not None:
            print(f"Data download warning for {self.symbol}: {last_exception}")
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

    def _signal_payload(
        self,
        df: pd.DataFrame,
        i: int,
        signal_type: str,
        score: int,
        feature_flags: dict[str, bool],
    ) -> dict:
        return {
            "symbol": self.symbol,
            "timestamp": df.index[i],
            "type": signal_type,
            "price": float(df["Close"].iloc[i]),
            "rsi": float(df["RSI"].iloc[i]),
            "macd": float(df["MACD"].iloc[i]),
            "adx": float(df["ADX"].iloc[i]),
            "score": score,
            "features": [name for name, is_on in feature_flags.items() if is_on],
        }

    def _evaluate_long_short(self, df: pd.DataFrame, i: int):
        curr = df.iloc[i]
        prev = df.iloc[i - 1]

        required = [
            "Close",
            "EMA20",
            "EMA50",
            "EMA200",
            "SMA20",
            "MACD",
            "MACD_Signal",
            "RSI",
            "ADX",
            "Volume",
            "Volume_SMA20",
            "Upper_Band",
            "Lower_Band",
        ]
        if any(pd.isna(curr.get(col)) for col in required):
            return None
        if pd.isna(prev.get("RSI")):
            return None

        # Regime filters
        uptrend = curr["EMA50"] > curr["EMA200"] and curr["Close"] > curr["EMA200"]
        downtrend = curr["EMA50"] < curr["EMA200"] and curr["Close"] < curr["EMA200"]
        adx_ok = curr["ADX"] >= settings.STRATEGY_MIN_ADX

        # Pullback + momentum confirmation
        long_pullback = curr["Close"] <= curr["EMA20"] or curr["Close"] <= curr["SMA20"]
        short_pullback = curr["Close"] >= curr["EMA20"] or curr["Close"] >= curr["SMA20"]
        long_momentum = (
            bool(curr["MACD_Cross_Up"])
            and settings.RSI_OVERSOLD <= curr["RSI"] <= settings.STRATEGY_MAX_LONG_RSI
        )
        short_momentum = (
            bool(curr["MACD_Cross_Down"])
            and settings.STRATEGY_MIN_SHORT_RSI <= curr["RSI"] <= settings.RSI_OVERBOUGHT
        )

        # Vol/volume filters
        vol_ok = curr["Volume"] >= (curr["Volume_SMA20"] * settings.STRATEGY_MIN_VOLUME_MULTIPLIER)
        band_bias_long = curr["Close"] <= (curr["Upper_Band"] - (curr["Upper_Band"] - curr["Lower_Band"]) * 0.35)
        band_bias_short = curr["Close"] >= (curr["Lower_Band"] + (curr["Upper_Band"] - curr["Lower_Band"]) * 0.65)
        long_rsi_slope = prev["RSI"] <= curr["RSI"]
        short_rsi_slope = prev["RSI"] >= curr["RSI"]

        long_flags = {
            "trend": bool(uptrend),
            "adx": bool(adx_ok),
            "pullback": bool(long_pullback),
            "momentum": bool(long_momentum),
            "volume": bool(vol_ok),
            "band_bias": bool(band_bias_long),
            "rsi_slope": bool(long_rsi_slope),
        }
        short_flags = {
            "trend": bool(downtrend),
            "adx": bool(adx_ok),
            "pullback": bool(short_pullback),
            "momentum": bool(short_momentum),
            "volume": bool(vol_ok),
            "band_bias": bool(band_bias_short),
            "rsi_slope": bool(short_rsi_slope),
        }

        long_score = sum(
            [uptrend, adx_ok, long_pullback, long_momentum, vol_ok, band_bias_long]
        )
        short_score = sum(
            [downtrend, adx_ok, short_pullback, short_momentum, vol_ok, band_bias_short]
        )

        if long_score >= settings.STRATEGY_MIN_SIGNAL_SCORE and long_rsi_slope:
            return self._signal_payload(df, i, "LONG", long_score, long_flags)
        if short_score >= settings.STRATEGY_MIN_SIGNAL_SCORE and short_rsi_slope:
            return self._signal_payload(df, i, "SHORT", short_score, short_flags)
        return None

    def generate_signals(self, df: pd.DataFrame) -> list[dict]:
        signals: list[dict] = []
        start_i = max(1, settings.MIN_SIGNAL_WARMUP_BARS - 1)
        for i in range(start_i, len(df)):
            signal = self._evaluate_long_short(df, i)
            if signal:
                signals.append(signal)
        return signals

    def generate_latest_signal(self, df: pd.DataFrame):
        if df is None:
            return None

        if len(df) < settings.MIN_SIGNAL_WARMUP_BARS:
            return None

        if settings.USE_LAST_CLOSED_CANDLE:
            if len(df) < max(settings.MIN_SIGNAL_WARMUP_BARS, 3):
                return None
            return self._evaluate_long_short(df, len(df) - 2)

        if len(df) < max(settings.MIN_SIGNAL_WARMUP_BARS, 2):
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
