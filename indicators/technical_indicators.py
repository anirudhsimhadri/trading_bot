from ta.trend import MACD, EMAIndicator, ADXIndicator
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange
import pandas as pd

class TechnicalIndicators:
    @staticmethod
    def add_indicators(df: pd.DataFrame, rsi_period: int, 
                      macd_fast: int, macd_slow: int, macd_signal: int) -> pd.DataFrame:
        if df.empty or "Close" not in df.columns:
            return df

        # Calculate RSI
        rsi = RSIIndicator(close=df['Close'], window=rsi_period)
        df['RSI'] = rsi.rsi()

        # Calculate MACD
        macd = MACD(close=df['Close'], 
                    window_slow=macd_slow,
                    window_fast=macd_fast,
                    window_sign=macd_signal)
        
        df['MACD'] = macd.macd()
        df['MACD_Signal'] = macd.macd_signal()
        df['MACD_Hist'] = macd.macd_diff()
        df["MACD_Cross_Up"] = (df["MACD"] > df["MACD_Signal"]) & (df["MACD"].shift(1) <= df["MACD_Signal"].shift(1))
        df["MACD_Cross_Down"] = (df["MACD"] < df["MACD_Signal"]) & (df["MACD"].shift(1) >= df["MACD_Signal"].shift(1))

        # Trend regime
        df["EMA20"] = EMAIndicator(close=df["Close"], window=20).ema_indicator()
        df["EMA50"] = EMAIndicator(close=df["Close"], window=50).ema_indicator()
        df["EMA200"] = EMAIndicator(close=df["Close"], window=200).ema_indicator()

        # Strength and volatility filters
        if {"High", "Low", "Close"}.issubset(df.columns):
            adx = ADXIndicator(high=df["High"], low=df["Low"], close=df["Close"], window=14)
            atr = AverageTrueRange(high=df["High"], low=df["Low"], close=df["Close"], window=14)
            df["ADX"] = adx.adx()
            df["ATR"] = atr.average_true_range()
        else:
            df["ADX"] = float("nan")
            df["ATR"] = float("nan")

        # Volume confirmation
        if "Volume" in df.columns:
            df["Volume_SMA20"] = df["Volume"].rolling(window=20).mean()
        else:
            df["Volume_SMA20"] = float("nan")

        # Calculate trend deviations
        df['SMA20'] = df['Close'].rolling(window=20).mean()
        df['STD20'] = df['Close'].rolling(window=20).std()
        df['Upper_Band'] = df['SMA20'] + (df['STD20'] * 2)
        df['Lower_Band'] = df['SMA20'] - (df['STD20'] * 2)

        return df

