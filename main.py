
import asyncio
import os
import time
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from telegram import Bot

from indicators import analyze_market
from market_data import get_candles
from backtesting import run_backtest


app = FastAPI(title="Forex Hunter AI 4.0")

PAIRS = [
    "EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF",
    "AUD/USD", "USD/CAD", "EUR/GBP", "EUR/JPY",
    "EUR/CHF", "EUR/AUD", "EUR/CAD", "GBP/JPY",
    "GBP/CHF", "GBP/AUD", "GBP/CAD", "AUD/JPY",
    "AUD/CHF", "AUD/CAD", "CAD/JPY", "CAD/CHF",
    "CHF/JPY"
]

LAST_SENT_SIGNALS = {}
ACTIVE_SIGNALS = {}
SIGNAL_HISTORY = []

MAX_HISTORY = 100
SCAN_SEMAPHORE = asyncio.Semaphore(1)


def now_text():
    return datetime.now(timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )


async def send_telegram_message(message):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        return False

    try:
        bot = Bot(token=token)

        async with bot:
            await bot.send_message(
                chat_id=chat_id,
                text=message
            )

        return True

    except Exception as error:
        print("Telegram error:", error)
        return False


def record_signal(pair, result):
    item = {
        "pair": pair,
        "signal": result.get("signal"),
        "entry": result.get("entry"),
        "stop_loss": result.get("stop_loss"),
        "take_profit_1": result.get("take_profit_1"),
        "take_profit_2": result.get("take_profit_2"),
        "score": result.get("analysis_score", 0),
        "time": now_text()
    }

    SIGNAL_HISTORY.insert(0, item)
    del SIGNAL_HISTORY[MAX_HISTORY:]

    return item


async def maybe_send_trade_signal(pair, result):
    signal = result.get("signal")

    if signal not in ("LONG", "SHORT"):
        ACTIVE_SIGNALS.pop(pair, None)
        LAST_SENT_SIGNALS.pop(pair, None)
        return

    ACTIVE_SIGNALS[pair] = result

    if LAST_SENT_SIGNALS.get(pair) == signal:
        return

    message = (
        "Forex Hunter AI 4.0\n\n"
        f"Pair: {pair}\n"
        f"Signal: {signal}\n"
        f"Entry: {result.get('entry')}\n"
        f"Stop Loss: {result.get('stop_loss')}\n"
        f"Take Profit 1: {result.get('take_profit_1')}\n"
        f"Take Profit 2: {result.get('take_profit_2')}\n"
        f"Analysis score: {result.get('analysis_score')}/100\n"
        f"RSI: {result.get('rsi')}\n"
        f"ADX: {result.get('adx')}\n\n"
        "SIMULATION ONLY. NOT FINANCIAL ADVICE."
    )

    sent = await send_telegram_message(message)

    if sent:
        LAST_SENT_SIGNALS[pair] = signal


async def analyze_pair(pair, interval):
    try:
        candles = await get_candles(
            pair,
            interval,
            outputsize=100
        )

        if isinstance(candles, dict) and "error" in candles:
            return {"error": candles["error"]}

        analysis = analyze_market(candles)

        if analysis.get("status") != "success":
            return {
                "error": analysis.get(
                    "message",
                    "Analysis unavailable"
                )
            }

        return {
            "candles_count": len(candles),
            "analysis": analysis
        }

    except Exception as error:
        return {"error": str(error)}


