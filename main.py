
import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from pydantic import BaseModel, Field

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes
)

from config import (
    PROJECT_NAME, VERSION, TELEGRAM_BOT_TOKEN,
    PAIRS, CANDLE_LIMIT, SCAN_INTERVAL,
    MAX_HISTORY, MIN_SIGNAL_SCORE
)

from market_data import get_candles
from indicators import analyze_market
from sentiment import get_market_sentiment
from risk_agent import check_signal_risk


# =====================================
# FOREX HUNTER AI 5.2
# SIMULATION ONLY
# =====================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger(__name__)

app = FastAPI(title=PROJECT_NAME, version=VERSION)

TELEGRAM_APP = None
TELEGRAM_RUNNING = False

HISTORY = []
MONITORS = {}
LAST_SIGNALS = {}


# =====================================
# HELPERS
# =====================================

def normalize_pair(pair):
    return pair.upper().replace("-", "/").strip()


def valid_pair(pair):
    return normalize_pair(pair) in PAIRS


def menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💱 Выбрать пару", callback_data="pairs")],
        [
            InlineKeyboardButton("📊 Анализ", callback_data="analyze"),
            InlineKeyboardButton("▶️ Мониторинг", callback_data="monitor")
        ],
        [
            InlineKeyboardButton("⏹ Стоп", callback_data="stop"),
            InlineKeyboardButton("📜 История", callback_data="history")
        ],
        [InlineKeyboardButton("ℹ️ Статус", callback_data="status")]
    ])


def pairs_keyboard():
    buttons = [
        [
            InlineKeyboardButton(
                pair,
                callback_data=f"pair:{pair}"
            )
            for pair in PAIRS[i:i + 2]
        ]
        for i in range(0, len(PAIRS), 2)
    ]

    buttons.append([
        InlineKeyboardButton("⬅️ Главное меню", callback_data="home")
    ])

    return InlineKeyboardMarkup(buttons)


# =====================================
# MARKET ANALYSIS
# =====================================

async def analyze_pair(pair):
    pair = normalize_pair(pair)

    if not valid_pair(pair):
        return {"error": "Неизвестная валютная пара"}

    try:
        m1, m5 = await asyncio.gather(
            get_candles(pair, "1min", CANDLE_LIMIT),
            get_candles(pair, "5min", CANDLE_LIMIT)
        )

        if isinstance(m1, dict):
            return {"error": f"M1: {m1.get('error', 'Нет данных')}"}

        if isinstance(m5, dict):
            return {"error": f"M5: {m5.get('error', 'Нет данных')}"}

        risk = check_signal_risk(m1, m5)

        a1 = analyze_market(m1)
        a5 = analyze_market(m5)

        if a1.get("error") or a5.get("error"):
            return {
                "error": (
                    f"M1: {a1.get('error', 'OK')} | "
                    f"M5: {a5.get('error', 'OK')}"
                )
            }

        signal = "WAIT"

        if risk.get("allowed"):
            if (
                a1.get("signal") == a5.get("signal") == "LONG"
                and a1.get("score", 0) >= MIN_SIGNAL_SCORE
                and a5.get("score", 0) >= MIN_SIGNAL_SCORE
            ):
                signal = "LONG"

            elif (
                a1.get("signal") == a5.get("signal") == "SHORT"
                and a1.get("score", 0) >= MIN_SIGNAL_SCORE
                and a5.get("score", 0) >= MIN_SIGNAL_SCORE
            ):
                signal = "SHORT"

        try:
            sentiment = await get_market_sentiment(pair)
        except Exception:
            logger.exception("Sentiment unavailable")
            sentiment = {"combined": {"status": "unavailable"}}

        result = {
            "pair": pair,
            "signal": signal,
            "m1": a1,
            "m5": a5,
            "risk": risk,
            "sentiment": sentiment,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": "SIMULATION"
        }

        if signal != "WAIT":
            result.update({
                "entry": a1.get("entry"),
                "stop_loss": a1.get("stop_loss"),
                "take_profit": a1.get("take_profit")
            })

        HISTORY.append(result)
        del HISTORY[:-MAX_HISTORY]

        return result

    except Exception as error:
        logger.exception("Analysis failed: %s", pair)
        return {"error": str(error)}


# =====================================
# TELEGRAM MESSAGE
# =====================================

