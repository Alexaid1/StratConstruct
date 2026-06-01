import pandas as pd
import numpy as np
import pytest
from indicators.calculator import (
    add_rsi, add_macd, add_ema, add_sma, add_bbands,
    add_stochastic, add_atr, add_volume_sma, add_cci, add_supertrend,
)


def make_df(n: int = 200) -> pd.DataFrame:
    np.random.seed(42)
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    high  = close + np.abs(np.random.randn(n) * 0.3)
    low   = close - np.abs(np.random.randn(n) * 0.3)
    vol   = np.random.randint(1000, 5000, n).astype(float)
    idx   = pd.date_range("2024-01-01", periods=n, freq="1h")
    return pd.DataFrame({"open": close, "high": high, "low": low, "close": close, "volume": vol}, index=idx)


def test_rsi_range():
    df = add_rsi(make_df(), period=14)
    col = "RSI_14"
    valid = df[col].dropna()
    assert (valid >= 0).all() and (valid <= 100).all()


def test_macd_columns():
    df = add_macd(make_df())
    assert "MACD_12_26_9" in df.columns
    assert "MACDs_12_26_9" in df.columns
    assert "MACDh_12_26_9" in df.columns


def test_ema_shorter_than_sma_lag():
    df = make_df()
    df = add_ema(df, 20)
    df = add_sma(df, 20)
    ema_first = df["EMA_20"].first_valid_index()
    sma_first = df["SMA_20"].first_valid_index()
    # EMA starts with valid values earlier or at same point
    assert ema_first <= sma_first


def test_bbands_band_order():
    df = add_bbands(make_df(), period=20, std=2.0)
    valid = df.dropna()
    assert (valid["BB_upper_20_2_0"] >= valid["BB_mid_20_2_0"]).all()
    assert (valid["BB_mid_20_2_0"]   >= valid["BB_lower_20_2_0"]).all()


def test_stochastic_range():
    df = add_stochastic(make_df())
    for col in ["STOCHk_14_3_3", "STOCHd_14_3_3"]:
        valid = df[col].dropna()
        assert (valid >= 0).all() and (valid <= 100).all()


def test_atr_positive():
    df = add_atr(make_df(), period=14)
    assert (df["ATR_14"].dropna() > 0).all()


def test_volume_sma_column():
    df = add_volume_sma(make_df(), period=20)
    assert "VolSMA_20" in df.columns
    assert df["VolSMA_20"].dropna().shape[0] > 0


def test_cci_column():
    df = add_cci(make_df(), period=20)
    assert "CCI_20" in df.columns


def test_supertrend_direction_binary():
    df = add_supertrend(make_df(), period=7, multiplier=3.0)
    col = "ST_dir_7_3_0"
    valid = df[col].dropna()
    assert set(valid.unique()).issubset({1, -1})


def test_no_lookahead_bias():
    """
    Indicators must not use future data.
    Compute indicator on full series, then on series truncated at midpoint.
    Values at the midpoint must match.
    """
    df_full  = make_df(200)
    df_half  = make_df(200).iloc[:100].copy()

    df_full  = add_rsi(df_full,  period=14)
    df_half  = add_rsi(df_half,  period=14)

    mid = 99
    full_val = df_full["RSI_14"].iloc[mid]
    half_val = df_half["RSI_14"].iloc[mid]

    assert abs(full_val - half_val) < 1e-8, (
        f"Lookahead bias detected: RSI at midpoint differs "
        f"when computed on full ({full_val}) vs truncated ({half_val}) series"
    )
