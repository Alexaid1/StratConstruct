"""Клиент ISS Мосбиржи: свечи с пагинацией и (если доступны) дивиденды.

Сетевой слой отделён от разбора: в функции передаётся объект с методом
``get(url, params=..., timeout=...)`` (requests.Session или подделка в тестах).
"""

from __future__ import annotations

import time
from datetime import date

import pandas as pd
import requests

ISS_BASE = "https://iss.moex.com/iss"
CANDLES_URL = ISS_BASE + "/engines/stock/markets/shares/boards/{board}/securities/{ticker}/candles.json"
DIVIDENDS_URL = ISS_BASE + "/securities/{ticker}/dividends.json"

CANDLE_COLUMNS = ["open", "high", "low", "close", "volume", "value"]

# Предохранитель от бесконечного цикла: 2000 страниц × 500 строк = 1 млн свечей.
MAX_PAGES = 2000


def _get_json(session, url: str, params: dict, retries: int = 3, pause: float = 1.0) -> dict:
    """GET с повторами на сетевые сбои и 5xx."""
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            resp = session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_exc = exc
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else 0
            if status < 500:
                raise
            last_exc = exc
        time.sleep(pause * (attempt + 1))
    raise RuntimeError(f"ISS не ответил после {retries} попыток: {url}") from last_exc


def candles_to_frame(columns: list[str], rows: list[list]) -> pd.DataFrame:
    """Строки блока ``candles`` → DataFrame с индексом-временем начала свечи (МСК)."""
    if not rows:
        return pd.DataFrame(columns=CANDLE_COLUMNS, index=pd.DatetimeIndex([], name="time"))
    df = pd.DataFrame(rows, columns=columns)
    df["time"] = pd.to_datetime(df["begin"])
    df = df.set_index("time")[CANDLE_COLUMNS].astype(float)
    df = df[~df.index.duplicated(keep="first")].sort_index()
    return df


def fetch_candles(
    ticker: str,
    interval: int,
    start: date,
    end: date,
    *,
    board: str = "TQBR",
    session=None,
    page_pause: float = 0.05,
) -> pd.DataFrame:
    """Все свечи тикера за [start, end].

    ISS отдаёт свечи порциями (обычно по 500 строк). Листаем параметром
    ``start`` до пустой страницы — так не зависим от точного размера порции.
    """
    session = session or requests.Session()
    url = CANDLES_URL.format(board=board, ticker=ticker)
    columns: list[str] | None = None
    rows: list[list] = []
    offset = 0
    prev_first: list | None = None

    for _ in range(MAX_PAGES):
        payload = _get_json(session, url, {
            "interval": interval,
            "from": start.isoformat(),
            "till": end.isoformat(),
            "start": offset,
            "iss.meta": "off",
        })
        block = payload.get("candles") or {}
        page = block.get("data") or []
        if not page:
            break
        # Сервер проигнорировал start и вернул ту же страницу — дальше не листаем.
        if prev_first is not None and page[0] == prev_first:
            break
        prev_first = page[0]
        columns = block["columns"]
        rows.extend(page)
        offset += len(page)
        if page_pause:
            time.sleep(page_pause)
    else:
        raise RuntimeError(f"{ticker}: больше {MAX_PAGES} страниц — похоже на зацикливание")

    return candles_to_frame(columns or [], rows)


def fetch_dividends_iss(ticker: str, *, session=None) -> pd.DataFrame:
    """Дивиденды из ISS, если эндпоинт их отдаёт.

    На осень 2026 публичный ``/securities/{ticker}/dividends`` больше не
    возвращает блок ``dividends`` (только описание бумаги), а раздел
    ``/cci/corp-actions`` закрыт авторизацией. Поэтому пустой результат —
    нормальная ситуация: основной источник — data/dividends.csv.
    """
    session = session or requests.Session()
    try:
        payload = _get_json(session, DIVIDENDS_URL.format(ticker=ticker), {"iss.meta": "off"})
    except Exception:
        return empty_dividends()
    block = payload.get("dividends")
    if not block or not block.get("data"):
        return empty_dividends()
    df = pd.DataFrame(block["data"], columns=block["columns"])
    df = df.rename(columns={"registryclosedate": "registry_date"})
    df["registry_date"] = pd.to_datetime(df["registry_date"])
    df["ticker"] = ticker
    return df[["ticker", "registry_date", "value"]]


def empty_dividends() -> pd.DataFrame:
    return pd.DataFrame({
        "ticker": pd.Series(dtype=str),
        "registry_date": pd.Series(dtype="datetime64[ns]"),
        "value": pd.Series(dtype=float),
    })
