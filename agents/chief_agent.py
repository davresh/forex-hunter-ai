
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
    Chief Agent — combines all specialist agents.

    A signal is approved only when:
    1. M1 and M5 agree.
    2. Technical Agent approves both timeframes.
    3. Strategy Agent approves both timeframes.
    4. Risk Agent approves the trade.
    5. News Agent approves the market conditions.
    """

    try:
        # 1. Technical analysis
        m1_technical = technical_agent(m1_candles)
        m5_technical = technical_agent(m5_candles)

        m1_signal = m1_technical.get("signal")
        m5_signal = m5_technical.get("signal")

        if (
            not m1_technical.get("approved")
            or not m5_technical.get("approved")
            or m1_signal != m5_signal
        ):
            return {
                "approved": False,
                "signal": "WAIT",
                "pair": pair,
                "reason": "M1/M5 technical confirmation failed",
                "agents": {
                    "m1": m1_technical,
                    "m5": m5_technical
                }
            }

        signal = m1_signal

        # 2. Strategy analysis
        m1_strategy = strategy_agent(
            m1_technical["analysis"]
        )
        m5_strategy = strategy_agent(
            m5_technical["analysis"]
        )

        if (
            not m1_strategy.get("approved")
            or not m5_strategy.get("approved")
            or m1_strategy.get("signal") != signal
            or m5_strategy.get("signal") != signal
        ):
            return {
                "approved": False,
                "signal": "WAIT",
                "pair": pair,
                "reason": "Strategy confirmation failed",
                "agents": {
                    "m1_strategy": m1_strategy,
                    "m5_strategy": m5_strategy
                }
            }

        # 3. Risk analysis
        risk = risk_agent(
            m5_technical["analysis"],
            daily_loss_percent=daily_loss_percent
        )

        if (
            not risk.get("approved")
            or risk.get("signal") != signal
        ):
            return {
                "approved": False,
                "signal": "WAIT",
                "pair": pair,
                "reason": risk.get("reason"),
                "agents": {"risk": risk}
            }

        # 4. News analysis
        news = await news_agent(pair)

        if not news.get("approved"):
            return {
                "approved": False,
                "signal": "WAIT",
                "pair": pair,
                "reason": news.get("reason"),
                "agents": {
                    "news": news,
                    "risk": risk
                }
            }

        # 5. Final decision
        return {
            "approved": True,
            "signal": signal,
            "pair": pair,
            "timeframes": ["M1", "M5"],
            "analysis_score": round(
                (
                    m1_technical["score"]
                    + m5_technical["score"]
                ) / 2,
                2
            ),
            "entry": m5_technical["analysis"].get("price"),
            "stop_loss": risk.get("stop_loss"),
            "take_profit": risk.get("take_profit"),
            "risk_reward": risk.get("risk_reward"),
            "agents": {
                "m1_technical": m1_technical,
                "m5_technical": m5_technical,
                "m1_strategy": m1_strategy,
                "m5_strategy": m5_strategy,
                "risk": risk,
                "news": news
            },
            "reason": "All agents approved the signal"
        }

    except Exception as error:
        return {
            "approved": False,
            "signal": "WAIT",
            "pair": pair,
            "reason": str(error)
        }
