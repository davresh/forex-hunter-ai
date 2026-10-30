
import asyncio
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from telegram import (
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

TELEGRAM_APP = None

SCAN_STATUS = "Ожидание"
LAST_SCAN_TIME = None

# Prevent overlapping full scans and manual scans.
SCAN_LOCK = asyncio.Lock()

# Prevent simultaneous processing of individual pairs.
SCAN_SEMAPHORE = asyncio.Semaphore(1)


# =========================================================
# HELPERS
# =========================================================

def now_text():
    return datetime.now(timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )


def is_allowed_chat(chat_id):
    if not TELEGRAM_CHAT_ID:
        return False

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
    """
    A signal is valid only when Chief Agent explicitly approves it.
    """

    if not isinstance(result, dict):
        return "WAIT"

    if result.get("approved") is not True:
        return "WAIT"

    signal = str(result.get("signal", "")).upper()

    if signal in ALLOWED_SIGNALS:
        return signal

    return "WAIT"


def get_agents(result):
    agents = result.get("agents", {})

    return agents if isinstance(agents, dict) else {}


def get_analysis(result):
    """
    Extract the M5 technical analysis when available.
    """

    agents = get_agents(result)

    m5 = agents.get("m5_technical", {})

    if isinstance(m5, dict):
        analysis = m5.get("analysis")

        if isinstance(analysis, dict):
            return analysis

    m1 = agents.get("m1_technical", {})

    if isinstance(m1, dict):
        analysis = m1.get("analysis")

        if isinstance(analysis, dict):
            return analysis

    return {}


def get_score(result):
    score = result.get("analysis_score")

    if score is not None:
        return score

    agents = get_agents(result)

    m5 = agents.get("m5_technical", {})

    if isinstance(m5, dict):
        return m5.get("score", 0)

    return 0


def format_signal_message(pair, result):
    signal = get_signal(result)

    return (
        f"🚀 {APP_NAME}\n\n"
        f"💱 Пара: {pair}\n"
        f"📊 Сигнал: {signal}\n"
        f"💰 Вход: {result.get('entry', '—')}\n"
        f"🛑 Stop Loss: {result.get('stop_loss', '—')}\n"
        f"🎯 Take Profit: {result.get('take_profit', '—')}\n"
        f"⚖️ Risk/Reward: {result.get('risk_reward', '—')}\n"
        f"⭐ Оценка: {get_score(result)}/100\n"
        f"📈 RSI: {result.get('rsi', '—')}\n"
        f"📊 ADX: {result.get('adx', '—')}\n"
        f"🕒 Время: {now_text()}\n\n"
        "⚠️ Аналитический сигнал. "
        "Не является финансовой рекомендацией."
    )


def format_analysis_message(pair, result):
    signal = get_signal(result)
    analysis = get_analysis(result)

    def value(key):
        return result.get(key, analysis.get(key, "—"))

    lines = [
        "🔎 ПОДРОБНЫЙ АНАЛИЗ",
        "",
        f"💱 Пара: {pair}",
        f"📊 Решение: {signal}",
        f"⭐ Оценка: {get_score(result)}/100",
        "",
        f"💰 Цена: {value('price')}",
        f"📈 RSI: {value('rsi')}",
        f"📊 ADX: {value('adx')}",
        f"📐 EMA 50: {value('ema_50')}",
        f"🌡 ATR: {value('atr')}",
        f"📉 Поддержка: {value('support')}",
        f"📈 Сопротивление: {value('resistance')}",
        "",
        f"🛑 Stop Loss: {result.get('stop_loss', '—')}",
        f"🎯 Take Profit: {result.get('take_profit', '—')}",
        f"⚖️ Risk/Reward: {result.get('risk_reward', '—')}",
        "",
        f"📝 Итог: {result.get('reason', 'Нет дополнительной информации')}",
        f"🕒 {now_text()}"
    ]

    reasons = result.get(
        "reasons",
        analysis.get("reasons", [])
    )

    if reasons:
        lines.extend(["", "📋 ТЕХНИЧЕСКИЕ ПРИЧИНЫ"])

        if isinstance(reasons, list):
            lines.extend(
                f"• {reason}"
                for reason in reasons[:8]
            )
        else:
            lines.append(str(reasons))

    agents = get_agents(result)

    if agents:
        lines.extend(["", "🤖 РЕЗУЛЬТАТЫ АГЕНТОВ"])

        for name, agent_result in agents.items():
            if not isinstance(agent_result, dict):
                continue

            if "approved" not in agent_result:
                continue

            approved = agent_result.get("approved") is True
            status = "✅" if approved else "❌"

            reason = agent_result.get(
                "reason",
                "Результат получен"
            )

            lines.append(
                f"{status} {name}: {reason}"
            )

            events = agent_result.get("events", [])

            if isinstance(events, list):
                for event in events[:3]:
                    if isinstance(event, dict):
                        lines.append(
                            f"   • {event.get('currency', '')}: "
                            f"{event.get('title', '')}"
                        )

    if result.get("error"):
        lines.extend([
            "",
            f"⚠️ Ошибка: {result['error']}"
        ])

    lines.extend([
        "",
        "⚠️ WAIT означает, что все условия "
        "для подтверждённого сигнала не выполнены."
    ])

    return "\n".join(lines)


async def send_long_message(bot, chat_id, message):
    """
    Split long Telegram messages without cutting lines.
    """

    max_length = 3800
    chunks = []
    current = ""

    for line in message.splitlines():
        if len(current) + len(line) + 1 > max_length:
            if current:
                chunks.append(current)

            current = line
        else:
            current += ("\n" if current else "") + line

    if current:
        chunks.append(current)

    for chunk in chunks:
        await bot.send_message(
            chat_id=chat_id,
            text=chunk
        )


# =========================================================
# TELEGRAM
# =========================================================

async def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram credentials are not configured.")
        return False

    if TELEGRAM_APP is not None:
        try:
            await TELEGRAM_APP.bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text=message
            )

            return True

        except Exception as error:
            print("Telegram send error:", error)
            return False

    return False


