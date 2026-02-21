import telebot
from ratelimit import limits, sleep_and_retry

class TelegramClient:
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.bot = telebot.TeleBot(token)
        self.chat_id = chat_id

    def _sanitize_error(self, error: Exception) -> str:
        msg = str(error)
        if self.token:
            msg = msg.replace(self.token, "[REDACTED_TOKEN]")
        return msg

    @sleep_and_retry
    @limits(calls=1, period=5)
    def send_alert(self, message: str):
        try:
            self.bot.send_message(self.chat_id, message)
        except Exception as e:
            sanitized = self._sanitize_error(e)
            print(f"Error sending Telegram message: {sanitized}")

    def send_heartbeat(self):
        message = "✅ Trading Bot Active"
        self.send_alert(message)
