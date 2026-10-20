"""Генератор раундов: нормировка, дивиденды, события и отсутствие заглядывания вперёд."""

import json

import numpy as np
import pandas as pd
import pytest

from trainer import config
from trainer.dataset import available_series, load_series
from trainer.rounds import (
    F,
    H,
    W,
    RoundSpec,
    build_round,
    generate_round,
    predict_payload,
    reveal_payload,
)

N = 400


def synthetic_series(seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 250 * np.exp(np.cumsum(rng.normal(0, 0.015, N)))
    open_ = np.r_[close[0], close[:-1]] * (1 + rng.normal(0, 0.003, N))
    high = np.maximum(open_, close) * (1 + rng.random(N) * 0.01)
    low = np.minimum(open_, close) * (1 - rng.random(N) * 0.01)
    idx = pd.bdate_range("2019-01-01", periods=N)
    return pd.DataFrame({
        "open": open_, "high": high, "low": low, "close": close,
        "volume": rng.integers(1_000, 5_000, N).astype(float),
        "value": 0.0, "gap_before": False, "dividend": 0.0,
    }, index=idx)


def events_frame(rows) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=["date", "ticker", "type", "title", "scheduled"])
    df["date"] = pd.to_datetime(df["date"])
    return df


NO_EVENTS = events_frame([])
START = 150  # позиция первой видимой свечи в синтетическом ряду


def spec_for(df: pd.DataFrame, start: int = START) -> RoundSpec:
    return RoundSpec("SBER", "1d", str(df.index[start]), seed=0)


def without_id(payload: dict) -> str:
    return json.dumps({k: v for k, v in payload.items() if k != "round_id"}, sort_keys=True)


# ─── Нет заглядывания вперёд ──────────────────────────────────────────────────

def test_predict_payload_does_not_depend_on_future_prices():
    df = synthetic_series()
    spec = spec_for(df)
    before = predict_payload(build_round(spec, df, NO_EVENTS))

    # Подменяем всё будущее: другие цены и объёмы.
    tampered = df.copy()
    fut = slice(START + H, START + H + F)
    for col in ["open", "high", "low", "close"]:
        tampered.iloc[fut, tampered.columns.get_loc(col)] *= 1.7
    tampered.iloc[fut, tampered.columns.get_loc("volume")] *= 9
    after = predict_payload(build_round(spec, tampered, NO_EVENTS))

    assert without_id(before) == without_id(after)


def test_future_dividend_shows_only_as_neutral_scheduled_event():
    # Дату отсечки объявляют заранее, поэтому метка в зоне будущего допустима,
    # но без суммы — и свечи с индикаторами меняться не должны.
    df = synthetic_series()
    spec = spec_for(df)
    before = predict_payload(build_round(spec, df, NO_EVENTS))
    with_div = df.copy()
    with_div.iloc[START + H + 3, with_div.columns.get_loc("dividend")] = 25.0
    after = predict_payload(build_round(spec, with_div, NO_EVENTS))

    for key in ["candles", "indicators", "last_close", "atr"]:
        assert before[key] == after[key], key
    assert before["events"] == []
    assert after["events"] == [{"bar": H + 3, "type": "dividend_cutoff", "label": "Дивидендная отсечка"}]


def test_predict_payload_has_no_future_candles():
    df = synthetic_series()
    payload = predict_payload(build_round(spec_for(df), df, NO_EVENTS))
    assert len(payload["candles"]) == H
    assert "future" not in payload
    assert all(len(v) == H for v in payload["indicators"].values())


def test_visible_indicators_are_causal():
    # Значения индикаторов на видимых свечах те же, что и в полном расчёте с будущим.
    df = synthetic_series()
    rd = build_round(spec_for(df), df, NO_EVENTS)
    for name, visible in rd.indicators_visible.items():
        np.testing.assert_allclose(visible, rd.indicators_full[name][:H], equal_nan=True, err_msg=name)


def test_warmup_fills_indicators_from_first_visible_bar():
    df = synthetic_series()
    rd = build_round(spec_for(df), df, NO_EVENTS)
    for name in ["ma1", "ma2", "rsi", "macd", "macd_signal", "bb_upper"]:
        assert np.isfinite(rd.indicators_visible[name][0]), name


def test_sideways_threshold_uses_only_visible_atr():
    df = synthetic_series()
    rd1 = build_round(spec_for(df), df, NO_EVENTS)
    tampered = df.copy()
    tampered.iloc[START + H:, tampered.columns.get_loc("high")] *= 1.5
    rd2 = build_round(spec_for(df), tampered, NO_EVENTS)
    assert rd1.atr == pytest.approx(rd2.atr)


# ─── Нормировка и дивиденды ───────────────────────────────────────────────────

def test_first_visible_close_is_100():
    df = synthetic_series()
    rd = build_round(spec_for(df), df, NO_EVENTS)
    assert rd.candles["close"].iloc[0] == pytest.approx(100)
    assert rd.scale * 100 == pytest.approx(df["close"].iloc[START])


