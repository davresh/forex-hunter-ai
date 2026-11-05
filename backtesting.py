
import logging
import math

from indicators import analyze_market

logger = logging.getLogger(__name__)

# =====================================
# FOREX HUNTER AI 5.0
# BACKTESTING ENGINE
# SIMULATION ONLY
# =====================================


def run_backtest(
    candles,
    initial_balance=10000,
    risk_percent=1.0,
    reward_risk=2.0,
    warmup=200
):
    """
    Historical strategy simulation.

    Signals are calculated only from candles available
    at that moment. Entry is at the next candle open.

    If SL and TP are touched in the same candle,
    SL is assumed to be hit first (conservative rule).
    """

    try:
        if not isinstance(candles, list):
            return {"error": "Invalid candle data"}

        if len(candles) < warmup + 2:
            return {
                "error": (
                    f"Need at least {warmup + 2} candles"
                )
            }

        if initial_balance <= 0:
            return {"error": "Invalid initial balance"}

        if not 0 < risk_percent <= 5:
            return {
                "error": "Risk percent must be between 0 and 5"
            }

        if reward_risk <= 0:
            return {"error": "Invalid reward/risk ratio"}

        required = ["open", "high", "low", "close"]

        # Validate historical candle structure
        clean_candles = []

        for candle in candles:
            if not isinstance(candle, dict):
                continue

            try:
                item = {
                    key: float(candle[key])
                    for key in required
                }

                if not all(
                    math.isfinite(value) and value > 0
                    for value in item.values()
                ):
                    continue

                if item["high"] < item["low"]:
                    continue

                if item["high"] < max(
                    item["open"], item["close"]
                ):
                    continue

                if item["low"] > min(
                    item["open"], item["close"]
                ):
                    continue

                clean_candles.append(item)

            except (KeyError, TypeError, ValueError):
                continue

        if len(clean_candles) < warmup + 2:
            return {
                "error": "Not enough valid historical candles"
            }

        balance = float(initial_balance)
        peak_balance = balance
        max_drawdown = 0.0

        wins = 0
        losses = 0

        gross_profit = 0.0
        gross_loss = 0.0

        trades = []
        equity_curve = [round(balance, 2)]

        index = warmup
        total = len(clean_candles)

        # =====================================
        # HISTORICAL SIMULATION
        # =====================================

        while index < total - 1:

            history = clean_candles[:index + 1]

            analysis = analyze_market(history)

            if not isinstance(analysis, dict):
                index += 1
                continue

            signal = analysis.get("signal")

            if signal not in ("LONG", "SHORT"):
                index += 1
                continue

            signal_entry = analysis.get("entry")
            signal_stop = analysis.get("stop_loss")

            if signal_entry is None or signal_stop is None:
                index += 1
                continue

            signal_entry = float(signal_entry)
            signal_stop = float(signal_stop)

            risk_distance = abs(
                signal_entry - signal_stop
            )

            if (
                not math.isfinite(risk_distance)
                or risk_distance <= 0
            ):
                index += 1
                continue

            # =====================================
            # NEXT CANDLE ENTRY
            # =====================================

            entry_candle = clean_candles[index + 1]

            entry = entry_candle["open"]

            if signal == "LONG":
                stop_loss = entry - risk_distance
                take_profit = (
                    entry + risk_distance * reward_risk
                )
            else:
                stop_loss = entry + risk_distance
                take_profit = (
                    entry - risk_distance * reward_risk
                )

            risk_amount = balance * (
                risk_percent / 100
            )

            position_size = (
                risk_amount / risk_distance
            )

            if not math.isfinite(position_size):
                index += 1
                continue

            # =====================================
            # TRADE MANAGEMENT
            # =====================================

            exit_price = None
            exit_reason = None
            exit_index = None

            for future_index in range(
                index + 1,
                total
            ):
                candle = clean_candles[future_index]

                if signal == "LONG":

                    stop_hit = (
                        candle["low"] <= stop_loss
                    )

                    target_hit = (
                        candle["high"] >= take_profit
                    )

                    # Conservative: stop first
                    if stop_hit:
                        exit_price = stop_loss
                        exit_reason = "STOP_LOSS"
                    elif target_hit:
                        exit_price = take_profit
                        exit_reason = "TAKE_PROFIT"

                else:

                    stop_hit = (
                        candle["high"] >= stop_loss
                    )

                    target_hit = (
                        candle["low"] <= take_profit
                    )

                    # Conservative: stop first
                    if stop_hit:
                        exit_price = stop_loss
                        exit_reason = "STOP_LOSS"
                    elif target_hit:
                        exit_price = take_profit
                        exit_reason = "TAKE_PROFIT"

                if exit_price is not None:
                    exit_index = future_index
                    break

            # Ignore unfinished trade at the end
            if exit_price is None:
                break

            # =====================================
            # PROFIT / LOSS
            # =====================================

            if signal == "LONG":
                price_difference = exit_price - entry
            else:
                price_difference = entry - exit_price

            pnl = position_size * price_difference

            if not math.isfinite(pnl):
                index = exit_index + 1
                continue

            balance += pnl

            if pnl > 0:
                wins += 1
                gross_profit += pnl
            else:
                losses += 1
                gross_loss += abs(pnl)

            peak_balance = max(peak_balance, balance)

            drawdown = (
                (peak_balance - balance)
                / peak_balance
                * 100
            ) if peak_balance > 0 else 0

            max_drawdown = max(
                max_drawdown,
                drawdown
            )

            trades.append({
                "trade_number": len(trades) + 1,
                "signal": signal,
                "entry": round(entry, 6),
                "exit": round(exit_price, 6),
                "stop_loss": round(stop_loss, 6),
                "take_profit": round(take_profit, 6),
                "exit_reason": exit_reason,
                "position_size": round(position_size, 4),
                "risk_amount": round(risk_amount, 2),
                "pnl": round(pnl, 2),
                "balance": round(balance, 2),
                "entry_index": index + 1,
                "exit_index": exit_index
            })

            equity_curve.append(round(balance, 2))

            # No overlapping positions
            index = exit_index + 1

        # =====================================
        # FINAL STATISTICS
        # =====================================

        total_trades = len(trades)

        win_rate = (
            wins / total_trades * 100
            if total_trades else 0
        )

        profit_factor = (
            gross_profit / gross_loss
            if gross_loss > 0
            else (
                float("inf")
                if gross_profit > 0
                else 0
            )
        )

        net_profit = balance - initial_balance

        return {
            "status": "completed",
            "mode": "SIMULATION",

            "initial_balance": round(
                initial_balance, 2
            ),

            "final_balance": round(balance, 2),

            "net_profit": round(net_profit, 2),

            "return_percent": round(
                net_profit / initial_balance * 100,
                2
            ),

            "total_trades": total_trades,
            "winning_trades": wins,
            "losing_trades": losses,

            "win_rate": round(win_rate, 2),

            "profit_factor": (
                round(profit_factor, 2)
                if math.isfinite(profit_factor)
                else "Infinity"
            ),

            "max_drawdown": round(
                max_drawdown, 2
            ),

            "risk_percent": risk_percent,
            "reward_risk": reward_risk,

            "trades": trades,
            "equity_curve": equity_curve,

            "unfinished_trade_ignored": True,
            "overlapping_trades": False,

            "limitations": [
                "Spread and commissions are not included",
                "Slippage is not included",
                "Intracandle price order is unknown",
                "Unfinished final trade is ignored"
            ]
        }

    except Exception as error:
        logger.exception("Backtest failed")

        return {
            "status": "error",
            "error": str(error)
        }
