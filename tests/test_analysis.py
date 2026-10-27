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


@pytest.mark.parametrize("value, vote", [
    (75, DOWN), (25, UP), (60, UP), (40, DOWN), (50, None),
    (45, None), (55, None),          # 40–60 — без сигнала: 43 и 45 не должны давать разные выводы
    (69, UP), (31, DOWN),
])
def test_rsi_zones(value, vote):
    assert A.rsi_signal(np.array([50.0, value]))["vote"] == vote


@pytest.mark.parametrize("value, phrase", [(69, "рукой подать"), (66, "рукой подать"), (62, "ещё есть запас"),
                                           (31, "рукой подать"), (38, "ещё есть запас")])
def test_rsi_near_extreme_is_not_called_far(value, phrase):
    # Находка тестировщика: «RSI 69 — до перегрева далеко» при границе 70.
    reading = A.rsi_signal(np.array([50.0, value]))["reading"]
    assert phrase in reading and "далеко" not in reading


def test_bollinger_squeeze_votes_for_a_move_without_direction():
    n = 100
    mid = np.full(n, 100.0)
    width = np.r_[np.full(n - 1, 4.0), 1.0]          # на последней свече коридор резко сузился
    s = A.bollinger_signal(mid.copy(), mid + width, mid, mid - width)
    assert s["vote"] == MOVE and s["squeeze"]
    assert "не подсказывает" in s["reading"]


@pytest.mark.parametrize("pos, phrase", [(0.85, "верхней части"), (0.5, "около средней"),
                                         (0.15, "нижней части")])
def test_bollinger_position_wording(pos, phrase):
    # Находка тестировщика: 85% высоты коридора называлось «серединой».
    n = 100
    mid = np.full(n, 100.0)
    half = np.linspace(2.0, 4.0, n)                  # коридор расширяется — сжатия нет
    close = np.full(n, 100.0 - 4.0 + pos * 8.0)     # последняя свеча на pos высоты коридора
    s = A.bollinger_signal(close, mid + half, mid, mid - half)
    assert s["value"].startswith(f"{pos * 100:.0f}%")
    assert s["vote"] is None and not s["squeeze"] and phrase in s["reading"]


def test_bollinger_upper_band_votes_down():
    n = 100
    mid = np.full(n, 100.0)
    close = np.full(n, 101.9)
    s = A.bollinger_signal(close, mid + 2, mid, mid - 2)
    assert s["vote"] == DOWN and s["extreme"]


def _levels(close_last: float):
    """Окно: диапазон 80–100 (20 ATR при ATR = 1), последняя цена — close_last."""
    n = 100
    close = np.r_[np.linspace(85, 95, n - 1), close_last]
    high, low = close + 0.3, close - 0.3
    high[10], low[20] = 100.0, 80.0
    return A.levels_signal(close, high, low, atr=1.0)


def test_levels_upper_part_names_the_resistance():
    # Находка тестировщика: при 93% диапазона писалось «в середине, до уровней далеко».
    s = _levels(98.6)
    assert s["value"].startswith("93%")
    assert "верхней части" in s["reading"] and "1.4 ATR" in s["reading"]
    assert "середине" not in s["reading"] and "далеко" not in s["reading"]


def test_levels_middle_gives_both_distances():
    s = _levels(90.0)
    assert "середине" in s["reading"] and "до максимума 10.0 ATR" in s["reading"]


def test_levels_near_high_is_resistance():
    s = _levels(99.5)
    assert "сопротивление" in s["reading"] and "0.5 ATR" in s["reading"]


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


def test_small_event_reaction_is_not_the_headline():
    # Падение на 25%, из них на реакцию после заседания ЦБ — меньше трети: событие не «главное».
    st = {"actual": DOWN, "change_atr": -12.0, "big": None, "breakout": None,
          "events": [{"type": "cbr_meeting", "atr": -3.0, "bar": 11, "title": "ЦБ снизил ставку",
                      "pct": -7.7, "n": 3}]}
    title, why = A.explain([], st, {"lean": None})
    assert title == "Почему цена пошла вниз" and "совпало с событием" not in why


