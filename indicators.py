
import logging
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

# =====================================
# FOREX HUNTER AI 5.0
# TECHNICAL INDICATORS
# =====================================

MIN_CANDLES = 200
MIN_SIGNAL_SCORE = 70


def error_result(message):
    return {
        "signal": "WAIT",
        "score": 0,
        "analysis_score": 0,
        "confidence": 0,
        "error": message
    }


def analyze_market(candles):
    """
    Analyze Forex market using technical indicators.

    Signals:
        LONG  - bullish setup
        SHORT - bearish setup
        WAIT  - insufficient confirmation

    This module is for analysis and simulation only.
    """

    try:
        if not isinstance(candles, list):
            return error_result("Invalid candle data")

        if len(candles) < MIN_CANDLES:
            return error_result(
                f"Need at least {MIN_CANDLES} candles"
            )

        df = pd.DataFrame(candles)

        required = ["open", "high", "low", "close"]

        if not all(column in df.columns for column in required):
            return error_result("Missing OHLC columns")

        for column in required:
            df[column] = pd.to_numeric(
                df[column],
                errors="coerce"
            )

        df = df.replace([np.inf, -np.inf], np.nan)
        df = df.dropna(subset=required).reset_index(drop=True)

        if len(df) < MIN_CANDLES:
            return error_result("Not enough valid candles")

        if (df[required] <= 0).any().any():
            return error_result("Invalid price values")

        if (
            (df["high"] < df["low"]).any()
            or (df["high"] < df[["open", "close"]].max(axis=1)).any()
            or (df["low"] > df[["open", "close"]].min(axis=1)).any()
        ):
            return error_result("Invalid OHLC candle structure")

        # =====================================
        # EMA
        # =====================================

        df["ema9"] = df["close"].ewm(
            span=9, adjust=False
        ).mean()

        df["ema21"] = df["close"].ewm(
            span=21, adjust=False
        ).mean()

        df["ema50"] = df["close"].ewm(
            span=50, adjust=False
        ).mean()

        df["ema200"] = df["close"].ewm(
            span=200, adjust=False
        ).mean()

        # =====================================
        # RSI
        # =====================================

        delta = df["close"].diff()

        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)

        avg_gain = gain.ewm(
            alpha=1 / 14,
            adjust=False,
            min_periods=14
        ).mean()

        avg_loss = loss.ewm(
            alpha=1 / 14,
            adjust=False,
            min_periods=14
        ).mean()

        rs = avg_gain / avg_loss.replace(0, np.nan)

        df["rsi"] = 100 - (100 / (1 + rs))

        df.loc[
            (avg_loss == 0) & (avg_gain > 0),
            "rsi"
        ] = 100

        df.loc[
            (avg_gain == 0) & (avg_loss > 0),
            "rsi"
        ] = 0

        # =====================================
        # MACD
        # =====================================

        ema12 = df["close"].ewm(
            span=12,
            adjust=False
        ).mean()

        ema26 = df["close"].ewm(
            span=26,
            adjust=False
        ).mean()

        df["macd"] = ema12 - ema26

        df["macd_signal"] = df["macd"].ewm(
            span=9,
            adjust=False
        ).mean()

        df["macd_hist"] = (
            df["macd"] - df["macd_signal"]
        )

        # =====================================
        # ATR
        # =====================================

        previous_close = df["close"].shift(1)

        tr = pd.concat(
            [
                df["high"] - df["low"],
                (df["high"] - previous_close).abs(),
                (df["low"] - previous_close).abs()
            ],
            axis=1
        ).max(axis=1)

        df["atr"] = tr.ewm(
            alpha=1 / 14,
            adjust=False
        ).mean()

        # =====================================
        # ADX
        # =====================================

        up_move = df["high"].diff()
        down_move = -df["low"].diff()

        plus_dm = pd.Series(
            np.where(
                (up_move > down_move) & (up_move > 0),
                up_move,
                0
            ),
            index=df.index
        )

        minus_dm = pd.Series(
            np.where(
                (down_move > up_move) & (down_move > 0),
                down_move,
                0
            ),
            index=df.index
        )

        atr_safe = df["atr"].replace(0, np.nan)

        plus_di = (
            100 * plus_dm.ewm(
                alpha=1 / 14,
                adjust=False
            ).mean() / atr_safe
        )

        minus_di = (
            100 * minus_dm.ewm(
                alpha=1 / 14,
                adjust=False
            ).mean() / atr_safe
        )

        dx = (
            100 * (plus_di - minus_di).abs()
            / (plus_di + minus_di).replace(0, np.nan)
        )

        df["adx"] = dx.ewm(
            alpha=1 / 14,
            adjust=False
        ).mean()

        df["plus_di"] = plus_di
        df["minus_di"] = minus_di

        # =====================================
        # BOLLINGER BANDS
        # =====================================

        df["bb_middle"] = df["close"].rolling(20).mean()

        bb_std = df["close"].rolling(20).std()

        df["bb_upper"] = df["bb_middle"] + 2 * bb_std
        df["bb_lower"] = df["bb_middle"] - 2 * bb_std

        # =====================================
        # FINAL CANDLE
        # =====================================

        last = df.iloc[-1]

        values = [
            last["ema9"],
            last["ema21"],
            last["ema50"],
            last["ema200"],
            last["rsi"],
            last["macd"],
            last["macd_signal"],
            last["atr"],
            last["adx"],
            last["plus_di"],
            last["minus_di"],
            last["bb_upper"],
            last["bb_lower"]
        ]

        if not all(np.isfinite(value) for value in values):
            return error_result("Indicators are not ready")

        price = float(last["close"])
        atr = float(last["atr"])
        rsi = float(last["rsi"])
        adx = float(last["adx"])

        if atr <= 0 or price <= 0:
            return error_result("Invalid ATR or price")

        # =====================================
        # SUPPORT AND RESISTANCE
        # =====================================

        recent = df.tail(50)

        support = float(recent["low"].min())
        resistance = float(recent["high"].max())

        # =====================================
        # SIGNAL SCORING
        # =====================================

        long_points = 0
        short_points = 0

        # EMA trend
        if last["ema9"] > last["ema21"]:
            long_points += 15
        elif last["ema9"] < last["ema21"]:
            short_points += 15

        if last["ema21"] > last["ema50"]:
            long_points += 15
        elif last["ema21"] < last["ema50"]:
            short_points += 15

        if price > last["ema200"]:
            long_points += 10
        elif price < last["ema200"]:
            short_points += 10

        # RSI
        if 50 < rsi < 70:
            long_points += 15
        elif 30 < rsi < 50:
            short_points += 15

        # MACD
        if last["macd"] > last["macd_signal"]:
            long_points += 15
        elif last["macd"] < last["macd_signal"]:
            short_points += 15

        # ADX trend strength and direction
        if adx >= 20:
            if last["plus_di"] > last["minus_di"]:
                long_points += 15
            elif last["minus_di"] > last["plus_di"]:
                short_points += 15

        # Bollinger position
        if price > last["bb_middle"]:
            long_points += 10
        elif price < last["bb_middle"]:
            short_points += 10

        # =====================================
        # SIGNAL DECISION
        # =====================================

        if (
            long_points >= MIN_SIGNAL_SCORE
            and long_points > short_points
        ):
            signal = "LONG"
            score = long_points

        elif (
            short_points >= MIN_SIGNAL_SCORE
            and short_points > long_points
        ):
            signal = "SHORT"
            score = short_points

        else:
            signal = "WAIT"
            score = max(long_points, short_points)

        # =====================================
        # ENTRY / STOP LOSS / TARGET
        # =====================================

        entry = price
        stop_loss = None
        take_profit = None

        if signal == "LONG":
            stop_loss = entry - (atr * 1.5)
            take_profit = entry + (
                (entry - stop_loss) * 2
            )

        elif signal == "SHORT":
            stop_loss = entry + (atr * 1.5)
            take_profit = entry - (
                (stop_loss - entry) * 2
            )

        # =====================================
        # RESULT
        # =====================================

        return {
            "signal": signal,
            "score": int(score),
            "analysis_score": int(score),
            "confidence": int(score),

            "price": round(price, 6),
            "entry": round(entry, 6),

            "stop_loss": (
                round(stop_loss, 6)
                if stop_loss is not None else None
            ),

            "take_profit": (
                round(take_profit, 6)
                if take_profit is not None else None
            ),

            "indicators": {
                "ema9": round(float(last["ema9"]), 6),
                "ema21": round(float(last["ema21"]), 6),
                "ema50": round(float(last["ema50"]), 6),
                "ema200": round(float(last["ema200"]), 6),
                "rsi": round(rsi, 2),
                "macd": round(float(last["macd"]), 6),
                "macd_signal": round(
                    float(last["macd_signal"]), 6
                ),
                "adx": round(adx, 2),
                "atr": round(atr, 6),
                "plus_di": round(
                    float(last["plus_di"]), 2
                ),
                "minus_di": round(
                    float(last["minus_di"]), 2
                )
            },

            "support": round(support, 6),
            "resistance": round(resistance, 6),

            "long_score": int(long_points),
            "short_score": int(short_points),

            "mode": "SIMULATION"
        }

    except Exception as error:
        logger.exception("Market analysis failed")
        return error_result(str(error))