async def telegram_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if (
        not update.effective_chat
        or not is_allowed_chat(update.effective_chat.id)
    ):
        if update.message:
            await update.message.reply_text(
                "⛔ Доступ запрещён."
            )
        return

    if update.message:
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


async def telegram_analyze(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if (
        not update.effective_chat
        or not is_allowed_chat(update.effective_chat.id)
    ):
        if update.message:
            await update.message.reply_text(
                "⛔ Доступ запрещён."
            )
        return

    await update.message.reply_text(
        "🔎 Запускаю анализ всех валютных пар.\n"
        "Пожалуйста, подожди..."
    )

    results = await run_full_scan(notify=False)

    if (
        len(results) == 1
        and results[0].get("status") == "Сканирование уже выполняется"
    ):
        await update.message.reply_text(
            "⏳ Сканирование уже выполняется. "
            "Попробуй немного позже."
        )
        return

    for result in results:
        pair = result.get("pair", "?")

        await send_long_message(
            context.bot,
            update.effective_chat.id,
            format_analysis_message(pair, result)
        )


async def telegram_buttons(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    global SCANNING_ENABLED

    query = update.callback_query

    await query.answer()

    if (
        not query.message
        or not is_allowed_chat(query.message.chat_id)
    ):
        if query.message:
            await query.edit_message_text(
                "⛔ Доступ запрещён."
            )
        return

    if query.data == "start":
        SCANNING_ENABLED = True

        message = (
            "🟢 Автоматическое сканирование включено."
        )

    elif query.data == "stop":
        SCANNING_ENABLED = False

        message = (
            "🔴 Автоматическое сканирование остановлено."
        )

    elif query.data == "status":
        message = await telegram_status_text()

    elif query.data == "analyze":
        await query.edit_message_text(
            "🔎 Запускаю анализ всех валютных пар...\n"
            "Подожди, пожалуйста."
        )

        results = await run_full_scan(notify=False)

        if (
            len(results) == 1
            and results[0].get("status")
            == "Сканирование уже выполняется"
        ):
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="⏳ Сканирование уже выполняется.",
                reply_markup=telegram_keyboard()
            )
            return

        for result in results:
            await send_long_message(
                context.bot,
                query.message.chat_id,
                format_analysis_message(
                    result.get("pair", "?"),
                    result
                )
            )

        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="✅ Анализ завершён.",
            reply_markup=telegram_keyboard()
        )
        return

    else:
        return

    await query.edit_message_text(
        message,
        reply_markup=telegram_keyboard()
    )


# =========================================================
# SCANNING
# =========================================================

async def scan_one_pair(pair, notify=True):
    global SCAN_STATUS

    async with SCAN_SEMAPHORE:
        started = time.time()
        SCAN_STATUS = f"Анализ {pair}"

        try:
            result = await scan_pair(pair)

            if not isinstance(result, dict):
                return {
                    "pair": pair,
                    "approved": False,
                    "signal": "WAIT",
                    "status": "Ошибка результата"
                }

            # Chief Agent approval is mandatory.
            signal = get_signal(result)

            result["pair"] = pair
            result["signal"] = signal
            result["duration"] = round(
                time.time() - started,
                2
            )

            result["analysis_score"] = get_score(result)

            if signal == "WAIT":
                result["status"] = "ОЖИДАНИЕ"
                return result

            result["status"] = f"ПОДТВЕРЖДЁН {signal}"

            # Send only a new direction for this pair.
            if notify and LAST_SENT.get(pair) != signal:
                message = format_signal_message(
                    pair,
                    result
                )

                sent = await send_telegram(message)

                if sent:
                    LAST_SENT[pair] = signal

            SIGNAL_HISTORY.insert(0, {
                "pair": pair,
                "signal": signal,
                "entry": result.get("entry"),
                "stop_loss": result.get("stop_loss"),
                "take_profit": result.get("take_profit"),
                "score": result.get("analysis_score"),
                "time": now_text()
            })

            del SIGNAL_HISTORY[MAX_HISTORY:]

            return result

        except Exception as error:
            print(
                f"Scanning error for {pair}: {error}"
            )

            return {
                "pair": pair,
                "approved": False,
                "signal": "WAIT",
                "status": "ОШИБКА",
                "error": str(error)
            }


