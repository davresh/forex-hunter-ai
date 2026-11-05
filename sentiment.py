
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# =====================================
# FOREX HUNTER AI 5.0
# MARKET SENTIMENT MODULE
# =====================================

PROVIDERS = {
    "myfxbook": {
        "name": "Myfxbook Community Outlook",
        "enabled": False
    },
    "fxssi": {
        "name": "FXSSI Current Ratio",
        "enabled": False
    },
    "fxcm": {
        "name": "FXCM SSI",
        "enabled": False
    },
    "cftc": {
        "name": "CFTC Commitments of Traders",
        "enabled": False
    }
}


def normalize_pair(pair: str) -> str:
    return pair.upper().replace("-", "/").strip()


def unavailable_provider(provider: str):
    return {
        "provider": provider,
        "status": "unavailable",
        "buy_percent": None,
        "sell_percent": None,
        "message": "Provider API is not configured"
    }


def validate_sentiment(buy_percent, sell_percent):
    try:
        buy = float(buy_percent)
        sell = float(sell_percent)

        if not (0 <= buy <= 100):
            return False

        if not (0 <= sell <= 100):
            return False

        if abs((buy + sell) - 100) > 2:
            return False

        return True

    except (TypeError, ValueError):
        return False


def create_sentiment_result(
    provider,
    buy_percent,
    sell_percent,
    observed_at=None
):
    if not validate_sentiment(buy_percent, sell_percent):
        return {
            "provider": provider,
            "status": "invalid_data",
            "buy_percent": None,
            "sell_percent": None
        }

    return {
        "provider": provider,
        "status": "available",
        "buy_percent": round(float(buy_percent), 2),
        "sell_percent": round(float(sell_percent), 2),
        "observed_at": observed_at
    }


def combine_sentiment(results):
    """
    Combine only valid and available sentiment readings.

    Returns unavailable when no real provider data exists.
    """

    valid_results = [
        item for item in results
        if item.get("status") == "available"
        and validate_sentiment(
            item.get("buy_percent"),
            item.get("sell_percent")
        )
    ]

    if not valid_results:
        return {
            "status": "unavailable",
            "buy_percent": None,
            "sell_percent": None,
            "direction": "UNKNOWN",
            "providers_used": 0
        }

    buy_values = [
        item["buy_percent"] for item in valid_results
    ]

    sell_values = [
        item["sell_percent"] for item in valid_results
    ]

    buy = sum(buy_values) / len(buy_values)
    sell = sum(sell_values) / len(sell_values)

    if buy >= 60:
        direction = "BUY"
    elif sell >= 60:
        direction = "SELL"
    else:
        direction = "NEUTRAL"

    return {
        "status": "available",
        "buy_percent": round(buy, 2),
        "sell_percent": round(sell, 2),
        "direction": direction,
        "providers_used": len(valid_results)
    }


async def get_market_sentiment(pair: str):
    """
    Get market sentiment for one Forex pair.

    No provider is activated until its real data
    access and response format have been verified.
    """

    pair = normalize_pair(pair)

    results = []

    for provider, config in PROVIDERS.items():

        if not config["enabled"]:
            results.append(
                unavailable_provider(provider)
            )
            continue

        # Provider adapters will be implemented
        # after official access is configured.
        results.append(
            unavailable_provider(provider)
        )

    combined = combine_sentiment(results)

    return {
        "pair": pair,
        "timestamp": datetime.now(
            timezone.utc
        ).isoformat(),
        "sources": results,
        "combined": combined,
        "mode": "SIMULATION"
    }
