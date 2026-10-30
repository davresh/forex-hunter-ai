
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

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
bot = Bot(token=TOKEN) if TOKEN else None
LAST_SENT_SIGNALS = {}

PAIRS = [
    "EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF",
    "AUD/USD", "USD/CAD",
    "EUR/GBP", "EUR/JPY", "EUR/CHF", "EUR/AUD",
    "EUR/CAD",
    "GBP/JPY", "GBP/CHF", "GBP/AUD", "GBP/CAD",
    "AUD/JPY", "AUD/CHF", "AUD/CAD",
    "CAD/JPY", "CAD/CHF", "CHF/JPY"
]


async def send_telegram_message(message):
    if not bot or not CHAT_ID:
        return {"error": "Telegram settings are missing"}

    try:
        await bot.send_message(chat_id=CHAT_ID, text=message)
        return {"success": True}
    except Exception as error:
        return {"error": str(error)}


async def maybe_send_trade_signal(pair, m1, m5):
    if m1 in ("LONG", "SHORT") and m1 == m5:
        if LAST_SENT_SIGNALS.get(pair) != m1:
            emoji = "🟢" if m1 == "LONG" else "🔴"

            message = (
                "━━━━━━━━━━━━━━━━━━\n"
                "🤖 FOREX HUNTER AI\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                f"{emoji} CONFIRMED {m1}\n\n"
                f"💱 Pair: {pair}\n"
                f"📈 M1: {m1}\n"
                f"📊 M5: {m5}\n\n"
                "🧠 Strategy: EMA + MACD + RSI\n"
                "🛡️ MODE: SIMULATION\n"
                "⚠️ Educational signal, not financial advice."
            )

            result = await send_telegram_message(message)
            if result.get("success"):
                LAST_SENT_SIGNALS[pair] = m1
    else:
        LAST_SENT_SIGNALS.pop(pair, None)


