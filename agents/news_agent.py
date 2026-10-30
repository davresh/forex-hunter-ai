
import asyncio
import time
import httpx

from datetime import datetime, timezone, timedelta

from config import (
    NEWS_ENABLED,
    NEWS_BLOCK_BEFORE_MINUTES,
    NEWS_BLOCK_AFTER_MINUTES,
)

NEWS_URL = (
    "https://nfs.faireconomy.media/"
    "ff_calendar_thisweek.json"
)

HIGH_IMPACT = {"High", "Holiday"}

CACHE_TTL = 300

_news_cache = {
    "data": None,
    "timestamp": 0
}

_news_lock = asyncio.Lock()


async def get_news_calendar():
    """Download and cache the economic calendar."""

    cached_data = _news_cache["data"]

    if (
        cached_data is not None
        and time.time() - _news_cache["timestamp"] < CACHE_TTL
    ):
        return cached_data

    async with _news_lock:
        # Check again after waiting for another request.
        cached_data = _news_cache["data"]

        if (
            cached_data is not None
            and time.time() - _news_cache["timestamp"] < CACHE_TTL
        ):
            return cached_data

        async with httpx.AsyncClient(
            timeout=10,
            follow_redirects=True
        ) as client:
            response = await client.get(NEWS_URL)
            response.raise_for_status()

            data = response.json()

        if not isinstance(data, list):
            raise ValueError("Invalid news calendar format")

        _news_cache["data"] = data
        _news_cache["timestamp"] = time.time()

        return data


async def news_agent(pair):
    """
    Blocks signals near high-impact economic events.

    If the calendar is unavailable, automatic signals
    are rejected for safety.
    """

    if not NEWS_ENABLED:
        return {
            "agent": "News Agent",
            "approved": True,
            "blocked": False,
            "events": [],
            "reason": "News filter disabled"
        }

    try:
        currencies = pair.upper().replace("/", " ").split()

        if len(currencies) != 2:
            raise ValueError("Invalid currency pair")

        data = await get_news_calendar()

        now = datetime.now(timezone.utc)

        before = timedelta(
            minutes=NEWS_BLOCK_BEFORE_MINUTES
        )

        after = timedelta(
            minutes=NEWS_BLOCK_AFTER_MINUTES
        )

        relevant_events = []

        for event in data:
            if not isinstance(event, dict):
                continue

            currency = str(
                event.get("country", "")
            ).upper()

            impact = str(
                event.get("impact", "")
            ).strip()

            if currency not in currencies:
                continue

            if impact not in HIGH_IMPACT:
                continue

            date_text = event.get("date")

            if not date_text:
                continue

            event_time = datetime.fromisoformat(
                str(date_text).replace("Z", "+00:00")
            )

            if event_time.tzinfo is None:
                event_time = event_time.replace(
                    tzinfo=timezone.utc
                )

            if now - before <= event_time <= now + after:
                relevant_events.append({
                    "currency": currency,
                    "title": event.get(
                        "title",
                        "Economic event"
                    ),
                    "impact": impact,
                    "time": event_time.isoformat()
                })

        blocked = bool(relevant_events)

        return {
            "agent": "News Agent",
            "approved": not blocked,
            "blocked": blocked,
            "events": relevant_events,
            "reason": (
                "High-impact event near current time"
                if blocked
                else "No relevant high-impact events found"
            )
        }

    except Exception as error:
        return {
            "agent": "News Agent",
            "approved": False,
            "blocked": True,
            "events": [],
            "reason": (
                "News calendar unavailable: "
                + str(error)
            )
        }
