
import os
import time
import asyncio
import logging

from dotenv import load_dotenv
from lse import LSE

load_dotenv()

# =====================================
# FOREX HUNTER AI 5.0
# MARKET DATA
# =====================================

logger = logging.getLogger(__name__)

API_KEY = os.getenv("LSE_API_KEY")

client = LSE(api_key=API_KEY) if API_KEY else None

CACHE = {}
CACHE_TTL = 30

API_SEMAPHORE = asyncio.Semaphore(2)

TIMEFRAME_MAP = {
    "1min": "1m",
    "5min": "5m"
}


def normalize_pair(pair: str) -> str:
    """Normalize Forex pair format."""
    return pair.upper().replace("-", "/").strip()


def validate_candles(candles):
    """Check candle structure and values."""

    if not isinstance(candles, list):
        return False

    if len(candles) < 60:
        return False

    required = ["open", "high", "low", "close"]

    for candle in candles:
        if not isinstance(candle, dict):
            return False

        for field in required:
            if field not in candle:
                return False

            try:
                value = float(candle[field])
                if not (value > 0 and value < float("inf")):
                    return False
            except (TypeError, ValueError):
                return False

        high = float(candle["high"])
        low = float(candle["low"])
        open_price = float(candle["open"])
        close_price = float(candle["close"])

        if high < low:
            return False

        if high < max(open_price, close_price):
            return False

        if low > min(open_price, close_price):
            return False

    return True


async def get_candles(
    pair: str,
    interval: str = "1min",
    outputsize: int = 300
):
    """
    Get Forex candles.

    Returns:
        List of OHLC candles or an error dictionary.
    """

    if client is None:
        return {
            "error": "LSE_API_KEY is not configured"
        }

    pair = normalize_pair(pair)

    if interval not in TIMEFRAME_MAP:
        return {
            "error": f"Unsupported timeframe: {interval}"
        }

    if outputsize < 60:
        return {
            "error": "At least 60 candles are required"
        }

    cache_key = (pair, interval, outputsize)
    current_time = time.time()

    # Check cache
    cached = CACHE.get(cache_key)

    if cached:
        cached_time, cached_data = cached

        if current_time - cached_time < CACHE_TTL:
            return cached_data

    timeframe = TIMEFRAME_MAP[interval]

    try:
        async with API_SEMAPHORE:

            # API request runs in a separate thread
            response = await asyncio.to_thread(
                client.candles,
                pair,
                timeframe,
                limit=outputsize,
                order="asc"
            )

        if not response:
            return {
                "error": f"No market data received for {pair}"
            }

        if isinstance(response, dict):
            response = response.get("candles", response.get("data", []))

        if not isinstance(response, list):
            return {
                "error": "Unexpected market data format"
            }

        candles = []

        for item in response:
            try:
                candle = {
                    "open": float(item["open"]),
                    "high": float(item["high"]),
                    "low": float(item["low"]),
                    "close": float(item["close"])
                }

                if "volume" in item:
                    candle["volume"] = float(item["volume"])

                if "time" in item:
                    candle["time"] = item["time"]
                elif "timestamp" in item:
                    candle["time"] = item["timestamp"]

                candles.append(candle)

            except (KeyError, TypeError, ValueError):
                continue

        if not validate_candles(candles):
            return {
                "error": (
                    f"Insufficient or invalid candle data for {pair}. "
                    f"Received: {len(candles)}"
                )
            }

        # Keep the latest requested number of candles
        candles = candles[-outputsize:]

        CACHE[cache_key] = (time.time(), candles)

        return candles

    except Exception as error:
        logger.exception(
            "Market data error for %s (%s)",
            pair,
            interval
        )

        return {
            "error": str(error)
        }


def clear_cache():
    """Clear cached market data."""
    CACHE.clear()
