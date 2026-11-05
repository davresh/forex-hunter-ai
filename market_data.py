import os
import time
import asyncio
import logging

from dotenv import load_dotenv
from lse import LSE

load_dotenv()

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

FOREX_MARKET = "forex"


def normalize_pair(pair: str) -> str:
    return pair.upper().replace("-", "/").strip()


def provider_symbol(pair: str) -> str:
    return normalize_pair(pair).replace("/", "_")


def validate_candles(candles):
    if not isinstance(candles, list) or len(candles) < 60:
        return False

    required = ["open", "high", "low", "close"]

    for candle in candles:
        if not isinstance(candle, dict):
            return False

        try:
            values = {
                field: float(candle[field])
                for field in required
            }

            for value in values.values():
                if not (0 < value < float("inf")):
                    return False

            high = values["high"]
            low = values["low"]
            open_price = values["open"]
            close_price = values["close"]

            if high < low:
                return False

            if high < max(open_price, close_price):
                return False

            if low > min(open_price, close_price):
                return False

        except (KeyError, TypeError, ValueError):
            return False

    return True


async def get_candles(
    pair: str,
    interval: str = "1min",
    outputsize: int = 300
):
    if client is None:
        return {"error": "LSE_API_KEY is not configured"}

    pair = normalize_pair(pair)

    if interval not in TIMEFRAME_MAP:
        return {"error": f"Unsupported timeframe: {interval}"}

    if outputsize < 60:
        return {"error": "At least 60 candles are required"}

    cache_key = (pair, interval, outputsize)
    current_time = time.time()

    cached = CACHE.get(cache_key)

    if cached:
        cached_time, cached_data = cached

        if current_time - cached_time < CACHE_TTL:
            return cached_data

    timeframe = TIMEFRAME_MAP[interval]
    symbol = provider_symbol(pair)

    try:
        async with API_SEMAPHORE:
            response = await asyncio.to_thread(
                client.candles,
                symbol,
                timeframe,
                limit=outputsize,
                order="asc",
                market=FOREX_MARKET
            )

        if not response:
            return {
                "error": f"No market data received for {pair}"
            }

        if isinstance(response, dict):
            response = response.get(
                "candles",
                response.get("data", [])
            )

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

                timestamp = (
                    item.get("timestamp")
                    or item.get("time")
                    or item.get("ts")
                )

                if timestamp is not None:
                    candle["time"] = timestamp

                candles.append(candle)

            except (KeyError, TypeError, ValueError):
                continue

        if not validate_candles(candles):
            return {
                "error": (
                    f"Insufficient or invalid candle data "
                    f"for {pair}. Received: {len(candles)}"
                )
            }

        candles = candles[-outputsize:]

        CACHE[cache_key] = (
            time.time(),
            candles
        )

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
    CACHE.clear()
