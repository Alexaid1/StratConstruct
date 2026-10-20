"""Скачать котировки Мосбиржи для тренажёра.

    python scripts/fetch_moex.py                 # все тикеры из конфига
    python scripts/fetch_moex.py --tickers SBER  # только один

Что делает:
  1. Дневки с 2015 года и часовики за последние 3 года из ISS (с пагинацией).
  2. Помечает дыры в торгах (колонка gap_before) — окна через них в игру не идут.
  3. Ставит сумму дивиденда на свечу дня гэпа (колонка dividend) по
     data/dividends.csv (+ ISS, если вдруг снова начнёт отдавать дивиденды).
  4. Сохраняет data/moex/{TICKER}_{1d|1h}.parquet и manifest.json, печатает
     сверку дивидендов с реальными гэпами открытия.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from trainer import config  # noqa: E402
from trainer.dataset import (  # noqa: E402
    check_dividend_gaps,
    dividend_column,
    gap_ranges,
    load_dividends_csv,
    mark_gaps,
    series_path,
)
from trainer.moex import fetch_candles, fetch_dividends_iss  # noqa: E402


def collect_dividends(ticker: str, session) -> pd.DataFrame:
    csv = load_dividends_csv()
    csv = csv[csv["ticker"] == ticker]
    iss = fetch_dividends_iss(ticker, session=session)
    merged = pd.concat([csv, iss], ignore_index=True)
    # Одна отсечка из двух источников — оставляем запись из CSV (её проверяли руками).
    return merged.drop_duplicates(subset=["registry_date", "value"], keep="first")


def prepare(df: pd.DataFrame, dividends: pd.DataFrame, calendar: pd.DatetimeIndex) -> pd.DataFrame:
    df = df.copy()
    df["gap_before"] = mark_gaps(df.index)
    df["dividend"] = dividend_column(df.index, dividends, calendar)
    return df


def describe(df: pd.DataFrame) -> dict:
    return {
        "rows": int(len(df)),
        "first": str(df.index[0]),
        "last": str(df.index[-1]),
        "gaps": [[str(a), str(b)] for a, b in gap_ranges(df)],
        "dividend_bars": int((df["dividend"] > 0).sum()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tickers", nargs="+", default=config.TICKERS)
    parser.add_argument("--since", type=date.fromisoformat, default=config.DAILY_SINCE)
    parser.add_argument("--hourly-years", type=int, default=config.HOURLY_YEARS)
    args = parser.parse_args()

    # Сегодняшняя свеча ещё не закрыта — берём данные по вчерашний день.
    till = date.today() - timedelta(days=1)
    hourly_since = till - timedelta(days=365 * args.hourly_years)
    config.MOEX_DIR.mkdir(parents=True, exist_ok=True)

    manifest_path = config.MOEX_DIR / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    session = requests.Session()

    for ticker in args.tickers:
        print(f"\n=== {ticker}")
        daily = fetch_candles(ticker, config.TIMEFRAMES["1d"], args.since, till, session=session)
        hourly = fetch_candles(ticker, config.TIMEFRAMES["1h"], hourly_since, till, session=session)
        if daily.empty:
            print("  нет данных — пропускаю")
            continue

        dividends = collect_dividends(ticker, session)
        daily = prepare(daily, dividends, daily.index)
        hourly = prepare(hourly, dividends, daily.index)

        for tf, df in (("1d", daily), ("1h", hourly)):
            if df.empty:
                continue
            df.to_parquet(series_path(ticker, tf))
            info = describe(df)
            manifest[f"{ticker}_{tf}"] = info
            print(f"  {tf}: {info['rows']} свечей, {info['first'][:10]} → {info['last'][:10]}, "
                  f"дыр: {len(info['gaps'])}, отсечек: {info['dividend_bars']}")
            for a, b in info["gaps"]:
                print(f"      дыра: {a} → {b}")

        report = check_dividend_gaps(daily)
        if not report.empty:
            print("  сверка дивидендов (ratio = гэп открытия / дивиденд, ожидаем ≈ 1):")
            print(report.to_string(index=False).replace("\n", "\n    ").join(["    ", ""]))

    manifest["_fetched_at"] = datetime.now().isoformat(timespec="seconds")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nГотово: {config.MOEX_DIR}")


if __name__ == "__main__":
    main()
