"""Подготовка данных: дыры в торгах, дни дивидендного гэпа, допустимые окна, события."""

import numpy as np
import pandas as pd
import pytest

from trainer.dataset import (
    dividend_column,
    ex_dividend_date,
    load_events,
    mark_gaps,
    valid_window_starts,
)


def calendar(start: str, end: str, drop=(), add=()) -> pd.DatetimeIndex:
    """Будни за период минус нерабочие дни плюс торговые выходные."""
    days = set(pd.bdate_range(start, end)) - {pd.Timestamp(d) for d in drop}
    days |= {pd.Timestamp(d) for d in add}
    return pd.DatetimeIndex(sorted(days))


# ─── Дыры ─────────────────────────────────────────────────────────────────────

def test_new_year_holidays_are_not_a_gap():
    idx = pd.DatetimeIndex(["2015-12-29", "2015-12-30", "2016-01-11", "2016-01-12"])  # 12 дней
    assert not mark_gaps(idx, min_days=14).any()


def test_trading_suspension_is_a_gap():
    idx = pd.DatetimeIndex(["2022-02-24", "2022-02-25", "2022-03-24", "2022-03-25"])  # 27 дней
    assert mark_gaps(idx, min_days=14).tolist() == [False, False, True, False]


def test_hourly_night_and_weekend_breaks_are_not_gaps():
    idx = pd.DatetimeIndex(["2024-03-01 18:00", "2024-03-04 10:00", "2024-03-04 11:00"])
    assert not mark_gaps(idx, min_days=14).any()


def test_mark_gaps_empty_index():
    assert mark_gaps(pd.DatetimeIndex([])).size == 0


# ─── Окна ─────────────────────────────────────────────────────────────────────

def test_windows_crossing_a_gap_are_excluded():
    gap_before = np.zeros(12, dtype=bool)
    gap_before[5] = True
    starts = valid_window_starts(gap_before, length=4)
    # Окна 2,3,4 содержат свечу 5 не первой — через дыру. Окно 5 начинается после неё.
    assert starts.tolist() == [0, 1, 5, 6, 7, 8]


def test_no_windows_when_series_is_too_short():
    assert valid_window_starts(np.zeros(3, dtype=bool), length=4).size == 0


def test_every_valid_window_is_gap_free():
    rng = np.random.default_rng(0)
    gap_before = rng.random(500) < 0.02
    for s in valid_window_starts(gap_before, length=120):
        assert not gap_before[s + 1:s + 120].any()


# ─── Дивидендный гэп ──────────────────────────────────────────────────────────

def test_ex_date_t2_with_holiday_before_registry():
    # SBER 2019: реестр 13.06 (чт), 12.06 — праздник. T+2: купить надо было
    # до 10.06 включительно, гэп — 11.06.
    days = calendar("2019-06-01", "2019-06-30", drop=["2019-06-12"])
    assert ex_dividend_date(pd.Timestamp("2019-06-13"), days) == pd.Timestamp("2019-06-11")


def test_ex_date_t1():
    # SBER 2024: реестр 11.07 (чт), T+1 — гэп в сам день реестра.
    days = calendar("2024-07-01", "2024-07-31")
    assert ex_dividend_date(pd.Timestamp("2024-07-11"), days) == pd.Timestamp("2024-07-11")


def test_ex_date_t2_right_before_t1_switch():
    # Пятница 28.07.2023 ещё T+2 → расчёты во вторник 01.08, позже реестра 31.07.
    days = calendar("2023-07-17", "2023-08-11")
    assert ex_dividend_date(pd.Timestamp("2023-07-31"), days) == pd.Timestamp("2023-07-28")


def test_ex_date_on_weekend_session():
    # YDEX 2026: реестр в понедельник 27.04. Сделка субботы 25.04 рассчитывается
    # как сделка понедельника → во вторник → уже без дивиденда. Гэп — в субботу.
    days = calendar("2026-04-13", "2026-05-08", add=["2026-04-25", "2026-04-26"])
    assert ex_dividend_date(pd.Timestamp("2026-04-27"), days) == pd.Timestamp("2026-04-25")


