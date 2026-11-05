
import os
import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from pydantic import BaseModel
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes
)

from config import (
    PROJECT_NAME,
    VERSION,
    TELEGRAM_BOT_TOKEN,
    PAIRS,
    CANDLE_LIMIT,
    SCAN_INTERVAL,
    MAX_HISTORY,
    MIN_SIGNAL_SCORE,
    INITIAL_BALANCE,
    RISK_PERCENT,
    REWARD_RISK
)

from market_data import get_candles
from indicators import analyze_market
from sentiment import get_market_sentiment
from backtesting import run_backtest


# =====================================
# FOREX HUNTER AI 5.0
# MAIN APPLICATION
# SIMULATION ONLY
# =====================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)

SIGNAL_HISTORY = []
MONITOR_TASKS = {}
LAST_SENT = {}

TELEGRAM_APP = None


# =====================================
# TELEGRAM KEYBOARDS
# =====================================

def main_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "💱 Выбрать валютную пару",
                callback_data="menu|pairs"
            )
        ],
        [
            InlineKeyboardButton(
                "📊 Анализировать",
                callback_data="menu|analyze"
            ),
            InlineKeyboardButton(
                "▶️ Мониторинг",
                callback_data="menu|monitor"
            )
        ],
        [
            InlineKeyboardButton(
                "⏹ Остановить",
                callback_data="menu|stop"
            ),
            InlineKeyboardButton(
                "📜 История",
                callback_data="menu|history"
            )
        ],
        [
            InlineKeyboardButton(
                "ℹ️ Статус",
                callback_data="menu|status"
            )
        ]
    ])


def pairs_keyboard():
    buttons = []

    for index in range(0, len(PAIRS), 2):
        row = [
            InlineKeyboardButton(
                pair,
                callback_data=f"pair|{pair}"
            )
            for pair in PAIRS[index:index + 2]
        ]

        buttons.append(row)

    buttons.append([
        InlineKeyboardButton(
            "⬅️ Главное меню",
            callback_data="menu|home"
        )
    ])

    return InlineKeyboardMarkup(buttons)


# =====================================
# MARKET ANALYSIS
# =====================================

async def analyze_pair(pair: str):
    """
    Analyze one selected pair on M1 and M5.
    """

    pair = pair.upper().strip()

    if pair not in PAIRS:
        return {
            "error": "Unsupported currency pair"
        }

    m1_candles = await get_candles(
        pair,
        "1min",
        CANDLE_LIMIT
    )

    m5_candles = await get_candles(
        pair,
        "5min",
        CANDLE_LIMIT
    )

    if isinstance(m1_candles, dict):
        return {
            "error": "M1: " + m1_candles.get(
                "error", "Market data unavailable"
            )
        }

    if isinstance(m5_candles, dict):
        return {
            "error": "M5: " + m5_candles.get(
                "error", "Market data unavailable"
            )
        }

    m1 = analyze_market(m1_candles)
    m5 = analyze_market(m5_candles)

    if m1.get("error") or m5.get("error"):
        return {
            "error": (
                "M1: "
                + str(m1.get("error", "OK"))
                + " | M5: "
                + str(m5.get("error", "OK"))
            )
        }

    signal = "WAIT"

    if (
        m1.get("signal") == "LONG"
        and m5.get("signal") == "LONG"
        and m1.get("score", 0) >= MIN_SIGNAL_SCORE
        and m5.get("score", 0) >= MIN_SIGNAL_SCORE
    ):
        signal = "LONG"

    elif (
        m1.get("signal") == "SHORT"
        and m5.get("signal") == "SHORT"
        and m1.get("score", 0) >= MIN_SIGNAL_SCORE
        and m5.get("score", 0) >= MIN_SIGNAL_SCORE
    ):
        signal = "SHORT"

    sentiment = await get_market_sentiment(pair)

    result = {
        "pair": pair,
        "signal": signal,
        "m1": m1,
        "m5": m5,
        "sentiment": sentiment,
        "timestamp": datetime.now(
            timezone.utc
        ).isoformat(),
        "mode": "SIMULATION"
    }

    if signal in ("LONG", "SHORT"):
        result["entry"] = m1.get("entry")
        result["stop_loss"] = m1.get("stop_loss")
        result["take_profit"] = m1.get("take_profit")

    SIGNAL_HISTORY.append(result)

    if len(SIGNAL_HISTORY) > MAX_HISTORY:
        SIGNAL_HISTORY.pop(0)

    return result


