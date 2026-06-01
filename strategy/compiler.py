from __future__ import annotations
import pandas as pd
from indicators.calculator import INDICATOR_MAP
from strategy.models import Condition, Rule, Strategy, IndicatorConfig


def add_indicators(df: pd.DataFrame, configs: list[IndicatorConfig]) -> pd.DataFrame:
    """Add all required indicators to a copy of df."""
    df = df.copy()
    for cfg in configs:
        if cfg.name not in INDICATOR_MAP:
            raise ValueError(f"Unknown indicator '{cfg.name}'. Available: {list(INDICATOR_MAP)}")
        df = INDICATOR_MAP[cfg.name](df, **cfg.params)
    return df


def evaluate_condition(df: pd.DataFrame, cond: Condition) -> pd.Series:
    """
    Evaluate a single condition against df, returning a boolean Series.
    NaN values → False (no signal while indicator is warming up).
    """
    if cond.indicator not in df.columns:
        raise KeyError(
            f"Column '{cond.indicator}' not found in DataFrame. "
            f"Did you add the indicator to the strategy's indicators list?"
        )

    left = df[cond.indicator]

    if isinstance(cond.value, str):
        if cond.value not in df.columns:
            raise KeyError(f"Column '{cond.value}' not found in DataFrame.")
        right = df[cond.value]
        prev_right = right.shift(1)
    else:
        right = cond.value
        prev_right = cond.value

    op = cond.operator
    if op == "<":
        result = left < right
    elif op == ">":
        result = left > right
    elif op == "<=":
        result = left <= right
    elif op == ">=":
        result = left >= right
    elif op == "==":
        result = left == right
    elif op == "crosses_above":
        # This candle: left > right; previous candle: left <= right
        prev_left = left.shift(1)
        result = (left > right) & (prev_left <= prev_right)
    elif op == "crosses_below":
        prev_left = left.shift(1)
        result = (left < right) & (prev_left >= prev_right)
    else:
        raise ValueError(f"Unknown operator '{op}'")

    return result.fillna(False)


def compile_rule(df: pd.DataFrame, rule: Rule) -> pd.Series:
    """
    Combine all conditions in a Rule with AND / OR logic.
    Returns a boolean Series aligned to df.index.
    """
    if not rule.conditions:
        return pd.Series(False, index=df.index)

    signals = [evaluate_condition(df, c) for c in rule.conditions]
    result = signals[0]
    for s in signals[1:]:
        if rule.logic == "AND":
            result = result & s
        else:
            result = result | s
    return result


def compile_strategy(
    df: pd.DataFrame,
    strategy: Strategy,
) -> tuple[pd.Series, pd.Series, pd.DataFrame]:
    """
    Full pipeline: add indicators → compile entry/exit rules.

    Returns:
        entry_signal : boolean Series (signal fires on candle T, trade opens at T+1)
        exit_signal  : boolean Series (same convention)
        enriched_df  : df with all indicator columns added
    """
    enriched = add_indicators(df, strategy.indicators)

    entry_signal = compile_rule(enriched, strategy.entry_rule)

    if strategy.exit_rule and strategy.exit_rule.conditions:
        exit_signal = compile_rule(enriched, strategy.exit_rule)
    else:
        exit_signal = pd.Series(False, index=enriched.index)

    return entry_signal, exit_signal, enriched