def format_analysis(data):
    if data.get("error"):
        return f"⚠️ Ошибка анализа\n\n{data['error']}"

    pair = data["pair"]
    signal = data["signal"]
    a1, a5 = data["m1"], data["m5"]
    risk = data["risk"]
    combined = data.get("sentiment", {}).get("combined", {})

    names = {
        "LONG": "🟢 BUY / LONG",
        "SHORT": "🔴 SELL / SHORT",
        "WAIT": "🟡 WAIT / ОЖИДАНИЕ"
    }

    message = (
        f"📊 FOREX HUNTER AI {VERSION}\n\n"
        f"💱 Пара: {pair}\n"
        f"📍 Сигнал: {names[signal]}\n\n"
        f"⏱ M1: {a1.get('signal')} ({a1.get('score')}/100)\n"
        f"⏱ M5: {a5.get('signal')} ({a5.get('score')}/100)\n"
    )

    if signal != "WAIT":
        message += (
            f"\n🎯 Entry: {data.get('entry')}\n"
            f"🛑 Stop Loss: {data.get('stop_loss')}\n"
            f"🏁 Take Profit: {data.get('take_profit')}\n"
        )

    message += "\n🛡 RISK AGENT\n"

    message += (
        "🟢 SAFE\n"
        if risk.get("allowed")
        else f"🔴 BLOCKED\nПричина: {risk.get('reason', 'Risk check failed')}\n"
    )

    for timeframe in ("m1", "m5"):
        ratio = risk.get(timeframe, {}).get("volatility_ratio")
        if ratio is not None:
            message += f"{timeframe.upper()} volatility: {ratio}x\n"

    message += "\n📈 MARKET SENTIMENT\n"

    if combined.get("status") == "available":
        message += (
            f"BUY: {combined.get('buy_percent')}%\n"
            f"SELL: {combined.get('sell_percent')}%\n"
            f"Direction: {combined.get('direction')}\n"
        )
    else:
        message += "BUY/SELL данные пока недоступны.\n"

    message += (
        "\n⚠️ Фильтр новостей пока не подключён.\n"
        "Оценка стратегии не является вероятностью прибыли.\n"
        "Режим SIMULATION — реальные сделки отключены."
    )

    return message


# =====================================
# MONITORING
# =====================================

async def monitor_pair(chat_id, pair):
    try:
        while True:
            result = await analyze_pair(pair)

            if result.get("error"):
                logger.warning("Monitor error: %s", result["error"])

            else:
                signal = result["signal"]
                previous = LAST_SIGNALS.get(chat_id)

                if signal in ("LONG", "SHORT"):
                    current = (pair, signal)

                    if current != previous:
                        await TELEGRAM_APP.bot.send_message(
                            chat_id=chat_id,
                            text="🚨 НОВЫЙ СИГНАЛ\n\n" + format_analysis(result),
                            reply_markup=menu_keyboard()
                        )
                        LAST_SIGNALS[chat_id] = current

                else:
                    LAST_SIGNALS.pop(chat_id, None)

            await asyncio.sleep(SCAN_INTERVAL)

    except asyncio.CancelledError:
        raise

    except Exception:
        logger.exception("Monitoring stopped after an error")

    finally:
        if MONITORS.get(chat_id) is asyncio.current_task():
            MONITORS.pop(chat_id, None)


