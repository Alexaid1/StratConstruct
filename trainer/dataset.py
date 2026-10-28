"""Подготовка котировок к игре: дыры в торгах, дивидендные гэпы, события, окна."""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from trainer import config

EVENT_TYPES = {"cbr_meeting", "earnings", "dividend_cutoff"}
# Дата этих событий известна заранее (исход — нет), поэтому до ответа
# их можно показать даже в зоне «будущего».
SCHEDULED_EVENT_TYPES = {"cbr_meeting", "earnings", "dividend_cutoff"}


# ─── Дыры в торгах ────────────────────────────────────────────────────────────

def mark_gaps(index: pd.DatetimeIndex, min_days: int = config.GAP_MIN_DAYS) -> np.ndarray:
    """True у свечи, перед которой торги стояли дольше ``min_days`` календарных дней.

    Работает одинаково для дневок и часовиков: ночные и выходные перерывы
    короче порога, а приостановка торгов — длиннее.
    """
    if len(index) == 0:
        return np.zeros(0, dtype=bool)
    gaps = np.zeros(len(index), dtype=bool)
    deltas = np.diff(index.values) / np.timedelta64(1, "D")
    gaps[1:] = deltas > min_days
    return gaps


def gap_ranges(df: pd.DataFrame) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Список дыр как пар (последняя свеча до, первая свеча после)."""
    pos = np.flatnonzero(df["gap_before"].to_numpy())
    return [(df.index[p - 1], df.index[p]) for p in pos]


# ─── Дивиденды ────────────────────────────────────────────────────────────────

def settlement_lag(trade_day: pd.Timestamp, switch: date = config.T1_SWITCH_DATE) -> int:
    """Режим расчётов: T+2 до перехода, T+1 после."""
    return 1 if trade_day.date() >= switch else 2


# Фиксированные нерабочие праздники РФ (месяц, день). С марта 2025 биржа
# торгует в выходные и праздники, но расчёты в эти дни не проводятся.
# До этого, если биржа работала (например, в начале января), расчёты шли —
# это подтверждают реальные гэпы Магнита в январе 2016, 2020 и 2021.
# Переносы выходных сюда не входят: на практике они на отсечки не влияли.
RU_HOLIDAYS = {(1, d) for d in range(1, 9)} | {(2, 23), (3, 8), (5, 1), (5, 9), (6, 12), (11, 4)}


def is_settlement_day(day: pd.Timestamp) -> bool:
    if day.dayofweek >= 5:
        return False
    if day.date() >= config.HOLIDAY_SESSIONS_SINCE:
        return (day.month, day.day) not in RU_HOLIDAYS
    return True


def ex_dividend_date(
    registry_date: pd.Timestamp,
    trading_days: pd.DatetimeIndex,
    switch: date = config.T1_SWITCH_DATE,
) -> pd.Timestamp | None:
    """Первый торговый день, купив в который, дивиденд уже не получить.

    Покупка в день D попадает в реестр, только если расчёты по ней прошли
    не позже даты закрытия реестра R: settle(D) <= R. Расчёты идут только
    в рабочие дни; сделки выходных и праздников рассчитываются как сделки
    ближайшего рабочего дня. Возвращает None, если отсечка за пределами
    имеющегося календаря.
    """
    days = pd.DatetimeIndex(sorted(set(trading_days.normalize())))
    if len(days) == 0:
        return None
    settle_days = days[[is_settlement_day(d) for d in days]]
    registry = pd.Timestamp(registry_date).normalize()
    if registry < days[0]:
        return None

    # Гэп случается за несколько торговых дней до реестра; 20 календарных
    # дней с запасом покрывают и новогодние каникулы.
    start = days.searchsorted(registry - pd.Timedelta(days=20))
    for k in range(start, len(days)):
        day = days[k]
        # Сделку выходного дня биржа рассчитывает как сделку ближайшего буднего дня.
        i = settle_days.searchsorted(day)
        lag = settlement_lag(day, switch)
        if i + lag >= len(settle_days):
            return None
        if settle_days[i + lag] > registry:
            # Если это самый первый день календаря, не знаем, был ли гэп раньше.
            return None if k == 0 else day
    return None


def dividend_column(
    index: pd.DatetimeIndex,
    dividends: pd.DataFrame,
    trading_days: pd.DatetimeIndex,
) -> np.ndarray:
    """Сумма дивиденда на первой свече дня отсечки (гэпа), 0 на остальных.

    ``trading_days`` — календарь по дневкам: часовой ряд за 3 года
    не годится, чтобы считать отсечки 2015 года.
    """
    out = np.zeros(len(index))
    for _, row in dividends.iterrows():
        # Явная дата гэпа из CSV — для случаев, где правило T+1 не сработало
        # (например, бумага почти не торговалась в субботнюю сессию).
        manual = row.get("ex_date")
        ex = (pd.Timestamp(manual).normalize() if manual is not None and pd.notna(manual)
              else ex_dividend_date(row["registry_date"], trading_days))
        if ex is None:
            continue
        pos = index.searchsorted(ex)  # первая свеча с временем >= полуночи дня гэпа
        if pos < len(index) and index[pos].normalize() == ex:
            out[pos] += float(row["value"])
    return out


def load_dividends_csv(path: Path = config.DIVIDENDS_CSV) -> pd.DataFrame:
    df = pd.read_csv(path, comment="#")
    df["registry_date"] = pd.to_datetime(df["registry_date"])
    df["value"] = df["value"].astype(float)
    df["ex_date"] = pd.to_datetime(df["ex_date"]) if "ex_date" in df else pd.NaT
    return df[["ticker", "registry_date", "value", "ex_date"]]


def check_dividend_gaps(daily: pd.DataFrame) -> pd.DataFrame:
    """Сверка дивидендов с котировками: гэп открытия в день отсечки vs сумма.

    ratio ≈ 1 — дивиденд и дата правдоподобны; около 0 — гэпа не было
    (возможна ошибка в дате или сумме).
    """
    rows = []
    for pos in np.flatnonzero(daily["dividend"].to_numpy() > 0):
        if pos == 0:
            continue
        div = daily["dividend"].iloc[pos]
        prev_close = daily["close"].iloc[pos - 1]
        gap = prev_close - daily["open"].iloc[pos]
        rows.append({
            "ex_date": daily.index[pos].date(),
            "dividend": div,
            "gap": round(gap, 2),
            "ratio": round(gap / div, 2),
            "yield_pct": round(div / prev_close * 100, 2),
        })
    return pd.DataFrame(rows)


# ─── События ──────────────────────────────────────────────────────────────────

def load_events(path: Path = config.EVENTS_CSV) -> pd.DataFrame:
    """events.csv: date, ticker (или ALL), type, title [, scheduled].

    scheduled — была ли дата известна заранее: 1 по умолчанию, 0 для
    внезапных (внеплановое заседание ЦБ). Строки с # — комментарии.
    """
    cols = ["date", "ticker", "type", "title", "scheduled"]
    if not path.exists():
        return pd.DataFrame(columns=cols)
    df = pd.read_csv(path, comment="#", skip_blank_lines=True, dtype=str).fillna("")
    missing = set(cols[:4]) - set(df.columns)
    if missing:
        raise ValueError(f"{path.name}: нет колонок {sorted(missing)}")
    if "scheduled" not in df.columns:
        df["scheduled"] = ""
    df = df[cols].copy()
    df["date"] = pd.to_datetime(df["date"].str.strip())
    df["ticker"] = df["ticker"].str.strip().str.upper()
    df["type"] = df["type"].str.strip()
    df["title"] = df["title"].str.strip()
    df["scheduled"] = df["scheduled"].str.strip() != "0"
    unknown = set(df["type"]) - EVENT_TYPES
    if unknown:
        raise ValueError(f"{path.name}: неизвестные типы событий {sorted(unknown)}")
    return df.reset_index(drop=True)


def dividend_events(ticker: str, daily: pd.DataFrame) -> pd.DataFrame:
    """Отсечки из котировок → события типа dividend_cutoff (дата = день гэпа)."""
    pos = np.flatnonzero(daily["dividend"].to_numpy() > 0)
    return pd.DataFrame({
        "date": daily.index[pos].normalize(),
        "ticker": ticker,
        "type": "dividend_cutoff",
        "title": [f"Дивидендная отсечка: {v:g} ₽ на акцию" for v in daily["dividend"].iloc[pos]],
    })


# ─── Окна для игры ────────────────────────────────────────────────────────────

def valid_window_starts(gap_before: np.ndarray, length: int) -> np.ndarray:
    """Позиции s, для которых окно [s, s+length) не пересекает дыру.

    Дыра «внутри» окна — это флаг gap_before у любой свечи кроме первой:
    если дыра прямо перед первой свечой окна, окно начинается уже после неё.
    """
    n = len(gap_before)
    if n < length:
        return np.zeros(0, dtype=int)
    csum = np.concatenate([[0], np.cumsum(gap_before.astype(int))])
    starts = np.arange(0, n - length + 1)
    inside = csum[starts + length] - csum[starts + 1]
    return starts[inside == 0]


# ─── Загрузка сохранённых рядов ───────────────────────────────────────────────

def series_path(ticker: str, timeframe: str, base: Path = config.MOEX_DIR) -> Path:
    return base / f"{ticker}_{timeframe}.parquet"


@lru_cache(maxsize=32)
def load_series(ticker: str, timeframe: str) -> pd.DataFrame:
    """Свечи + служебные колонки gap_before и dividend (см. scripts/fetch_moex.py)."""
    return pd.read_parquet(series_path(ticker, timeframe))


def available_series() -> list[tuple[str, str]]:
    return [
        (t, tf)
        for t in config.TICKERS
        for tf in config.TIMEFRAMES
        if series_path(t, tf).exists()
    ]
