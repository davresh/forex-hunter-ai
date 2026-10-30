
import asyncio
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from telegram import (
    Bot,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes
)

from indicators import analyze_market
from market_data import get_candles
from backtesting import run_backtest


PAIRS = [
    "EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF",
    "AUD/USD", "USD/CAD", "EUR/GBP", "EUR/JPY",
    "EUR/CHF", "EUR/AUD", "EUR/CAD", "GBP/JPY",
    "GBP/CHF", "GBP/AUD", "GBP/CAD", "AUD/JPY",
    "AUD/CHF", "AUD/CAD", "CAD/JPY", "CAD/CHF",
    "CHF/JPY"
]

SCANNING_ENABLED = False
LAST_SENT = {}
SIGNAL_HISTORY = []
MAX_HISTORY = 100

SCAN_SEMAPHORE = asyncio.Semaphore(1)
TELEGRAM_APP = None
SCAN_STATUS = "Ожидание"


def now_text():
    return datetime.now(timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )


def telegram_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("▶ СТАРТ", callback_data="start"),
            InlineKeyboardButton("⏹ СТОП", callback_data="stop")
        ],
        [
            InlineKeyboardButton(
                "☁️ СТАТУС RENDER",
                callback_data="status"
            )
        ]
    ])


async def send_telegram(message):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("Не настроены данные Telegram")
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
        print("Ошибка Telegram:", error)
        return False


async def telegram_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    allowed_chat = os.getenv("TELEGRAM_CHAT_ID")

    if str(update.effective_chat.id) != str(allowed_chat):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return

    await update.message.reply_text(
        "🚀 FOREX HUNTER AI\n\n"
        "Добро пожаловать!\n"
        "Выберите действие:",
        reply_markup=telegram_keyboard()
    )


async def telegram_buttons(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    global SCANNING_ENABLED

    query = update.callback_query
    await query.answer()

    allowed_chat = os.getenv("TELEGRAM_CHAT_ID")

    if str(query.message.chat_id) != str(allowed_chat):
        await query.edit_message_text("⛔ Доступ запрещён.")
        return

    if query.data == "start":
        SCANNING_ENABLED = True
        message = "🟢 Сканирование запущено!"

    elif query.data == "stop":
        SCANNING_ENABLED = False
        message = "🔴 Сканирование остановлено!"

    elif query.data == "status":
        message = (
            "☁️ СТАТУС FOREX HUNTER AI\n\n"
            "🟢 Render: ПРИЛОЖЕНИЕ ОТВЕЧАЕТ\n"
            f"📡 Сканирование: "
            f"{'ВКЛЮЧЕНО 🟢' if SCANNING_ENABLED else 'ОСТАНОВЛЕНО 🔴'}\n"
            f"🔄 Текущий процесс: {SCAN_STATUS}\n"
            f"💱 Валютных пар: {len(PAIRS)}\n"
            "📊 Таймфреймы: M1 + M5\n"
            f"🕒 Время: {now_text()}"
        )

    else:
        return

    await query.edit_message_text(
        message,
        reply_markup=telegram_keyboard()
    )


async def analyze_pair(pair, interval):
    try:
        candles = await get_candles(
            pair,
            interval,
            outputsize=100
        )

        if isinstance(candles, dict) and "error" in candles:
            return {"error": candles["error"]}

        result = analyze_market(candles)

        if result.get("status") != "success":
            return {
                "error": result.get(
                    "message",
                    "Ошибка анализа"
                )
            }

        return result

    except Exception as error:
        return {"error": str(error)}


async def scan_one_pair(pair):
    global SCAN_STATUS

    async with SCAN_SEMAPHORE:
        started = time.time()
        SCAN_STATUS = f"Анализ {pair}"

        m1 = await analyze_pair(pair, "1min")
        m5 = await analyze_pair(pair, "5min")

        if "error" in m1 or "error" in m5:
            return {
                "pair": pair,
                "status": "ОШИБКА ДАННЫХ",
                "m1": m1,
                "m5": m5
            }

        signal1 = m1.get("signal")
        signal5 = m5.get("signal")

        if (
            signal1 not in ("LONG", "SHORT")
            or signal1 != signal5
        ):
            LAST_SENT.pop(pair, None)

            return {
                "pair": pair,
                "status": "ОЖИДАНИЕ",
                "m1": m1,
                "m5": m5
            }

        result = dict(m5)
        result["signal"] = signal1

        result["analysis_score"] = round(
            (
                m1.get("analysis_score", 0)
                + m5.get("analysis_score", 0)
            ) / 2
        )

        if LAST_SENT.get(pair) != signal1:
            message = (
                "🚀 FOREX HUNTER AI\n\n"
                f"💱 Валютная пара: {pair}\n"
                f"📊 Сигнал: {signal1}\n"
                f"💰 Вход: {result.get('entry')}\n"
                f"🛑 Стоп-лосс: {result.get('stop_loss')}\n"
                f"🎯 Тейк-профит 1: {result.get('take_profit_1')}\n"
                f"🎯 Тейк-профит 2: {result.get('take_profit_2')}\n"
                f"⭐ Оценка: {result.get('analysis_score')}/100\n"
                f"📈 RSI: {result.get('rsi')}\n"
                f"📊 ADX: {result.get('adx')}\n"
                f"🕒 Время: {now_text()}\n\n"
                "⚠️ Только аналитический сигнал. "
                "Не финансовая рекомендация."
            )

            if await send_telegram(message):
                LAST_SENT[pair] = signal1

        SIGNAL_HISTORY.insert(0, {
            "pair": pair,
            "signal": signal1,
            "entry": result.get("entry"),
            "stop_loss": result.get("stop_loss"),
            "take_profit_1": result.get("take_profit_1"),
            "score": result.get("analysis_score"),
            "time": now_text()
        })

        del SIGNAL_HISTORY[MAX_HISTORY:]

        return {
            "pair": pair,
            "status": f"ПОДТВЕРЖДЁН {signal1}",
            "m1": m1,
            "m5": m5,
            "combined": result,
            "duration": round(time.time() - started, 2)
        }


async def automatic_scan():
    global SCAN_STATUS

    await asyncio.sleep(10)

    while True:
        if SCANNING_ENABLED:
            print("Начало автоматического сканирования:", now_text())

            for pair in PAIRS:
                if not SCANNING_ENABLED:
                    break

                try:
                    result = await scan_one_pair(pair)
                    print(pair, result.get("status"))

                except Exception as error:
                    print("Ошибка сканирования:", pair, error)

            SCAN_STATUS = (
                "Сканирование остановлено"
                if not SCANNING_ENABLED
                else "Ожидание следующего цикла"
            )

        await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global TELEGRAM_APP

    scan_task = asyncio.create_task(automatic_scan())
    token = os.getenv("TELEGRAM_BOT_TOKEN")

    try:
        if token:
            TELEGRAM_APP = (
                Application.builder()
                .token(token)
                .build()
            )

            TELEGRAM_APP.add_handler(
                CommandHandler("start", telegram_start)
            )

            TELEGRAM_APP.add_handler(
                CallbackQueryHandler(telegram_buttons)
            )

            await TELEGRAM_APP.initialize()
            await TELEGRAM_APP.start()
            await TELEGRAM_APP.updater.start_polling()

        yield

    finally:
        scan_task.cancel()

        try:
            await scan_task
        except asyncio.CancelledError:
            pass

        if TELEGRAM_APP:
            await TELEGRAM_APP.updater.stop()
            await TELEGRAM_APP.stop()
            await TELEGRAM_APP.shutdown()


app = FastAPI(
    title="Forex Hunter AI 4.0",
    lifespan=lifespan
)


@app.get("/")
async def home():
    return {
        "name": "Forex Hunter AI 4.0",
        "status": "online",
        "pairs": len(PAIRS),
        "scanning": SCANNING_ENABLED
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "time": now_text(),
        "scanning": SCANNING_ENABLED,
        "scan_status": SCAN_STATUS
    }


@app.get("/pairs")
async def get_pairs():
    return {
        "pairs": PAIRS,
        "total": len(PAIRS)
    }


@app.get("/telegram-test")
async def telegram_test():
    sent = await send_telegram(
        "🚀 FOREX HUNTER AI\n\n"
        "✅ Подключение Telegram успешно!"
    )

    return {"telegram_sent": sent}


@app.get("/scan/{pair:path}")
async def scan(pair: str):
    pair = pair.replace("-", "/").upper()

    if pair not in PAIRS:
        return {"error": "Валютная пара не найдена"}

    return await scan_one_pair(pair)


@app.get("/scan-all")
async def scan_all():
    results = []

    for pair in PAIRS:
        results.append(await scan_one_pair(pair))

    return {
        "total": len(results),
        "results": results,
        "time": now_text()
    }


@app.get("/analyze")
async def analyze_endpoint():
    return await scan_all()


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
        "scanning": SCANNING_ENABLED,
        "scan_status": SCAN_STATUS,
        "history": SIGNAL_HISTORY,
        "time": now_text()
    }


