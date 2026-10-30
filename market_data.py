import time

CACHE = {}
CACHE_TTL = 60
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("TWELVE_DATA_API_KEY")
BASE_URL = "https://api.twelvedata.com/time_series"


async def get_candles(pair: str, interval: str = "1min", outputsize: int = 100):
    if not API_KEY:
        return {"error": "API key is missing"}

    params = {
        "symbol": pair.replace("/", "/"),
        "interval": interval,
        "outputsize": outputsize,
        "apikey": API_KEY
    }

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(BASE_URL, params=params)
        response.raise_for_status()
        data = response.json()

    if "values" not in data:
        return {"error": data.get("message", "Market data unavailable")}

    candles = []

    for item in reversed(data["values"]):
        candles.append({
            "open": float(item["open"]),
            "high": float(item["high"]),
            "low": float(item["low"]),
            "close": float(item["close"])
        })

    return candles
