
import logging
from statistics import median

logger = logging.getLogger(__name__)

MIN_CANDLES = 60
ATR_PERIOD = 14
BASELINE_PERIOD = 50

# Пороговые значения для защитной проверки
MAX_LAST_CANDLE_ATR = 2.5
MAX_VOLATILITY_RATIO = 2.0
MAX_PRICE_JUMP_ATR = 2.5


def calculate_true_ranges(candles):
    ranges = []

    for i, candle in enumerate(candles):
        high = float(candle["high"])
        low = float(candle["low"])
        close = float(candle["close"])

        if i == 0:
            previous_close = float(candle["open"])
        else:
            previous_close = float(candles[i - 1]["close"])

        true_range = max(
            high - low,
            abs(high - previous_close),
            abs(low - previous_close)
        )

        ranges.append(true_range)

    return ranges


def check_market_risk(candles):
    """
    Checks volatility and abnormal candle movements.
    Returns a protective risk assessment.
    """

    if not isinstance(candles, list):
        return {
            "status": "blocked",
            "allowed": False,
            "reason": "Invalid candle data"
        }

    if len(candles) < MIN_CANDLES:
        return {
            "status": "blocked",
            "allowed": False,
            "reason": "Not enough candles for risk analysis"
        }

    try:
        true_ranges = calculate_true_ranges(candles)

        atr_values = []

        for i in range(ATR_PERIOD - 1, len(true_ranges)):
            window = true_ranges[i - ATR_PERIOD + 1:i + 1]
            atr_values.append(sum(window) / ATR_PERIOD)

        if len(atr_values) < BASELINE_PERIOD + 1:
            return {
                "status": "blocked",
                "allowed": False,
                "reason": "Not enough ATR history"
            }

        current_atr = atr_values[-1]

        baseline_values = atr_values[
            -(BASELINE_PERIOD + 1):-1
        ]

        baseline_atr = median(baseline_values)

        if current_atr <= 0 or baseline_atr <= 0:
            return {
                "status": "blocked",
                "allowed": False,
                "reason": "Invalid ATR values"
            }

        last_candle = candles[-1]

        last_range = (
            float(last_candle["high"])
            - float(last_candle["low"])
        )

        previous_close = float(candles[-2]["close"])
        current_open = float(last_candle["open"])

        price_jump = abs(current_open - previous_close)

        volatility_ratio = current_atr / baseline_atr
        last_candle_ratio = last_range / current_atr
        price_jump_ratio = price_jump / current_atr

        reasons = []

        if volatility_ratio > MAX_VOLATILITY_RATIO:
            reasons.append("Abnormally high market volatility")

        if last_candle_ratio > MAX_LAST_CANDLE_ATR:
            reasons.append("Abnormally large last candle")

        if price_jump_ratio > MAX_PRICE_JUMP_ATR:
            reasons.append("Abnormal price gap")

        if reasons:
            return {
                "status": "blocked",
                "allowed": False,
                "reason": "; ".join(reasons),
                "current_atr": current_atr,
                "baseline_atr": baseline_atr,
                "volatility_ratio": round(volatility_ratio, 2),
                "last_candle_ratio": round(last_candle_ratio, 2),
                "price_jump_ratio": round(price_jump_ratio, 2)
            }

        return {
            "status": "safe",
            "allowed": True,
            "reason": "No abnormal volatility detected",
            "current_atr": current_atr,
            "baseline_atr": baseline_atr,
            "volatility_ratio": round(volatility_ratio, 2),
            "last_candle_ratio": round(last_candle_ratio, 2),
            "price_jump_ratio": round(price_jump_ratio, 2)
        }

    except (KeyError, TypeError, ValueError, ZeroDivisionError) as error:
        logger.exception("Risk analysis failed")

        return {
            "status": "blocked",
            "allowed": False,
            "reason": f"Risk analysis error: {error}"
        }


def check_signal_risk(m1_candles, m5_candles):
    """
    Both M1 and M5 must pass the risk check.
    """

    m1_risk = check_market_risk(m1_candles)
    m5_risk = check_market_risk(m5_candles)

    allowed = (
        m1_risk["allowed"]
        and m5_risk["allowed"]
    )

    return {
        "allowed": allowed,
        "status": "safe" if allowed else "blocked",
        "m1": m1_risk,
        "m5": m5_risk,
        "reason": (
            "M1 and M5 risk checks passed"
            if allowed
            else "Risk protection blocked the signal"
        )
    }
