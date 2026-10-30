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

from config import (
    APP_NAME,
    APP_VERSION,
    PAIRS,
    TELEGRAM_CHAT_ID,
    TELEGRAM_BOT_TOKEN,
    MAX_HISTORY,
    SCAN_INTERVAL_SECONDS,
    START_DELAY_SECONDS,
    ALLOWED_SIGNALS
)

from market_data import get_candles
from indicators import analyze_market
from backtesting import run_backtest
from scanner import scan_pair


# =========================================================
# GLOBAL STATE
# =========================================================

SCANNING_ENABLED = False
LAST_SENT = {}
SIGNAL_HISTORY = []

SCAN_SEMAPHORE = asyncio.Semaphore(1)
TELEGRAM_APP = None

SCAN_STATUS = "Ожидание"
LAST_SCAN_TIME = None

# Защита от одновременного запуска нескольких полных сканирований.
SCAN_LOCK = asyncio.Lock()


# =========================================================
# HELPERS
# =========================================================

def now_text():
    return datetime.now(timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )


def is_allowed_chat(chat_id):
    return str(chat_id) == str(TELEGRAM_CHAT_ID)


def telegram_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "▶ СТАРТ",
                callback_data="start"
            ),
            InlineKeyboardButton(
                "⏹ СТОП",
                callback_data="stop"
            )
        ],
        [
            InlineKeyboardButton(
                "📊 АНАЛИЗ",
                callback_data="analyze"
            ),
            InlineKeyboardButton(
                "☁️ СТАТУС",
                callback_data="status"
            )
        ]
    ])


def get_signal(result):
    signal = result.get("signal")

    if signal in ALLOWED_SIGNALS:
        return signal

    return "WAIT"


def get_score(result):
    return result.get(
        "analysis_score",
        result.get("score", 0)
    )


def format_signal_message(pair, result):
    signal = get_signal(result)

    return (
        f"🚀 {APP_NAME}\n\n"
        f"💱 Пара: {pair}\n"
        f"📊 Сигнал: {signal}\n"
        f"💰 Вход: {result.get('entry', '—')}\n"
        f"🛑 Stop Loss: {result.get('stop_loss', '—')}\n"
        f"🎯 Take Profit 1: {result.get('take_profit_1', '—')}\n"
        f"🎯 Take Profit 2: {result.get('take_profit_2', '—')}\n"
        f"⭐ Оценка: {get_score(result)}/100\n"
        f"📈 RSI: {result.get('rsi', '—')}\n"
        f"📊 ADX: {result.get('adx', '—')}\n"
        f"🕒 Время: {now_text()}\n\n"
        "⚠️ Аналитический сигнал. "
        "Не является финансовой рекомендацией."
    )


def format_analysis_message(pair, result):
    signal = get_signal(result)

    lines = [
        f"🔎 ПОДРОБНЫЙ АНАЛИЗ",
        "",
        f"💱 Пара: {pair}",
        f"📊 Решение: {signal}",
        f"⭐ Оценка: {get_score(result)}/100",
        f"📈 RSI: {result.get('rsi', '—')}",
        f"📊 ADX: {result.get('adx', '—')}",
        f"💰 Цена: {result.get('price', '—')}",
        f"📐 EMA 50: {result.get('ema_50', '—')}",
        f"🌡 ATR: {result.get('atr', '—')}",
        "",
        f"🛑 Stop Loss: {result.get('stop_loss', '—')}",
        f"🎯 Take Profit 1: {result.get('take_profit_1', '—')}",
        f"🎯 Take Profit 2: {result.get('take_profit_2', '—')}",
        "",
        f"🕒 {now_text()}",
        "",
        "⚠️ WAIT означает, что условия для сильного сигнала не выполнены."
    ]

    reasons = result.get("reasons", [])

    if reasons:
        lines.extend(["", "📋 Причины:"])

        if isinstance(reasons, list):
            lines.extend(f"• {reason}" for reason in reasons[:8])
        else:
            lines.append(str(reasons))

    # Дополнительные результаты агентов, если Chief Agent их возвращает.
    agents = result.get("agents", {})

    if isinstance(agents, dict) and agents:
        lines.extend(["", "🤖 РЕЗУЛЬТАТЫ АГЕНТОВ"])

        for name, agent_result in agents.items():
            if isinstance(agent_result, dict):
                approved = agent_result.get("approved")
                status = "✅" if approved else "❌"
                reason = agent_result.get("reason", "")
                lines.append(f"{status} {name}: {reason}")
            else:
                lines.append(f"• {name}: {agent_result}")

    return "\n".join(lines)


# =========================================================
# TELEGRAM
# =========================================================

