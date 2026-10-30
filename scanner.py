import asyncio
from market_data import get_candles
from indicators import analyze_market
from main import PAIRS


async def scan_pair(pair, interval):
    try:
        candles = await get_candles(pair, interval)

        if isinstance(candles, dict):
            return {
                "pair": pair,
                "timeframe": interval,
                "error": candles.get("error")
            }

        return {
            "pair": pair,
            "timeframe": interval,
            "analysis": analyze_market(candles)
        }

    except Exception as error:
        return {
            "pair": pair,
            "timeframe": interval,
            "error": str(error)
        }


async def scan_all():
    results = []

    for pair in PAIRS:
        for interval in ["1min", "5min"]:
            result = await scan_pair(pair, interval)
            results.append(result)

            print(result)

            await asyncio.sleep(2)

    return results


if __name__ == "__main__":
    asyncio.run(scan_all())