# =====================================
# TELEGRAM COMMANDS
# =====================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.setdefault("selected_pair", None)

    await update.message.reply_text(
        "🤖 FOREX HUNTER AI\n\n"
        "Выбери валютную пару и управляй ботом через кнопки.\n\n"
        "⚠️ Только симуляция, реальные сделки отключены.",
        reply_markup=menu_keyboard()
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    chat_id = update.effective_chat.id
    data = query.data or ""

    if data.startswith("pair:"):
        pair = normalize_pair(data.split(":", 1)[1])

        if not valid_pair(pair):
            await query.edit_message_text("Неизвестная пара.")
            return

        context.user_data["selected_pair"] = pair

        await query.edit_message_text(
            f"✅ Выбрана {pair}",
            reply_markup=menu_keyboard()
        )
        return

    pair = context.user_data.get("selected_pair")

    if data == "home":
        await query.edit_message_text(
            "🤖 Главное меню",
            reply_markup=menu_keyboard()
        )
        return

    if data == "pairs":
        await query.edit_message_text(
            "💱 Выбери валютную пару:",
            reply_markup=pairs_keyboard()
        )
        return

    if data in ("analyze", "monitor") and not pair:
        await query.edit_message_text(
            "Сначала выбери пару:",
            reply_markup=pairs_keyboard()
        )
        return

    if data == "analyze":
        await query.edit_message_text(f"⏳ Анализирую {pair}...")
        result = await analyze_pair(pair)

        await context.bot.send_message(
            chat_id=chat_id,
            text=format_analysis(result),
            reply_markup=menu_keyboard()
        )
        return

    if data == "monitor":
        existing = MONITORS.get(chat_id)

        if existing and not existing.done():
            await query.edit_message_text(
                f"Мониторинг уже работает: {pair}",
                reply_markup=menu_keyboard()
            )
            return

        MONITORS[chat_id] = asyncio.create_task(
            monitor_pair(chat_id, pair)
        )

        await query.edit_message_text(
            f"▶️ Мониторинг запущен\n\n"
            f"Пара: {pair}\n"
            f"Таймфреймы: M1 + M5\n"
            f"Проверка каждые {SCAN_INTERVAL} сек.",
            reply_markup=menu_keyboard()
        )
        return

    if data == "stop":
        task = MONITORS.pop(chat_id, None)

        if task:
            task.cancel()
            LAST_SIGNALS.pop(chat_id, None)
            message = "⏹ Мониторинг остановлен."
        else:
            message = "Мониторинг не запущен."

        await query.edit_message_text(
            message,
            reply_markup=menu_keyboard()
        )
        return

    if data == "history":
        records = [
            item for item in HISTORY
            if item["pair"] == pair
        ][-10:] if pair else []

        message = (
            "📜 История\n\n" +
            "\n".join(
                f"{item['pair']}: {item['signal']}"
                for item in records
            )
            if records else "📜 История пока пуста."
        )

        await query.edit_message_text(
            message,
            reply_markup=menu_keyboard()
        )
        return

    if data == "status":
        task = MONITORS.get(chat_id)
        running = bool(task and not task.done())

        await query.edit_message_text(
            "ℹ️ FOREX HUNTER AI\n\n"
            f"Версия: {VERSION}\n"
            f"Пара: {pair or 'Не выбрана'}\n"
            f"Мониторинг: {'Включён' if running else 'Выключен'}\n"
            f"История: {len(HISTORY)}\n"
            f"Telegram: {'Online' if TELEGRAM_RUNNING else 'Offline'}\n"
            "Режим: SIMULATION\n"
            "Реальные сделки: ОТКЛЮЧЕНЫ",
            reply_markup=menu_keyboard()
        )


# =====================================
# TELEGRAM LIFECYCLE
# =====================================

async def start_telegram():
    global TELEGRAM_APP, TELEGRAM_RUNNING

    if not TELEGRAM_BOT_TOKEN:
        logger.warning("Telegram token is missing")
        return

    try:
        bot = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

        bot.add_handler(CommandHandler("start", start_command))
        bot.add_handler(CallbackQueryHandler(button_handler))

        await bot.initialize()
        await bot.start()

        if bot.updater:
            await bot.updater.start_polling()

        TELEGRAM_APP = bot
        TELEGRAM_RUNNING = True

        logger.info("Telegram bot started")

    except Exception:
        logger.exception("Telegram startup failed")
        TELEGRAM_RUNNING = False

        if TELEGRAM_APP:
            await stop_telegram()


async def stop_telegram():
    global TELEGRAM_APP, TELEGRAM_RUNNING

    TELEGRAM_RUNNING = False

    tasks = list(MONITORS.values())

    for task in tasks:
        task.cancel()

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

    MONITORS.clear()
    LAST_SIGNALS.clear()

    if TELEGRAM_APP:
        if TELEGRAM_APP.updater:
            await TELEGRAM_APP.updater.stop()

        await TELEGRAM_APP.stop()
        await TELEGRAM_APP.shutdown()

        TELEGRAM_APP = None


# =====================================
# FASTAPI
# =====================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    await start_telegram()
    yield
    await stop_telegram()


app.router.lifespan_context = lifespan


@app.get("/")
async def home():
    return {
        "project": PROJECT_NAME,
        "version": VERSION,
        "status": "online",
        "mode": "simulation"
    }


@app.get("/health")
async def health():
    return {
        "status": "online",
        "telegram": "connected" if TELEGRAM_RUNNING else "offline",
        "mode": "simulation"
    }


class AnalyzeRequest(BaseModel):
    pair: str
    candles: list = Field(default_factory=list)


@app.post("/analyze")
async def analyze_endpoint(request: AnalyzeRequest):
    pair = normalize_pair(request.pair)

    if not valid_pair(pair):
        return {"error": "Unsupported currency pair"}

    if request.candles:
        return analyze_market(request.candles)

    return await analyze_pair(pair)
