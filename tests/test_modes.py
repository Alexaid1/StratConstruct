"""Режимы: проверка ответа, исход, очки, серии и сериализация в JSON."""

import json

import numpy as np
import pandas as pd
import pytest

from trainer.modes import MODES, AnswerError
from trainer.rounds import H, build_round, predict_payload, reveal_payload
from tests.test_rounds import NO_EVENTS, spec_for, synthetic_series


@pytest.fixture
def rd():
    df = synthetic_series()
    return build_round(spec_for(df), df, NO_EVENTS)


def test_quick_rejects_bad_answers(rd):
    quick = MODES["quick"]
    with pytest.raises(AnswerError):
        quick.parse_answer({"choice": "sideways", "confidence": 70}, rd)
    with pytest.raises(AnswerError):
        quick.parse_answer({"choice": "up", "confidence": 30}, rd)
    with pytest.raises(AnswerError):
        quick.parse_answer({"choice": "up", "confidence": "много"}, rd)
    assert quick.parse_answer({"choice": "up", "confidence": 35}, rd)["confidence"] == 35


def test_quick_points_follow_three_outcome_brier(rd):
    quick = MODES["quick"]
    actual = quick.evaluate(rd, {"choice": "up", "confidence": 50})["actual"]
    hit = quick.evaluate(rd, {"choice": actual, "confidence": 100})
    assert hit["correct"] and hit["points"] == 100 and hit["brier"] == 0
    wrong = next(c for c in ("up", "flat", "down") if c != actual)
    miss = quick.evaluate(rd, {"choice": wrong, "confidence": 100})
    assert not miss["correct"] and miss["points"] == -200 and miss["brier"] == 2
    # Около «наугад» (33%) ставка почти ничего не стоит — ни в плюс, ни в минус.
    for c in (actual, wrong):
        assert abs(quick.evaluate(rd, {"choice": c, "confidence": 35})["points"]) <= 5


def test_three_outcome_brier_is_proper():
    # Выгоднее всего называть ту уверенность, которая совпадает с настоящей частотой попаданий.
    from trainer.scoring import quick_brier

    for true_p in (0.4, 0.6, 0.8):
        expected = {c: true_p * quick_brier(c, True) + (1 - true_p) * quick_brier(c, False)
                    for c in range(35, 101, 5)}
        best = min(expected, key=expected.get)
        assert abs(best / 100 - true_p) <= 0.05, (true_p, best)


def test_trade_validation(rd):
    trade = MODES["trade"]
    e, a = rd.last_close, rd.atr
    with pytest.raises(AnswerError, match="ниже"):
        trade.parse_answer({"direction": "long", "stop": e + a, "take": e + 2 * a}, rd)
    with pytest.raises(AnswerError, match="близко"):
        trade.parse_answer({"direction": "long", "stop": e - 0.05 * a, "take": e + 2 * a}, rd)
    with pytest.raises(AnswerError, match="далеко"):
        trade.parse_answer({"direction": "short", "stop": e + a, "take": e - 40 * a}, rd)
    ok = trade.parse_answer({"direction": "short", "stop": e + a, "take": e - 2 * a}, rd)
    assert ok["entry"] == pytest.approx(e, abs=1e-4)


def test_outcomes_are_json_serializable(rd):
    e, a = rd.last_close, rd.atr
    quick = MODES["quick"].evaluate(rd, {"choice": "up", "confidence": 70})
    trade_ans = MODES["trade"].parse_answer({"direction": "long", "stop": e - a, "take": e + 2 * a}, rd)
    trade = MODES["trade"].evaluate(rd, trade_ans)
    json.dumps({"q": quick, "t": trade, "a": trade_ans})
    json.dumps(predict_payload(rd))
    json.dumps(reveal_payload(rd))
    assert isinstance(trade["win"], bool) and isinstance(quick["correct"], bool)


def test_trade_real_prices_use_scale(rd):
    e, a = rd.last_close, rd.atr
    ans = MODES["trade"].parse_answer({"direction": "long", "stop": e - a, "take": e + 2 * a}, rd)
    out = MODES["trade"].evaluate(rd, ans)
    assert out["entry_real"] == pytest.approx(e * rd.scale, abs=0.01)


def test_summary_streaks():
    def att(win, r=0.0, pts=0):
        return {"outcome": {"win": win, "r": r, "points": pts}}

    s = MODES["quick"].summary([att(True), att(True), att(False), att(True), att(True), att(True)])
    assert (s["streak"], s["best_streak"], s["hits"], s["rounds"]) == (3, 3, 5, 6)
    t = MODES["trade"].summary([att(True, 2.0), att(False, -1.0), att(True, 0.5)])
    assert t["total_r"] == 1.5 and t["win_rate"] == 67 and t["streak"] == 1


def test_empty_summary():
    assert MODES["quick"].summary([])["accuracy"] is None
    assert MODES["trade"].summary([])["avg_r"] is None