def test_ex_date_on_holiday_session():
    # LKOH 2026: реестр в понедельник 04.05. 1 мая (пятница) биржа торговала,
    # но расчётов не было — это как выходной. Реальный гэп был 01.05.
    days = calendar("2026-04-20", "2026-05-15", add=["2026-05-02", "2026-05-03"])
    assert pd.Timestamp("2026-05-01") in days
    assert ex_dividend_date(pd.Timestamp("2026-05-04"), days) == pd.Timestamp("2026-05-01")


def test_ex_date_january_before_holiday_sessions():
    # MGNT 2021: реестр 08.01, биржа работала 4–6 января и расчёты шли (до 2025
    # праздничных сессий без расчётов не было). Реальный гэп — 06.01.
    days = calendar("2020-12-21", "2021-01-29", drop=["2021-01-01", "2021-01-07"])
    assert ex_dividend_date(pd.Timestamp("2021-01-08"), days) == pd.Timestamp("2021-01-06")


def test_ex_date_outside_calendar_is_none():
    days = calendar("2015-01-05", "2015-12-31")
    assert ex_dividend_date(pd.Timestamp("2014-06-17"), days) is None
    assert ex_dividend_date(pd.Timestamp("2016-06-17"), days) is None


def test_dividend_lands_on_first_hourly_candle_of_gap_day():
    daily = calendar("2024-07-01", "2024-07-31")
    hourly = pd.DatetimeIndex([
        "2024-07-10 18:00", "2024-07-10 19:00",
        "2024-07-11 07:00", "2024-07-11 10:00", "2024-07-11 11:00",
    ])
    divs = pd.DataFrame({"ticker": ["SBER"], "registry_date": [pd.Timestamp("2024-07-11")], "value": [33.3]})
    col = dividend_column(hourly, divs, daily)
    assert col.tolist() == [0, 0, 33.3, 0, 0]


# ─── События ──────────────────────────────────────────────────────────────────

def test_load_events(tmp_path):
    p = tmp_path / "events.csv"
    p.write_text(
        "date,ticker,type,title\n"
        "# комментарий\n"
        "2024-07-26,ALL,cbr_meeting,Заседание ЦБ\n"
        "2024-08-01,sber,earnings,МСФО за 6 мес.\n",
        encoding="utf-8",
    )
    ev = load_events(p)
    assert len(ev) == 2
    assert ev.loc[1, "ticker"] == "SBER"
    assert ev.loc[0, "date"] == pd.Timestamp("2024-07-26")
    assert ev["scheduled"].all()  # без колонки — всё считается плановым


def test_load_events_scheduled_flag(tmp_path):
    p = tmp_path / "events.csv"
    p.write_text(
        "date,ticker,type,title,scheduled\n"
        "2022-02-28,ALL,cbr_meeting,Внеплановое заседание,0\n"
        "2022-03-18,ALL,cbr_meeting,Плановое заседание,1\n"
        "2022-04-29,ALL,cbr_meeting,Плановое заседание,\n",
        encoding="utf-8",
    )
    assert load_events(p)["scheduled"].tolist() == [False, True, True]


def test_repository_events_file_is_valid():
    ev = load_events()
    assert len(ev) > 0
    assert (ev["type"] == "cbr_meeting").any()


def test_load_events_rejects_unknown_type(tmp_path):
    p = tmp_path / "events.csv"
    p.write_text("date,ticker,type,title\n2024-07-26,ALL,party,Корпоратив\n", encoding="utf-8")
    with pytest.raises(ValueError, match="неизвестные типы"):
        load_events(p)


def test_missing_events_file_is_empty(tmp_path):
    assert load_events(tmp_path / "nope.csv").empty
