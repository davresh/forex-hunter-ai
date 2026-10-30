
import pandas as pd

from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD, ADXIndicator
from ta.volatility import AverageTrueRange, BollingerBands


def analyze_market(candles):
    """
    Forex Hunter AI — Institutional Analyst

    Анализирует:
    - EMA 9 / 21 / 50
    - RSI
    - MACD
    - ADX
    - ATR
    - Bollinger Bands
    - Свечную структуру
    - Поддержку и сопротивление

    Возвращает LONG, SHORT или WAIT.
    Это аналитический сигнал, а не гарантия прибыли.
    """

    if not isinstance(candles, list) or len(candles) < 60:
        return {
            "status": "insufficient_data",
            "signal": "WAIT",
            "message": "Need at least 60 candles",
            "confidence": 0
        }

    try:
        df = pd.DataFrame(candles)

        required = ["open", "high", "low", "close"]

        if any(column not in df.columns for column in required):
            return {
                "status": "error",
                "signal": "WAIT",
                "message": "Missing OHLC candle data",
                "confidence": 0
            }

        for column in required:
            df[column] = pd.to_numeric(
                df[column], errors="coerce"
            )

        df = df.dropna(subset=required).reset_index(drop=True)

        if len(df) < 60:
            return {
                "status": "insufficient_data",
                "signal": "WAIT",
                "message": "Not enough valid candles",
                "confidence": 0
            }

        if (df["high"] < df["low"]).any():
            raise ValueError("Invalid candle: high is below low")

        if (df["close"] <= 0).any():
            raise ValueError("Invalid candle close price")

        close = df["close"]
        high = df["high"]
        low = df["low"]

        # -------------------------
        # 1. TECHNICAL INDICATORS
        # -------------------------

        df["ema_9"] = EMAIndicator(
            close=close, window=9
        ).ema_indicator()

        df["ema_21"] = EMAIndicator(
            close=close, window=21
        ).ema_indicator()

        df["ema_50"] = EMAIndicator(
            close=close, window=50
        ).ema_indicator()

        df["rsi"] = RSIIndicator(
            close=close, window=14
        ).rsi()

        macd = MACD(close=close)

        df["macd"] = macd.macd()
        df["macd_signal"] = macd.macd_signal()
        df["macd_hist"] = macd.macd_diff()

        adx = ADXIndicator(
            high=high,
            low=low,
            close=close,
            window=14
        )

        df["adx"] = adx.adx()
        df["plus_di"] = adx.adx_pos()
        df["minus_di"] = adx.adx_neg()

        atr = AverageTrueRange(
            high=high,
            low=low,
            close=close,
            window=14
        )

        df["atr"] = atr.average_true_range()

        bb = BollingerBands(
            close=close,
            window=20,
            window_dev=2
        )

        df["bb_upper"] = bb.bollinger_hband()
        df["bb_middle"] = bb.bollinger_mavg()
        df["bb_lower"] = bb.bollinger_lband()

        last = df.iloc[-1]
        previous = df.iloc[-2]

        indicator_columns = [
            "ema_9", "ema_21", "ema_50",
            "rsi", "macd", "macd_signal",
            "macd_hist", "adx", "plus_di",
            "minus_di", "atr", "bb_upper",
            "bb_middle", "bb_lower"
        ]

        if last[indicator_columns].isna().any():
            return {
                "status": "insufficient_data",
                "signal": "WAIT",
                "message": "Indicators are not ready",
                "confidence": 0
            }

        # -------------------------
        # 2. MARKET TREND
        # -------------------------

        bullish_trend = (
            last["ema_9"] > last["ema_21"]
            and last["ema_21"] > last["ema_50"]
            and last["close"] > last["ema_50"]
        )

        bearish_trend = (
            last["ema_9"] < last["ema_21"]
            and last["ema_21"] < last["ema_50"]
            and last["close"] < last["ema_50"]
        )

        # -------------------------
        # 3. MOMENTUM
        # -------------------------

        bullish_macd = (
            last["macd"] > last["macd_signal"]
            and last["macd_hist"] > previous["macd_hist"]
        )

        bearish_macd = (
            last["macd"] < last["macd_signal"]
            and last["macd_hist"] < previous["macd_hist"]
        )

        rsi = float(last["rsi"])

        bullish_rsi = 50 < rsi < 70
        bearish_rsi = 30 < rsi < 50

        # -------------------------
        # 4. MARKET STRENGTH
        # -------------------------

        adx_value = float(last["adx"])

        strong_market = adx_value >= 20

        bullish_direction = (
            last["plus_di"] > last["minus_di"]
        )

        bearish_direction = (
            last["minus_di"] > last["plus_di"]
        )

        # -------------------------
        # 5. CANDLE ANALYSIS
        # -------------------------

        candle_range = float(
            last["high"] - last["low"]
        )

        candle_body = abs(
            float(last["close"] - last["open"])
        )

        candle_strength = (
            candle_body / candle_range
            if candle_range > 0 else 0
        )

        bullish_candle = (
            last["close"] > last["open"]
            and candle_strength >= 0.4
        )

        bearish_candle = (
            last["close"] < last["open"]
            and candle_strength >= 0.4
        )

        # -------------------------
        # 6. SUPPORT / RESISTANCE
        # -------------------------

        recent = df.iloc[-21:-1]

        support = float(recent["low"].min())
        resistance = float(recent["high"].max())

        current_price = float(last["close"])

        # -------------------------
        # 7. VOLATILITY
        # -------------------------

        atr_value = float(last["atr"])

        bb_upper = float(last["bb_upper"])
        bb_lower = float(last["bb_lower"])

        volatility_percent = (
            atr_value / current_price * 100
            if current_price > 0 else 0
        )

        # -------------------------
        # 8. INTELLIGENCE SCORE
        # -------------------------

        long_score = 0
        short_score = 0
        reasons = []

        if bullish_trend:
            long_score += 2
            reasons.append("Bullish EMA trend")

        if bearish_trend:
            short_score += 2
            reasons.append("Bearish EMA trend")

        if bullish_macd:
            long_score += 2
            reasons.append("MACD bullish momentum")

        if bearish_macd:
            short_score += 2
            reasons.append("MACD bearish momentum")

        if bullish_rsi:
            long_score += 1
            reasons.append("RSI supports buyers")

        if bearish_rsi:
            short_score += 1
            reasons.append("RSI supports sellers")

        if strong_market and bullish_direction:
            long_score += 1
            reasons.append("ADX confirms bullish direction")

        if strong_market and bearish_direction:
            short_score += 1
            reasons.append("ADX confirms bearish direction")

        if bullish_candle:
            long_score += 1
            reasons.append("Bullish candle confirmation")

        if bearish_candle:
            short_score += 1
            reasons.append("Bearish candle confirmation")

        # -------------------------
        # 9. SIGNAL DECISION
        # -------------------------

        signal = "WAIT"

        if (
            bullish_trend
            and strong_market
            and long_score >= 6
            and long_score > short_score
            and not bearish_candle
        ):
            signal = "LONG"

        elif (
            bearish_trend
            and strong_market
            and short_score >= 6
            and short_score > long_score
            and not bullish_candle
        ):
            signal = "SHORT"

        # Score is NOT a probability of winning.
        best_score = max(long_score, short_score)

        analysis_score = min(
            100, round(best_score / 7 * 100)
        )

        # -------------------------
        # 10. VIRTUAL TRADE LEVELS
        # -------------------------

        entry = current_price
        stop_loss = None
        take_profit_1 = None
        take_profit_2 = None

        if signal == "LONG":
            stop_loss = entry - (atr_value * 1.5)
            take_profit_1 = entry + (atr_value * 2)
            take_profit_2 = entry + (atr_value * 3)

        elif signal == "SHORT":
            stop_loss = entry + (atr_value * 1.5)
            take_profit_1 = entry - (atr_value * 2)
            take_profit_2 = entry - (atr_value * 3)

        # -------------------------
        # 11. EXPLANATION
        # -------------------------

        if signal == "WAIT":
            reasons.append(
                "Conditions are not strong enough for confirmation"
            )

        return {
            "status": "success",
            "signal": signal,

            "analysis_score": analysis_score,
            "confidence": analysis_score,

            "long_score": long_score,
            "short_score": short_score,

            "price": round(current_price, 6),

            "rsi": round(rsi, 2),

            "ema_9": round(float(last["ema_9"]), 6),
            "ema_21": round(float(last["ema_21"]), 6),
            "ema_50": round(float(last["ema_50"]), 6),

            "macd": round(float(last["macd"]), 6),
            "macd_signal": round(
                float(last["macd_signal"]), 6
            ),

            "adx": round(adx_value, 2),

            "atr": round(atr_value, 6),
            "volatility_percent": round(
                volatility_percent, 4
            ),

            "bb_upper": round(bb_upper, 6),
            "bb_middle": round(
                float(last["bb_middle"]), 6
            ),
            "bb_lower": round(bb_lower, 6),

            "support": round(support, 6),
            "resistance": round(resistance, 6),

            "candle_strength": round(
                candle_strength, 2
            ),

            "entry": round(entry, 6),
            "stop_loss": (
                round(stop_loss, 6)
                if stop_loss is not None else None
            ),
            "take_profit_1": (
                round(take_profit_1, 6)
                if take_profit_1 is not None else None
            ),
            "take_profit_2": (
                round(take_profit_2, 6)
                if take_profit_2 is not None else None
            ),

            "reasons": reasons
        }

    except Exception as error:
        return {
            "status": "error",
            "signal": "WAIT",
            "message": str(error),
            "confidence": 0
        }
