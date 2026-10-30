
from agents.technical_agent import technical_agent
from agents.strategy_agent import strategy_agent
from agents.risk_agent import risk_agent
from agents.news_agent import news_agent


async def chief_agent(
    pair,
    m1_candles,
    m5_candles,
    daily_loss_percent=0
):
    """
    Chief Agent coordinates all agents.

    A LONG or SHORT signal is returned only if:
    1. M1 technical analysis approves.
    2. M5 technical analysis approves.
    3. M1 and M5 directions match.
    4. Both strategy agents approve the same direction.
    5. Risk Agent approves.
    6. News Agent approves.

    This is an analytical system, not a guarantee of profit.
    """

    agents = {}

    try:
        # 1. Technical analysis: M1 and M5
        m1 = technical_agent(m1_candles)
        m5 = technical_agent(m5_candles)

        agents["m1_technical"] = m1
        agents["m5_technical"] = m5

        if not m1.get("approved") or not m5.get("approved"):
            return {
                "pair": pair,
                "approved": False,
                "signal": "WAIT",
                "reason": "Technical Agent rejected the signal",
                "agents": agents
            }

        m1_signal = m1.get("signal")
        m5_signal = m5.get("signal")

        if m1_signal != m5_signal:
            return {
                "pair": pair,
                "approved": False,
                "signal": "WAIT",
                "reason": "M1 and M5 directions do not match",
                "agents": agents
            }

        signal = m1_signal

        # 2. Strategy confirmation
        m1_strategy = strategy_agent(m1["analysis"])
        m5_strategy = strategy_agent(m5["analysis"])

        agents["m1_strategy"] = m1_strategy
        agents["m5_strategy"] = m5_strategy

        if (
            not m1_strategy.get("approved")
            or not m5_strategy.get("approved")
            or m1_strategy.get("signal") != signal
            or m5_strategy.get("signal") != signal
        ):
            return {
                "pair": pair,
                "approved": False,
                "signal": "WAIT",
                "reason": "Strategy confirmation failed",
                "agents": agents
            }

        # 3. Risk management
        risk = risk_agent(
            m5["analysis"],
            daily_loss_percent=daily_loss_percent
        )

        agents["risk"] = risk

        if (
            not risk.get("approved")
            or risk.get("signal") != signal
        ):
            return {
                "pair": pair,
                "approved": False,
                "signal": "WAIT",
                "reason": risk.get(
                    "reason",
                    "Risk Agent rejected the signal"
                ),
                "agents": agents
            }

        # 4. News filter
        news = await news_agent(pair)
        agents["news"] = news

        if not news.get("approved"):
            return {
                "pair": pair,
                "approved": False,
                "signal": "WAIT",
                "reason": news.get(
                    "reason",
                    "News Agent rejected the signal"
                ),
                "agents": agents
            }

        # 5. Final approved signal
        analysis = m5["analysis"]

        return {
            "pair": pair,
            "approved": True,
            "signal": signal,

            "timeframes": ["M1", "M5"],

            "analysis_score": round(
                (
                    m1.get("score", 0)
                    + m5.get("score", 0)
                ) / 2,
                2
            ),

            "price": analysis.get("price"),
            "entry": analysis.get("price"),

            "rsi": analysis.get("rsi"),
            "adx": analysis.get("adx"),
            "ema_50": analysis.get("ema_50"),
            "atr": analysis.get("atr"),
            "volatility_percent": analysis.get(
                "volatility_percent"
            ),

            "support": analysis.get("support"),
            "resistance": analysis.get("resistance"),

            "stop_loss": risk.get("stop_loss"),
            "take_profit": risk.get("take_profit"),
            "risk_reward": risk.get("risk_reward"),

            "reasons": analysis.get("reasons", []),

            "agents": agents,

            "reason": "All agents approved the signal"
        }

    except Exception as error:
        return {
            "pair": pair,
            "approved": False,
            "signal": "WAIT",
            "reason": f"Chief Agent error: {str(error)}",
            "agents": agents
        }
