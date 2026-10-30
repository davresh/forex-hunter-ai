
import asyncio
import os
import time
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from telegram import Bot

from indicators import analyze_market
from market_data import get_candles


app = FastAPI(title="Forex Hunter AI", version="2.0.0")

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
bot = Bot(token=TOKEN) if TOKEN else None

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


def now_text():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


async def send_telegram_message(message):
    if not bot or not CHAT_ID:
        return {"error": "Telegram settings missing"}

    try:
        await bot.send_message(chat_id=CHAT_ID, text=message)
        return {"success": True}
    except Exception as error:
        return {"error": str(error)}


def record_signal(pair, signal):
    event = {
        "pair": pair,
        "signal": signal,
        "time": now_text(),
        "mode": "SIMULATION"
    }

    ACTIVE_SIGNALS[pair] = event
    SIGNAL_HISTORY.insert(0, event)
    del SIGNAL_HISTORY[MAX_HISTORY:]


async def maybe_send_trade_signal(pair, m1, m5):
    if m1 in ("LONG", "SHORT") and m1 == m5:
        if LAST_SENT_SIGNALS.get(pair) == m1:
            return

        record_signal(pair, m1)

        emoji = "🟢" if m1 == "LONG" else "🔴"
        message = (
            "🤖 FOREX HUNTER AI\n\n"
            f"{emoji} CONFIRMED {m1}\n"
            f"💱 Pair: {pair}\n"
            f"📈 M1: {m1} | M5: {m5}\n"
            "🧠 EMA + MACD + RSI\n"
            "🛡️ SIMULATION MODE\n"
            "⚠️ Educational signal, not financial advice."
        )

        result = await send_telegram_message(message)

        if result.get("success"):
            LAST_SENT_SIGNALS[pair] = m1

    else:
        LAST_SENT_SIGNALS.pop(pair, None)
        ACTIVE_SIGNALS.pop(pair, None)


async def analyze_pair(pair, interval, retries=2):
    last_error = "Unknown data error"

    for attempt in range(retries + 1):
        try:
            candles = await get_candles(pair, interval)

            if isinstance(candles, dict):
                if candles.get("error"):
                    raise ValueError(str(candles["error"]))
                return interval, candles

            if not candles:
                raise ValueError("No candle data returned")

            analysis = analyze_market(candles)

            return interval, {
                "candles_count": len(candles),
                "analysis": analysis
            }

        except Exception as error:
            last_error = str(error)

            if attempt < retries:
                await asyncio.sleep(1.5 * (attempt + 1))

    return interval, {"error": last_error}


async def scan_one_pair(pair):
    started = time.perf_counter()

    frames = dict(await asyncio.gather(
        analyze_pair(pair, "1min"),
        analyze_pair(pair, "5min")
    ))

    m1 = frames.get("1min", {}).get("analysis", {}).get("signal")
    m5 = frames.get("5min", {}).get("analysis", {}).get("signal")

    has_error = any(
        "error" in frames.get(tf, {})
        for tf in ("1min", "5min")
    )

    if has_error:
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
        "trade_status": status,
        "scan_seconds": round(time.perf_counter() - started, 2)
    }


@app.get("/")
def home():
    return {
        "project": "Forex Hunter AI",
        "version": "2.0.0",
        "status": "online",
        "mode": "simulation"
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "time": now_text()
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
        "🚀 FOREX HUNTER AI\nTelegram connection successful!\nSimulation Mode"
    )


@app.post("/analyze")
def analyze(data: dict):
    return analyze_market(data.get("candles", []))


@app.get("/market/{pair:path}")
async def market(pair: str, interval: str = "1min"):
    if interval not in ("1min", "5min"):
        return {"error": "Use 1min or 5min"}

    _, result = await analyze_pair(pair, interval)
    return {"pair": pair, "timeframe": interval, **result}


@app.get("/scan/{pair:path}")
async def scan_pair_endpoint(pair: str):
    result = await scan_one_pair(pair)
    return result


@app.get("/scan-all")
async def scan_all(offset: int = 0, limit: int = 4):
    if offset < 0 or limit < 1 or limit > 4:
        return {"error": "Use limit 1-4 and offset >= 0"}

    selected = PAIRS[offset:offset + limit]

    results = await asyncio.gather(
        *(scan_one_pair(pair) for pair in selected)
    )

    statuses = [item["trade_status"] for item in results]

    summary = {
        "confirmed_long": statuses.count("CONFIRMED LONG"),
        "confirmed_short": statuses.count("CONFIRMED SHORT"),
        "waiting": statuses.count("WAITING"),
        "data_errors": statuses.count("DATA ERROR")
    }

    next_offset = offset + len(selected)

    return {
        "total_pairs": len(PAIRS),
        "scanned_pairs": len(selected),
        "next_offset": (
            next_offset if next_offset < len(PAIRS) else None
        ),
        "summary": summary,
        "results": results
    }