async def scan_one_pair(pair):
    async with SCAN_SEMAPHORE:
        started = time.time()

        m1 = await analyze_pair(pair, "1min")
        m5 = await analyze_pair(pair, "5min")

        duration = round(time.time() - started, 2)

        if "error" in m1 or "error" in m5:
            return {
                "pair": pair,
                "status": "DATA ERROR",
                "m1": m1,
                "m5": m5,
                "duration": duration
            }

        a1 = m1["analysis"]
        a5 = m5["analysis"]

        signal1 = a1["signal"]
        signal5 = a5["signal"]

        if (
            signal1 == signal5
            and signal1 in ("LONG", "SHORT")
        ):
            combined = dict(a5)

            combined["signal"] = signal1

            combined["analysis_score"] = round(
                (
                    a1["analysis_score"]
                    + a5["analysis_score"]
                ) / 2
            )

            status = f"CONFIRMED {signal1}"

            record_signal(pair, combined)

            await maybe_send_trade_signal(
                pair,
                combined
            )

        else:
            combined = {
                "signal": "WAIT",
                "analysis_score": 0
            }

            status = "WAITING"

            ACTIVE_SIGNALS.pop(pair, None)
            LAST_SENT_SIGNALS.pop(pair, None)

        return {
            "pair": pair,
            "status": status,
            "m1": m1,
            "m5": m5,
            "combined": combined,
            "duration": duration
        }


@app.get("/")
async def home():
    return {
        "name": "Forex Hunter AI 4.0",
        "status": "online",
        "pairs": len(PAIRS),
        "mode": "SIMULATION ONLY"
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "time": now_text()
    }


@app.get("/pairs")
async def get_pairs():
    return {
        "pairs": PAIRS,
        "total": len(PAIRS)
    }


@app.get("/telegram-test")
async def telegram_test():
    sent = await send_telegram_message(
        "Forex Hunter AI 4.0: Telegram test successful."
    )

    return {"telegram_sent": sent}


@app.get("/analyze")
async def analyze_endpoint():
    results = []

    for pair in PAIRS:
        results.append(
            await scan_one_pair(pair)
        )

    return {
        "total": len(results),
        "results": results
    }


@app.get("/market/{pair:path}")
async def market(pair: str):
    pair = pair.replace("-", "/").upper()

    if pair not in PAIRS:
        return {"error": "Pair not found"}

    candles = await get_candles(
        pair,
        "1min",
        outputsize=100
    )

    if isinstance(candles, dict) and "error" in candles:
        return candles

    return {
        "pair": pair,
        "candles_count": len(candles),
        "analysis": analyze_market(candles)
    }


@app.get("/scan/{pair:path}")
async def scan(pair: str):
    pair = pair.replace("-", "/").upper()

    if pair not in PAIRS:
        return {
            "error": "Pair not found",
            "pair": pair
        }

    return await scan_one_pair(pair)


@app.get("/scan-all")
async def scan_all():
    results = []

    for pair in PAIRS:
        result = await scan_one_pair(pair)
        results.append(result)

    return {
        "total": len(results),
        "results": results,
        "active_signals": ACTIVE_SIGNALS,
        "history_count": len(SIGNAL_HISTORY),
        "time": now_text()
    }


@app.get("/signal-history")
async def signal_history():
    return {
        "total": len(SIGNAL_HISTORY),
        "signals": SIGNAL_HISTORY
    }


@app.get("/dashboard-data")
async def dashboard_data():
    return {
        "pairs": len(PAIRS),
        "active_signals": ACTIVE_SIGNALS,
        "history": SIGNAL_HISTORY,
        "time": now_text()
    }


