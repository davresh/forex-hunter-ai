from fastapi import FastAPI
from datetime import datetime, timezone

app = FastAPI(
    title="Forex Hunter AI",
    description="Forex signal monitoring — simulation only",
    version="1.0.0"
)

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
        "pairs": [
            "EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF",
            "AUD/USD", "USD/CAD", "NZD/USD"
        ]
    }
