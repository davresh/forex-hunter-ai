import asyncio
from indicators import analyze_market
from market_data import get_candles
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
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

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    return """
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Forex Hunter AI</title>
        <style>
            * { box-sizing: border-box; }

            body {
                margin: 0;
                padding: 25px;
                background: #0b1120;
                color: #e5e7eb;
                font-family: Arial, sans-serif;
            }

            .container {
                max-width: 1100px;
                margin: auto;
            }

            h1 { color: #38bdf8; }

            .subtitle { color: #94a3b8; }

            .stats {
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 15px;
                margin: 25px 0;
            }

            .card {
                background: #172033;
                padding: 20px;
                border-radius: 12px;
            }

            .number {
                font-size: 28px;
                font-weight: bold;
                margin-top: 10px;
            }

            button {
                background: #2563eb;
                color: white;
                border: 0;
                padding: 12px 18px;
                border-radius: 8px;
                cursor: pointer;
                margin: 5px 5px 15px 0;
            }

            button:hover { background: #1d4ed8; }

            .table-wrap { overflow-x: auto; }

            table {
                width: 100%;
                border-collapse: collapse;
                background: #172033;
                border-radius: 12px;
                overflow: hidden;
            }

            th, td {
                padding: 14px;
                text-align: left;
                border-bottom: 1px solid #293449;
                white-space: nowrap;
            }

            th { color: #94a3b8; }

            .LONG { color: #22c55e; font-weight: bold; }
            .SHORT { color: #ef4444; font-weight: bold; }
            .WAIT { color: #facc15; font-weight: bold; }

            #status { color: #94a3b8; margin: 15px 0; }

            @media(max-width: 600px) {
                body { padding: 12px; }
                .stats { grid-template-columns: 1fr; }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>FOREX HUNTER AI</h1>
            <p class="subtitle">Market Scanner | Simulation Mode</p>

            <div class="stats">
                <div class="card">
                    Currency Pairs
                    <div class="number" id="total">28</div>
                </div>
                <div class="card">
                    LONG Signals
                    <div class="number" id="long">0</div>
                </div>
                <div class="card">
                    SHORT Signals
                    <div class="number" id="short">0</div>
                </div>
            </div>

            <button onclick="startScan()">Scan All Pairs</button>

            <div id="status">Ready to scan</div>

            <div class="table-wrap">
                <table>
                    <thead>
                        <tr>
                            <th>Pair</th>
                            <th>M1</th>
                            <th>M5</th>
                        </tr>
                    </thead>
                    <tbody id="results"></tbody>
                </table>
            </div>
        </div>

        <script>
            
async function startScan() {
    const tbody = document.getElementById("results");
    const status = document.getElementById("status");

    tbody.innerHTML = "";
    let longCount = 0;
    let shortCount = 0;
    let foundPairs = 0;

    for (let offset = 0; offset < 28; offset += 2) {
        status.textContent =
            "Scanning " + Math.min(offset + 2, 28) + " / 28...";

        try {
            const response = await fetch(
                "/scan-all?offset=" + offset + "&limit=2"
            );

            const data = await response.json();

            if (!response.ok || !data.results) {
                continue;
            }

            for (const item of data.results) {
                const m1 = item.timeframes["1min"]?.analysis?.signal || "ERROR";
                const m5 = item.timeframes["5min"]?.analysis?.signal || "ERROR";

                // Показываем только пары с LONG или SHORT
                const hasSignal = ["LONG", "SHORT"].includes(m1) ||
                                  ["LONG", "SHORT"].includes(m5);

                if (!hasSignal) continue;

                foundPairs++;

                if (m1 === "LONG") longCount++;
                if (m5 === "LONG") longCount++;
                if (m1 === "SHORT") shortCount++;
                if (m5 === "SHORT") shortCount++;

                const row = document.createElement("tr");

                const pairCell = document.createElement("td");
                pairCell.textContent = item.pair;

                const m1Cell = document.createElement("td");
                m1Cell.textContent = m1;
                m1Cell.className = m1;

                const m5Cell = document.createElement("td");
                m5Cell.textContent = m5;
                m5Cell.className = m5;

                row.append(pairCell, m1Cell, m5Cell);
                tbody.appendChild(row);
            }

            document.getElementById("long").textContent = longCount;
            document.getElementById("short").textContent = shortCount;

        } catch (error) {
            console.error(error);
        }
    }

    status.textContent = foundPairs > 0
        ? "Found " + foundPairs + " pairs with trading signals."
        : "No trading signals found.";
}
        
    </script>
    </body>
    </html>
    """
