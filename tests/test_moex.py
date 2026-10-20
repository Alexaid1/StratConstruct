"""Клиент ISS: пагинация свечей и разбор ответов — без сети, на подделке."""

from datetime import date, datetime, timedelta

import pytest

from trainer.moex import fetch_candles, fetch_dividends_iss

COLUMNS = ["open", "close", "high", "low", "value", "volume", "begin", "end"]


def make_rows(n: int, offset: int = 0) -> list[list]:
    base = datetime(2020, 1, 1)
    rows = []
    for i in range(offset, offset + n):
        t = base + timedelta(days=i)
        rows.append([100 + i, 101 + i, 102 + i, 99 + i, 1e6, 1000,
                     t.strftime("%Y-%m-%d %H:%M:%S"), t.strftime("%Y-%m-%d 23:59:59")])
    return rows


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


class PagedSession:
    """Отдаёт total строк порциями по page_size, как ISS."""

    def __init__(self, total: int, page_size: int = 500, ignore_start: bool = False):
        self.total = total
        self.page_size = page_size
        self.ignore_start = ignore_start
        self.starts: list[int] = []

    def get(self, url, params=None, timeout=None):
        start = params["start"]
        self.starts.append(start)
        if self.ignore_start:
            start = 0
        n = max(0, min(self.page_size, self.total - start))
        return FakeResponse({"candles": {"columns": COLUMNS, "data": make_rows(n, start)}})


def fetch(session):
    return fetch_candles("SBER", 24, date(2020, 1, 1), date(2030, 1, 1), session=session, page_pause=0)


def test_pagination_collects_all_pages():
    s = PagedSession(total=1123)
    df = fetch(s)
    assert len(df) == 1123
    assert s.starts == [0, 500, 1000, 1123]  # последний запрос — пустая страница
    assert df.index.is_monotonic_increasing
    assert not df.index.duplicated().any()


def test_pagination_exact_multiple_of_page_size():
    s = PagedSession(total=1000)
    df = fetch(s)
    assert len(df) == 1000
    assert s.starts == [0, 500, 1000]


def test_pagination_does_not_depend_on_page_size():
    # Если ISS поменяет размер порции, листаем всё равно до пустой страницы.
    s = PagedSession(total=250, page_size=100)
    df = fetch(s)
    assert len(df) == 250
    assert s.starts == [0, 100, 200, 250]


def test_pagination_stops_when_server_ignores_start():
    s = PagedSession(total=1500, ignore_start=True)
    df = fetch(s)
    assert len(df) == 500          # одна уникальная страница, без дублей
    assert len(s.starts) == 2      # вторая такая же страница остановила цикл


def test_empty_response_gives_empty_frame():
    df = fetch(PagedSession(total=0))
    assert df.empty
    assert list(df.columns) == ["open", "high", "low", "close", "volume", "value"]


def test_candle_columns_are_mapped_by_name():
    # ISS отдаёт open, close, high, low — не в порядке OHLC.
    df = fetch(PagedSession(total=1))
    row = df.iloc[0]
    assert (row["open"], row["high"], row["low"], row["close"]) == (100, 102, 99, 101)


def test_iss_dividends_missing_block_returns_empty():
    class DescriptionOnly:
        def get(self, url, params=None, timeout=None):
            return FakeResponse({"description": {"columns": [], "data": []}, "boards": {}})

    assert fetch_dividends_iss("SBER", session=DescriptionOnly()).empty


def test_iss_dividends_parsed_when_present():
    class WithDividends:
        def get(self, url, params=None, timeout=None):
            return FakeResponse({"dividends": {
                "columns": ["secid", "isin", "registryclosedate", "value", "currencyid"],
                "data": [["SBER", "RU0009029540", "2024-07-11", 33.3, "RUB"]],
            }})

    df = fetch_dividends_iss("SBER", session=WithDividends())
    assert len(df) == 1
    assert df.iloc[0]["value"] == pytest.approx(33.3)
    assert str(df.iloc[0]["registry_date"].date()) == "2024-07-11"