# =====================================
# FORMAT ANALYSIS
# =====================================

def format_analysis(result):
    if result.get("error"):
        return (
            "⚠️ Ошибка анализа\n\n"
            + str(result["error"])
        )

    pair = result["pair"]
    signal = result["signal"]

    m1 = result["m1"]
    m5 = result["m5"]

    sentiment = result.get("sentiment", {})
    combined = sentiment.get("combined", {})

    signal_names = {
        "LONG": "🟢 BUY / LONG",
        "SHORT": "🔴 SELL / SHORT",
        "WAIT": "🟡 WAIT / ОЖИДАНИЕ"
    }

    message = (
        f"📊 FOREX HUNTER AI {VERSION}\n\n"
        f"💱 Пара: {pair}\n"
        f"📍 Сигнал: {signal_names.get(signal, signal)}\n\n"
        f"⏱ M1: {m1.get('signal')} "
        f"({m1.get('score')}/100)\n"
        f"⏱ M5: {m5.get('signal')} "
        f"({m5.get('score')}/100)\n\n"
    )

    if signal in ("LONG", "SHORT"):
        message += (
            f"🎯 Entry: {result.get('entry')}\n"
            f"🛑 Stop Loss: {result.get('stop_loss')}\n"
            f"🏁 Take Profit: {result.get('take_profit')}\n\n"
        )

    message += "📈 MARKET SENTIMENT\n"

    if combined.get("status") == "available":
        message += (
            f"BUY: {combined.get('buy_percent')}%\n"
            f"SELL: {combined.get('sell_percent')}%\n"
            f"Направление: {combined.get('direction')}\n"
        )
    else:
        message += (
            "Данные BUY/SELL пока недоступны.\n"
        )

    message += (
        "\n⚠️ Фильтр новостей не подключён.\n"
        "Оценка индикаторов не является вероятностью прибыли.\n"
        "Режим: SIMULATION — реальные сделки отключены."
    )

    return message


# =====================================
# TELEGRAM START
# =====================================

async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    context.user_data.setdefault("selected_pair", None)

    await update.message.reply_text(
        "🤖 Добро пожаловать в Forex Hunter AI!\n\n"
        "Выбери валютную пару и управляй анализом "
        "через кнопки.\n\n"
        "⚠️ Бот работает в режиме симуляции.",
        reply_markup=main_keyboard()
    )


# =====================================
# TELEGRAM CALLBACKS
# =====================================