@app.get("/market/{pair:path}")
async def market(pair: str):
    pair = pair.replace("-", "/").upper()

    if pair not in PAIRS:
        return {"error": "Валютная пара не найдена"}

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


@app.get("/backtest/{pair:path}")
async def backtest_endpoint(
    pair: str,
    interval: str = "1min"
):
    pair = pair.replace("-", "/").upper()

    if pair not in PAIRS:
        return {
            "status": "error",
            "message": "Валютная пара не найдена"
        }

    if interval not in ("1min", "5min"):
        return {
            "status": "error",
            "message": "Интервал должен быть 1min или 5min"
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
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Forex Hunter AI</title>
        <style>
            body {
                background: #0b1120;
                color: white;
                font-family: Arial, sans-serif;
                padding: 20px;
            }
            h1 { color: #38bdf8; }
            .card {
                background: #172033;
                padding: 18px;
                border-radius: 10px;
                margin: 12px 0;
            }
        </style>
    </head>
    <body>
        <h1>Forex Hunter AI 4.0</h1>
        <div class="card">
            <p>21 валютная пара</p>
            <p>Анализ M1 + M5</p>
            <p>Управление через Telegram</p>
            <p>Состояние: <strong id="status">Проверка...</strong></p>
        </div>
        <script>
            async function updateStatus() {
                try {
                    const response = await fetch("/health");
                    const data = await response.json();

                    document.getElementById("status").textContent =
                        data.scanning ? "СКАНИРОВАНИЕ ВКЛЮЧЕНО" :
                        "СКАНИРОВАНИЕ ОСТАНОВЛЕНО";
                } catch (error) {
                    document.getElementById("status").textContent =
                        "СЕРВЕР НЕДОСТУПЕН";
                }
            }

            updateStatus();
            setInterval(updateStatus, 10000);
        </script>
    </body>
    </html>
    """
