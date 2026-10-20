"""Генератор раундов.

Раунд — это окно свечей: [разгон | видимая часть | будущее].
  • разгон (WARMUP_BARS) — прошлое до окна, не показывается, нужен только
    чтобы индикаторы были посчитаны с первой видимой свечи;
  • видимая часть (HISTORY_BARS) — то, что игрок видит до ответа;
  • будущее (FUTURE_BARS) — раскрывается после ответа.

Защита от знания будущего:
  • в браузер до ответа уходит только predict_payload — он строится из
    разгона и видимой части и не зависит от будущих свечей (это проверяют тесты);
  • тикер, даты и реальные цены скрыты: цены нормированы (первое видимое
    закрытие = 100), вместо дат — номера свечей;
  • дивидендный гэп убирается прибавлением дивиденда к ценам после отсечки
    (вперёд, а не назад — иначе будущий дивиденд сдвинул бы видимые цены).
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from functools import lru_cache

import numpy as np
import pandas as pd

from indicators.calculator import add_bbands, add_macd, add_rsi, add_sma
from trainer import config
from trainer.dataset import (
    available_series,
    load_events,
    load_series,
    valid_window_starts,
)

import pandas_ta as ta

H = config.HISTORY_BARS
F = config.FUTURE_BARS
W = config.WARMUP_BARS
WINDOW = W + H + F

PRICE_COLS = ["open", "high", "low", "close"]
CBR_DECISION_TIME = pd.Timedelta(hours=13, minutes=30)  # пресс-релиз ЦБ в 13:30 МСК

EVENT_LABELS = {
    "cbr_meeting": "Заседание ЦБ",
    "earnings": "Отчётность",
    "dividend_cutoff": "Дивидендная отсечка",
}


# ─── Описание раунда ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RoundSpec:
    """Минимум, по которому раунд восстанавливается целиком (хранится в журнале)."""

    ticker: str
    timeframe: str
    start_time: str  # время первой видимой свечи
    seed: int

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "RoundSpec":
        return cls(d["ticker"], d["timeframe"], d["start_time"], int(d["seed"]))


@dataclass
class RoundData:
    spec: RoundSpec
    id: str
    times: pd.DatetimeIndex          # реальные времена видимой части и будущего (H + F)
    candles: pd.DataFrame            # open high low close volume, нормированы, H + F строк
    indicators_visible: dict          # серии длиной H — посчитаны без будущего
    indicators_full: dict             # серии длиной H + F — для анимации раскрытия
    scale: float                     # реальная цена = нормированная × scale
    atr: float                       # ATR последней видимой свечи (нормированный)
    events: list[dict] = field(default_factory=list)

    @property
    def last_close(self) -> float:
        return float(self.candles["close"].iloc[H - 1])

    @property
    def visible(self) -> pd.DataFrame:
        return self.candles.iloc[:H]

    @property
    def future(self) -> pd.DataFrame:
        return self.candles.iloc[H:]


# ─── Выбор окна ───────────────────────────────────────────────────────────────

@lru_cache(maxsize=32)
def _visible_starts(ticker: str, timeframe: str) -> np.ndarray:
    df = load_series(ticker, timeframe)
    return valid_window_starts(df["gap_before"].to_numpy(), WINDOW) + W


def generate_round(
    seed: int | None = None,
    tickers: list[str] | None = None,
    timeframes: list[str] | None = None,
) -> RoundSpec:
    """Случайный тикер → таймфрейм → окно, не пересекающее дыр в торгах.

    Одинаковый seed на одних и тех же данных даёт тот же раунд — на этом
    потом строится «Задача дня» (seed из даты).
    """
    if seed is None:
        seed = int(np.random.default_rng().integers(0, 2**31 - 1))
    rng = np.random.default_rng(seed)

    series = [
        (t, tf) for t, tf in available_series()
        if (not tickers or t in tickers) and (not timeframes or tf in timeframes)
    ]
    series = [(t, tf) for t, tf in series if len(_visible_starts(t, tf))]
    if not series:
        raise ValueError("нет данных под выбранные фильтры — запусти scripts/fetch_moex.py")

    ticker = rng.choice(sorted({t for t, _ in series}))
    timeframe = rng.choice(sorted(tf for t, tf in series if t == ticker))
    starts = _visible_starts(ticker, timeframe)
    start = int(rng.choice(starts))
    start_time = load_series(ticker, timeframe).index[start]
    return RoundSpec(str(ticker), str(timeframe), str(start_time), seed)


# ─── Сборка раунда ────────────────────────────────────────────────────────────

def adjust_for_dividends(window: pd.DataFrame) -> pd.DataFrame:
    """Прибавить дивиденд к ценам начиная со свечи гэпа — гэп исчезает."""
    out = window.copy()
    shift = out["dividend"].cumsum().to_numpy()
    for col in PRICE_COLS:
        out[col] = out[col].to_numpy() + shift
    return out


def compute_indicators(df: pd.DataFrame) -> dict[str, np.ndarray]:
    """Индикаторы для графика. Все они «смотрят» только назад."""
    x = df[["open", "high", "low", "close", "volume"]].copy()
    m1, m2 = config.MA_PERIODS
    add_sma(x, m1)
    add_sma(x, m2)
    add_rsi(x, config.RSI_PERIOD)
    fast, slow, signal = config.MACD_PARAMS
    add_macd(x, fast, slow, signal)
    bb_len, bb_std = config.BB_PARAMS
    add_bbands(x, bb_len, bb_std)
    s = str(bb_std).replace(".", "_")
    tag = f"{fast}_{slow}_{signal}"
    return {
        "ma1": x[f"SMA_{m1}"].to_numpy(),
        "ma2": x[f"SMA_{m2}"].to_numpy(),
        "rsi": x[f"RSI_{config.RSI_PERIOD}"].to_numpy(),
        "macd": x[f"MACD_{tag}"].to_numpy(),
        "macd_signal": x[f"MACDs_{tag}"].to_numpy(),
        "macd_hist": x[f"MACDh_{tag}"].to_numpy(),
        "bb_upper": x[f"BB_upper_{bb_len}_{s}"].to_numpy(),
        "bb_mid": x[f"BB_mid_{bb_len}_{s}"].to_numpy(),
        "bb_lower": x[f"BB_lower_{bb_len}_{s}"].to_numpy(),
    }


def last_atr(df: pd.DataFrame, period: int = config.ATR_PERIOD) -> float:
    atr = ta.atr(df["high"], df["low"], df["close"], length=period)
    return float(atr.iloc[-1])


def event_bar(times: pd.DatetimeIndex, when: pd.Timestamp, kind: str, timeframe: str) -> int:
    """Номер свечи окна, к которой относится событие (len(times), если позже окна)."""
    day = pd.Timestamp(when).normalize()
    i = int(times.searchsorted(day))
    if kind == "cbr_meeting" and timeframe != "1d":
        # На часовиках — свеча, в которую вышел пресс-релиз (13:30).
        j = int(times.searchsorted(day + CBR_DECISION_TIME, side="right")) - 1
        if j >= i and times[j].normalize() == day:
            i = j
    return i


def collect_events(
    spec: RoundSpec,
    times: pd.DatetimeIndex,
    window: pd.DataFrame,
    events: pd.DataFrame,
) -> list[dict]:
    """События внутри видимой части и будущего: из events.csv + отсечки из котировок."""
    out = []
    first_day = times[0].normalize()
    relevant = events[
        events["ticker"].isin(["ALL", spec.ticker])
        & (events["type"] != "dividend_cutoff")  # отсечки берём из котировок
        & (events["date"] >= first_day)
        & (events["date"] <= times[-1])
    ]
    for _, ev in relevant.iterrows():
        bar = event_bar(times, ev["date"], ev["type"], spec.timeframe)
        if bar < len(times):
            out.append({"bar": bar, "type": ev["type"], "title": ev["title"],
                        "scheduled": bool(ev["scheduled"])})

    # Дивиденд: позиции в окне без разгона; доля от цены — до нормировки неважна.
    tail = window.iloc[W:]
    closes = window["close"].to_numpy()
    for k in np.flatnonzero(tail["dividend"].to_numpy() > 0):
        div = float(tail["dividend"].iloc[k])
        prev_close = closes[W + k - 1]
        pct = div / prev_close * 100
        out.append({
            "bar": int(k), "type": "dividend_cutoff", "scheduled": True,
            "title": f"Дивидендная отсечка: {div:g} ₽ ({pct:.1f}% от цены). Гэп убран из графика.",
            "dividend_pct": round(pct, 2),
        })
    return sorted(out, key=lambda e: e["bar"])


def build_round(
    spec: RoundSpec,
    series: pd.DataFrame | None = None,
    events: pd.DataFrame | None = None,
) -> RoundData:
    """Собрать раунд по описанию. series/events можно подменить в тестах."""
    df = series if series is not None else load_series(spec.ticker, spec.timeframe)
    ev = events if events is not None else load_events()
    start = int(df.index.get_loc(pd.Timestamp(spec.start_time)))
    if start < W or start + H + F > len(df):
        raise ValueError("окно раунда выходит за пределы данных")

    window = adjust_for_dividends(df.iloc[start - W:start + H + F])
    base = float(window["close"].iloc[W])           # первое видимое закрытие
    norm = window.copy()
    for col in PRICE_COLS:
        norm[col] = norm[col] / base * 100
    vol_median = float(np.median(norm["volume"].iloc[W:W + H])) or 1.0
    norm["volume"] = norm["volume"] / vol_median * 100

    # Индикаторы для прогноза — строго по разгону + видимой части.
    past = norm.iloc[:W + H]
    ind_visible = {k: v[W:] for k, v in compute_indicators(past).items()}
    ind_full = {k: v[W:] for k, v in compute_indicators(norm).items()}

    times = df.index[start:start + H + F]
    candles = norm.iloc[W:][["open", "high", "low", "close", "volume"]].reset_index(drop=True)

    return RoundData(
        spec=spec,
        id=uuid.uuid4().hex[:12],
        times=times,
        candles=candles,
        indicators_visible=ind_visible,
        indicators_full=ind_full,
        scale=base / 100,
        atr=last_atr(past),
        events=collect_events(spec, times, window, ev),
    )


# ─── Что уходит в браузер ─────────────────────────────────────────────────────

def _num(x: float, nd: int = 4):
    return None if x is None or not np.isfinite(x) else round(float(x), nd)


def _candles_json(df: pd.DataFrame) -> list[list]:
    return [[_num(o), _num(h), _num(l), _num(c), _num(v, 1)]
            for o, h, l, c, v in df[["open", "high", "low", "close", "volume"]].to_numpy()]


def _series_json(ind: dict) -> dict:
    return {k: [_num(x) for x in v] for k, v in ind.items()}


def time_labels(times: pd.DatetimeIndex, timeframe: str) -> list[str]:
    fmt = "%d.%m.%Y" if timeframe == "1d" else "%d.%m.%Y %H:%M"
    return [t.strftime(fmt) for t in times]


def public_event_label(event: dict) -> str:
    """Подпись события до ответа: без цифр и формулировок, по которым
    легко узнать период (например, «ставка 20%» — это февраль 2022)."""
    if event["type"] == "cbr_meeting":
        t = event["title"].lower()
        if "повысил" in t:
            return "ЦБ повысил ставку"
        if "снизил" in t:
            return "ЦБ снизил ставку"
        if "сохранил" in t:
            return "ЦБ сохранил ставку"
        return "Заседание ЦБ"
    if event["type"] == "dividend_cutoff" and "dividend_pct" in event:
        return f"Отсечка: дивиденд {event['dividend_pct']:.1f}%"
    return EVENT_LABELS[event["type"]]


def identity(rd: RoundData) -> dict:
    labels = time_labels(rd.times, rd.spec.timeframe)
    return {
        "ticker": rd.spec.ticker,
        "name": config.TICKER_NAMES.get(rd.spec.ticker, rd.spec.ticker),
        "timeframe": rd.spec.timeframe,
        "timeframe_label": config.TIMEFRAME_LABELS.get(rd.spec.timeframe, rd.spec.timeframe),
        "period": f"{labels[0]} — {labels[-1]}",
        "scale": rd.scale,
    }


def predict_payload(rd: RoundData, show_identity: bool = False) -> dict:
    """Данные для фазы прогноза. Будущие свечи и исходы сюда не попадают."""
    events = []
    for e in rd.events:
        if e["bar"] < H:
            # Уже случилось — игрок мог это знать.
            events.append({"bar": e["bar"], "type": e["type"],
                           "label": e["title"] if show_identity else public_event_label(e)})
        elif e["scheduled"]:
            # Впереди, но дата известна заранее — исход нет.
            events.append({"bar": e["bar"], "type": e["type"], "label": EVENT_LABELS[e["type"]]})
    payload = {
        "round_id": rd.id,
        "phase": "predict",
        "history": H,
        "future_slots": F,
        "candles": _candles_json(rd.visible),
        "indicators": _series_json(rd.indicators_visible),
        "events": events,
        "last_close": _num(rd.last_close),
        "atr": _num(rd.atr),
        "identity": None,
        "labels": None,
    }
    if show_identity:
        ident = identity(rd)
        ident["period"] = ident["period"].split(" — ")[0] + " — …"
        payload["identity"] = ident
        payload["labels"] = time_labels(rd.times[:H], rd.spec.timeframe)
    return payload


def reveal_payload(rd: RoundData) -> dict:
    """Всё о раунде — уходит в браузер только после ответа."""
    return {
        "round_id": rd.id,
        "phase": "reveal",
        "history": H,
        "future_slots": F,
        "candles": _candles_json(rd.visible),
        "future": _candles_json(rd.future),
        "indicators": _series_json(rd.indicators_full),
        "events": [{"bar": e["bar"], "type": e["type"], "label": e["title"]} for e in rd.events],
        "last_close": _num(rd.last_close),
        "atr": _num(rd.atr),
        "identity": identity(rd),
        "labels": time_labels(rd.times, rd.spec.timeframe),
    }
