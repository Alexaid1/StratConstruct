from __future__ import annotations
from dataclasses import dataclass, field
from typing import Union, Optional, Literal

OPERATORS = ["<", ">", "<=", ">=", "==", "crosses_above", "crosses_below"]
LOGIC_TYPES = ["AND", "OR"]


@dataclass
class Condition:
    """
    One comparison: <indicator> <operator> <value_or_column>.

    Examples:
        Condition("RSI_14", "<", 30)
        Condition("close", ">", "EMA_200")
        Condition("MACD_12_26_9", "crosses_above", "MACDs_12_26_9")
    """
    indicator: str
    operator: str
    value: Union[float, int, str]  # number → threshold; str → column name in df

    def __post_init__(self):
        if self.operator not in OPERATORS:
            raise ValueError(f"Unknown operator '{self.operator}'. Allowed: {OPERATORS}")


@dataclass
class Rule:
    """
    A group of conditions combined with AND or OR logic.
    An empty rule evaluates to all-False (no signal).
    """
    conditions: list[Condition]
    logic: Literal["AND", "OR"] = "AND"

    def __post_init__(self):
        if self.logic not in LOGIC_TYPES:
            raise ValueError(f"Logic must be 'AND' or 'OR', got '{self.logic}'")


@dataclass
class IndicatorConfig:
    """
    Specifies which indicator to add to the DataFrame and with what params.

    Example:
        IndicatorConfig("RSI", {"period": 14})
        IndicatorConfig("EMA", {"period": 200})
    """
    name: str
    params: dict = field(default_factory=dict)


@dataclass
class Strategy:
    """
    Complete strategy definition: indicators + entry/exit rules + TP/SL.
    Fully serialisable — no live data inside.
    """
    indicators: list[IndicatorConfig]
    entry_rule: Rule
    exit_rule: Optional[Rule] = None
    take_profit_pct: Optional[float] = None
    stop_loss_pct: Optional[float] = None