@app.get("/")
def home():
    return {
        "project": "Forex Hunter AI",
        "status": "online",
        "mode": "simulation"
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


@app.get("/telegram-test")
async def telegram_test():
    return await send_telegram_message(
        "🚀 FOREX HUNTER AI\n\nTelegram connection successful!\nSimulation Mode"
    )


@app.post("/analyze")
def analyze(data: dict):
    return analyze_market(data.get("candles", []))


async def analyze_pair(pair, interval):
    try:
        candles = await get_candles(pair, interval)

        if isinstance(candles, dict):
            return interval, candles

        return interval, {
            "candles_count": len(candles),
            "analysis": analyze_market(candles)
        }
    except Exception as error:
        return interval, {"error": str(error)}


@app.get("/market/{pair:path}")
async def market(pair: str, interval: str = "1min"):
    if interval not in ("1min", "5min"):
        return {"error": "Use 1min or 5min"}

    _, result = await analyze_pair(pair, interval)
    return {
        "pair": pair,
        "timeframe": interval,
        **result
    }


@app.get("/scan/{pair:path}")
async def scan_pair_endpoint(pair: str):
    frames = dict(await asyncio.gather(
        analyze_pair(pair, "1min"),
        analyze_pair(pair, "5min")
    ))

    m1 = frames.get("1min", {}).get("analysis", {}).get("signal")
    m5 = frames.get("5min", {}).get("analysis", {}).get("signal")

    await maybe_send_trade_signal(pair, m1, m5)

    return {"pair": pair, "results": frames}


@app.get("/scan-all")
async def scan_all(offset: int = 0, limit: int = 4):
    if offset < 0 or limit < 1 or limit > 4:
        return {"error": "Use limit from 1 to 4 and offset from 0"}

    selected = PAIRS[offset:offset + limit]

    async def scan_pair(pair):
        frames = dict(await asyncio.gather(
            analyze_pair(pair, "1min"),
            analyze_pair(pair, "5min")
        ))

        m1 = frames.get("1min", {}).get("analysis", {}).get("signal")
        m5 = frames.get("5min", {}).get("analysis", {}).get("signal")

        if "error" in frames.get("1min", {}) or "error" in frames.get("5min", {}):
            status = "DATA ERROR"
        elif m1 == m5 == "LONG":
            status = "CONFIRMED LONG"
        elif m1 == m5 == "SHORT":
            status = "CONFIRMED SHORT"
        else:
            status = "WAITING"

        await maybe_send_trade_signal(pair, m1, m5)

        return {
            "pair": pair,
            "timeframes": frames,
            "trade_status": status
        }

    results = await asyncio.gather(*(scan_pair(p) for p in selected))

    summary = {
        "confirmed_long": sum(r["trade_status"] == "CONFIRMED LONG" for r in results),
        "confirmed_short": sum(r["trade_status"] == "CONFIRMED SHORT" for r in results),
        "waiting": sum(r["trade_status"] == "WAITING" for r in results),
        "data_errors": sum(r["trade_status"] == "DATA ERROR" for r in results)
    }

    next_offset = offset + len(selected)

    return {
        "total_pairs": len(PAIRS),
        "scanned_pairs": len(selected),
        "next_offset": next_offset if next_offset < len(PAIRS) else None,
        "summary": summary,
        "results": results
    }


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    return """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Forex Hunter AI</title>
<style>
*{box-sizing:border-box}
body{margin:0;padding:20px;background:#0b1120;color:#e5e7eb;font-family:Arial}
.container{max-width:1150px;margin:auto}
h1{color:#38bdf8}
.subtitle{color:#94a3b8}
.stats,.time-grid{display:grid;gap:12px;margin:20px 0}
.stats{grid-template-columns:repeat(5,1fr)}
.time-grid{grid-template-columns:repeat(3,1fr)}
.card{background:#172033;padding:16px;border:1px solid #293449;border-radius:10px}
.number{font-size:24px;font-weight:bold;margin-top:8px}
button{background:#2563eb;color:white;border:0;padding:13px 20px;border-radius:8px;cursor:pointer}
button:disabled{opacity:.5}
#status{color:#38bdf8;margin:15px 0}
.progress{height:10px;background:#293449;border-radius:10px;overflow:hidden;margin:15px 0}
#progressBar{height:100%;width:0;background:#22c55e}
.table-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;background:#172033}
th,td{padding:12px;text-align:left;border-bottom:1px solid #293449;white-space:nowrap}
th{color:#94a3b8}
.LONG{color:#22c55e;font-weight:bold}
.SHORT{color:#ef4444;font-weight:bold}
.WAIT{color:#facc15;font-weight:bold}
.ERROR{color:#f97316;font-weight:bold}
@media(max-width:850px){.stats{grid-template-columns:repeat(2,1fr)}}
@media(max-width:600px){body{padding:10px}.time-grid{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="container">
<h1>FOREX HUNTER AI</h1>
<p class="subtitle">Market Scanner | Simulation Mode</p>

<div class="stats">
<div class="card">Currency Pairs<div class="number" id="total">21</div></div>
<div class="card">Confirmed LONG<div class="number LONG" id="long">0</div></div>
<div class="card">Confirmed SHORT<div class="number SHORT" id="short">0</div></div>
<div class="card">Waiting<div class="number WAIT" id="waiting">0</div></div>
<div class="card">Data Errors<div class="number ERROR" id="errors">0</div></div>
</div>

<button id="scanButton" onclick="startScan()">Scan All Pairs</button>
<div id="status">Ready to scan</div>
<div class="progress"><div id="progressBar"></div></div>

<div class="time-grid">
<div class="card">Scan started<div class="number" id="scanStarted">—</div></div>
<div class="card">Scan finished<div class="number" id="scanFinished">—</div></div>
<div class="card">Scan duration<div class="number" id="scanDuration">—</div></div>
</div>

<p class="subtitle" id="lastUpdated">Last updated: —</p>

<div class="table-wrap">
<table>
<thead><tr><th>Pair</th><th>M1</th><th>M5</th><th>TRADE STATUS</th></tr></thead>
<tbody id="results"></tbody>
</table>
</div>
</div>

<script>
async function startScan(){
    const tbody=document.getElementById("results");
    const status=document.getElementById("status");
    const button=document.getElementById("scanButton");
    const progress=document.getElementById("progressBar");
    const started=new Date();
    const timer=performance.now();

    button.disabled=true;
    tbody.innerHTML="";
    progress.style.width="0%";

    document.getElementById("scanStarted").textContent=started.toLocaleString();
    document.getElementById("scanFinished").textContent="Scanning...";
    document.getElementById("scanDuration").textContent="—";
    document.getElementById("lastUpdated").textContent="Scanning in progress...";

    let totals={confirmedLong:0,confirmedShort:0,waiting:0,errors:0};
    let scanned=0;

    ["long","short","waiting","errors"].forEach(id=>{
        document.getElementById(id).textContent="0";
    });

    try{
        for(let offset=0;offset<21;offset+=4){
            status.textContent="Scanning "+Math.min(offset+4,21)+" / 21 pairs...";

            const response=await fetch(
                "/scan-all?offset="+offset+"&limit=4"
            );

            if(!response.ok) throw new Error("Server error: "+response.status);

            const data=await response.json();
            if(!data.results||!data.summary){
                throw new Error(data.error||"Invalid server response");
            }

            totals.confirmedLong+=data.summary.confirmed_long||0;
            totals.confirmedShort+=data.summary.confirmed_short||0;
            totals.waiting+=data.summary.waiting||0;
            totals.errors+=data.summary.data_errors||0;

            for(const item of data.results){
                const frames=item.timeframes||{};
                const m1=frames["1min"]?.analysis?.signal||"ERROR";
                const m5=frames["5min"]?.analysis?.signal||"ERROR";
                const row=document.createElement("tr");

                function cell(value,cls){
                    const td=document.createElement("td");
                    td.textContent=value;
                    td.className=cls||"";
                    return td;
                }

                const trade=item.trade_status||"WAITING";
                const cls=trade==="CONFIRMED LONG"?"LONG":
                    trade==="CONFIRMED SHORT"?"SHORT":
                    trade==="DATA ERROR"?"ERROR":"WAIT";

                row.append(
                    cell(item.pair),
                    cell(m1,m1),
                    cell(m5,m5),
                    cell(trade,cls)
                );

                tbody.appendChild(row);
                scanned++;
            }

            document.getElementById("long").textContent=totals.confirmedLong;
            document.getElementById("short").textContent=totals.confirmedShort;
            document.getElementById("waiting").textContent=totals.waiting;
            document.getElementById("errors").textContent=totals.errors;
            progress.style.width=(scanned/21*100)+"%";
        }

        status.textContent="Scan complete. Scanned "+scanned+" / 21 pairs.";

    }catch(error){
        status.textContent="Scan failed: "+error.message;
    }finally{
        const finished=new Date();
        document.getElementById("scanFinished").textContent=finished.toLocaleString();
        document.getElementById("scanDuration").textContent=
            ((performance.now()-timer)/1000).toFixed(1)+" seconds";
        document.getElementById("lastUpdated").textContent=
            "Last updated: "+finished.toLocaleString();
        button.disabled=false;
    }
}
</script>
</body>
</html>
"""
