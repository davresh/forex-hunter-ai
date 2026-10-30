
def statistics_agent(trades):
    """
    Statistics Agent — calculates trading performance.

    Expects a list of completed trades.
    Each trade should contain:
    result: WIN or LOSS
    pnl: numeric profit or loss
    r_multiple: optional numeric R result
    """

    if not isinstance(trades, list):
        return {
            "status": "error",
            "message": "Trades must be a list"
        }

    valid_trades = []

    for trade in trades:
        if not isinstance(trade, dict):
            continue

        if trade.get("result") not in ("WIN", "LOSS"):
            continue

        try:
            pnl = float(trade.get("pnl", 0))
            valid_trades.append({
                "result": trade["result"],
                "pnl": pnl
            })
        except (TypeError, ValueError):
            continue

    total = len(valid_trades)

    if total == 0:
        return {
            "status": "success",
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0,
            "profit_factor": None,
            "net_profit": 0,
            "max_drawdown_percent": 0
        }

    wins = sum(
        trade["result"] == "WIN"
        for trade in valid_trades
    )

    losses = total - wins

    gross_profit = sum(
        trade["pnl"]
        for trade in valid_trades
        if trade["pnl"] > 0
    )

    gross_loss = abs(sum(
        trade["pnl"]
        for trade in valid_trades
        if trade["pnl"] < 0
    ))

    net_profit = sum(
        trade["pnl"] for trade in valid_trades
    )

    profit_factor = (
        gross_profit / gross_loss
        if gross_loss > 0
        else None
    )

    balance = 0.0
    peak = 0.0
    max_drawdown = 0.0

    for trade in valid_trades:
        balance += trade["pnl"]
        peak = max(peak, balance)

        if peak > 0:
            drawdown = (
                (peak - balance) / peak
            ) * 100

            max_drawdown = max(
                max_drawdown,
                drawdown
            )

    return {
        "status": "success",
        "total_trades": total,
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / total * 100, 2),
        "profit_factor": (
            round(profit_factor, 2)
            if profit_factor is not None else None
        ),
        "net_profit": round(net_profit, 2),
        "max_drawdown_percent": round(
            max_drawdown, 2
        )
    }
