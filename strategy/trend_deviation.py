import time
import pandas as pd
import yfinance as yf

from config import settings
from indicators.technical_indicators import TechnicalIndicators


class TrendDeviationStrategy:
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.security_type = settings.get_security_type(symbol)
        self.profile = settings.strategy_profile(symbol)
        self.required_price_columns = ["Open", "High", "Low", "Close", "Volume"]
        self._htf_direction_cache: dict | None = None

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
            max_zero_volume_pct = settings.max_zero_volume_pct_for_symbol(self.symbol)
            if zero_volume_pct > max_zero_volume_pct:
                print(
                    f"Data quality warning for {self.symbol}: "
                    f"zero-volume bars {zero_volume_pct:.2f}% exceeds "
                    f"{max_zero_volume_pct:.2f}%."
                )
                return pd.DataFrame()

        return df

    def _build_higher_timeframe_cache(self, df: pd.DataFrame) -> dict:
        if not settings.ENABLE_HIGHER_TIMEFRAME_CONFIRMATION:
            return {}
        if df.empty or "Close" not in df.columns:
            return {}
        if not isinstance(df.index, pd.DatetimeIndex):
            return {}

        rule = str(settings.HIGHER_TIMEFRAME_RESAMPLE_RULE).strip()
        if not rule:
            return {}

        close = pd.to_numeric(df["Close"], errors="coerce").dropna()
        if close.empty:
            return {}

        htf_close = close.resample(rule).last().dropna()
        if htf_close.empty:
            return {}
        if len(htf_close) < int(settings.HIGHER_TIMEFRAME_MIN_BARS):
            return {}

        ema_fast = htf_close.ewm(span=50, adjust=False).mean()
        ema_slow = htf_close.ewm(span=200, adjust=False).mean()
        direction = pd.Series("neutral", index=htf_close.index, dtype="object")
        direction = direction.mask(ema_fast > ema_slow, "up")
        direction = direction.mask(ema_fast < ema_slow, "down")
        mapped = direction.reindex(df.index, method="ffill").fillna("neutral")
        return mapped.to_dict()

    def _higher_timeframe_direction(self, df: pd.DataFrame, i: int) -> str:
        if not settings.ENABLE_HIGHER_TIMEFRAME_CONFIRMATION:
            return "neutral"
        if self._htf_direction_cache is None:
            self._htf_direction_cache = self._build_higher_timeframe_cache(df)
        if not self._htf_direction_cache:
            return "neutral"
        return str(self._htf_direction_cache.get(df.index[i], "neutral"))

    def _volume_ok(self, curr, multiplier: float, allow_bypass: bool) -> bool:
        volume = curr.get("Volume")
        volume_sma = curr.get("Volume_SMA20")
        if pd.isna(volume) or pd.isna(volume_sma):
            return bool(allow_bypass)
        volume = float(volume)
        volume_sma = float(volume_sma)
        if volume_sma <= 0:
            return bool(allow_bypass)
        return bool(volume >= (volume_sma * multiplier) or allow_bypass)

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
        strategy_name: str,
        regime: str,
        regime_confidence: float,
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
            "atr": float(df["ATR"].iloc[i]) if "ATR" in df.columns and not pd.isna(df["ATR"].iloc[i]) else 0.0,
            "score": score,
            "strategy": strategy_name,
            "regime": regime,
            "regime_confidence": regime_confidence,
            "features": [name for name, is_on in feature_flags.items() if is_on],
        }

    def _regime_context(self, df: pd.DataFrame, i: int) -> dict:
        curr = df.iloc[i]
        required = ["Close", "ADX", "EMA50", "EMA200", "Upper_Band", "Lower_Band"]
        if any(pd.isna(curr.get(col)) for col in required):
            return {"regime": "neutral", "confidence": 0.0}

        close = float(curr["Close"])
        if close <= 0:
            return {"regime": "neutral", "confidence": 0.0}

        lookback = max(5, int(settings.REGIME_LOOKBACK_BARS))
        start = max(0, i - lookback + 1)
        window = df.iloc[start : i + 1]
        adx_now = float(curr["ADX"])
        adx_avg = float(window["ADX"].dropna().mean()) if not window["ADX"].dropna().empty else adx_now
        ema_gap = abs(float(curr["EMA50"]) - float(curr["EMA200"])) / close
        band_width = max(float(curr["Upper_Band"]) - float(curr["Lower_Band"]), 0.0) / close

        trend_score = sum(
            [
                adx_now >= float(settings.REGIME_TREND_ADX_HIGH),
                ema_gap >= float(settings.REGIME_TREND_EMA_GAP_PCT),
                band_width >= float(settings.REGIME_TREND_BANDWIDTH_PCT),
                adx_now >= adx_avg,
            ]
        )
        choppy_score = sum(
            [
                adx_now <= float(settings.REGIME_CHOPPY_ADX_LOW),
                ema_gap <= float(settings.REGIME_CHOPPY_EMA_GAP_PCT),
                band_width <= float(settings.REGIME_CHOPPY_BANDWIDTH_PCT),
                adx_now <= adx_avg,
            ]
        )

        if trend_score >= 3 and trend_score > choppy_score:
            return {"regime": "trending", "confidence": float(trend_score) / 4.0}
        if choppy_score >= 3 and choppy_score > trend_score:
            return {"regime": "choppy", "confidence": float(choppy_score) / 4.0}
        return {"regime": "neutral", "confidence": max(float(trend_score), float(choppy_score)) / 4.0}

    def _regime_confirmed(self, df: pd.DataFrame, i: int, regime: str) -> bool:
        if regime not in {"trending", "choppy"}:
            return True

        confirm_bars = max(1, int(settings.REGIME_CONFIRM_BARS))
        start = i - confirm_bars + 1
        if start < 1:
            return False

        for idx in range(start, i + 1):
            if str(self._regime_context(df, idx).get("regime", "neutral")) != regime:
                return False
        return True

    def _evaluate_trend_signal(self, df: pd.DataFrame, i: int, regime_ctx: dict):
        curr = df.iloc[i]
        prev = df.iloc[i - 1]
        profile = self.profile

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
        regime = str(regime_ctx.get("regime", "neutral"))
        regime_conf = float(regime_ctx.get("confidence", 0.0))

        # Regime filters
        uptrend = curr["EMA50"] > curr["EMA200"] and curr["Close"] > curr["EMA200"]
        downtrend = curr["EMA50"] < curr["EMA200"] and curr["Close"] < curr["EMA200"]
        adx_ok = curr["ADX"] >= float(profile["trend_min_adx"])
        if not adx_ok:
            return None
        if not (uptrend or downtrend):
            return None
        htf_direction = self._higher_timeframe_direction(df, i)
        htf_long_ok = (not settings.ENABLE_HIGHER_TIMEFRAME_CONFIRMATION) or htf_direction in {"up", "neutral"}
        htf_short_ok = (not settings.ENABLE_HIGHER_TIMEFRAME_CONFIRMATION) or htf_direction in {"down", "neutral"}

        # Pullback + momentum confirmation
        long_pullback = curr["Close"] <= curr["EMA20"] or curr["Close"] <= curr["SMA20"]
        short_pullback = curr["Close"] >= curr["EMA20"] or curr["Close"] >= curr["SMA20"]
        long_momentum = (
            bool(curr["MACD_Cross_Up"])
            and settings.RSI_OVERSOLD <= curr["RSI"] <= float(profile["trend_max_long_rsi"])
        )
        short_momentum = (
            bool(curr["MACD_Cross_Down"])
            and float(profile["trend_min_short_rsi"]) <= curr["RSI"] <= settings.RSI_OVERBOUGHT
        )

        # Vol/volume filters
        vol_ok = self._volume_ok(
            curr,
            float(profile["trend_min_volume_mult"]),
            bool(profile["allow_volume_bypass"]),
        )
        band_bias_long = curr["Close"] <= (curr["Upper_Band"] - (curr["Upper_Band"] - curr["Lower_Band"]) * 0.35)
        band_bias_short = curr["Close"] >= (curr["Lower_Band"] + (curr["Upper_Band"] - curr["Lower_Band"]) * 0.65)
        long_rsi_slope = prev["RSI"] <= curr["RSI"]
        short_rsi_slope = prev["RSI"] >= curr["RSI"]

        long_flags = {
            "strategy_trend": True,
            f"regime_{regime}": True,
            f"security_{self.security_type}": True,
            "trend": bool(uptrend),
            "adx": bool(adx_ok),
            "pullback": bool(long_pullback),
            "momentum": bool(long_momentum),
            "volume": bool(vol_ok),
            "band_bias": bool(band_bias_long),
            "rsi_slope": bool(long_rsi_slope),
            "htf_confirm": bool(htf_long_ok),
        }
        short_flags = {
            "strategy_trend": True,
            f"regime_{regime}": True,
            f"security_{self.security_type}": True,
            "trend": bool(downtrend),
            "adx": bool(adx_ok),
            "pullback": bool(short_pullback),
            "momentum": bool(short_momentum),
            "volume": bool(vol_ok),
            "band_bias": bool(band_bias_short),
            "rsi_slope": bool(short_rsi_slope),
            "htf_confirm": bool(htf_short_ok),
        }

        long_score = sum(
            [uptrend, adx_ok, long_pullback, long_momentum, vol_ok, band_bias_long, htf_long_ok]
        )
        short_score = sum(
            [downtrend, adx_ok, short_pullback, short_momentum, vol_ok, band_bias_short, htf_short_ok]
        )

        if long_score >= settings.STRATEGY_MIN_SIGNAL_SCORE and long_rsi_slope and htf_long_ok:
            return self._signal_payload(
                df,
                i,
                "LONG",
                long_score,
                "trend",
                regime,
                regime_conf,
                long_flags,
            )
        if short_score >= settings.STRATEGY_MIN_SIGNAL_SCORE and short_rsi_slope and htf_short_ok:
            return self._signal_payload(
                df,
                i,
                "SHORT",
                short_score,
                "trend",
                regime,
                regime_conf,
                short_flags,
            )
        return None

    def _evaluate_mean_reversion_signal(self, df: pd.DataFrame, i: int, regime_ctx: dict):
        curr = df.iloc[i]
        prev = df.iloc[i - 1]
        profile = self.profile

        required = [
            "Close",
            "SMA20",
            "STD20",
            "Upper_Band",
            "Lower_Band",
            "RSI",
            "Volume",
            "Volume_SMA20",
            "ADX",
            "MACD",
            "MACD_Hist",
        ]
        if any(pd.isna(curr.get(col)) for col in required):
            return None
        if pd.isna(prev.get("RSI")):
            return None
        if pd.isna(prev.get("MACD_Hist")):
            return None

        regime = str(regime_ctx.get("regime", "neutral"))
        regime_conf = float(regime_ctx.get("confidence", 0.0))
        close = float(curr["Close"])
        std20 = float(curr["STD20"])
        sma20 = float(curr["SMA20"])
        upper = float(curr["Upper_Band"])
        lower = float(curr["Lower_Band"])
        if close <= 0 or std20 <= 0:
            return None

        zscore = (close - sma20) / std20
        vol_ok = self._volume_ok(
            curr,
            float(profile["mean_min_volume_mult"]),
            bool(profile["allow_volume_bypass"]),
        )
        zscore_entry = float(profile["mean_zscore_entry"])
        long_extreme = close <= lower or zscore <= -zscore_entry
        short_extreme = close >= upper or zscore >= zscore_entry
        macd_reversal_long = curr["MACD_Hist"] >= prev["MACD_Hist"]
        macd_reversal_short = curr["MACD_Hist"] <= prev["MACD_Hist"]
        long_reversal = (
            curr["RSI"] <= float(profile["mean_rsi_long_max"])
            and curr["RSI"] >= prev["RSI"]
            and macd_reversal_long
        )
        short_reversal = (
            curr["RSI"] >= float(profile["mean_rsi_short_min"])
            and curr["RSI"] <= prev["RSI"]
            and macd_reversal_short
        )
        long_location = close <= sma20
        short_location = close >= sma20
        low_adx = curr["ADX"] <= settings.REGIME_CHOPPY_ADX_LOW
        htf_direction = self._higher_timeframe_direction(df, i)
        htf_long_ok = (not settings.ENABLE_HIGHER_TIMEFRAME_CONFIRMATION) or htf_direction != "down"
        htf_short_ok = (not settings.ENABLE_HIGHER_TIMEFRAME_CONFIRMATION) or htf_direction != "up"

        long_flags = {
            "strategy_mean_reversion": True,
            f"regime_{regime}": True,
            f"security_{self.security_type}": True,
            "zscore_extreme": bool(long_extreme),
            "rsi_reversal": bool(long_reversal),
            "macd_reversal": bool(macd_reversal_long),
            "volume": bool(vol_ok),
            "below_midline": bool(long_location),
            "adx": bool(low_adx),
            "htf_confirm": bool(htf_long_ok),
        }
        short_flags = {
            "strategy_mean_reversion": True,
            f"regime_{regime}": True,
            f"security_{self.security_type}": True,
            "zscore_extreme": bool(short_extreme),
            "rsi_reversal": bool(short_reversal),
            "macd_reversal": bool(macd_reversal_short),
            "volume": bool(vol_ok),
            "above_midline": bool(short_location),
            "adx": bool(low_adx),
            "htf_confirm": bool(htf_short_ok),
        }

        long_core_ok = long_extreme and long_reversal and long_location and low_adx and htf_long_ok
        short_core_ok = short_extreme and short_reversal and short_location and low_adx and htf_short_ok

        long_score = sum(
            [
                long_extreme,
                long_reversal,
                macd_reversal_long,
                vol_ok,
                long_location,
                zscore < 0,
                low_adx,
                htf_long_ok,
            ]
        )
        short_score = sum(
            [
                short_extreme,
                short_reversal,
                macd_reversal_short,
                vol_ok,
                short_location,
                zscore > 0,
                low_adx,
                htf_short_ok,
            ]
        )
        min_score = int(profile["mean_min_signal_score"])

        if long_core_ok and long_score >= min_score:
            return self._signal_payload(
                df,
                i,
                "LONG",
                long_score,
                "mean_reversion",
                regime,
                regime_conf,
                long_flags,
            )
        if short_core_ok and short_score >= min_score:
            return self._signal_payload(
                df,
                i,
                "SHORT",
                short_score,
                "mean_reversion",
                regime,
                regime_conf,
                short_flags,
            )
        return None

    def _evaluate_signal(self, df: pd.DataFrame, i: int):
        regime_ctx = self._regime_context(df, i)
        regime = str(regime_ctx.get("regime", "neutral"))
        if not self._regime_confirmed(df, i, regime):
            return None

        trend_signal = None
        mean_signal = None
        if regime == "trending":
            trend_signal = self._evaluate_trend_signal(df, i, regime_ctx)
        elif regime == "choppy":
            mean_signal = self._evaluate_mean_reversion_signal(df, i, regime_ctx)
        elif settings.ALLOW_NEUTRAL_REGIME_TRADES:
            trend_signal = self._evaluate_trend_signal(df, i, regime_ctx)
            mean_signal = self._evaluate_mean_reversion_signal(df, i, regime_ctx)

        if regime == "trending":
            return trend_signal
        if regime == "choppy":
            return mean_signal
        if not settings.ALLOW_NEUTRAL_REGIME_TRADES:
            return None

        candidates = [s for s in [trend_signal, mean_signal] if s]
        if not candidates:
            return None
        candidates.sort(
            key=lambda s: (
                float(s.get("score", 0.0)),
                float(s.get("regime_confidence", 0.0)),
            ),
            reverse=True,
        )
        return candidates[0]

    def generate_signals(self, df: pd.DataFrame) -> list[dict]:
        self._htf_direction_cache = self._build_higher_timeframe_cache(df)
        signals: list[dict] = []
        start_i = max(1, settings.MIN_SIGNAL_WARMUP_BARS - 1)
        for i in range(start_i, len(df)):
            signal = self._evaluate_signal(df, i)
            if signal:
                signals.append(signal)
        return signals

    def generate_latest_signal(self, df: pd.DataFrame):
        if df is None:
            return None

        if len(df) < settings.MIN_SIGNAL_WARMUP_BARS:
            return None
        self._htf_direction_cache = self._build_higher_timeframe_cache(df)

        if settings.USE_LAST_CLOSED_CANDLE:
            if len(df) < max(settings.MIN_SIGNAL_WARMUP_BARS, 3):
                return None
            return self._evaluate_signal(df, len(df) - 2)

        if len(df) < max(settings.MIN_SIGNAL_WARMUP_BARS, 2):
            return None
        return self._evaluate_signal(df, len(df) - 1)

    def format_alert_message(self, signal: dict) -> str:
        return (
            f"🚨 {signal['symbol']} ALERT 🚨\n"
            f"Model: {signal.get('strategy', 'unknown')} | Regime: {signal.get('regime', 'n/a')} "
            f"({float(signal.get('regime_confidence', 0.0)):.2f})\n"
            f"Signal: {signal['type']} (score {signal['score']})\n"
            f"Time: {signal['timestamp']}\n"
            f"Price: ${signal['price']:.2f}\n"
            f"RSI: {signal['rsi']:.2f}\n"
            f"MACD: {signal['macd']:.2f}\n"
            f"ADX: {signal['adx']:.2f}"
        )