async def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Не настроены данные Telegram.")
        return False

    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)

        async with bot:
            await bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
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
    if not update.effective_chat or not is_allowed_chat(
        update.effective_chat.id
    ):
        if update.message:
            await update.message.reply_text("⛔ Доступ запрещён.")
        return

    await update.message.reply_text(
        f"🚀 {APP_NAME}\n\n"
        "Система готова к работе.\n"
        "Выберите действие:",
        reply_markup=telegram_keyboard()
    )


async def telegram_status_text():
    return (
        f"☁️ СТАТУС {APP_NAME}\n\n"
        "🟢 Render: приложение отвечает\n"
        f"📡 Сканирование: "
        f"{'ВКЛЮЧЕНО 🟢' if SCANNING_ENABLED else 'ОСТАНОВЛЕНО 🔴'}\n"
        f"🔄 Процесс: {SCAN_STATUS}\n"
        f"💱 Валютных пар: {len(PAIRS)}\n"
        "📊 Таймфреймы: M1 + M5\n"
        f"🕒 Последний цикл: {LAST_SCAN_TIME or 'Ещё не запускался'}\n"
        f"🕒 Серверное время: {now_text()}"
    )


async def telegram_buttons(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    global SCANNING_ENABLED

    query = update.callback_query
    await query.answer()

    if not query.message or not is_allowed_chat(
        query.message.chat_id
    ):
        await query.edit_message_text("⛔ Доступ запрещён.")
        return

    if query.data == "start":
        SCANNING_ENABLED = True
        message = "🟢 Автоматическое сканирование включено."

    elif query.data == "stop":
        SCANNING_ENABLED = False
        message = "🔴 Автоматическое сканирование остановлено."

    elif query.data == "status":
        message = await telegram_status_text()

    elif query.data == "analyze":
        await query.edit_message_text(
            "🔎 Запускаю подробный анализ всех валютных пар...\n"
            "Это может занять некоторое время."
        )

        results = await run_full_scan(notify=False)

        lines = ["📊 РЕЗУЛЬТАТЫ АНАЛИЗА", ""]

        for item in results:
            pair = item.get("pair", "?")
            signal = item.get("signal", "WAIT")
            score = item.get("analysis_score", 0)

            lines.append(
                f"{pair}: {signal} | Оценка: {score}/100"
            )

        text = "\n".join(lines)

        # Telegram ограничивает длину одного сообщения.
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=text[:4000],
            reply_markup=telegram_keyboard()
        )
        return

    else:
        return

    await query.edit_message_text(
        message,
        reply_markup=telegram_keyboard()
    )


