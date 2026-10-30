import os

# =====================================
# FOREX HUNTER AI — CONFIGURATION
# =====================================

APP_NAME = "Forex Hunter AI"
APP_VERSION = "5.0.0"

# API
LSE_API_KEY = os.getenv("LSE_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# =====================================
# CURRENCY PAIRS
# =====================================

PAIRS = [
    "EUR/USD",
    "GBP/USD",
    "USD/JPY",
    "USD/CHF",
    "AUD/USD",
    "USD/CAD",
    "EUR/GBP",
    "EUR/JPY",
    "EUR/CHF",
    "EUR/AUD",
    "EUR/CAD",
    "GBP/JPY",
    "GBP/CHF",
    "GBP/AUD",
    "GBP/CAD",
    "AUD/JPY",
    "AUD/CHF",
    "AUD/CAD",
    "CAD/JPY",
    "CAD/CHF",
    "CHF/JPY",
]

# =====================================
# TIMEFRAMES
# =====================================

TIMEFRAMES = {
    "M1": "1min",
    "M5": "5min",
}

# =====================================
# MARKET DATA
# =====================================

CANDLE_LIMIT = 100
MIN_CANDLES = 60

CACHE_TTL = 60
API_CONCURRENCY = 4
MAX_API_REQUESTS_PER_MINUTE = 50

# =====================================
# SCANNER
# =====================================

SCAN_INTERVAL_SECONDS = 60
START_DELAY_SECONDS = 10
SCAN_START_DELAY_SECONDS = START_DELAY_SECONDS

SCAN_SEMAPHORE_LIMIT = 1

# =====================================
# SIGNAL FILTERS
# =====================================

MIN_ANALYSIS_SCORE = 75

REQUIRE_M1_M5_CONFIRMATION = True
REQUIRE_RISK_APPROVAL = True
REQUIRE_NEWS_APPROVAL = True

ALLOWED_SIGNALS = ("LONG", "SHORT")

# =====================================
# RISK MANAGEMENT
# =====================================

RISK_PERCENT = 1.0

ATR_STOP_MULTIPLIER = 1.5
REWARD_RISK_RATIO = 2.0

MAX_DAILY_LOSS_PERCENT = 3.0
MAX_CONSECUTIVE_LOSSES = 3

# =====================================
# NEWS FILTER
# =====================================

NEWS_ENABLED = True

NEWS_BLOCK_BEFORE_MINUTES = 30
NEWS_BLOCK_AFTER_MINUTES = 30

# =====================================
# TELEGRAM
# =====================================

TELEGRAM_ENABLED = True

SEND_WAIT_SIGNALS = False
SEND_ONLY_CONFIRMED_SIGNALS = True

MAX_HISTORY = 100
MAX_SIGNAL_HISTORY = MAX_HISTORY

# =====================================
# BACKTESTING
# =====================================

BACKTEST_INITIAL_BALANCE = 10000
BACKTEST_RISK_PERCENT = 1.0
BACKTEST_REWARD_RISK = 2.0
BACKTEST_WARMUP = 60
