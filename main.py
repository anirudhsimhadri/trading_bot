import time
from config import settings
from notifications.telegram_client import TelegramClient
from strategy.trend_deviation import TrendDeviationStrategy
from utils.market_time import is_market_open

def main():
    # Initialize Telegram client
    telegram_client = TelegramClient(
        token=settings.TELEGRAM_TOKEN,
        chat_id=settings.TELEGRAM_CHAT_ID
    )
    
    # Initialize strategy
    strategy = TrendDeviationStrategy(telegram_client)
    
    print("Bot started...")
    
    while True:
        try:
            if is_market_open():
                df = strategy.get_data()
                signals = strategy.generate_signals(df)
                
                if signals:
                    latest_signal = signals[-1]
                    message = strategy.format_alert_message(latest_signal)
                    telegram_client.send_alert(message)
            
            time.sleep(300)  # Check every 5 minutes
            
        except Exception as e:
            error_message = f"⚠️ Trading Bot Error ⚠️\n{str(e)}"
            telegram_client.send_alert(error_message)
            time.sleep(60)

if __name__ == "__main__":
    main()
