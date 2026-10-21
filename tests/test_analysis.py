"""Разбор раунда: сигналы без заглядывания вперёд, проверка исходов и тексты выводов."""

import json

import numpy as np
import pandas as pd
import pytest

from tests.test_rounds import NO_EVENTS, START, events_frame, spec_for, synthetic_series
from trainer import analysis as A
from trainer.analysis import MOVE
from trainer.dataset import available_series
from trainer.modes import MODES
from trainer.rounds import F, H, build_round, generate_round
from trainer.scoring import DOWN, FLAT, UP

PRICES = ["open", "high", "low", "close"]


def drifting_series(drift: float, noise: float, seed: int = 3) -> pd.DataFrame:
    """Ряд с ровным трендом: drift — средний лог-прирост за свечу."""
    df = synthetic_series(seed)
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(drift + rng.normal(0, noise, len(df))))
    open_ = np.r_[close[0], close[:-1]]
    df["open"], df["close"] = open_, close
    df["high"] = np.maximum(open_, close) * 1.002
    df["low"] = np.minimum(open_, close) * 0.998
    return df


# ─── Нет заглядывания вперёд ──────────────────────────────────────────────────

def test_signals_do_not_depend_on_future():
    df = synthetic_series()
    spec = spec_for(df)
    before = A.signals(build_round(spec, df, NO_EVENTS))

    tampered = df.copy()
    fut = slice(START + H, START + H + F)
    for col in PRICES:
        tampered.iloc[fut, tampered.columns.get_loc(col)] *= 1.7
    tampered.iloc[fut, tampered.columns.get_loc("volume")] *= 9
    after = A.signals(build_round(spec, tampered, NO_EVENTS))

    assert json.dumps(before, sort_keys=True) == json.dumps(after, sort_keys=True)


# ─── Отдельные сигналы ────────────────────────────────────────────────────────

def test_steady_uptrend_reads_as_trend_and_breakout_up():
    df = drifting_series(0.004, noise=0.001)
    sig = {s["id"]: s for s in A.signals(build_round(spec_for(df), df, NO_EVENTS))}
    assert sig["trend"]["vote"] == UP
    assert sig["levels"]["vote"] == UP
    assert sig["rsi"]["vote"] == DOWN and sig["rsi"]["extreme"]   # перекупленность


def test_steady_downtrend_reads_as_trend_down():
    df = drifting_series(-0.004, noise=0.001)
    sig = {s["id"]: s for s in A.signals(build_round(spec_for(df), df, NO_EVENTS))}
    assert sig["trend"]["vote"] == DOWN
    assert sig["levels"]["vote"] == DOWN


@pytest.mark.parametrize("value, vote", [(75, DOWN), (25, UP), (60, UP), (40, DOWN), (50, None)])
def test_rsi_zones(value, vote):
    assert A.rsi_signal(np.array([50.0, value]))["vote"] == vote


def test_bollinger_squeeze_votes_for_a_move():
    n = 100
    mid = np.full(n, 100.0)
    width = np.r_[np.full(n - 1, 4.0), 1.0]          # на последней свече коридор резко сузился
    s = A.bollinger_signal(mid.copy(), mid + width, mid, mid - width)
    assert s["vote"] == MOVE and s["squeeze"]


def test_bollinger_upper_band_votes_down():
    n = 100
    mid = np.full(n, 100.0)
    close = np.full(n, 101.9)
    s = A.bollinger_signal(close, mid + 2, mid, mid - 2)
    assert s["vote"] == DOWN and s["extreme"]


def test_volume_spike_confirms_the_move():
    close = np.r_[np.full(95, 100.0), np.linspace(100.5, 104, 5)]
    volume = np.r_[np.full(95, 100.0), np.full(5, 300.0)]
    s = A.volume_signal(close, volume, atr=1.0)
    assert s["vote"] == UP
    assert "3.0×" in s["value"]


def test_worked_and_consensus():
    assert A.worked(MOVE, FLAT) is False
    assert A.worked(MOVE, DOWN) is True
    assert A.worked(None, UP) is None
    assert A.worked(UP, UP) is True

    c = A.consensus([{"vote": UP}, {"vote": UP}, {"vote": DOWN}, {"vote": None}], DOWN)
    assert c["lean"] == UP and c["matched"] is False
    assert (c["up"], c["down"], c["neutral"]) == (2, 1, 1)
    assert A.consensus([{"vote": UP}, {"vote": DOWN}], UP)["lean"] is None


# ─── Что случилось в будущем ──────────────────────────────────────────────────

