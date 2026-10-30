import os
import time
import asyncio
from dotenv import load_dotenv
from lse import LSE

load_dotenv()

CACHE = {}
CACHE_TTL = 60

API_KEY = os.getenv("LSE_API_KEY")

client = LSE(api_key=API_KEY) if API_KEY else None


async def get_candles(
    pair: str,
    interval: str = "1min",
    outputsize: int = 100
):
    cache_key = (pair, interval, outputsize)

    cached = CACHE.get(cache_key)

    if cached and time.time() - cached["time"] < CACHE_TTL:
        return cached["data"]

    if not client:
        return {"error": "LSE_API_KEY is missing"}

    timeframe_map = {
        "1min": "1m",
        "5min": "5m"
    }

    timeframe = timeframe_map.get(interval)

    if not timeframe:
        return {"error": f"Unsupported interval: {interval}"}

    async def fetch_candles():
        rows = await asyncio.to_thread(
            client.candles,
            pair,
            timeframe,
            limit=outputsize,
            order="asc"
        )

        if not rows:
            return {"error": f"No candles returned for {pair}"}

        candles = []

        for item in rows:
            candles.append({
                "open": float(item["open"]),
                "high": float(item["high"]),
                "low": float(item["low"]),
                "close": float(item["close"])
            })

        CACHE[cache_key] = {
            "time": time.time(),
            "data": candles
        }

        return candles

    try:
        return await fetch_candles()

    except Exception:
        await asyncio.sleep(2)

        try:
            return await fetch_candles()

        except Exception as retry_error:
            return {
                "error": f"{pair}: {str(retry_error)}"
            }