async def button_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query

    await query.answer()

    chat_id = update.effective_chat.id
    data = query.data

    if data.startswith("pair|"):
        pair = data.split("|", 1)[1]

        if pair not in PAIRS:
            await query.edit_message_text(
                "Неизвестная валютная пара."
            )
            return

        context.user_data["selected_pair"] = pair

        await query.edit_message_text(
            f"✅ Выбрана пара: {pair}\n\n"
            "Теперь можешь запустить анализ "
            "или мониторинг.",
            reply_markup=main_keyboard()
        )

        return

    action = data.split("|", 1)[1]

    if action == "home":
        await query.edit_message_text(
            "🤖 FOREX HUNTER AI\n\n"
            "Главное меню:",
            reply_markup=main_keyboard()
        )
        return

    if action == "pairs":
        await query.edit_message_text(
            "💱 Выбери одну валютную пару:",
            reply_markup=pairs_keyboard()
        )
        return

    pair = context.user_data.get("selected_pair")

    if action in ("analyze", "monitor") and not pair:
        await query.edit_message_text(
            "Сначала выбери валютную пару.",
            reply_markup=pairs_keyboard()
        )
        return

    if action == "analyze":
        await query.edit_message_text(
            f"⏳ Анализирую {pair} на M1 и M5..."
        )

        result = await analyze_pair(pair)

        await query.message.reply_text(
            format_analysis(result),
            reply_markup=main_keyboard()
        )
        return

    if action == "monitor":
        if chat_id in MONITOR_TASKS:
            await query.edit_message_text(
                f"Мониторинг {pair} уже запущен.",
                reply_markup=main_keyboard()
            )
            return

        task = asyncio.create_task(
            monitor_pair(chat_id, pair)
        )

        MONITOR_TASKS[chat_id] = task

        await query.edit_message_text(
            f"▶️ Мониторинг запущен!\n\n"
            f"Пара: {pair}\n"
            f"Таймфреймы: M1 + M5\n"
            f"Интервал проверки: {SCAN_INTERVAL} сек.",
            reply_markup=main_keyboard()
        )
        return

    if action == "stop":
        task = MONITOR_TASKS.pop(chat_id, None)

        if task:
            task.cancel()

            await query.edit_message_text(
                "⏹ Мониторинг остановлен.",
                reply_markup=main_keyboard()
            )
        else:
            await query.edit_message_text(
                "Мониторинг сейчас не запущен.",
                reply_markup=main_keyboard()
            )
        return

    if action == "history":
        history = [
            item for item in SIGNAL_HISTORY
            if item.get("pair") == pair
        ] if pair else []

        if not history:
            message = "📜 История пока пуста."
        else:
            lines = ["📜 Последние результаты:\n"]

            for item in history[-10:]:
                lines.append(
                    f"{item['pair']}: {item['signal']}"
                )

            message = "\n".join(lines)

        await query.edit_message_text(
            message,
            reply_markup=main_keyboard()
        )
        return

    if action == "status":
        monitoring = chat_id in MONITOR_TASKS

        message = (
            "ℹ️ FOREX HUNTER AI STATUS\n\n"
            f"Версия: {VERSION}\n"
            f"Выбранная пара: {pair or 'Не выбрана'}\n"
            f"Мониторинг: "
            f"{'Включён' if monitoring else 'Выключен'}\n"
            f"История: {len(SIGNAL_HISTORY)} записей\n"
            "Режим: SIMULATION\n"
            "Реальная торговля: ОТКЛЮЧЕНА"
        )

        await query.edit_message_text(
            message,
            reply_markup=main_keyboard()
        )


# =====================================
# MONITORING
# =====================================

async def monitor_pair(chat_id, pair):
    """
    Monitor only the selected pair.
    """

    try:
        while True:
            result = await analyze_pair(pair)

            if result.get("error"):
                logger.warning(
                    "Monitoring error for %s: %s",
                    pair,
                    result["error"]
                )

            else:
                signal = result.get("signal")

                if signal in ("LONG", "SHORT"):

                    previous = LAST_SENT.get(chat_id)

                    if previous != (pair, signal):
                        await TELEGRAM_APP.bot.send_message(
                            chat_id=chat_id,
                            text=(
                                "🚨 НОВЫЙ ПОДТВЕРЖДЁННЫЙ СИГНАЛ\n\n"
                                + format_analysis(result)
                            ),
                            reply_markup=main_keyboard()
                        )

                        LAST_SENT[chat_id] = (
                            pair,
                            signal
                        )

                else:
                    LAST_SENT.pop(chat_id, None)

            await asyncio.sleep(SCAN_INTERVAL)

    except asyncio.CancelledError:
        logger.info(
            "Monitoring stopped for chat %s",
            chat_id
        )
        raise

    except Exception:
        logger.exception(
            "Monitoring crashed for chat %s",
            chat_id
        )

    finally:
        current_task = asyncio.current_task()

        if MONITOR_TASKS.get(chat_id) is current_task:
            MONITOR_TASKS.pop(chat_id, None)


# =====================================
# TELEGRAM APPLICATION
# =====================================

