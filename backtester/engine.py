from dataclasses import dataclass, field
from typing import Optional
import numpy as np
import pandas as pd


@dataclass
class BacktestResult:
    trades: list
    equity_curve: pd.Series
    total_return_pct: float
    num_trades: int
    win_rate_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float
    avg_win_pct: float
    avg_loss_pct: float


def run_backtest(
    df: pd.DataFrame,
    entry_signal: pd.Series,
    exit_signal: pd.Series,
    take_profit_pct: Optional[float] = None,
    stop_loss_pct: Optional[float] = None,
    commission: float = 0.001,
    initial_capital: float = 10_000.0,
) -> BacktestResult:
    """
    Vectorized backtest engine. Long-only, one position at a time.

    Lookahead-bias rule:
      Signal fires on candle T → trade executes at OPEN of candle T+1.
    """
    # Shift signals by 1 so execution happens at next candle's open
    entry = entry_signal.shift(1).fillna(False).astype(bool)
    exit_ = exit_signal.shift(1).fillna(False).astype(bool)

    opens  = df["open"].values
    highs  = df["high"].values
    lows   = df["low"].values
    index  = df.index

    capital = initial_capital
    equity  = np.full(len(df), np.nan)
    trades  = []

    in_position   = False
    entry_price   = 0.0
    entry_idx     = 0
    position_size = 0.0  # in base asset units

    for i in range(len(df)):
        if not in_position:
            if entry.iloc[i]:
                price = opens[i]
                cost  = capital * (1 - commission)
                position_size = cost / price
                entry_price   = price
                entry_idx     = i
                capital       = 0.0
                in_position   = True
        else:
            close_price = None
            reason      = None

            # Check stop-loss and take-profit against intrabar high/low
            if stop_loss_pct is not None:
                sl_price = entry_price * (1 - stop_loss_pct / 100)
                if lows[i] <= sl_price:
                    close_price = sl_price
                    reason      = "stop_loss"

            if take_profit_pct is not None and close_price is None:
                tp_price = entry_price * (1 + take_profit_pct / 100)
                if highs[i] >= tp_price:
                    close_price = tp_price
                    reason      = "take_profit"

            # Exit signal fires at this candle's open (already shifted)
            if close_price is None and exit_.iloc[i]:
                close_price = opens[i]
                reason      = "signal"

            if close_price is not None:
                proceeds = position_size * close_price * (1 - commission)
                pnl_pct  = (close_price / entry_price - 1) * 100

                trades.append({
                    "entry_time":  index[entry_idx],
                    "exit_time":   index[i],
                    "entry_price": entry_price,
                    "exit_price":  close_price,
                    "pnl_pct":     pnl_pct,
                    "reason":      reason,
                })

                capital      = proceeds
                in_position  = False
                position_size = 0.0

        equity[i] = capital + (position_size * opens[i] if in_position else 0)

    # Force-close any position still open at end of data
    if in_position:
        last_i      = len(df) - 1
        close_price = df["close"].values[last_i]
        proceeds    = position_size * close_price * (1 - commission)
        pnl_pct     = (close_price / entry_price - 1) * 100
        trades.append({
            "entry_time":  index[entry_idx],
            "exit_time":   index[last_i],
            "entry_price": entry_price,
            "exit_price":  close_price,
            "pnl_pct":     pnl_pct,
            "reason":      "end_of_data",
        })
        capital = proceeds
        equity[last_i] = capital

    equity_series = pd.Series(equity, index=index)

    # --- Metrics ---
    total_return = (equity_series.iloc[-1] / initial_capital - 1) * 100

    num_trades = len(trades)
    if num_trades == 0:
        return BacktestResult(
            trades=[], equity_curve=equity_series,
            total_return_pct=total_return, num_trades=0,
            win_rate_pct=0, max_drawdown_pct=0,
            sharpe_ratio=0, avg_win_pct=0, avg_loss_pct=0,
        )

    pnls    = [t["pnl_pct"] for t in trades]
    wins    = [p for p in pnls if p > 0]
    losses  = [p for p in pnls if p <= 0]
    win_rate = len(wins) / num_trades * 100

    # Max drawdown on equity curve
    roll_max   = equity_series.cummax()
    drawdowns  = (equity_series - roll_max) / roll_max * 100
    max_dd     = drawdowns.min()

    # Sharpe (annualised, assuming daily returns from equity curve, 252 trading days)
    daily_ret  = equity_series.pct_change().dropna()
    sharpe     = 0.0
    if daily_ret.std() > 0:
        sharpe = (daily_ret.mean() / daily_ret.std()) * np.sqrt(252)

    return BacktestResult(
        trades=trades,
        equity_curve=equity_series,
        total_return_pct=round(total_return, 2),
        num_trades=num_trades,
        win_rate_pct=round(win_rate, 2),
        max_drawdown_pct=round(max_dd, 2),
        sharpe_ratio=round(sharpe, 3),
        avg_win_pct=round(sum(wins) / len(wins), 2) if wins else 0.0,
        avg_loss_pct=round(sum(losses) / len(losses), 2) if losses else 0.0,
    )
