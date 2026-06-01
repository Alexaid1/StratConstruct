import pandas as pd
import numpy as np
import pytest
from strategy.models import Condition, Rule, IndicatorConfig, Strategy, OPERATORS
from strategy.compiler import evaluate_condition, compile_rule, compile_strategy, add_indicators


def make_df(n: int = 100) -> pd.DataFrame:
    np.random.seed(0)
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    high  = close + np.abs(np.random.randn(n) * 0.3)
    low   = close - np.abs(np.random.randn(n) * 0.3)
    idx   = pd.date_range("2024-01-01", periods=n, freq="1h")
    return pd.DataFrame({
        "open": close, "high": high, "low": low,
        "close": close, "volume": np.ones(n) * 1000,
    }, index=idx)


# --- Condition validation ---

def test_invalid_operator_raises():
    with pytest.raises(ValueError, match="Unknown operator"):
        Condition("RSI_14", "!=", 30)


def test_all_valid_operators_accepted():
    df = make_df()
    df["RSI_14"] = 50.0
    for op in OPERATORS:
        cond = Condition("RSI_14", op, "RSI_14" if "crosses" in op else 50)
        result = evaluate_condition(df, cond)
        assert isinstance(result, pd.Series)


def test_missing_indicator_column_raises():
    df = make_df()
    cond = Condition("RSI_14", "<", 30)
    with pytest.raises(KeyError, match="RSI_14"):
        evaluate_condition(df, cond)


def test_missing_value_column_raises():
    df = make_df()
    df["RSI_14"] = 50.0
    cond = Condition("RSI_14", ">", "EMA_200")
    with pytest.raises(KeyError, match="EMA_200"):
        evaluate_condition(df, cond)


# --- Numeric comparison ---

def test_less_than_numeric():
    df = make_df()
    df["RSI_14"] = np.where(np.arange(100) < 50, 25.0, 75.0)
    cond = Condition("RSI_14", "<", 30)
    result = evaluate_condition(df, cond)
    assert result.iloc[:50].all()
    assert not result.iloc[50:].any()


def test_greater_than_numeric():
    df = make_df()
    df["val"] = np.linspace(0, 100, 100)
    cond = Condition("val", ">", 50)
    result = evaluate_condition(df, cond)
    assert result.iloc[-1]
    assert not result.iloc[0]


# --- Column-to-column comparison ---

def test_column_vs_column():
    df = make_df()
    df["fast"] = np.linspace(10, 20, 100)
    df["slow"] = np.linspace(15, 15, 100)
    cond = Condition("fast", ">", "slow")
    result = evaluate_condition(df, cond)
    # fast > slow only in second half
    assert not result.iloc[0]
    assert result.iloc[-1]


# --- Crossover ---

def test_crosses_above():
    df = make_df()
    fast = np.full(100, 10.0)
    slow = np.full(100, 12.0)
    fast[50] = 13.0  # crosses above at index 50
    df["fast"] = fast
    df["slow"] = slow
    cond = Condition("fast", "crosses_above", "slow")
    result = evaluate_condition(df, cond)
    assert result.iloc[50]
    assert not result.iloc[49]
    assert not result.iloc[51]


def test_crosses_below():
    df = make_df()
    fast = np.full(100, 15.0)
    slow = np.full(100, 12.0)
    fast[60] = 10.0  # crosses below at index 60
    df["fast"] = fast
    df["slow"] = slow
    cond = Condition("fast", "crosses_below", "slow")
    result = evaluate_condition(df, cond)
    assert result.iloc[60]
    assert not result.iloc[59]


def test_nan_evaluates_to_false():
    df = make_df()
    col = np.full(100, np.nan)
    col[50:] = 25.0
    df["RSI_14"] = col
    cond = Condition("RSI_14", "<", 30)
    result = evaluate_condition(df, cond)
    assert not result.iloc[:50].any()   # NaN rows → False
    assert result.iloc[50:].all()


# --- Rule logic ---

def test_and_rule():
    df = make_df()
    df["A"] = np.where(np.arange(100) >= 30, 1.0, 0.0)
    df["B"] = np.where(np.arange(100) >= 60, 1.0, 0.0)
    rule = Rule([
        Condition("A", ">", 0),
        Condition("B", ">", 0),
    ], logic="AND")
    result = compile_rule(df, rule)
    assert not result.iloc[29]   # A false
    assert not result.iloc[50]   # A true, B false
    assert result.iloc[70]       # both true


def test_or_rule():
    df = make_df()
    df["A"] = np.where(np.arange(100) >= 30, 1.0, 0.0)
    df["B"] = np.where(np.arange(100) >= 60, 1.0, 0.0)
    rule = Rule([
        Condition("A", ">", 0),
        Condition("B", ">", 0),
    ], logic="OR")
    result = compile_rule(df, rule)
    assert not result.iloc[29]  # both false
    assert result.iloc[50]      # A true
    assert result.iloc[70]      # both true


def test_empty_rule_returns_false():
    df = make_df()
    rule = Rule(conditions=[], logic="AND")
    result = compile_rule(df, rule)
    assert not result.any()


# --- Full strategy compilation ---

def test_compile_strategy_adds_indicators():
    df = make_df()
    strategy = Strategy(
        indicators=[IndicatorConfig("RSI", {"period": 14})],
        entry_rule=Rule([Condition("RSI_14", "<", 40)]),
    )
    entry, exit_, enriched = compile_strategy(df, strategy)
    assert "RSI_14" in enriched.columns


def test_compile_strategy_no_exit_rule():
    df = make_df()
    strategy = Strategy(
        indicators=[IndicatorConfig("RSI", {"period": 14})],
        entry_rule=Rule([Condition("RSI_14", "<", 40)]),
        exit_rule=None,
    )
    _, exit_, _ = compile_strategy(df, strategy)
    assert not exit_.any()


def test_compile_strategy_with_exit_rule():
    df = make_df()
    strategy = Strategy(
        indicators=[IndicatorConfig("RSI", {"period": 14})],
        entry_rule=Rule([Condition("RSI_14", "<", 35)]),
        exit_rule=Rule([Condition("RSI_14", ">", 65)]),
    )
    entry, exit_, _ = compile_strategy(df, strategy)
    assert isinstance(entry, pd.Series)
    assert isinstance(exit_, pd.Series)


def test_compile_strategy_does_not_mutate_original_df():
    df = make_df()
    original_cols = list(df.columns)
    strategy = Strategy(
        indicators=[IndicatorConfig("EMA", {"period": 20})],
        entry_rule=Rule([Condition("EMA_20", "<", 101)]),
    )
    compile_strategy(df, strategy)
    assert list(df.columns) == original_cols


def test_strategy_entry_exit_do_not_overlap_unexpectedly():
    """Entry and exit signals can coexist on same candle — backtester handles priority."""
    df = make_df()
    strategy = Strategy(
        indicators=[IndicatorConfig("RSI", {"period": 14})],
        entry_rule=Rule([Condition("RSI_14", "<", 60)]),
        exit_rule=Rule([Condition("RSI_14", ">", 40)]),
    )
    entry, exit_, _ = compile_strategy(df, strategy)
    assert entry.dtype == bool
    assert exit_.dtype == bool
