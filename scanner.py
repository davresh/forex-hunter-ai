
import asyncio

from config import PAIRS, TIMEFRAMES
from market_data import get_candles
from agents.chief_agent import chief_agent


async def scan_pair(pair):
    """
    Scans one pair using M1 and M5
    and asks Chief Agent for a final decision.
    """

    try:
        m1_candles, m5_candles = await asyncio.gather(
            get_candles(pair, TIMEFRAMES["M1"]),
            get_candles(pair, TIMEFRAMES["M5"])
        )

        if isinstance(m1_candles, dict):
            return {
                "pair": pair,
                "signal": "WAIT",
                "approved": False,
                "reason": m1_candles.get("error")
            }

        if isinstance(m5_candles, dict):
            return {
                "pair": pair,
                "signal": "WAIT",
                "approved": False,
                "reason": m5_candles.get("error")
            }

        return await chief_agent(
            pair=pair,
            m1_candles=m1_candles,
            m5_candles=m5_candles
        )

    except Exception as error:
        return {
            "pair": pair,
            "signal": "WAIT",
            "approved": False,
            "reason": str(error)
        }


async def scan_all():
    """
    Scans all configured pairs sequentially.
    """

    results = []

    for pair in PAIRS:
        result = await scan_pair(pair)
        results.append(result)

        print(result)

        await asyncio.sleep(1)

    return results


if __name__ == "__main__":
    asyncio.run(scan_all())
