
import logging

from config import PAIRS, CANDLE_LIMIT
from market_data import get_candles
from indicators import analyze_market

logger = logging.getLogger(__name__)

# =====================================
# FOREX HUNTER AI 5.0
# SINGLE PAIR SCANNER
# =====================================


async def scan_pair(pair: str):
    """
    Analyze only the requested Forex pair.
    No automatic scanning of all pairs.
    """

    pair = pair.upper().strip()

    if pair not in PAIRS:
        return {
            "pair": pair,
            "status": "error",
            "error": "Unsupported currency pair"
        }

    results = {}

    for interval in ("1min", "5min"):

        candles = await get_candles(
            pair,
            interval,
            CANDLE_LIMIT
        )

        if isinstance(candles, dict):
            return {
                "pair": pair,
                "status": "error",
                "timeframe": interval,
                "error": candles.get("error")
            }

        analysis = analyze_market(candles)

        results[interval] = analysis

        if analysis.get("error"):
            return {
                "pair": pair,
                "status": "error",
                "timeframe": interval,
                "error": analysis["error"]
            }

    m1 = results["1min"]
    m5 = results["5min"]

    signal = "WAIT"

    if (
        m1["signal"] == "LONG"
        and m5["signal"] == "LONG"
        and m1["score"] >= 70
        and m5["score"] >= 70
    ):
        signal = "LONG"

    elif (
        m1["signal"] == "SHORT"
        and m5["signal"] == "SHORT"
        and m1["score"] >= 70
        and m5["score"] >= 70
    ):
        signal = "SHORT"

    return {
        "pair": pair,
        "status": "completed",
        "signal": signal,
        "M1": m1,
        "M5": m5,
        "mode": "SIMULATION"
    }
