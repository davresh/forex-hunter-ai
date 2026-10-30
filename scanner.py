import asyncio
from market_data import get_candles
from indicators import analyze_market
from main import PAIRS


async def scan_pair(pair, interval):
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


async def scan_all():
    tasks = []

    for pair in PAIRS:
        for interval in ["1min", "5min"]:
            tasks.append(scan_pair(pair, interval))

    return await asyncio.gather(*tasks)


if __name__ == "__main__":
    results = asyncio.run(scan_all())

    for result in results:
        print(result)
