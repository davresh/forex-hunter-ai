
from indicators import analyze_market
from config import MIN_ANALYSIS_SCORE, ALLOWED_SIGNALS


def technical_agent(candles):
    """
    Technical Agent — проверяет технические сигналы.

    Использует:
    EMA 9/21/50, RSI, MACD, ADX, ATR,
    Bollinger Bands и свечной анализ.
    """

    try:
        analysis = analyze_market(candles)

        if analysis.get("status") != "success":
            return {
                "agent": "Technical Agent",
                "approved": False,
                "signal": "WAIT",
                "score": 0,
                "reason": analysis.get(
                    "message",
                    "Technical analysis failed"
                )
            }

        signal = analysis.get("signal", "WAIT")
        score = float(
            analysis.get("analysis_score", 0)
        )

        if signal not in ALLOWED_SIGNALS:
            return {
                "agent": "Technical Agent",
                "approved": False,
                "signal": "WAIT",
                "score": score,
                "reason": "No confirmed trading direction",
                "analysis": analysis
            }

        if score < MIN_ANALYSIS_SCORE:
            return {
                "agent": "Technical Agent",
                "approved": False,
                "signal": "WAIT",
                "score": score,
                "reason": "Technical score is too low",
                "analysis": analysis
            }

        adx = float(analysis.get("adx") or 0)
        rsi = float(analysis.get("rsi") or 0)
        price = float(analysis.get("price") or 0)
        ema_50 = float(analysis.get("ema_50") or 0)

        if adx < 20:
            return {
                "agent": "Technical Agent",
                "approved": False,
                "signal": "WAIT",
                "score": score,
                "reason": "Trend strength is insufficient",
                "analysis": analysis
            }

        if signal == "LONG":
            if price <= ema_50 or not 50 < rsi < 70:
                return {
                    "agent": "Technical Agent",
                    "approved": False,
                    "signal": "WAIT",
                    "score": score,
                    "reason": "Bullish confirmation failed",
                    "analysis": analysis
                }

        if signal == "SHORT":
            if price >= ema_50 or not 30 < rsi < 50:
                return {
                    "agent": "Technical Agent",
                    "approved": False,
                    "signal": "WAIT",
                    "score": score,
                    "reason": "Bearish confirmation failed",
                    "analysis": analysis
                }

        return {
            "agent": "Technical Agent",
            "approved": True,
            "signal": signal,
            "score": score,
            "reason": "Technical conditions confirmed",
            "analysis": analysis
        }

    except Exception as error:
        return {
            "agent": "Technical Agent",
            "approved": False,
            "signal": "WAIT",
            "score": 0,
            "reason": str(error)
        }
