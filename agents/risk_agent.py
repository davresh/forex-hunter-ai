
from config import (
    MAX_DAILY_LOSS_PERCENT,
    ATR_STOP_MULTIPLIER,
    REWARD_RISK_RATIO,
)


def risk_agent(analysis, daily_loss_percent=0):
    """
    Risk Agent — evaluates trade risk.

    This is a preliminary risk filter.
    It does not guarantee profitable trades.
    """

    try:
        if not isinstance(analysis, dict):
            return {
                "agent": "Risk Agent",
                "approved": False,
                "signal": "WAIT",
                "reason": "Invalid analysis"
            }

        signal = analysis.get("signal", "WAIT")

        if signal not in ("LONG", "SHORT"):
            return {
                "agent": "Risk Agent",
                "approved": False,
                "signal": "WAIT",
                "reason": "No valid trading signal"
            }

        if daily_loss_percent >= MAX_DAILY_LOSS_PERCENT:
            return {
                "agent": "Risk Agent",
                "approved": False,
                "signal": "WAIT",
                "reason": "Daily loss limit reached"
            }

        price = float(analysis.get("price") or 0)
        atr = float(analysis.get("atr") or 0)
        volatility = float(
            analysis.get("volatility_percent") or 0
        )

        if price <= 0 or atr <= 0:
            return {
                "agent": "Risk Agent",
                "approved": False,
                "signal": "WAIT",
                "reason": "Invalid price or ATR"
            }

        if volatility <= 0 or volatility > 0.5:
            return {
                "agent": "Risk Agent",
                "approved": False,
                "signal": "WAIT",
                "reason": "Volatility outside configured limits"
            }

        stop_distance = atr * ATR_STOP_MULTIPLIER
        target_distance = stop_distance * REWARD_RISK_RATIO

        if stop_distance <= 0 or target_distance <= 0:
            return {
                "agent": "Risk Agent",
                "approved": False,
                "signal": "WAIT",
                "reason": "Invalid trade levels"
            }

        if signal == "LONG":
            stop = price - stop_distance
            target = price + target_distance
        else:
            stop = price + stop_distance
            target = price - target_distance

        return {
            "agent": "Risk Agent",
            "approved": True,
            "signal": signal,
            "risk_reward": REWARD_RISK_RATIO,
            "stop_loss": round(stop, 6),
            "take_profit": round(target, 6),
            "atr": round(atr, 6),
            "volatility_percent": round(volatility, 4),
            "reason": "Risk checks passed"
        }

    except Exception as error:
        return {
            "agent": "Risk Agent",
            "approved": False,
            "signal": "WAIT",
            "reason": str(error)
        }
