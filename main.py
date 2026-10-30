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
