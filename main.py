import asyncio
import os

from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from telegram import Bot

from indicators import analyze_market
from market_data import get_candles

app = FastAPI(
    title="Forex Hunter AI",
    description="Forex signal monitoring — simulation only",
    version="1.0.0"
)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

telegram_bot = (
    Bot(token=TELEGRAM_BOT_TOKEN)
    if TELEGRAM_BOT_TOKEN
    else None
)

LAST_SENT_SIGNALS = {}


async def send_telegram_message(message: str):
    if not telegram_bot:
        return {"error": "Telegram bot token is missing"}

    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not chat_id:
        return {"error": "Telegram chat ID is missing"}

    try:
        await telegram_bot.send_message(
            chat_id=chat_id,
            text=message
        )
        return {"success": True}

    except Exception as e:
        return {"error": str(e)}


async def send_trade_signal(pair: str, signal: str):
    emoji = "🟢" if signal == "LONG" else "🔴"
    arrow = "🚀" if signal == "LONG" else "📉"

    message = (
        "━━━━━━━━━━━━━━━━━━\n"
        "🤖 FOREX HUNTER AI\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"{emoji} CONFIRMED {signal} {arrow}\n\n"
        f"💱 Pair: {pair}\n"
        f"📈 M1: {signal}\n"
        f"📊 M5: {signal}\n\n"
        "🧠 Strategy: EMA + MACD + RSI\n"
        "✅ Both timeframes agree\n\n"
        "🛡️ MODE: SIMULATION\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "⚠️ Educational signal, not financial advice."
    )

    return await send_telegram_message(message)


async def maybe_send_trade_signal(pair: str, m1, m5):
    if m1 in ("LONG", "SHORT") and m1 == m5:
        if LAST_SENT_SIGNALS.get(pair) != m1:
            sent = await send_trade_signal(pair, m1)

            if sent.get("success"):
                LAST_SENT_SIGNALS[pair] = m1
    else:
        LAST_SENT_SIGNALS.pop(pair, None)


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


@app.get("/telegram-test")
async def telegram_test():
    return await send_telegram_message(
        "🚀 FOREX HUNTER AI\n\n"
        "Telegram connection successful!\n"
        "Simulation Mode"
    )


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
    if interval not in ("1min", "5min"):
        return {"error": "Use 1min or 5min"}

    candles = await get_candles(pair, interval)

    if isinstance(candles, dict):
        return candles

    return {
        "pair": pair,
        "timeframe": interval,
        "candles_count": len(candles),
        "analysis": analyze_market(candles)
    }


@app.get("/scan/{pair:path}")
async def scan_pair_endpoint(pair: str):
    results = {}

    for interval in ("1min", "5min"):
        candles = await get_candles(pair, interval)

        if isinstance(candles, dict):
            results[interval] = candles
        else:
            results[interval] = {
                "candles_count": len(candles),
                "analysis": analyze_market(candles)
            }

    m1 = results.get("1min", {}).get(
        "analysis", {}
    ).get("signal")

    m5 = results.get("5min", {}).get(
        "analysis", {}
    ).get("signal")

    await maybe_send_trade_signal(pair, m1, m5)

    return {
        "pair": pair,
        "results": results
    }