@app.get("/backtest/{pair:path}")
async def backtest_endpoint(
    pair: str,
    interval: str = "1min"
):
    pair = pair.replace("-", "/").upper()

    if pair not in PAIRS:
        return {
            "status": "error",
            "message": "Pair not found",
            "pair": pair
        }

    if interval not in ("1min", "5min"):
        return {
            "status": "error",
            "message": "Interval must be 1min or 5min"
        }

    candles = await get_candles(
        pair,
        interval,
        outputsize=100
    )

    if isinstance(candles, dict) and "error" in candles:
        return {
            "status": "error",
            "message": candles["error"]
        }

    result = run_backtest(
        candles,
        initial_balance=10000,
        risk_percent=1.0,
        reward_risk=2.0
    )

    result["pair"] = pair
    result["interval"] = interval

    return result


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport"
              content="width=device-width, initial-scale=1">

        <title>Forex Hunter AI 4.0</title>

        <style>
            * { box-sizing: border-box; }

            body {
                margin: 0;
                padding: 20px;
                background: #0b1120;
                color: #e5e7eb;
                font-family: Arial, sans-serif;
            }

            h1 { color: #38bdf8; }
            .sub { color: #94a3b8; }

            .stats {
                display: grid;
                grid-template-columns:
                    repeat(auto-fit,minmax(140px,1fr));
                gap: 12px;
                margin: 20px 0;
            }

            .card {
                background: #172033;
                padding: 16px;
                border-radius: 10px;
            }

            .number {
                font-size: 26px;
                font-weight: bold;
                margin-top: 8px;
            }

            button {
                background: #0284c7;
                border: 0;
                color: white;
                padding: 12px 18px;
                border-radius: 7px;
                cursor: pointer;
            }

            button:disabled {
                opacity: .5;
                cursor: wait;
            }

            .table-wrap {
                overflow-x: auto;
                margin-top: 16px;
            }

            table {
                width: 100%;
                border-collapse: collapse;
                min-width: 850px;
                background: #172033;
            }

            th, td {
                padding: 11px;
                border-bottom: 1px solid #334155;
                text-align: left;
                font-size: 13px;
            }

            th { color: #94a3b8; }

            .LONG { color: #4ade80; }
            .SHORT { color: #fb7185; }
            .WAITING { color: #facc15; }
            .error { color: #f87171; }

            #progress {
                margin: 15px 0;
                color: #94a3b8;
            }

            .section { margin-top: 30px; }
        </style>
    </head>

    <body>
        <h1>Forex Hunter AI 4.0</h1>

        <div class="sub">
            Advanced Forex Analysis | Simulation Only
        </div>

        <div class="stats">
            <div class="card">
                Currency pairs
                <div class="number" id="total">21</div>
            </div>

            <div class="card">
                Confirmed LONG
                <div class="number LONG" id="long">0</div>
            </div>

            <div class="card">
                Confirmed SHORT
                <div class="number SHORT" id="short">0</div>
            </div>

            <div class="card">
                Waiting
                <div class="number" id="waiting">0</div>
            </div>

            <div class="card">
                Data errors
                <div class="number error" id="errors">0</div>
            </div>
        </div>

        <button id="scanButton" onclick="startScan()">
            Start Market Scan
        </button>

        <div id="progress">Ready to scan.</div>

        <div class="section">
            <h2>Market Scanner</h2>

            <div class="table-wrap">
                <table>
                    <thead>
                        <tr>
                            <th>Pair</th>
                            <th>M1</th>
                            <th>M5</th>
                            <th>Decision</th>
                            <th>Score</th>
                            <th>Entry</th>
                            <th>Stop Loss</th>
                            <th>Take Profit</th>
                            <th>Seconds</th>
                        </tr>
                    </thead>

                    <tbody id="scanner"></tbody>
                </table>
            </div>
        </div>

        <div class="section">
            <h2>Signal History</h2>

            <div class="table-wrap">
                <table>
                    <thead>
                        <tr>
                            <th>Pair</th>
                            <th>Signal</th>
                            <th>Entry</th>
                            <th>Stop Loss</th>
                            <th>Take Profit</th>
                            <th>Score</th>
                            <th>Time</th>
                        </tr>
                    </thead>

                    <tbody id="history"></tbody>
                </table>
            </div>
        </div>

        <script>
            const pairs = [
                "EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF",
                "AUD/USD", "USD/CAD", "EUR/GBP", "EUR/JPY",
                "EUR/CHF", "EUR/AUD", "EUR/CAD", "GBP/JPY",
                "GBP/CHF", "GBP/AUD", "GBP/CAD", "AUD/JPY",
                "AUD/CHF", "AUD/CAD", "CAD/JPY", "CAD/CHF",
                "CHF/JPY"
            ];

            const scanner =
                document.getElementById("scanner");

            const historyBody =
                document.getElementById("history");

            const button =
                document.getElementById("scanButton");

            const progress =
                document.getElementById("progress");

            function cell(value) {
                return value === null || value === undefined
                    ? "—" : value;
            }

            function addRow(result) {
                const m1 =
                    result.m1?.analysis?.signal || "ERROR";

                const m5 =
                    result.m5?.analysis?.signal || "ERROR";

                const combined = result.combined || {};
                const signal = result.status || "WAITING";

                const values = [
                    result.pair,
                    m1,
                    m5,
                    signal,
                    cell(combined.analysis_score),
                    cell(combined.entry),
                    cell(combined.stop_loss),
                    cell(combined.take_profit_1),
                    cell(result.duration)
                ];

                const row = document.createElement("tr");

                values.forEach((value, index) => {
                    const td = document.createElement("td");
                    td.textContent = value;

                    if (index === 3) {
                        if (signal.includes("LONG")) {
                            td.className = "LONG";
                        } else if (signal.includes("SHORT")) {
                            td.className = "SHORT";
                        } else if (signal === "DATA ERROR") {
                            td.className = "error";
                        } else {
                            td.className = "WAITING";
                        }
                    }

                    row.appendChild(td);
                });

                scanner.appendChild(row);
            }

            async function loadHistory() {
                try {
                    const response =
                        await fetch("/signal-history");

                    const data = await response.json();

                    historyBody.innerHTML = "";

                    data.signals.forEach(item => {
                        const row =
                            document.createElement("tr");

                        [
                            item.pair,
                            item.signal,
                            cell(item.entry),
                            cell(item.stop_loss),
                            cell(item.take_profit_1),
                            cell(item.score),
                            item.time
                        ].forEach(value => {
                            const td =
                                document.createElement("td");

                            td.textContent = value;
                            row.appendChild(td);
                        });

                        historyBody.appendChild(row);
                    });

                } catch (error) {
                    console.error(error);
                }
            }

            async function startScan() {
                if (button.disabled) return;

                button.disabled = true;
                scanner.innerHTML = "";

                let completed = 0;
                let long = 0;
                let short = 0;
                let waiting = 0;
                let errors = 0;

                document.getElementById("long").textContent = "0";
                document.getElementById("short").textContent = "0";
                document.getElementById("waiting").textContent = "0";
                document.getElementById("errors").textContent = "0";

                progress.textContent = "Starting scan...";

                try {
                    for (const pair of pairs) {
                        progress.textContent =
                            "Scanning " + pair +
                            " (" + (completed + 1) +
                            "/" + pairs.length + ")...";

                        try {
                            const response = await fetch(
                                "/scan/" + encodeURIComponent(pair)
                            );

                            if (!response.ok) {
                                throw new Error(
                                    "HTTP " + response.status
                                );
                            }

                            const result = await response.json();

                            if (result.error) {
                                throw new Error(result.error);
                            }

                            addRow(result);

                            if (result.status === "CONFIRMED LONG") {
                                long++;
                            } else if (
                                result.status === "CONFIRMED SHORT"
                            ) {
                                short++;
                            } else if (
                                result.status === "DATA ERROR"
                            ) {
                                errors++;
                            } else {
                                waiting++;
                            }

                        } catch (error) {
                            errors++;

                            addRow({
                                pair: pair,
                                status: "DATA ERROR",
                                duration: "—"
                            });

                            console.error(pair, error);

                        } finally {
                            completed++;

                            document.getElementById("long").textContent = long;
                            document.getElementById("short").textContent = short;
                            document.getElementById("waiting").textContent = waiting;
                            document.getElementById("errors").textContent = errors;
                        }
                    }

                    await loadHistory();

                    progress.textContent =
                        "Scan complete: " + completed +
                        "/" + pairs.length + " pairs.";

                } catch (error) {
                    progress.textContent =
                        "Scan error: " + error.message;

                } finally {
                    button.disabled = false;
                }
            }

            loadHistory();
        </script>
    </body>
    </html>
    """
