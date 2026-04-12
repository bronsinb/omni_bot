import os
from dotenv import load_dotenv

load_dotenv()

ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")
ALPACA_PAPER = os.getenv("ALPACA_PAPER", "True").lower() == "true"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# We can add other config flags here, like maximum risk per trade, symbols to trade, etc.
MAX_RISK_PER_TRADE = 0.05  # 5% max risk
TICKERS_TO_WATCH = ["SPY", "QQQ", "AAPL", "TSLA"]