def test_cbr_shock_in_future_becomes_the_headline():
    df = drifting_series(0.0, noise=0.002)                 # спокойный рынок…
    p = START + H + 5                                       # …и обвал на 6-й свече будущего
    for col in PRICES:
        df.iloc[p:, df.columns.get_loc(col)] *= 0.92
    events = events_frame([[df.index[p].strftime("%Y-%m-%d"), "ALL", "cbr_meeting",
                            "ЦБ повысил ключевую ставку до 20%", 1]])
    rd = build_round(spec_for(df), df, events)

    st = A.story(rd)
    ev = [i for i in st["items"] if i["tone"] == "event"]
    assert ev and ev[0]["bar"] == 6 and ev[0]["text"].startswith("ЦБ повысил ключевую ставку до 20%.")

    sigs = A.signals(rd)
    title, why = A.explain(sigs, st, A.consensus(sigs, st["actual"]))
    assert st["actual"] == DOWN
    assert title == "Почему цена пошла вниз"
    assert "совпало с событием на свече +6" in why


def test_timeline_ends_with_total_and_skips_extreme_on_last_bar():
    df = drifting_series(0.004, noise=0.001)               # растёт до самой последней свечи
    items = A.story(build_round(spec_for(df), df, NO_EVENTS))["items"]
    assert items[-1].get("final") and items[-1]["bar"] == F
    assert [i["bar"] for i in items] == sorted(i["bar"] for i in items)
    assert not any("Самая высокая точка" in i["text"] for i in items)


def test_flat_round_explains_the_corridor():
    st = {"actual": FLAT, "change_atr": 0.4, "events": [], "big": None, "breakout": None}
    title, why = A.explain([], st, {"lean": None})
    assert title == "Почему цена осталась в коридоре"
    assert "спорили" in why


# ─── Выводы для игрока ────────────────────────────────────────────────────────

def test_quick_lessons_flag_overconfidence_and_missed_flat():
    lessons = A.quick_lessons({"choice": UP, "confidence": 90}, {"correct": False, "points": -224},
                              {"lean": None}, [], FLAT)
    assert any("Уверенность 90%" in x for x in lessons)
    assert any("Боковик" in x for x in lessons)
    assert len(lessons) <= 3


def _trade_round():
    df = synthetic_series()
    rd = build_round(spec_for(df), df, NO_EVENTS)
    e, a = rd.last_close, rd.atr
    fut = rd.candles.index[H:]
    rd.candles.loc[fut, PRICES] = [e, e + 0.1 * a, e - 0.1 * a, e]   # спокойное будущее
    return rd, e, a, fut


def test_trade_lesson_when_stop_hit_and_then_take_reached():
    rd, e, a, fut = _trade_round()
    rd.candles.loc[fut[0], "low"] = e - 0.6 * a            # выбило стоп…
    rd.candles.loc[fut[5:], "high"] = e + 1.5 * a          # …а потом цена ушла к тейку
    answer = {"direction": "long", "entry": e, "stop": e - 0.5 * a, "take": e + a}
    outcome = MODES["trade"].evaluate(rd, answer)
    assert outcome["reason"] == "stop"
    lessons = A.trade_lessons(rd, answer, outcome, {"lean": None})
    assert any("потом цена дошла до тейка" in x for x in lessons)


def test_trade_lesson_when_take_hit():
    rd, e, a, fut = _trade_round()
    rd.candles.loc[fut[5:], "high"] = e + 1.5 * a
    answer = {"direction": "long", "entry": e, "stop": e - a, "take": e + a}
    outcome = MODES["trade"].evaluate(rd, answer)
    assert outcome["reason"] == "take"
    lessons = A.trade_lessons(rd, answer, outcome, {"lean": DOWN})
    assert lessons[0].startswith("Ты зашёл в лонг, хотя перевес сигналов был за падение")
    assert any("Тейк сработал на свече +6" in x for x in lessons)


# ─── Целиком на настоящих данных ──────────────────────────────────────────────

@pytest.mark.skipif(not available_series(), reason="нет данных Мосбиржи — запусти scripts/fetch_moex.py")
def test_review_is_complete_and_json_ready_on_real_rounds():
    for seed in range(12):
        rd = build_round(generate_round(seed=seed))
        e, a = rd.last_close, rd.atr
        cases = [
            ("quick", {"choice": [UP, FLAT, DOWN][seed % 3], "confidence": 70}),
            ("trade", {"direction": "short", "entry": round(e, 4), "stop": e + a, "take": e - 2 * a}),
        ]
        for mode, answer in cases:
            outcome = MODES[mode].evaluate(rd, answer)
            rv = A.review(rd, mode, answer, outcome)
            json.dumps(rv)                                   # уходит в браузер как JSON
            assert rv["title"] and rv["why"] and rv["lessons"]
            assert len(rv["signals"]) == 6
            assert rv["timeline"][-1]["final"]
            assert all(s["worked"] in (True, False, None) for s in rv["signals"])
