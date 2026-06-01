import pytest
from strategy.models import Condition, Rule, IndicatorConfig
from strategy.validator import validate, estimate_candle_count, ValidationIssue


def make_rule(conditions=None, logic="AND"):
    return Rule(conditions or [], logic=logic)


def ind(name, **params):
    return IndicatorConfig(name, params)


# ── estimate_candle_count ──────────────────────────────────────────────────────

def test_estimate_candles_1d():
    n = estimate_candle_count("2024-01-01", "2024-04-01", "1d")
    assert 89 <= n <= 92  # ~91 days


def test_estimate_candles_1h():
    n = estimate_candle_count("2024-01-01", "2024-01-08", "1h")
    assert n == 7 * 24


def test_estimate_candles_zero_for_same_day():
    n = estimate_candle_count("2024-01-01", "2024-01-01", "1h")
    assert n == 0


# ── Date validation ────────────────────────────────────────────────────────────

def test_end_before_start_is_error():
    issues = validate(
        [ind("RSI", period=14)],
        make_rule([Condition("RSI_14", "<", 30)]),
        None,
        "2024-06-01", "2024-01-01", "1h",
    )
    errors = [i for i in issues if i.level == "error"]
    assert any("позже" in e.message for e in errors)


def test_equal_dates_is_error():
    issues = validate(
        [ind("RSI", period=14)],
        make_rule([Condition("RSI_14", "<", 30)]),
        None,
        "2024-01-01", "2024-01-01", "1h",
    )
    errors = [i for i in issues if i.level == "error"]
    assert errors


def test_short_period_is_warning():
    issues = validate(
        [ind("RSI", period=14)],
        make_rule([Condition("RSI_14", "<", 30)]),
        None,
        "2024-01-01", "2024-01-05", "1h",
    )
    warnings = [i for i in issues if i.level == "warning"]
    assert any("7 дней" in w.message for w in warnings)


# ── Column existence checks ────────────────────────────────────────────────────

def test_missing_indicator_column_is_error():
    # Added RSI(14) but condition uses RSI_7 — mismatch
    issues = validate(
        [ind("RSI", period=14)],
        make_rule([Condition("RSI_7", "<", 30)]),
        None,
        "2024-01-01", "2024-12-31", "1h",
    )
    errors = [i for i in issues if i.level == "error"]
    assert any("RSI_7" in e.message for e in errors)


def test_correct_column_no_error():
    issues = validate(
        [ind("RSI", period=14), ind("EMA", period=200)],
        make_rule([
            Condition("RSI_14", "<", 30),
            Condition("close",  ">", "EMA_200"),
        ]),
        None,
        "2024-01-01", "2024-12-31", "1h",
    )
    errors = [i for i in issues if i.level == "error"]
    assert not errors


def test_missing_right_side_column_is_error():
    # Condition: close > EMA_200, but EMA(200) not added
    issues = validate(
        [ind("RSI", period=14)],
        make_rule([Condition("close", ">", "EMA_200")]),
        None,
        "2024-01-01", "2024-12-31", "1h",
    )
    errors = [i for i in issues if i.level == "error"]
    assert any("EMA_200" in e.message for e in errors)


def test_ohlcv_columns_always_available():
    for col in ["open", "high", "low", "close", "volume"]:
        issues = validate(
            [ind("RSI", period=14)],
            make_rule([Condition(col, ">", 0)]),
            None,
            "2024-01-01", "2024-12-31", "1h",
        )
        errors = [i for i in issues if i.level == "error" and col in i.message]
        assert not errors, f"OHLCV column '{col}' incorrectly flagged as missing"


def test_exit_rule_column_also_checked():
    issues = validate(
        [ind("RSI", period=14)],
        make_rule([Condition("RSI_14", "<", 30)]),
        make_rule([Condition("RSI_21", ">", 70)]),   # wrong period
        "2024-01-01", "2024-12-31", "1h",
    )
    errors = [i for i in issues if i.level == "error"]
    assert any("RSI_21" in e.message for e in errors)


# ── Warmup warning ─────────────────────────────────────────────────────────────

def test_ema500_on_short_period_is_warning():
    # EMA(500) on 60 days 1h = ~1440 candles, min needed = 500*3 = 1500
    issues = validate(
        [ind("EMA", period=500)],
        make_rule([Condition("EMA_500", "<", 50000)]),
        None,
        "2024-01-01", "2024-03-01", "1h",  # ~60 days → ~1440 candles
    )
    warnings = [i for i in issues if i.level == "warning"]
    assert any("EMA" in w.message or "500" in w.message for w in warnings)


# ── No exit warning ────────────────────────────────────────────────────────────

def test_no_exit_rule_is_warning():
    issues = validate(
        [ind("RSI", period=14)],
        make_rule([Condition("RSI_14", "<", 30)]),
        None,
        "2024-01-01", "2024-12-31", "1h",
    )
    warnings = [i for i in issues if i.level == "warning"]
    assert any("выход" in w.message.lower() for w in warnings)


def test_with_exit_rule_no_exit_warning():
    issues = validate(
        [ind("RSI", period=14)],
        make_rule([Condition("RSI_14", "<", 30)]),
        make_rule([Condition("RSI_14", ">", 70)]),
        "2024-01-01", "2024-12-31", "1h",
    )
    warnings = [i for i in issues if i.level == "warning"
                and "выход" in i.message.lower()]
    assert not warnings