async def run_full_scan(notify=True):
    global SCAN_STATUS, LAST_SCAN_TIME

    if SCAN_LOCK.locked():
        return [{
            "pair": "SYSTEM",
            "approved": False,
            "signal": "WAIT",
            "status": "Сканирование уже выполняется"
        }]

    async with SCAN_LOCK:
        results = []

        try:
            for pair in PAIRS:
                SCAN_STATUS = f"Анализ {pair}"

                result = await scan_one_pair(
                    pair,
                    notify=notify
                )

                results.append(result)

                # Small delay between currency pairs.
                await asyncio.sleep(1)

            return results

        finally:
            SCAN_STATUS = "Ожидание следующего цикла"
            LAST_SCAN_TIME = now_text()


async def run_single_scan(pair):
    """
    Manual single-pair scan shares the same lock
    as automatic and full scans.
    """

    if SCAN_LOCK.locked():
        return {
            "pair": pair,
            "approved": False,
            "signal": "WAIT",
            "status": "Сканирование уже выполняется"
        }

    async with SCAN_LOCK:
        result = await scan_one_pair(
            pair,
            notify=False
        )

        return result


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
                    "Automatic scan started:",
                    now_text()
                )

                await run_full_scan(notify=True)

        except asyncio.CancelledError:
            raise

        except Exception as error:
            SCAN_STATUS = "Ошибка автоматического сканирования"
            print(
                "Automatic scanning error:",
                error
            )

        await asyncio.sleep(
            SCAN_INTERVAL_SECONDS
        )


# =========================================================
# FASTAPI LIFESPAN
# =========================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    global TELEGRAM_APP

    scan_task = asyncio.create_task(
        automatic_scan()
    )

    try:
        if TELEGRAM_BOT_TOKEN:
            TELEGRAM_APP = (
                Application.builder()
                .token(TELEGRAM_BOT_TOKEN)
                .build()
            )

            TELEGRAM_APP.add_handler(
                CommandHandler(
                    "start",
                    telegram_start
                )
            )

            TELEGRAM_APP.add_handler(
                CommandHandler(
                    "analyze",
                    telegram_analyze
                )
            )

            TELEGRAM_APP.add_handler(
                CallbackQueryHandler(
                    telegram_buttons
                )
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

            TELEGRAM_APP = None


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

    return {
        "telegram_sent": sent
    }


@app.get("/scan/{pair:path}")
async def scan(pair: str):
    pair = pair.replace("-", "/").upper()

    if pair not in PAIRS:
        return {
            "error": "Валютная пара не найдена"
        }

    return await run_single_scan(pair)


@app.get("/scan-all")
async def scan_all():
    results = await run_full_scan(
        notify=False
    )

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
        return {
            "error": "Валютная пара не найдена"
        }

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
        <meta name="viewport"
              content="width=device-width, initial-scale=1">

        <title>Forex Hunter AI</title>

        <style>
            body {
                background: #0b1120;
                color: white;
                font-family: Arial, sans-serif;
                padding: 20px;
            }

            h1 {
                color: #38bdf8;
            }

            .card {
                background: #172033;
                padding: 18px;
                border-radius: 10px;
                margin: 12px 0;
            }

            .online {
                color: #4ade80;
            }

            .offline {
                color: #f87171;
            }
        </style>
    </head>

    <body>
        <h1>Forex Hunter AI</h1>

        <div class="card">
            <p>21 валютная пара</p>
            <p>Анализ M1 + M5</p>
            <p>Технический, стратегический,
               новостной и риск-анализ</p>

            <p>
                Состояние:
                <strong id="status">Проверка...</strong>
            </p>

            <p>
                Процесс:
                <strong id="process">—</strong>
            </p>

            <p>
                Последний цикл:
                <strong id="last">—</strong>
            </p>
        </div>

        <script>
            async function updateStatus() {
                try {
                    const response = await fetch("/health");

                    if (!response.ok) {
                        throw new Error("Server error");
                    }

                    const data = await response.json();

                    const status =
                        document.getElementById("status");

                    status.textContent = data.scanning
                        ? "СКАНИРОВАНИЕ ВКЛЮЧЕНО"
                        : "СКАНИРОВАНИЕ ОСТАНОВЛЕНО";

                    status.className = data.scanning
                        ? "online"
                        : "offline";

                    document.getElementById("process").textContent =
                        data.scan_status || "—";

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