async def telegram_analyze(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if not update.effective_chat or not is_allowed_chat(
        update.effective_chat.id
    ):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return

    await update.message.reply_text(
        "🔎 Запускаю подробный анализ. Подожди..."
    )

    results = await run_full_scan(notify=False)

    lines = ["📊 РЕЗУЛЬТАТЫ АНАЛИЗА", ""]

    for item in results:
        lines.append(
            f"{item.get('pair', '?')}: "
            f"{item.get('signal', 'WAIT')} | "
            f"{item.get('analysis_score', 0)}/100"
        )

    await update.message.reply_text(
        "\n".join(lines)[:4000],
        reply_markup=telegram_keyboard()
    )


# =========================================================
# MARKET ANALYSIS
# =========================================================

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
        print(f"Ошибка анализа {pair} {interval}: {error}")
        return {"error": str(error)}


async def scan_one_pair(pair, notify=True):
    global SCAN_STATUS

    async with SCAN_SEMAPHORE:
        started = time.time()
        SCAN_STATUS = f"Анализ {pair}"

        try:
            # scanner.py получает M1/M5 и передаёт их Chief Agent.
            result = await scan_pair(pair)

            if not isinstance(result, dict):
                return {
                    "pair": pair,
                    "signal": "WAIT",
                    "status": "ОШИБКА РЕЗУЛЬТАТА"
                }

            signal = get_signal(result)
            score = get_score(result)

            result["pair"] = pair
            result["signal"] = signal
            result["analysis_score"] = score
            result["duration"] = round(
                time.time() - started,
                2
            )

            if signal not in ALLOWED_SIGNALS:
                result["status"] = "ОЖИДАНИЕ"
                return result

            result["status"] = f"ПОДТВЕРЖДЁН {signal}"

            if notify and LAST_SENT.get(pair) != signal:
                message = format_signal_message(pair, result)

                if await send_telegram(message):
                    LAST_SENT[pair] = signal

            SIGNAL_HISTORY.insert(0, {
                "pair": pair,
                "signal": signal,
                "entry": result.get("entry"),
                "stop_loss": result.get("stop_loss"),
                "take_profit_1": result.get("take_profit_1"),
                "score": score,
                "time": now_text()
            })

            del SIGNAL_HISTORY[MAX_HISTORY:]

            return result

        except Exception as error:
            print(f"Ошибка сканирования {pair}: {error}")

            return {
                "pair": pair,
                "signal": "WAIT",
                "status": "ОШИБКА",
                "error": str(error)
            }


async def run_full_scan(notify=True):
    global SCAN_STATUS, LAST_SCAN_TIME

    if SCAN_LOCK.locked():
        return [{
            "pair": "SYSTEM",
            "signal": "WAIT",
            "status": "Сканирование уже выполняется"
        }]

    async with SCAN_LOCK:
        results = []

        for pair in PAIRS:
            if not notify and not SCANNING_ENABLED:
                # Ручной анализ разрешён даже при выключенном
                # автоматическом сканировании.
                pass

            SCAN_STATUS = f"Анализ {pair}"

            result = await scan_one_pair(
                pair,
                notify=notify
            )

            results.append(result)

            await asyncio.sleep(1)

        SCAN_STATUS = "Ожидание следующего цикла"
        LAST_SCAN_TIME = now_text()

        return results


# =========================================================
# AUTOMATIC SCANNER
# =========================================================

async def automatic_scan():
    global SCAN_STATUS

    await asyncio.sleep(START_DELAY_SECONDS)

    while True:
        try:
            if SCANNING_ENABLED:
                print(
                    "Начало автоматического сканирования:",
                    now_text()
                )

                await run_full_scan(notify=True)

        except Exception as error:
            SCAN_STATUS = "Ошибка автоматического сканирования"
            print("Ошибка автоматического сканирования:", error)

        await asyncio.sleep(SCAN_INTERVAL_SECONDS)


# =========================================================
# FASTAPI LIFESPAN
# =========================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    global TELEGRAM_APP

    scan_task = asyncio.create_task(automatic_scan())

    try:
        if TELEGRAM_BOT_TOKEN:
            TELEGRAM_APP = (
                Application.builder()
                .token(TELEGRAM_BOT_TOKEN)
                .build()
            )

            TELEGRAM_APP.add_handler(
                CommandHandler("start", telegram_start)
            )

            TELEGRAM_APP.add_handler(
                CommandHandler("analyze", telegram_analyze)
            )

            TELEGRAM_APP.add_handler(
                CallbackQueryHandler(telegram_buttons)
            )

            await TELEGRAM_APP.initialize()
            await TELEGRAM_APP.start()

            if TELEGRAM_APP.updater:
                await TELEGRAM_APP.updater.start_polling()

        yield

    finally:
        scan_task.cancel()

        try:
            await scan_task
        except asyncio.CancelledError:
            pass

        if TELEGRAM_APP:
            if TELEGRAM_APP.updater:
                await TELEGRAM_APP.updater.stop()

            await TELEGRAM_APP.stop()
            await TELEGRAM_APP.shutdown()


# =========================================================
# FASTAPI APP
# =========================================================

app = FastAPI(
    title=f"{APP_NAME} {APP_VERSION}",
    lifespan=lifespan
)


@app.get("/")
async def home():
    return {
        "name": APP_NAME,
        "version": APP_VERSION,
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
        "scan_status": SCAN_STATUS,
        "last_scan_time": LAST_SCAN_TIME
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
        f"🚀 {APP_NAME}\n\n"
        "✅ Подключение Telegram успешно!"
    )

    return {"telegram_sent": sent}


@app.get("/scan/{pair:path}")
async def scan(pair: str):
    pair = pair.replace("-", "/").upper()

    if pair not in PAIRS:
        return {"error": "Валютная пара не найдена"}

    return await scan_one_pair(pair, notify=False)


@app.get("/scan-all")
async def scan_all():
    results = await run_full_scan(notify=False)

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
        "last_scan_time": LAST_SCAN_TIME,
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
        <h1>Forex Hunter AI</h1>
        <div class="card">
            <p>21 валютная пара</p>
            <p>Анализ M1 + M5</p>
            <p>Технический, стратегический, новостной и риск-анализ</p>
            <p>Состояние: <strong id="status">Проверка...</strong></p>
            <p>Последний цикл: <strong id="last">—</strong></p>
        </div>

        <script>
            async function updateStatus() {
                try {
                    const response = await fetch("/health");
                    const data = await response.json();

                    document.getElementById("status").textContent =
                        data.scanning ? "СКАНИРОВАНИЕ ВКЛЮЧЕНО" :
                        "СКАНИРОВАНИЕ ОСТАНОВЛЕНО";

                    document.getElementById("last").textContent =
                        data.last_scan_time || "Ещё не запускался";

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