def test_timeline_ends_with_total_and_skips_extreme_on_last_bar():
    df = drifting_series(0.004, noise=0.001)               # растёт до самой последней свечи
    items = A.story(build_round(spec_for(df), df, NO_EVENTS))["items"]
    assert items[-1].get("final") and items[-1]["bar"] == F
    assert [i["bar"] for i in items] == sorted(i["bar"] for i in items)
    assert not any("Самая высокая точка" in i["text"] for i in items)


def test_flat_round_explains_the_corridor():
    st = {"actual": FLAT, "change_atr": 0.4, "events": [], "big": None, "breakout": None,
          "max_up_atr": 0.9, "max_dn_atr": 0.7}
    title, why = A.explain([], st, {"lean": None})
    assert title == "Почему цена осталась в коридоре"
    assert "спорили" in why


def test_flat_round_that_left_the_corridor_says_so():
    # Находка тестировщика: «осталась в коридоре», хотя по пути цена выходила за обе границы.
    st = {"actual": FLAT, "change_atr": -0.0, "events": [], "big": None, "breakout": None,
          "max_up_atr": 1.6, "max_dn_atr": 1.9}
    title, why = A.explain([], st, {"lean": None})
    assert title == "Почему в итоге боковик"
    assert "вверх до +1.6 ATR" in why and "вниз до −1.9 ATR" in why
    assert "по закрытию последней свечи" in why
    assert "не дожали" not in why and "осталась" not in title


def test_squeeze_explanation_does_not_claim_a_direction():
    bb = {"id": "bb", "vote": MOVE, "squeeze": True, "extreme": False}
    st = {"actual": DOWN, "change_atr": -2.5, "events": [], "big": None, "breakout": None}
    title, why = A.explain([bb], st, {"lean": None})
    assert title == "Почему цена пошла вниз"
    assert "сжатие не подсказывало" in why


# ─── Выводы для игрока ────────────────────────────────────────────────────────

def test_quick_lessons_flag_overconfidence_and_missed_flat():
    lessons = A.quick_lessons({"choice": UP, "confidence": 90}, {"correct": False, "points": -224},
                              {"lean": None}, [], FLAT)
    assert any("Уверенность 90%" in x for x in lessons)
    assert any("Боковик" in x for x in lessons)
    assert len(lessons) <= 3


def test_move_signal_is_not_listed_as_a_direction_hint():
    # Находка тестировщика: «движение вниз подсказывали: MACD, Боллинджер», хотя сжатие
    # Боллинджера говорит только «будет сильное движение».
    sigs = [{"title": "MACD · 12/26/9", "vote": DOWN}, {"title": "Боллинджер", "vote": MOVE}]
    lessons = A.quick_lessons({"choice": FLAT, "confidence": 60}, {"correct": False, "points": -44},
                              {"lean": None}, sigs, DOWN)
    hint = next(x for x in lessons if x.startswith("Ты ждал боковика"))
    assert "движение вниз подсказывали: MACD;" in hint
    assert "без направления" in hint and hint.endswith("Боллинджер.")


def test_only_move_signals_still_warn_against_flat():
    sigs = [{"title": "Боллинджер", "vote": MOVE}]
    lessons = A.quick_lessons({"choice": FLAT, "confidence": 60}, {"correct": False, "points": -44},
                              {"lean": None}, sigs, UP)
    hint = next(x for x in lessons if x.startswith("Ты ждал боковика"))
    assert "подсказывали" not in hint and "без направления" in hint


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


def test_trade_lesson_flags_stop_inside_the_noise():
    rd, e, a, fut = _trade_round()
    rd.candles.loc[fut[1], "low"] = e - 0.6 * a             # тихое будущее, но стоп в 0.5 ATR выбило
    answer = {"direction": "long", "entry": e, "stop": e - 0.5 * a, "take": e + 3 * a}
    outcome = MODES["trade"].evaluate(rd, answer)
    assert outcome["reason"] == "stop"
    noise = A.typical_pullback(rd, long=True)
    assert noise is not None and noise > 0.5 / 0.8           # видимая часть шумнее, чем стоп
    lessons = A.trade_lessons(rd, answer, outcome, {"lean": None})
    assert any("в половине случаев" in x and "шум" in x for x in lessons)


