import asyncio
from indicators import analyze_market
from market_data import get_candles
from fastapi import FastAPI
from datetime import datetime, timezone
from indicators import analyze_market

app = FastAPI(
    title="Forex Hunter AI",
    description="Forex signal monitoring — simulation only",
    version="1.0.0"
)

PAIRS = [
    "EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF",
    "AUD/USD", "USD/CAD", "NZD/USD",
    "EUR/GBP", "EUR/JPY", "EUR/CHF", "EUR/AUD",
    "EUR/CAD", "EUR/NZD",
    "GBP/JPY", "GBP/CHF", "GBP/AUD", "GBP/CAD",
    "GBP/NZD",
    "AUD/JPY", "AUD/CHF", "AUD/CAD", "AUD/NZD",
    "CAD/JPY", "CAD/CHF",
    "NZD/JPY", "NZD/CHF", "NZD/CAD",
    "CHF/JPY"
]

@app.get("/")
def home():
    return {
        "project": "Forex Hunter AI",
        "status": "online",
        "mode": "simulation",
        "message": "Forex Hunter AI is running!"
    }

@app.get("/health")
def health():
    return {
        "status": "healthy",
        "time": datetime.now(timezone.utc).isoformat()
    }

@app.get("/pairs")
def pairs():
    return {
        "total": len(PAIRS),
        "timeframes": ["M1", "M5"],
        "pairs": PAIRS
    }
    
@app.post("/analyze")
def analyze(data: dict):
    candles = data.get("candles", [])
    return analyze_market(candles)

@app.get("/market/{pair:path}")
async def market(pair: str, interval: str = "1min"):
    if interval not in ["1min", "5min"]:
        return {"error": "Use 1min or 5min"}

    candles = await get_candles(pair, interval)

    if isinstance(candles, dict):
        return candles

    analysis = analyze_market(candles)

    return {
        "pair": pair,
        "timeframe": interval,
        "candles_count": len(candles),
        "analysis": analysis
    }

@app.get("/scan/{pair:path}")
async def scan_pair_endpoint(pair: str):
    results = {}

    for interval in ["1min", "5min"]:
        candles = await get_candles(pair, interval)

        if isinstance(candles, dict):
            results[interval] = candles
        else:
            results[interval] = {
                "candles_count": len(candles),
                "analysis": analyze_market(candles)
            }

    return {
        "pair": pair,
        "results": results
    }

@app.get("/scan-all")
async def scan_all(offset: int = 0, limit: int = 2):
    if limit < 1 or limit > 4 or offset < 0:
        return {"error": "Use limit from 1 to 4 and offset from 0"}

    selected_pairs = PAIRS[offset:offset + limit]
    results = []

    for pair in selected_pairs:
        pair_result = {
            "pair": pair,
            "timeframes": {}
        }

        for interval in ["1min", "5min"]:
            try:
                candles = await get_candles(pair, interval)

                if isinstance(candles, dict):
                    pair_result["timeframes"][interval] = candles
                else:
                    pair_result["timeframes"][interval] = {
                        "candles_count": len(candles),
                        "analysis": analyze_market(candles)
                    }

            except Exception as error:
                pair_result["timeframes"][interval] = {
                    "error": str(error)
                }

            await asyncio.sleep(1)

        results.append(pair_result)

    next_offset = offset + len(selected_pairs)

    return {
        "total_pairs": len(PAIRS),
        "scanned_pairs": len(selected_pairs),
        "next_offset": next_offset if next_offset < len(PAIRS) else None,
        "results": results
    }
