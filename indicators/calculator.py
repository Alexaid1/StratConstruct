import pandas as pd
import pandas_ta as ta


def add_rsi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    df[f"RSI_{period}"] = ta.rsi(df["close"], length=period)
    return df


def add_macd(
    df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9
) -> pd.DataFrame:
    result = ta.macd(df["close"], fast=fast, slow=slow, signal=signal)
    df[f"MACD_{fast}_{slow}_{signal}"] = result[f"MACD_{fast}_{slow}_{signal}"]
    df[f"MACDs_{fast}_{slow}_{signal}"] = result[f"MACDs_{fast}_{slow}_{signal}"]
    df[f"MACDh_{fast}_{slow}_{signal}"] = result[f"MACDh_{fast}_{slow}_{signal}"]
    return df


def add_ema(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    df[f"EMA_{period}"] = ta.ema(df["close"], length=period)
    return df


def add_sma(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    df[f"SMA_{period}"] = ta.sma(df["close"], length=period)
    return df


def add_bbands(df: pd.DataFrame, period: int = 20, std: float = 2.0) -> pd.DataFrame:
    result = ta.bbands(df["close"], length=period, std=std)
    upper_col = next(c for c in result.columns if c.startswith("BBU_"))
    mid_col   = next(c for c in result.columns if c.startswith("BBM_"))
    lower_col = next(c for c in result.columns if c.startswith("BBL_"))
    std_str = str(std).replace(".", "_")
    df[f"BB_upper_{period}_{std_str}"] = result[upper_col]
    df[f"BB_mid_{period}_{std_str}"]   = result[mid_col]
    df[f"BB_lower_{period}_{std_str}"] = result[lower_col]
    return df


def add_stochastic(df: pd.DataFrame, k: int = 14, d: int = 3) -> pd.DataFrame:
    result = ta.stoch(df["high"], df["low"], df["close"], k=k, d=d)
    df[f"STOCHk_{k}_{d}_3"] = result[f"STOCHk_{k}_{d}_3"]
    df[f"STOCHd_{k}_{d}_3"] = result[f"STOCHd_{k}_{d}_3"]
    return df


def add_atr(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    df[f"ATR_{period}"] = ta.atr(df["high"], df["low"], df["close"], length=period)
    return df


def add_volume_sma(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    df[f"VolSMA_{period}"] = ta.sma(df["volume"], length=period)
    return df


def add_cci(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    df[f"CCI_{period}"] = ta.cci(df["high"], df["low"], df["close"], length=period)
    return df


def add_supertrend(df: pd.DataFrame, period: int = 7, multiplier: float = 3.0) -> pd.DataFrame:
    result = ta.supertrend(df["high"], df["low"], df["close"], length=period, multiplier=multiplier)
    val_col = next(c for c in result.columns if c.startswith("SUPERT_") and not any(s in c for s in ["d_", "l_", "s_"]))
    dir_col = next(c for c in result.columns if c.startswith("SUPERTd_"))
    mul_str = str(multiplier).replace(".", "_")
    df[f"ST_{period}_{mul_str}"]     = result[val_col]
    df[f"ST_dir_{period}_{mul_str}"] = result[dir_col]
    return df


INDICATOR_MAP = {
    "RSI":          add_rsi,
    "MACD":         add_macd,
    "EMA":          add_ema,
    "SMA":          add_sma,
    "BB":           add_bbands,
    "Stochastic":   add_stochastic,
    "ATR":          add_atr,
    "VolumeSMA":    add_volume_sma,
    "CCI":          add_cci,
    "Supertrend":   add_supertrend,
}
