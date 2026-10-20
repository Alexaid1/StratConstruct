"""Исходы: вверх/вниз/боковик и сделка в R (включая стоп и тейк в одной свече)."""

import numpy as np
import pytest

from trainer.scoring import DOWN, FLAT, UP, classify_move, trade_outcome


# ─── Быстрый режим ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("final, expected", [
    (103.0, UP),       # +3 при пороге 1.2 × 2 = 2.4
    (97.0, DOWN),
    (101.0, FLAT),
    (98.0, FLAT),
    (102.4, UP),       # ровно на пороге — уже движение
])
def test_classify_move(final, expected):
    assert classify_move(100.0, final, atr=2.0, mult=1.2) == expected


# ─── Сделка ───────────────────────────────────────────────────────────────────

def bars(*rows):
    return np.array(rows, dtype=float)  # open, high, low, close


def test_long_take_first():
    res = trade_outcome("long", 100, 98, 104, bars(
        [100, 101, 99, 100.5],
        [100.5, 104.5, 100, 104],
    ))
    assert (res.reason, res.exit_bar, res.exit_price) == ("take", 1, 104)
    assert res.r == pytest.approx(2.0)


def test_long_stop_first():
    res = trade_outcome("long", 100, 98, 104, bars(
        [100, 100.5, 97.5, 98.2],
        [98.2, 105, 98, 104.5],
    ))
    assert res.reason == "stop" and res.exit_bar == 0
    assert res.r == pytest.approx(-1.0)


def test_stop_and_take_in_one_candle_counts_as_stop():
    res = trade_outcome("long", 100, 98, 104, bars([100, 105, 97, 103]))
    assert res.reason == "stop"
    assert res.r == pytest.approx(-1.0)


def test_short_stop_and_take_in_one_candle_counts_as_stop():
    res = trade_outcome("short", 100, 102, 96, bars([100, 103, 95, 97]))
    assert res.reason == "stop"
    assert res.r == pytest.approx(-1.0)


def test_gap_through_stop_fills_at_open():
    res = trade_outcome("long", 100, 98, 104, bars(
        [100, 100.5, 99, 99.5],
        [96, 97, 95, 96.5],        # открылись ниже стопа
    ))
    assert res.reason == "stop" and res.exit_price == 96
    assert res.r == pytest.approx(-2.0)


def test_gap_through_take_fills_at_take():
    res = trade_outcome("long", 100, 98, 104, bars([106, 107, 105, 106]))
    assert res.reason == "take" and res.exit_price == 104
    assert res.r == pytest.approx(2.0)


def test_short_take():
    res = trade_outcome("short", 100, 101, 97, bars([100, 100.5, 96.5, 97]))
    assert res.reason == "take"
    assert res.r == pytest.approx(3.0)


def test_nothing_hit_closes_at_last_close():
    res = trade_outcome("short", 100, 102, 95, bars(
        [100, 101, 99, 99.5],
        [99.5, 100, 98.5, 99],
    ))
    assert (res.reason, res.exit_bar, res.exit_price) == ("close", 1, 99)
    assert res.r == pytest.approx(0.5)


@pytest.mark.parametrize("direction, stop, take", [
    ("long", 101, 104),    # стоп выше входа
    ("long", 98, 99),      # тейк ниже входа
    ("short", 98, 96),     # стоп ниже входа для шорта
    ("sideways", 98, 104),
])
def test_invalid_orders_rejected(direction, stop, take):
    with pytest.raises(ValueError):
        trade_outcome(direction, 100, stop, take, bars([100, 101, 99, 100]))
