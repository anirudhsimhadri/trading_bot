import yfinance as yf
from indicators.technical_indicators import TechnicalIndicators
from notifications.telegram_client import TelegramClient
from config import settings

class TrendDeviationStrategy:
    def __init__(self, telegram_client: TelegramClient):
        self.telegram_client = telegram_client
        self.symbol = settings.SYMBOL

    def get_data(self):
        df = yf.download(self.symbol, period=settings.PERIOD, interval=settings.TIMEFRAME)
        return TechnicalIndicators.add_indicators(
            df, 
            settings.RSI_PERIOD,
            settings.MACD_FAST,
            settings.MACD_SLOW,
            settings.MACD_SIGNAL
        )

    def generate_signals(self, df):
        signals = []
        
        for i in range(1, len(df)):
            # Previous and current values
            prev_macd = df['MACD'].iloc[i-1]
            curr_macd = df['MACD'].iloc[i]
            prev_signal = df['MACD_Signal'].iloc[i-1]
            curr_signal = df['MACD_Signal'].iloc[i]
            curr_rsi = df['RSI'].iloc[i]
            
            # Check for long signals
            if (prev_macd < prev_signal and curr_macd > curr_signal and  # MACD crossover
                curr_rsi < settings.RSI_OVERSOLD and  # RSI oversold
                df['Close'].iloc[i] < df['Lower_Band'].iloc[i]):  # Price below lower band
                
                signals.append({
                    'timestamp': df.index[i],
                    'type': 'LONG',
                    'price': df['Close'].iloc[i],
                    'rsi': curr_rsi,
                    'macd': curr_macd
                })
            
            # Check for short signals
            elif (prev_macd > prev_signal and curr_macd < curr_signal and  # MACD crossover
                  curr_rsi > settings.RSI_OVERBOUGHT and  # RSI overbought
                  df['Close'].iloc[i] > df['Upper_Band'].iloc[i]):  # Price above upper band
                
                signals.append({
                    'timestamp': df.index[i],
                    'type': 'SHORT',
                    'price': df['Close'].iloc[i],
                    'rsi': curr_rsi,
                    'macd': curr_macd
                })
        
        return signals

    def format_alert_message(self, signal):
        return (
            f"🚨 NQ FUTURES ALERT 🚨\n"
            f"Signal: {signal['type']}\n"
            f"Time: {signal['timestamp']}\n"
            f"Price: ${signal['price']:.2f}\n"
            f"RSI: {signal['rsi']:.2f}\n"
            f"MACD: {signal['macd']:.2f}"
        )
