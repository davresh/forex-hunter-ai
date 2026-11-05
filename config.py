
import os

# =====================================
# FOREX HUNTER AI 5.0
# PROJECT CONFIGURATION
# =====================================

PROJECT_NAME = "Forex Hunter AI"
VERSION = "5.0"

# =====================================
# TELEGRAM SETTINGS
# =====================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# =====================================
# MARKET DATA SETTINGS
# =====================================

LSE_API_KEY = os.getenv("LSE_API_KEY")

CANDLE_LIMIT = 300
CACHE_TTL = 30

# =====================================
# FOREX CURRENCY PAIRS
# =====================================

PAIRS = [
    "AUD/CAD",
    "AUD/JPY",
    "EUR/GBP",
    "GBP/USD",
    "GBP/AUD",
    "CAD/JPY",
    "EUR/USD",
    "GBP/CAD",
    "AUD/USD",
    "AUD/CHF",
    "CAD/CHF",
    "EUR/CHF",
    "EUR/JPY",
    "GBP/CHF",
    "USD/CAD",
    "USD/CHF",
    "USD/JPY",
    "CHF/JPY",
    "GBP/JPY",
    "EUR/CAD",
    "EUR/AUD"
]

# =====================================
# TIMEFRAMES
# =====================================

TIMEFRAMES = [
    "1min",
    "5min"
]

# =====================================
# ANALYSIS SETTINGS
# =====================================

MIN_CANDLES = 200
MIN_SIGNAL_SCORE = 70

# =====================================
# RISK MANAGEMENT
# SIMULATION ONLY
# =====================================

INITIAL_BALANCE = 10000
RISK_PERCENT = 1.0
REWARD_RISK = 2.0

# =====================================
# SCANNER SETTINGS
# =====================================

SCAN_INTERVAL = 60
MAX_HISTORY = 100

# =====================================
# MARKET SENTIMENT
# =====================================

SENTIMENT_ENABLED = True
SENTIMENT_MIN_PERCENT = 70

# =====================================
# BACKTESTING
# =====================================

BACKTEST_ENABLED = True

# =====================================
# SAFETY SETTINGS
# =====================================

LIVE_TRADING_ENABLED = False