def test_trade_lesson_never_gives_hindsight_breakeven_rule():
    # Находка тестировщика: «перенос стопа в безубыток спас бы сделку» — правило по одной сделке.
    rd, e, a, fut = _trade_round()
    rd.candles.loc[fut[2], "high"] = e + 4 * a              # сначала +2R…
    rd.candles.loc[fut[4], "low"] = e - 2.2 * a             # …потом стоп
    answer = {"direction": "long", "entry": e, "stop": e - 2 * a, "take": e + 5 * a}
    outcome = MODES["trade"].evaluate(rd, answer)
    assert outcome["reason"] == "stop"
    lessons = A.trade_lessons(rd, answer, outcome, {"lean": None})
    assert not any("спас бы" in x for x in lessons)


def test_typical_move_sees_the_trend():
    # В ровном росте цена в сторону лонга уходит дальше, чем против него; у шорта — наоборот.
    df = drifting_series(0.004, noise=0.001)
    rd = build_round(spec_for(df), df, NO_EVENTS)
    assert A.typical_move(rd, long=True, against=False) > A.typical_move(rd, long=True, against=True)
    assert A.typical_move(rd, long=False, against=True) == pytest.approx(A.typical_move(rd, long=True, against=False))


def test_far_take_lesson_uses_the_typical_move():
    rd, e, a, fut = _trade_round()                          # спокойное будущее — закрытие по времени
    run = A.typical_move(rd, long=True, against=False)
    answer = {"direction": "long", "entry": e, "stop": e - 2 * a, "take": e + (1.6 * run + 0.5) * a}
    outcome = MODES["trade"].evaluate(rd, answer)
    assert outcome["reason"] == "close"
    lessons = A.trade_lessons(rd, answer, outcome, {"lean": None})
    assert any("далеко" in x and "в половине случаев" in x for x in lessons)


def test_typical_pullback_uses_only_the_visible_part():
    rd, e, a, fut = _trade_round()
    before = A.typical_pullback(rd, long=True)
    rd.candles.loc[fut, "low"] = e - 10 * a                 # будущее не должно влиять
    assert A.typical_pullback(rd, long=True) == before


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


@pytest.mark.skipif(not available_series(), reason="нет данных Мосбиржи — запусти scripts/fetch_moex.py")
def test_signal_wording_matches_the_numbers_on_real_rounds():
    """Подпись карточки не спорит с цифрой рядом (все находки тестировщика разом)."""
    for seed in range(80):
        rd = build_round(generate_round(seed=seed))
        sig = {s["id"]: s for s in A.signals(rd)}
        bb, lv, rsi, tr = sig.get("bb"), sig.get("levels"), sig.get("rsi"), sig.get("trend")
        if tr and tr["vote"] is None:
            to_fast, to_slow = (float(x.split("%")[0].replace("−", "-")) for x in tr["value"].split(" · "))
            if min(abs(to_fast), abs(to_slow)) < 0.1:
                pass                                          # округление до 0.0% прячет знак
            elif to_fast > 0 and to_slow > 0:
                assert "выше обеих средних" in tr["reading"], (seed, tr)
            elif to_fast < 0 and to_slow < 0:
                assert "ниже обеих средних" in tr["reading"], (seed, tr)
            else:
                assert "между" in tr["reading"], (seed, tr)
        if bb:
            pos = int(bb["value"].split("%")[0])
            if pos > 65 or pos < 35:
                assert "около средней" not in bb["reading"], (seed, bb)
        if lv and lv["vote"] is None:
            pos = int(lv["value"].split("%")[0])
            if pos >= 75 or pos <= 25:
                assert "середине" not in lv["reading"], (seed, lv)
        if rsi and rsi["level"] >= 65 or rsi and rsi["level"] <= 35:
            assert "далеко" not in rsi["reading"], (seed, rsi)
        rv = A.review(rd, "trade", *_short_trade(rd))
        assert not any("спас бы" in x for x in rv["lessons"])


def _short_trade(rd):
    e, a = rd.last_close, rd.atr
    answer = {"direction": "short", "entry": round(e, 4), "stop": e + a, "take": e - 2 * a}
    return answer, MODES["trade"].evaluate(rd, answer)
