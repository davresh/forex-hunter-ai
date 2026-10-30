import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD


def analyze_market(candles):
    """
    candles: список свечей с полями:
    open, high, low, close
    """

    if len(candles) < 50:
        return {
            "status": "insufficient_data",
            "message": "Need at least 50 candles"
        }

    df = pd.DataFrame(candles)

    close = df["close"]

    df["rsi"] = RSIIndicator(
        close=close,
        window=14
    ).rsi()

    df["ema_9"] = EMAIndicator(
        close=close,
        window=9
    ).ema_indicator()

    df["ema_21"] = EMAIndicator(
        close=close,
        window=21
    ).ema_indicator()

    macd = MACD(close=close)

    df["macd"] = macd.macd()
    df["signal"] = macd.macd_signal()

    last = df.iloc[-1]

    score = 0

    if last["ema_9"] > last["ema_21"]:
        score += 1
    else:
        score -= 1

    if last["macd"] > last["signal"]:
        score += 1
    else:
        score -= 1

    if last["rsi"] > 50:
        score += 1
    else:
        score -= 1

    if score >= 2:
        signal = "LONG"
    elif score <= -2:
        signal = "SHORT"
    else:
        signal = "WAIT"

    return {
        "status": "success",
        "signal": signal,
        "rsi": round(float(last["rsi"]), 2),
        "ema_9": round(float(last["ema_9"]), 6),
        "ema_21": round(float(last["ema_21"]), 6),
        "macd": round(float(last["macd"]), 6),
        "macd_signal": round(float(last["signal"]), 6),
        "score": score
    }
