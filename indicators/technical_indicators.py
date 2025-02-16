from ta.trend import MACD
from ta.momentum import RSIIndicator
import pandas as pd

class TechnicalIndicators:
    @staticmethod
    def add_indicators(df: pd.DataFrame, rsi_period: int, 
                      macd_fast: int, macd_slow: int, macd_signal: int) -> pd.DataFrame:
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

        # Calculate trend deviations
        df['SMA20'] = df['Close'].rolling(window=20).mean()
        df['STD20'] = df['Close'].rolling(window=20).std()
        df['Upper_Band'] = df['SMA20'] + (df['STD20'] * 2)
        df['Lower_Band'] = df['SMA20'] - (df['STD20'] * 2)

        return df
