
import os
import time
import logging
import asyncio

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://www.myfxbook.com/api"
CACHE_SECONDS = 900

_session = None
_session_lock = asyncio.Lock()

_outlook_cache = {}
_cache_time = 0


def normalize_pair(pair):
    return pair.upper().replace("/", "").replace("-", "").strip()


async def login(client):
    global _session

    email = os.getenv("MYFXBOOK_EMAIL")
    password = os.getenv("MYFXBOOK_PASSWORD")

    if not email or not password:
        raise RuntimeError("Myfxbook credentials are missing")

    response = await client.get(
        f"{BASE_URL}/login.json",
        params={"email": email, "password": password}
    )
    response.raise_for_status()

    data = response.json()

    if data.get("error") or not data.get("session"):
        raise RuntimeError(data.get("message") or "Myfxbook login failed")

    _session = data["session"]
    return _session


async def get_session(client):
    global _session

    async with _session_lock:
        if _session:
            return _session

        return await login(client)


async def fetch_outlook(client):
    global _outlook_cache, _cache_time, _session

    if _outlook_cache and time.monotonic() - _cache_time < CACHE_SECONDS:
        return _outlook_cache

    session = await get_session(client)

    for attempt in range(2):
        response = await client.get(
            f"{BASE_URL}/get-community-outlook.json",
            params={"session": session}
        )
        response.raise_for_status()
        data = response.json()

        if not data.get("error"):
            symbols = data.get("symbols", [])
            _outlook_cache = {
                normalize_pair(item["name"]): item
                for item in symbols
                if item.get("name")
            }
            _cache_time = time.monotonic()
            return _outlook_cache

        if attempt == 0:
            _session = None
            session = await get_session(client)

    raise RuntimeError(data.get("message") or "Outlook request failed")


def unavailable(pair, reason="Myfxbook data unavailable"):
    return {
        "pair": pair,
        "timestamp": None,
        "sources": [{
            "provider": "myfxbook",
            "status": "unavailable",
            "message": reason
        }],
        "combined": {
            "status": "unavailable",
            "buy_percent": None,
            "sell_percent": None,
            "direction": "UNKNOWN",
            "providers_used": 0
        },
        "mode": "SIMULATION"
    }


async def get_market_sentiment(pair):
    pair = normalize_pair(pair)

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            outlook = await fetch_outlook(client)

        item = outlook.get(pair)

        if not item:
            return unavailable(pair, "Pair not found in Myfxbook")

        buy = float(item["longPercentage"])
        sell = float(item["shortPercentage"])

        if not (0 <= buy <= 100 and 0 <= sell <= 100):
            return unavailable(pair, "Invalid sentiment percentages")

        if abs(buy + sell - 100) > 3:
            return unavailable(pair, "Invalid BUY/SELL balance")

        direction = (
            "BUY" if buy >= 60
            else "SELL" if sell >= 60
            else "NEUTRAL"
        )

        return {
            "pair": pair,
            "timestamp": time.time(),
            "sources": [{
                "provider": "Myfxbook Community Outlook",
                "status": "available",
                "buy_percent": buy,
                "sell_percent": sell
            }],
            "combined": {
                "status": "available",
                "buy_percent": buy,
                "sell_percent": sell,
                "direction": direction,
                "providers_used": 1
            },
            "mode": "SIMULATION"
        }

    except Exception as error:
        logger.warning("Myfxbook sentiment error: %s", error)
        return unavailable(pair, str(error))
