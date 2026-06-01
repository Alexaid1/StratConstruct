import pandas as pd
import pytest
from data.fetcher import fetch_ohlcv


def test_fetch_returns_dataframe():
    df = fetch_ohlcv("BTC/USDT", "1d", "2024-01-01", "2024-01-10")
    assert isinstance(df, pd.DataFrame)


def test_fetch_columns():
    df = fetch_ohlcv("BTC/USDT", "1d", "2024-01-01", "2024-01-10")
    assert set(["open", "high", "low", "close", "volume"]).issubset(df.columns)


def test_fetch_date_range():
    df = fetch_ohlcv("BTC/USDT", "1d", "2024-01-01", "2024-01-10")
    assert df.index.min() >= pd.Timestamp("2024-01-01", tz="UTC")
    assert df.index.max() <= pd.Timestamp("2024-01-10", tz="UTC")


def test_fetch_no_duplicates():
    df = fetch_ohlcv("BTC/USDT", "1d", "2024-01-01", "2024-01-31")
    assert not df.index.duplicated().any()


def test_fetch_sorted():
    df = fetch_ohlcv("BTC/USDT", "1d", "2024-01-01", "2024-01-31")
    assert df.index.is_monotonic_increasing


def test_fetch_no_nulls_in_close():
    df = fetch_ohlcv("BTC/USDT", "1d", "2024-01-01", "2024-01-31")
    assert df["close"].notna().all()