def test_dividend_gap_is_removed_and_marked():
    df = synthetic_series()
    p = START + 40
    div = 20.0
    df.iloc[p, df.columns.get_loc("open")] = df["close"].iloc[p - 1] - div   # гэп вниз на дивиденд
    df.iloc[p, df.columns.get_loc("dividend")] = div
    rd = build_round(spec_for(df), df, NO_EVENTS)

    k = p - START
    gap = rd.candles["close"].iloc[k - 1] - rd.candles["open"].iloc[k]
    assert abs(gap) < 1e-6
    ev = [e for e in rd.events if e["type"] == "dividend_cutoff"]
    assert len(ev) == 1 and ev[0]["bar"] == k
    label = [e for e in predict_payload(rd)["events"] if e["type"] == "dividend_cutoff"][0]["label"]
    assert "₽" not in label  # сумма в рублях выдала бы уровень цены


# ─── События ──────────────────────────────────────────────────────────────────

def test_event_visibility_before_and_after_answer():
    df = synthetic_series()
    t = df.index
    ev = events_frame([
        [t[START + 10], "ALL", "cbr_meeting", "ЦБ повысил ключевую ставку до 20% (+10,5 п.п.)", True],
        [t[START + H + 5], "ALL", "cbr_meeting", "ЦБ снизил ключевую ставку до 7% (−1 п.п.)", True],
        [t[START + H + 8], "ALL", "cbr_meeting", "Внеплановое заседание: ЦБ повысил ставку", False],
        [t[START + 20], "LKOH", "earnings", "Чужая отчётность", True],
    ])
    rd = build_round(spec_for(df), df, ev)
    before = predict_payload(rd)["events"]

    assert [e["bar"] for e in before] == [10, H + 5]          # внеплановое и чужое скрыты
    assert before[0]["label"] == "ЦБ повысил ставку"          # прошлое: направление, без цифр
    assert before[1]["label"] == "Заседание ЦБ"               # будущее: только факт заседания
    assert not any("%" in e["label"] for e in before)

    after = reveal_payload(rd)["events"]
    assert [e["bar"] for e in after] == [10, H + 5, H + 8]
    assert "20%" in after[0]["label"]


def test_identity_hidden_by_default():
    df = synthetic_series()
    payload = predict_payload(build_round(spec_for(df), df, NO_EVENTS))
    text = json.dumps(payload, ensure_ascii=False)
    assert payload["identity"] is None and payload["labels"] is None
    assert "SBER" not in text and "2019" not in text


def test_easy_mode_shows_identity_but_not_the_future():
    df = synthetic_series()
    rd = build_round(spec_for(df), df, NO_EVENTS)
    payload = predict_payload(rd, show_identity=True)
    assert payload["identity"]["ticker"] == "SBER"
    assert len(payload["labels"]) == H                         # даты только у видимых свечей
    assert payload["identity"]["period"].endswith("…")         # конец периода не раскрываем
    last_future = rd.times[-1].strftime("%d.%m.%Y")
    assert last_future not in json.dumps(payload, ensure_ascii=False)


def test_reveal_payload_has_everything():
    df = synthetic_series()
    payload = reveal_payload(build_round(spec_for(df), df, NO_EVENTS))
    assert len(payload["candles"]) == H and len(payload["future"]) == F
    assert len(payload["labels"]) == H + F
    assert payload["identity"]["ticker"] == "SBER"


def test_window_outside_data_is_rejected():
    df = synthetic_series()
    with pytest.raises(ValueError):
        build_round(spec_for(df, start=W - 1), df, NO_EVENTS)
    with pytest.raises(ValueError):
        build_round(spec_for(df, start=N - H), df, NO_EVENTS)


# ─── Генератор на реальных данных ─────────────────────────────────────────────

needs_data = pytest.mark.skipif(not available_series(), reason="нет data/moex — запусти scripts/fetch_moex.py")


@needs_data
def test_same_seed_same_round():
    assert generate_round(seed=42) == generate_round(seed=42)


@needs_data
def test_generated_windows_never_cross_trading_gaps():
    for seed in range(300):
        spec = generate_round(seed=seed)
        df = load_series(spec.ticker, spec.timeframe)
        s = df.index.get_loc(pd.Timestamp(spec.start_time))
        window_gaps = df["gap_before"].to_numpy()[s - W + 1:s + H + F]
        assert not window_gaps.any(), spec


@needs_data
def test_filters_are_respected():
    for seed in range(30):
        spec = generate_round(seed=seed, tickers=["YDEX"], timeframes=["1h"])
        assert (spec.ticker, spec.timeframe) == ("YDEX", "1h")


@needs_data
def test_real_round_builds():
    spec = generate_round(seed=7)
    rd = build_round(spec)
    assert len(rd.candles) == H + F
    assert rd.atr > 0
    assert set(config.TICKERS) >= {spec.ticker}