async def start_telegram():
    global TELEGRAM_APP

    if not TELEGRAM_BOT_TOKEN:
        logger.warning(
            "TELEGRAM_BOT_TOKEN is not configured"
        )
        return

    TELEGRAM_APP = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .build()
    )

    TELEGRAM_APP.add_handler(
        CommandHandler("start", start_command)
    )

    TELEGRAM_APP.add_handler(
        CallbackQueryHandler(button_handler)
    )

    await TELEGRAM_APP.initialize()
    await TELEGRAM_APP.start()

    if TELEGRAM_APP.updater:
        await TELEGRAM_APP.updater.start_polling()

    logger.info("Telegram bot started")


async def stop_telegram():
    global TELEGRAM_APP

    for task in list(MONITOR_TASKS.values()):
        task.cancel()

    if MONITOR_TASKS:
        await asyncio.gather(
            *MONITOR_TASKS.values(),
            return_exceptions=True
        )

    MONITOR_TASKS.clear()

    if TELEGRAM_APP:
        if TELEGRAM_APP.updater:
            await TELEGRAM_APP.updater.stop()

        await TELEGRAM_APP.stop()
        await TELEGRAM_APP.shutdown()

        TELEGRAM_APP = None


# =====================================
# FASTAPI LIFESPAN
# =====================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    await start_telegram()

    yield

    await stop_telegram()


app = FastAPI(
    title=PROJECT_NAME,
    version=VERSION,
    lifespan=lifespan
)


# =====================================
# API REQUEST MODEL
# =====================================

class AnalyzeRequest(BaseModel):
    pair: str
    candles: list = []


# =====================================
# API ENDPOINTS
# =====================================

@app.get("/")
async def home():
    return {
        "project": PROJECT_NAME,
        "version": VERSION,
        "status": "online",
        "mode": "simulation",
        "message": "Forex Hunter AI is running"
    }


@app.get("/health")
async def health():
    return {
        "status": "online",
        "telegram": (
            "connected"
            if TELEGRAM_APP
            else "not_configured"
        ),
        "mode": "simulation"
    }


@app.get("/pairs")
async def get_pairs():
    return {
        "total_pairs": len(PAIRS),
        "pairs": PAIRS
    }


@app.get("/scan/{pair:path}")
async def scan_endpoint(pair: str):
    return await analyze_pair(pair)


@app.post("/analyze")
async def analyze_endpoint(request: AnalyzeRequest):
    if request.pair.upper() not in PAIRS:
        return {"error": "Unsupported currency pair"}

    if request.candles:
        return analyze_market(request.candles)

    return await analyze_pair(request.pair)


@app.get("/signal-history")
async def signal_history():
    return {
        "total": len(SIGNAL_HISTORY),
        "history": SIGNAL_HISTORY[-MAX_HISTORY:]
    }


@app.get("/dashboard-data")
async def dashboard_data():
    return {
        "project": PROJECT_NAME,
        "version": VERSION,
        "pairs": PAIRS,
        "total_pairs": len(PAIRS),
        "history_count": len(SIGNAL_HISTORY),
        "monitoring_chats": len(MONITOR_TASKS),
        "mode": "simulation"
    }


@app.get("/market/{pair:path}")
async def market_endpoint(pair: str):
    if pair.upper() not in PAIRS:
        return {"error": "Unsupported currency pair"}

    m1 = await get_candles(
        pair,
        "1min",
        CANDLE_LIMIT
    )

    m5 = await get_candles(
        pair,
        "5min",
        CANDLE_LIMIT
    )

    return {
        "pair": pair,
        "M1": m1,
        "M5": m5
    }


@app.get("/backtest/{pair:path}")
async def backtest_endpoint(pair: str):
    if pair.upper() not in PAIRS:
        return {"error": "Unsupported currency pair"}

    candles = await get_candles(
        pair,
        "1min",
        CANDLE_LIMIT
    )

    if isinstance(candles, dict):
        return candles

    return run_backtest(
        candles,
        initial_balance=INITIAL_BALANCE,
        risk_percent=RISK_PERCENT,
        reward_risk=REWARD_RISK
    )
