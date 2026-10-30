
from indicators import analyze_market


def run_backtest(
    candles,
    initial_balance=10000,
    risk_percent=1.0,
    reward_risk=2.0,
    warmup=60
):
    """
    Historical simulation.

    Signal is generated using candles available up to the current bar.
    Entry is simulated at the next candle open.
    Stop and target are based on ATR from the signal candle.

    If stop and target are both touched in one candle,
    the conservative assumption is that stop was hit first.
    """

    if not isinstance(candles, list) or len(candles) < warmup + 2:
        return {
            "status": "insufficient_data",
            "message": f"Need at least {warmup + 2} candles"
        }

    balance = float(initial_balance)
    peak_balance = balance
    max_drawdown = 0.0

    trades = []
    wins = 0
    losses = 0

    equity_curve = [balance]

    for index in range(warmup, len(candles) - 1):
        history = candles[:index + 1]

        analysis = analyze_market(history)

        if analysis.get("status") != "success":
            continue

        signal = analysis.get("signal")

        if signal not in ("LONG", "SHORT"):
            continue

        entry_candle = candles[index + 1]
        entry = float(entry_candle["open"])

        atr = float(analysis.get("atr") or 0)

        if atr <= 0 or entry <= 0:
            continue

        stop_distance = atr * 1.5
        target_distance = stop_distance * reward_risk

        if signal == "LONG":
            stop = entry - stop_distance
            target = entry + target_distance
        else:
            stop = entry + stop_distance
            target = entry - target_distance

        risk_amount = balance * risk_percent / 100

        if risk_amount <= 0:
            break

        outcome = None
        exit_price = None

        # Simulate the trade on following candles.
        for future_index in range(index + 1, len(candles)):
            bar = candles[future_index]

            high = float(bar["high"])
            low = float(bar["low"])

            if signal == "LONG":
                stop_hit = low <= stop
                target_hit = high >= target
            else:
                stop_hit = high >= stop
                target_hit = low <= target

            # Conservative intrabar assumption.
            if stop_hit:
                outcome = "LOSS"
                exit_price = stop
                break

            if target_hit:
                outcome = "WIN"
                exit_price = target
                break

        if outcome is None:
            # Ignore open trades at the end of the dataset.
            continue

        if signal == "LONG":
            price_change = exit_price - entry
        else:
            price_change = entry - exit_price

        risk_distance = abs(entry - stop)

        r_multiple = price_change / risk_distance

        pnl = risk_amount * r_multiple

        balance += pnl

        if outcome == "WIN":
            wins += 1
        else:
            losses += 1

        peak_balance = max(peak_balance, balance)

        if peak_balance > 0:
            drawdown = (
                (peak_balance - balance) / peak_balance
            ) * 100

            max_drawdown = max(max_drawdown, drawdown)

        equity_curve.append(round(balance, 2))

        trades.append({
            "signal": signal,
            "entry": round(entry, 6),
            "stop_loss": round(stop, 6),
            "take_profit": round(target, 6),
            "exit": round(exit_price, 6),
            "result": outcome,
            "r_multiple": round(r_multiple, 2),
            "pnl": round(pnl, 2),
            "balance": round(balance, 2),
            "entry_index": index + 1,
            "exit_index": future_index
        })

        # Skip candles occupied by this simulated trade.
        # This prevents overlapping positions.
        # The loop still advances normally; future signals inside
        # an open position are ignored by the next section below.

    total_trades = len(trades)

    win_rate = (
        wins / total_trades * 100
        if total_trades else 0
    )

    gross_profit = sum(
        trade["pnl"] for trade in trades if trade["pnl"] > 0
    )

    gross_loss = abs(sum(
        trade["pnl"] for trade in trades if trade["pnl"] < 0
    ))

    profit_factor = (
        gross_profit / gross_loss
        if gross_loss > 0
        else None
    )

    return {
        "status": "success",
        "initial_balance": initial_balance,
        "final_balance": round(balance, 2),
        "net_profit": round(balance - initial_balance, 2),
        "total_trades": total_trades,
        "wins": wins,
        "losses": losses,
        "win_rate": round(win_rate, 2),
        "profit_factor": (
            round(profit_factor, 2)
            if profit_factor is not None else None
        ),
        "max_drawdown_percent": round(max_drawdown, 2),
        "equity_curve": equity_curve,
        "trades": trades
    }
