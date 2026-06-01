import pandas as pd
import numpy as np
import pytest
from backtester.engine import run_backtest


def make_df(n: int = 100, price: float = 100.0) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=n, freq="1h")
    prices = np.full(n, price, dtype=float)
    return pd.DataFrame(
        {"open": prices, "high": prices * 1.01, "low": prices * 0.99, "close": prices, "volume": np.ones(n) * 1000},
        index=idx,
    )


def make_signals(df, entry_at: list[int], exit_at: list[int]) -> tuple[pd.Series, pd.Series]:
    entry = pd.Series(False, index=df.index)
    exit_ = pd.Series(False, index=df.index)
    for i in entry_at:
        entry.iloc[i] = True
    for i in exit_at:
        exit_.iloc[i] = True
    return entry, exit_


def test_no_trades_when_no_signals():
    df = make_df()
    entry = pd.Series(False, index=df.index)
    exit_ = pd.Series(False, index=df.index)
    result = run_backtest(df, entry, exit_)
    assert result.num_trades == 0


def test_commission_reduces_capital():
    df = make_df()
    entry, exit_ = make_signals(df, [10], [20])
    result = run_backtest(df, entry, exit_, commission=0.001)
    # Flat price → only commission costs, so final capital < initial
    assert result.equity_curve.iloc[-1] < 10_000


def test_take_profit_triggers():
    n = 50
    idx = pd.date_range("2024-01-01", periods=n, freq="1h")
    prices = np.full(n, 100.0)
    prices[20:] = 110.0  # price jumps 10% at candle 20
    df = pd.DataFrame(
        {"open": prices, "high": prices, "low": prices * 0.99, "close": prices, "volume": np.ones(n)},
        index=idx,
    )
    entry, exit_ = make_signals(df, [10], [40])
    result = run_backtest(df, entry, exit_, take_profit_pct=5.0)
    tp_trades = [t for t in result.trades if t["reason"] == "take_profit"]
    assert len(tp_trades) >= 1


def test_stop_loss_triggers():
    n = 50
    idx = pd.date_range("2024-01-01", periods=n, freq="1h")
    prices = np.full(n, 100.0)
    prices[20:] = 90.0  # price drops 10% at candle 20
    df = pd.DataFrame(
        {"open": prices, "high": prices * 1.01, "low": prices * 0.85, "close": prices, "volume": np.ones(n)},
        index=idx,
    )
    entry, exit_ = make_signals(df, [10], [40])
    result = run_backtest(df, entry, exit_, stop_loss_pct=5.0)
    sl_trades = [t for t in result.trades if t["reason"] == "stop_loss"]
    assert len(sl_trades) >= 1


def test_no_lookahead_bias_in_backtest():
    """
    Signal at candle T must execute at candle T+1 open, not T.
    Entry signal fires at index 10, so trade must open at index 11.
    """
    df = make_df(50)
    entry, exit_ = make_signals(df, [10], [20])
    result = run_backtest(df, entry, exit_)
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade["entry_time"] == df.index[11], (
        f"Trade opened at {trade['entry_time']}, expected {df.index[11]} — lookahead bias!"
    )


def test_only_one_position_at_a_time():
    df = make_df(100)
    # Two entry signals close together, no exit between them
    entry, exit_ = make_signals(df, [10, 15], [50])
    result = run_backtest(df, entry, exit_)
    assert result.num_trades == 1


def test_win_rate_all_profitable():
    n = 60
    idx = pd.date_range("2024-01-01", periods=n, freq="1h")
    prices = np.linspace(100, 200, n)  # steadily rising
    df = pd.DataFrame(
        {"open": prices, "high": prices * 1.01, "low": prices * 0.99, "close": prices, "volume": np.ones(n)},
        index=idx,
    )
    entry, exit_ = make_signals(df, [5, 30], [20, 50])
    result = run_backtest(df, entry, exit_, commission=0)
    assert result.win_rate_pct == 100.0


def test_metrics_structure():
    df = make_df()
    entry, exit_ = make_signals(df, [10], [20])
    result = run_backtest(df, entry, exit_)
    assert hasattr(result, "total_return_pct")
    assert hasattr(result, "sharpe_ratio")
    assert hasattr(result, "max_drawdown_pct")


def test_open_position_force_closed_at_end():
    # Entry at candle 10, no exit signal → should be closed at end_of_data
    df = make_df(50)
    entry = pd.Series(False, index=df.index)
    exit_ = pd.Series(False, index=df.index)
    entry.iloc[10] = True
    result = run_backtest(df, entry, exit_)
    assert result.num_trades == 1
    assert result.trades[0]["reason"] == "end_of_data"
    assert result.trades[0]["exit_time"] == df.index[-1]


def test_force_closed_trade_counted_in_metrics():
    df = make_df(50)
    entry = pd.Series(False, index=df.index)
    exit_ = pd.Series(False, index=df.index)
    entry.iloc[5] = True
    result = run_backtest(df, entry, exit_)
    assert result.num_trades == 1
    assert result.win_rate_pct in (0.0, 100.0)  # one trade, either win or loss
