
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD


def analyze_market(candles):
    if len(candles) < 60:
        return {
            "status": "insufficient_data",
            "message": "Need at least 60 candles"
        }

    df = pd.DataFrame(candles)
    close = df["close"]

    df["rsi"] = RSIIndicator(close=close, window=14).rsi()
    df["ema_9"] = EMAIndicator(close=close, window=9).ema_indicator()
    df["ema_21"] = EMAIndicator(close=close, window=21).ema_indicator()
    df["ema_50"] = EMAIndicator(close=close, window=50).ema_indicator()

    macd = MACD(close=close)
    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()

    last = df.iloc[-1]
    previous = df.iloc[-2]

    if pd.isna(last[["rsi", "ema_9", "ema_21", "ema_50",
                     "macd", "macd_signal"]]).any():
        return {
            "status": "insufficient_data",
            "message": "Indicators are not ready"
        }

    score = 0
    reasons = []

    # EMA trend
    if last["ema_9"] > last["ema_21"]:
        score += 1
        reasons.append("EMA bullish")
    else:
        score -= 1
        reasons.append("EMA bearish")

    # MACD momentum
    if last["macd"] > last["macd_signal"]:
        score += 1
        reasons.append("MACD bullish")
    else:
        score -= 1
        reasons.append("MACD bearish")

    # RSI filter
    if 50 < last["rsi"] < 70:
        score += 1
        reasons.append("RSI bullish")
    elif 30 < last["rsi"] < 50:
        score -= 1
        reasons.append("RSI bearish")
    else:
        reasons.append("RSI extreme or neutral")

    # Main trend filter
    trend_up = last["close"] > last["ema_50"]
    trend_down = last["close"] < last["ema_50"]

    # Candle strength
    candle_range = last["high"] - last["low"]
    candle_body = abs(last["close"] - last["open"])

    candle_strength = (
        candle_body / candle_range if candle_range > 0 else 0
    )

    bullish_candle = (
        last["close"] > last["open"]
        and candle_strength >= 0.4
    )

    bearish_candle = (
        last["close"] < last["open"]
        and candle_strength >= 0.4
    )

    if trend_up and bullish_candle and score >= 2:
        signal = "LONG"
    elif trend_down and bearish_candle and score <= -2:
        signal = "SHORT"
    else:
        signal = "WAIT"

    if not trend_up and not trend_down:
        reasons.append("Price is at EMA 50")

    if not bullish_candle and not bearish_candle:
        reasons.append("Weak or neutral candle")

    confidence = min(100, max(0, abs(score) * 25))

    return {
        "status": "success",
        "signal": signal,
        "rsi": round(float(last["rsi"]), 2),
        "ema_9": round(float(last["ema_9"]), 6),
        "ema_21": round(float(last["ema_21"]), 6),
        "ema_50": round(float(last["ema_50"]), 6),
        "macd": round(float(last["macd"]), 6),
        "macd_signal": round(float(last["macd_signal"]), 6),
        "score": score,
        "confidence": confidence,
        "candle_strength": round(float(candle_strength), 2),
        "reasons": reasons
    }
