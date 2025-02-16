import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Access the environment variables
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# Bot link format (you can access this via f-string)
BOT_LINK = f"https://t.me/ani_tradingbot"

# Trading pairs configuration
SYMBOL = 'NQ=F'
TIMEFRAME = '15m' 
PERIOD = '1y'

# Technical indicators parameters
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

# Market hours (EST)
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 30
MARKET_CLOSE_HOUR = 16

# Trading parameters
POSITION_SIZE = 1
MAX_POSITIONS = 5
STOP_LOSS_PCT = 0.02
TAKE_PROFIT_PCT = 0.04

# Backtesting parameters
INITIAL_CAPITAL = 100000  # $100,000 initial capital
COMMISSION_PCT = 0.001  # 0.1% commission per trade