@app.get("/signal-history")
def signal_history():
    return {
        "active": list(ACTIVE_SIGNALS.values()),
        "history": SIGNAL_HISTORY
    }


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    return """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Forex Hunter AI</title>
<style>
*{box-sizing:border-box}
body{margin:0;padding:22px;background:#080e1c;color:#e2e8f0;font-family:Arial,sans-serif}
.container{max-width:1200px;margin:auto}
header{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px}
h1{color:#38bdf8;margin:8px 0}
h2{font-size:18px;margin-top:28px}
.subtitle,.muted{color:#94a3b8}
.pill{background:#12352c;color:#4ade80;padding:9px 14px;border-radius:20px}
.stats,.times{display:grid;gap:12px;margin:20px 0}
.stats{grid-template-columns:repeat(5,1fr)}
.times{grid-template-columns:repeat(3,1fr)}
.card{background:#121d30;border:1px solid #26364e;border-radius:13px;padding:16px}
.number{font-size:25px;font-weight:bold;margin-top:10px}
button{background:#0284c7;color:white;border:0;border-radius:9px;padding:13px 20px;font-size:15px;cursor:pointer}
button:disabled{opacity:.5;cursor:wait}
#status{margin:16px 0;color:#38bdf8}
.progress{height:9px;background:#26364e;border-radius:20px;overflow:hidden;margin:12px 0 22px}
#progressBar{height:100%;width:0;background:linear-gradient(90deg,#06b6d4,#22c55e);transition:width .2s}
.table-wrap{overflow-x:auto;border:1px solid #26364e;border-radius:12px}
table{width:100%;border-collapse:collapse;background:#121d30}
th,td{padding:12px;text-align:left;border-bottom:1px solid #26364e;white-space:nowrap}
th{color:#94a3b8;background:#17243a;font-size:12px}
tr:hover{background:#1b2b43}
.LONG{color:#4ade80;font-weight:bold}
.SHORT{color:#fb7185;font-weight:bold}
.WAIT{color:#facc15;font-weight:bold}
.ERROR{color:#fb923c;font-weight:bold}
.signal{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;padding:13px;margin:8px 0;background:#121d30;border:1px solid #26364e;border-radius:10px}
.empty{color:#94a3b8;padding:12px}
@media(max-width:850px){.stats{grid-template-columns:repeat(2,1fr)}}
@media(max-width:600px){body{padding:12px}.times{grid-template-columns:1fr}.number{font-size:20px}th,td{padding:9px;font-size:12px}}
</style>
</head>
<body>
<div class="container">
<header>
<div>
<h1>FOREX HUNTER AI</h1>
<p class="subtitle">Smart Market Scanner · Simulation Mode</p>
</div>
<div class="pill">● SYSTEM ONLINE</div>
</header>

<div class="stats">
<div class="card">Currency Pairs<div class="number" id="total">21</div></div>
<div class="card">Confirmed LONG<div class="number LONG" id="long">0</div></div>
<div class="card">Confirmed SHORT<div class="number SHORT" id="short">0</div></div>
<div class="card">Waiting<div class="number WAIT" id="waiting">0</div></div>
<div class="card">Data Errors<div class="number ERROR" id="errors">0</div></div>
</div>

<button id="scanButton" onclick="startScan()">▶ Scan All Pairs</button>
<div id="status">Ready to scan</div>
<div class="progress"><div id="progressBar"></div></div>

<div class="times">
<div class="card">Scan started<div class="number" id="scanStarted">—</div></div>
<div class="card">Scan finished<div class="number" id="scanFinished">—</div></div>
<div class="card">Total duration<div class="number" id="scanDuration">—</div></div>
</div>

<p class="muted" id="lastUpdated">Last updated: —</p>

<h2>⚡ Active Signals</h2>
<div id="activeSignals"><div class="empty">No active signals yet.</div></div>

<h2>📊 Market Scanner</h2>
<div class="table-wrap">
<table>
<thead><tr><th>PAIR</th><th>M1</th><th>M5</th><th>TRADE STATUS</th><th>TIME</th></tr></thead>
<tbody id="results"></tbody>
</table>
</div>

<h2>🕒 Signal History</h2>
<div class="table-wrap">
<table>
<thead><tr><th>TIME (UTC)</th><th>PAIR</th><th>SIGNAL</th><th>MODE</th></tr></thead>
<tbody id="history"></tbody>
</table>
</div>
</div>

<script>
const $ = id => document.getElementById(id);
const TOTAL = 21;

function signalClass(value){
    if(value === "LONG" || value === "CONFIRMED LONG") return "LONG";
    if(value === "SHORT" || value === "CONFIRMED SHORT") return "SHORT";
    if(value === "DATA ERROR" || value === "ERROR") return "ERROR";
    return "WAIT";
}

function addCell(row,value,cls=""){
    const td=document.createElement("td");
    td.textContent=value;
    if(cls) td.className=cls;
    row.appendChild(td);
}

function renderActive(items){
    const box=$("activeSignals");
    box.innerHTML="";

    if(!items.length){
        box.innerHTML='<div class="empty">No active signals yet.</div>';
        return;
    }

    items.forEach(item=>{
        const div=document.createElement("div");
        div.className="signal";
        const left=document.createElement("strong");
        left.className=signalClass(item.signal);
        left.textContent=item.pair+" · "+item.signal;
        const right=document.createElement("span");
        right.textContent=item.time;
        div.append(left,right);
        box.appendChild(div);
    });
}

async function refreshHistory(){
    try{
        const response=await fetch("/signal-history");
        const data=await response.json();

        renderActive(data.active || []);

        const body=$("history");
        body.innerHTML="";

        (data.history || []).forEach(item=>{
            const row=document.createElement("tr");
            addCell(row,item.time);
            addCell(row,item.pair);
            addCell(row,item.signal,signalClass(item.signal));
            addCell(row,item.mode);
            body.appendChild(row);
        });

        if(!body.children.length){
            const row=document.createElement("tr");
            addCell(row,"No signals recorded yet.");
            body.appendChild(row);
        }
    }catch(error){
        console.error("History error:",error);
    }
}

async function startScan(){
    const button=$("scanButton");
    const body=$("results");
    const started=new Date();
    const timer=performance.now();

    let scanned=0;
    const totals={long:0,short:0,waiting:0,errors:0};
    const allResults=[];

    button.disabled=true;
    body.innerHTML="";
    $("progressBar").style.width="0%";
    $("scanStarted").textContent=started.toLocaleString();
    $("scanFinished").textContent="Scanning...";
    $("scanDuration").textContent="—";
    $("lastUpdated").textContent="Scanning in progress...";

    ["long","short","waiting","errors"].forEach(id=>$(id).textContent="0");

    try{
        for(let offset=0;offset<TOTAL;offset+=4){
            $("status").textContent=
                `Scanning ${Math.min(offset+4,TOTAL)} / ${TOTAL} pairs...`;

            const response=await fetch(
                `/scan-all?offset=${offset}&limit=4`
            );

            if(!response.ok){
                throw new Error("Server error: "+response.status);
            }

            const data=await response.json();

            if(!data.results || !data.summary){
                throw new Error(data.error || "Invalid server response");
            }

            totals.long+=data.summary.confirmed_long || 0;
            totals.short+=data.summary.confirmed_short || 0;
            totals.waiting+=data.summary.waiting || 0;
            totals.errors+=data.summary.data_errors || 0;

            allResults.push(...data.results);
            scanned+=data.results.length;

            $("long").textContent=totals.long;
            $("short").textContent=totals.short;
            $("waiting").textContent=totals.waiting;
            $("errors").textContent=totals.errors;
            $("progressBar").style.width=(scanned/TOTAL*100)+"%";
        }

        // Confirmed signals first, then waiting, then errors.
        const priority={
            "CONFIRMED LONG":0,
            "CONFIRMED SHORT":1,
            "WAITING":2,
            "DATA ERROR":3
        };

        allResults.sort((a,b)=>
            (priority[a.trade_status] ?? 4) -
            (priority[b.trade_status] ?? 4)
        );

        allResults.forEach(item=>{
            const frames=item.timeframes || {};
            const m1=frames["1min"]?.analysis?.signal || "ERROR";
            const m5=frames["5min"]?.analysis?.signal || "ERROR";
            const row=document.createElement("tr");

            addCell(row,item.pair);
            addCell(row,m1,signalClass(m1));
            addCell(row,m5,signalClass(m5));
            addCell(row,item.trade_status,signalClass(item.trade_status));
            addCell(row,(item.scan_seconds ?? "—")+" s");

            body.appendChild(row);
        });

        $("status").textContent=
            `Scan complete. Scanned ${scanned} / ${TOTAL} pairs.`;

    }catch(error){
        $("status").textContent="Scan failed: "+error.message;
    }finally{
        const finished=new Date();

        $("scanFinished").textContent=finished.toLocaleString();
        $("scanDuration").textContent=
            ((performance.now()-timer)/1000).toFixed(1)+" sec";
        $("lastUpdated").textContent=
            "Last scan attempt: "+finished.toLocaleString();

        button.disabled=false;
        await refreshHistory();
    }
}

refreshHistory();
</script>
</body>
</html>
"""
