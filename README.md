# NQ Futures Trading Bot

An automated trading bot for NQ futures that uses trend deviation strategy with RSI and MACD indicators.

## General Setup

1. Bot Setup

Setup a telegram bot and get the token and chat id from BotFather

2. API Access

    1. Go to https://developer.tdameritrade.com/
    2. Create a developer account
    3. Create a new app to get your API key
    4. Set your callback URL to: http://localhost:8080

## Setup

3. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate
deactivate  # Close the virtual environment after using
rm -rf venv  # Remove the virtual environment if necessary
```

4. Install dependencies:
```bash
pip install -r requirements.txt
```

5. Run the bot:
```bash
python main.py
```

## Features

- Real-time NQ futures trading signals
- RSI and MACD indicator analysis
- Trend deviation strategy
- Telegram notifications
- Market hours awareness
- Rate-limited API calls

## Configuration

All configuration parameters can be found in `config/settings.py`. Adjust these according to your trading preferences.

## Disclaimer

This bot is for educational purposes only. Trade at your own risk.
