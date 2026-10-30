
from config import ALLOWED_SIGNALS


def strategy_agent(analysis):
    """
    Strategy Agent — evaluates five trading strategies.

    Returns independent strategy results.
    """

    if not isinstance(analysis, dict):
        return {
            "approved": False,
            "signal": "WAIT",
            "strategies": {},
            "reason": "Invalid analysis data"
        }

    if analysis.get("status") != "success":
        return {
            "approved": False,
            "signal": "WAIT",
            "strategies": {},
            "reason": "Technical analysis unavailable"
        }

    price = float(analysis.get("price") or 0)
    ema9 = float(analysis.get("ema_9") or 0)
    ema21 = float(analysis.get("ema_21") or 0)
    ema50 = float(analysis.get("ema_50") or 0)
    rsi = float(analysis.get("rsi") or 0)
    adx = float(analysis.get("adx") or 0)

    macd = float(analysis.get("macd") or 0)
    macd_signal = float(
        analysis.get("macd_signal") or 0
    )

    support = float(analysis.get("support") or 0)
    resistance = float(
        analysis.get("resistance") or 0
    )

    strategies = {}

    # 1. TREND FOLLOWING
    if ema9 > ema21 > ema50 and price > ema50 and adx >= 20:
        strategies["trend_following"] = "LONG"

    elif ema9 < ema21 < ema50 and price < ema50 and adx >= 20:
        strategies["trend_following"] = "SHORT"

    else:
        strategies["trend_following"] = "WAIT"

    # 2. BREAKOUT
    if resistance > 0 and price > resistance:
        strategies["breakout"] = "LONG"

    elif support > 0 and price < support:
        strategies["breakout"] = "SHORT"

    else:
        strategies["breakout"] = "WAIT"

    # 3. PULLBACK
    if (
        ema21 > ema50
        and price > ema50
        and price <= ema9
        and 45 <= rsi <= 60
    ):
        strategies["pullback"] = "LONG"

    elif (
        ema21 < ema50
        and price < ema50
        and price >= ema9
        and 40 <= rsi <= 55
    ):
        strategies["pullback"] = "SHORT"

    else:
        strategies["pullback"] = "WAIT"

    # 4. MOMENTUM
    if macd > macd_signal and rsi > 55 and adx >= 20:
        strategies["momentum"] = "LONG"

    elif macd < macd_signal and rsi < 45 and adx >= 20:
        strategies["momentum"] = "SHORT"

    else:
        strategies["momentum"] = "WAIT"

    # 5. SUPPORT / RESISTANCE
    if support > 0 and price > support:
        support_distance = abs(price - support) / price

        if support_distance < 0.001 and rsi > 40:
            strategies["support_resistance"] = "LONG"

        else:
            strategies["support_resistance"] = "WAIT"

    elif resistance > 0 and price < resistance:
        resistance_distance = abs(resistance - price) / price

        if resistance_distance < 0.001 and rsi < 60:
            strategies["support_resistance"] = "SHORT"

        else:
            strategies["support_resistance"] = "WAIT"

    else:
        strategies["support_resistance"] = "WAIT"

    long_count = sum(
        value == "LONG"
        for value in strategies.values()
    )

    short_count = sum(
        value == "SHORT"
        for value in strategies.values()
    )

    signal = "WAIT"

    # Require at least 3 of 5 strategies to agree.
    if long_count >= 3 and long_count > short_count:
        signal = "LONG"

    elif short_count >= 3 and short_count > long_count:
        signal = "SHORT"

    approved = signal in ALLOWED_SIGNALS

    return {
        "agent": "Strategy Agent",
        "approved": approved,
        "signal": signal,
        "long_count": long_count,
        "short_count": short_count,
        "strategies": strategies,
        "reason": (
            "At least three strategies agree"
            if approved
            else "Not enough strategy confirmations"
        )
    }
