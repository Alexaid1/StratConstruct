"""Собрать заседания ЦБ по ключевой ставке в data/events.csv.

    python scripts/build_cbr_events.py

Плановые заседания — из официального календаря cbr.ru (там и заседания,
где ставку сохранили: иначе сама метка «заседание» выдавала бы, что ставку
изменят). Решение каждого заседания — по дневной истории ключевой ставки.
Изменения ставки вне календаря — внеплановые заседания (scheduled=0):
до наступления даты игроку их не показываем.

Строки других типов (отчётность и т. п.) в events.csv не трогаются.
"""

from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from trainer import config  # noqa: E402

CALENDAR_URL = "https://www.cbr.ru/dkp/cal_mp/"
KEYRATE_URL = "https://www.cbr.ru/hd_base/KeyRate/"
HEADERS = {"User-Agent": "Mozilla/5.0"}

MONTHS = {m: i for i, m in enumerate(
    ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
     "августа", "сентября", "октября", "ноября", "декабря"], start=1)}

# Внеплановые решения после 2015 года (в календаре их нет).
UNSCHEDULED = [date(2022, 2, 28), date(2022, 4, 8), date(2022, 5, 26), date(2023, 8, 15)]

HEADER = """\
# События для тренажёра. Колонки:
#   date      — дата события (ГГГГ-ММ-ДД)
#   ticker    — тикер или ALL (касается всех)
#   type      — cbr_meeting | earnings | dividend_cutoff
#   title     — что произошло; до ответа игрок видит только тип события
#   scheduled — 1, если дата была известна заранее (по умолчанию), 0 — внезапное
# Заседания ЦБ собирает scripts/build_cbr_events.py, отчётность — вручную.
# Дивидендные отсечки берутся из data/dividends.csv автоматически.
"""


def _plain(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>|&#160;|&nbsp;|&mdash;", " ", html))


def fetch_meetings() -> list[date]:
    """Календарь разбит на вкладки по годам. В старых вкладках даты без года
    («8 февраля»), а формулировка заседания менялась — ищем общее начало."""
    html = requests.get(CALENDAR_URL, headers=HEADERS, timeout=40).text
    tabs = re.findall(r'id="tab_tab_(t\d+)"[^>]*data-text="(\d{4}) год"', html)
    date_re = re.compile(
        r"(\d{1,2}) (" + "|".join(MONTHS) + r")(?: (\d{4}) года)? (?:Дата Событие )?Заседание Совета директоров"
    )
    found: set[date] = set()
    for tab_id, year in tabs:
        start = html.find(f'id="tab_content_{tab_id}"')
        if start < 0:
            continue
        end = html.find('id="tab_content_', start + 10)
        content = _plain(html[start:end if end > 0 else len(html)])
        for d, m, y in date_re.findall(content):
            found.add(date(int(y or year), MONTHS[m], int(d)))
    return sorted(found)


def fetch_key_rate(since: date, till: date) -> pd.Series:
    params = {
        "UniDbQuery.Posted": "True",
        "UniDbQuery.From": since.strftime("%d.%m.%Y"),
        "UniDbQuery.To": till.strftime("%d.%m.%Y"),
    }
    html = requests.get(KEYRATE_URL, params=params, headers=HEADERS, timeout=40).text
    rows = re.findall(r"<td>(\d\d\.\d\d\.\d{4})</td>\s*<td>([\d,]+)</td>", html)
    s = pd.Series(
        [float(r.replace(",", ".")) for _, r in rows],
        index=pd.to_datetime([d for d, _ in rows], format="%d.%m.%Y"),
    )
    return s.sort_index()


def fmt_rate(x: float) -> str:
    return f"{x:g}".replace(".", ",") + "%"


def describe(before: float, after: float) -> str:
    diff = after - before
    if abs(diff) < 1e-9:
        return f"ЦБ сохранил ключевую ставку: {fmt_rate(after)}"
    verb = "повысил" if diff > 0 else "снизил"
    pp = f"{abs(diff):g}".replace(".", ",")
    return f"ЦБ {verb} ключевую ставку до {fmt_rate(after)} ({'+' if diff > 0 else '−'}{pp} п.п.)"


def decision_title(meeting: date, rates: pd.Series) -> str | None:
    """Ставка до и после заседания: до — действовавшая в день решения
    (внеплановое могло вступить в силу в тот же день — тогда берём накануне)."""
    ts = pd.Timestamp(meeting)
    before_part = rates[rates.index < ts]
    after_part = rates[rates.index > ts]
    if before_part.empty or after_part.empty:
        return None  # заседание ещё не прошло — решение неизвестно
    before = before_part.iloc[-1]
    # Новая ставка вступает в силу в ближайшие дни после решения.
    after = rates[(rates.index >= ts) & (rates.index <= ts + pd.Timedelta(days=7))]
    changed = after[after != before]
    return describe(before, changed.iloc[0] if len(changed) else before)


def main() -> None:
    since = config.DAILY_SINCE
    meetings = [m for m in fetch_meetings() if m >= since]
    rates = fetch_key_rate(date(2014, 12, 1), date.today())
    print(f"Плановых заседаний с {since}: {len(meetings)}; дней в истории ставки: {len(rates)}")

    rows = []
    for m in meetings:
        title = decision_title(m, rates)
        if title:
            rows.append({"date": m, "ticker": "ALL", "type": "cbr_meeting", "title": title, "scheduled": 1})
    for m in UNSCHEDULED:
        title = decision_title(m, rates)
        if title:
            rows.append({"date": m, "ticker": "ALL", "type": "cbr_meeting",
                         "title": "Внеплановое заседание: " + title, "scheduled": 0})

    # Контроль: каждое изменение ставки должно объясняться каким-то заседанием.
    known = {pd.Timestamp(r["date"]) for r in rows}
    changes = rates[rates.diff().fillna(0) != 0]
    orphans = [d.date() for d in changes.index
               if d.date() >= since and not any(pd.Timedelta(0) <= d - k <= pd.Timedelta(days=7) for k in known)]
    if orphans:
        print("ВНИМАНИЕ: изменения ставки без заседания:", orphans)

    new = pd.DataFrame(rows).sort_values("date")
    path = config.EVENTS_CSV
    if path.exists():
        old = pd.read_csv(path, comment="#", dtype=str).fillna("")
        old = old[old["type"] != "cbr_meeting"]
    else:
        old = pd.DataFrame(columns=["date", "ticker", "type", "title", "scheduled"])
    if "scheduled" not in old.columns:
        old["scheduled"] = ""
    new["date"] = new["date"].astype(str)
    new["scheduled"] = new["scheduled"].astype(str)
    out = pd.concat([old, new], ignore_index=True).sort_values(["date", "ticker"])

    path.write_text(HEADER + out.to_csv(index=False, lineterminator="\n"), encoding="utf-8")
    print(f"Записано: {path} ({len(new)} заседаний ЦБ, других строк: {len(old)})")
    print(new.tail(6).to_string(index=False))


if __name__ == "__main__":
    main()
