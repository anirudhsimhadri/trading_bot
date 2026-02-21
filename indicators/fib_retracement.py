import pandas as pd


def _resolve_column(df: pd.DataFrame, candidates: list[str]) -> str:
    for col in candidates:
        if col in df.columns:
            return col
    raise KeyError(f"Missing expected columns. Tried: {candidates}")


def detect_trend_break(df):
    close_col = _resolve_column(df, ["close", "Close"])

    df["ema_50"] = df[close_col].ewm(span=50, adjust=False).mean()
    df["ema_200"] = df[close_col].ewm(span=200, adjust=False).mean()

    # Bullish Trend Break (Price crosses above 200 EMA)
    df["bullish_break"] = (
        (df[close_col].shift(1) < df["ema_200"].shift(1))
        & (df[close_col] > df["ema_200"])
    )

    # Bearish Trend Break (Price crosses below 200 EMA)
    df["bearish_break"] = (
        (df[close_col].shift(1) > df["ema_200"].shift(1))
        & (df[close_col] < df["ema_200"])
    )

    return df


def fibonacci_levels(high, low):
    diff = high - low
    ratios = {
        "0": high - diff * 0,
        "0.382": high - diff * 0.382,
        "0.5": high - diff * 0.5,
        "0.618": high - diff * 0.618,
        "-0.382": high - diff * -0.382,
        "-0.618": high - diff * -0.618,
        "1": high - diff * 1,
        "-1.618": high - diff * -1.618,
    }
    return ratios


def check_fibonacci_entry(df, fib_levels):
    low_col = _resolve_column(df, ["low", "Low"])
    golden_zone = (fib_levels["0.5"], fib_levels["0.618"])
    df["entry_signal"] = (
        (df[low_col] <= golden_zone[1])
        & (df[low_col] >= golden_zone[0])
    )
    return df