@app.get("/scan-all")
async def scan_all(offset: int = 0, limit: int = 2):
    if limit < 1 or limit > 4 or offset < 0:
        return {
            "error": "Use limit from 1 to 4 and offset from 0"
        }

    selected_pairs = PAIRS[offset:offset + limit]
    results = []

    summary = {
        "confirmed_long": 0,
        "confirmed_short": 0,
        "waiting": 0,
        "data_errors": 0
    }

    for pair in selected_pairs:
        pair_result = {
            "pair": pair,
            "timeframes": {}
        }

        # Проверяем M1 и M5 одновременно
        async def fetch_timeframe(interval):
            try:
                candles = await get_candles(pair, interval)

                if isinstance(candles, dict):
                    return interval, candles

                return interval, {
                    "candles_count": len(candles),
                    "analysis": analyze_market(candles)
                }

            except Exception as error:
                return interval, {
                    "error": str(error)
                }

        timeframe_results = await asyncio.gather(
            fetch_timeframe("1min"),
            fetch_timeframe("5min")
        )

        pair_result["timeframes"] = dict(timeframe_results)

        frames = pair_result["timeframes"]

        m1_data = frames.get("1min", {})
        m5_data = frames.get("5min", {})

        m1 = m1_data.get("analysis", {}).get("signal")
        m5 = m5_data.get("analysis", {}).get("signal")

        has_error = (
            "error" in m1_data
            or "error" in m5_data
        )

        if has_error:
            summary["data_errors"] += 1
            pair_result["trade_status"] = "DATA ERROR"

        elif m1 == m5 == "LONG":
            summary["confirmed_long"] += 1
            pair_result["trade_status"] = "CONFIRMED LONG"

        elif m1 == m5 == "SHORT":
            summary["confirmed_short"] += 1
            pair_result["trade_status"] = "CONFIRMED SHORT"

        else:
            summary["waiting"] += 1
            pair_result["trade_status"] = "WAITING"

        await maybe_send_trade_signal(pair, m1, m5)

        results.append(pair_result)

    next_offset = offset + len(selected_pairs)

    return {
        "total_pairs": len(PAIRS),
        "scanned_pairs": len(selected_pairs),
        "next_offset": (
            next_offset if next_offset < len(PAIRS) else None
        ),
        "summary": summary,
        "results": results
    }


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    return """
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport"
              content="width=device-width, initial-scale=1">
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
                grid-template-columns: repeat(5, 1fr);
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
            .ERROR { color: #f97316; font-weight: bold; }

            #status { color: #94a3b8; margin: 15px 0; }

            @media(max-width: 600px) {
                body { padding: 12px; }
                .stats{ grid-template-columns: repeat(2, 1fr); }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>FOREX HUNTER AI</h1>
            <p class="subtitle">
                Market Scanner | Simulation Mode
            </p>

            <div class="stats">
    <div class="card">
        Currency Pairs
        <div class="number" id="total">28</div>
    </div>
    <div class="card">
        Confirmed LONG
        <div class="number" id="long">0</div>
    </div>
    <div class="card">
        Confirmed SHORT
        <div class="number" id="short">0</div>
    </div>
    <div class="card">
        Waiting
        <div class="number" id="waiting">0</div>
    </div>
    <div class="card">
        Data Errors
        <div class="number" id="errors">0</div>
    </div>
</div>
            <button id="scanButton" onclick="startScan()">
                Scan All Pairs
            </button>

            <div id="status">Ready to scan</div>

            <div class="table-wrap">
                <table>
                    <thead>
                        <tr>
                            <th>Pair</th>
                            <th>M1</th>
                            <th>M5</th>
                            <th>TRADE STATUS</th>
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
    const button = document.getElementById("scanButton");

    button.disabled = true;
    tbody.innerHTML = "";

    let confirmedLong = 0;
    let confirmedShort = 0;
    let waiting = 0;
    let errors = 0;
    let scanned = 0;

    try {
        for (let offset = 0; offset < 28; offset += 2) {
            status.textContent =
                "Scanning " + Math.min(offset + 2, 28) + " / 28...";

            const response = await fetch(
                "/scan-all?offset=" + offset + "&limit=2"
            );

            if (!response.ok) {
                throw new Error("Server error: " + response.status);
            }

            const data = await response.json();

            if (!data.results || !data.summary) {
                throw new Error(data.error || "Invalid response");
            }

            confirmedLong += data.summary.confirmed_long;
            confirmedShort += data.summary.confirmed_short;
            waiting += data.summary.waiting;
            errors += data.summary.data_errors;

            for (const item of data.results) {
                const frames = item.timeframes || {};

                const m1 = frames["1min"]?.analysis?.signal || "ERROR";
                const m5 = frames["5min"]?.analysis?.signal || "ERROR";

                const row = document.createElement("tr");

                const pairCell = document.createElement("td");
                pairCell.textContent = item.pair;

                const m1Cell = document.createElement("td");
                m1Cell.textContent = m1;
                m1Cell.className = m1;

                const m5Cell = document.createElement("td");
                m5Cell.textContent = m5;
                m5Cell.className = m5;

                const statusCell = document.createElement("td");
                statusCell.textContent = item.trade_status || "WAITING";

                if (item.trade_status === "CONFIRMED LONG") {
                    statusCell.className = "LONG";
                } else if (item.trade_status === "CONFIRMED SHORT") {
                    statusCell.className = "SHORT";
                } else if (item.trade_status === "DATA ERROR") {
                    statusCell.className = "ERROR";
                } else {
                    statusCell.className = "WAIT";
                }

                row.append(pairCell, m1Cell, m5Cell, statusCell);
                tbody.appendChild(row);
                scanned++;
            }

            document.getElementById("long").textContent = confirmedLong;
            document.getElementById("short").textContent = confirmedShort;
            document.getElementById("waiting").textContent = waiting;
            document.getElementById("errors").textContent = errors;
        }

        status.textContent =
            "Scan complete. Scanned " + scanned + " / 28 pairs.";

    } catch (error) {
        status.textContent = "Scan failed: " + error.message;
    } finally {
        button.disabled = false;
    }
}
</script>
    </body>
    </html>
    """
