"""Разбор раунда: что показывал график в момент прогноза и что случилось потом.

Сигналы считаются только по видимой части — ровно по тому, что видел
игрок. Будущее нужно лишь для проверки: какие подсказки сработали и что
происходило с ценой. Настоящую причину движения не знает никто, поэтому
разбор не выдумывает новостей: он опирается на индикаторы, уровни
и события из календаря (заседания ЦБ, отчётность, отсечки).
"""

from __future__ import annotations

import math

import numpy as np

from trainer import config
from trainer.rounds import F, H, RoundData
from trainer.scoring import DOWN, FLAT, OUTCOME_LABELS, UP, classify_move

MOVE = "move"  # сигнал «будет сильное движение», направление не важно

VOTE_LABELS = {UP: "за рост", DOWN: "за падение", MOVE: "за сильное движение", None: "без сигнала"}
MOVE_WORDS = {UP: "вверх", DOWN: "вниз", FLAT: "в боковик"}

REACTION_BARS = 3      # сколько свечей после события смотреть на реакцию цены
BIG_BAR_ATR = 1.5      # «сильная свеча»: изменение за свечу больше 1.5 ATR
SHOCK_BAR_ATR = 2.5    # свеча-рывок: больше 2.5 ATR за раз…
SHOCK_SHARE = 0.5      # …и не меньше половины всего движения за раунд
DRIVER_EVENTS = {"cbr_meeting", "earnings"}  # отсечка не в счёт: её гэп убран из графика
EVENT_SHARE = 0.4      # событие — главная версия, только если на реакцию пришлось ≥40% движения


# ─── Мелочи ───────────────────────────────────────────────────────────────────

def plural(n: int, one: str, few: str, many: str) -> str:
    m10, m100 = n % 10, n % 100
    if m10 == 1 and m100 != 11:
        return one
    if 2 <= m10 <= 4 and not 12 <= m100 <= 14:
        return few
    return many


def _num(x: float, nd: int = 1, unit: str = "") -> str:
    """Число со знаком: +1.2% / −0.8 ATR."""
    v = round(float(x), nd)
    sign = "+" if v > 0 else "−" if v < 0 else ""
    return f"{sign}{abs(v):.{nd}f}{unit}"


def _pct(x: float, nd: int = 1) -> str:
    return _num(x, nd, "%")


def _plain(x: float, nd: int = 2) -> str:
    """Число без плюса, но с настоящим минусом."""
    return f"{float(x):.{nd}f}".replace("-", "−")


def _bars(n: int) -> str:
    return f"{n} {plural(n, 'свеча', 'свечи', 'свечей')}"


def _bars_ago(n: int) -> str:
    return "на последней свече" if n == 0 else f"{n} {plural(n, 'свечу', 'свечи', 'свечей')} назад"


def _finite(*xs) -> bool:
    return all(x is not None and math.isfinite(float(x)) for x in xs)


def _recent_cross(diff: np.ndarray, lookback: int) -> tuple[int, str] | None:
    """Последняя смена знака diff за lookback свечей: (сколько свечей назад, куда)."""
    d = np.asarray(diff, dtype=float)[-(lookback + 1):]
    for k in range(len(d) - 1, 0, -1):
        a, b = d[k - 1], d[k]
        if np.isfinite(a) and np.isfinite(b) and b != 0 and np.sign(a) != np.sign(b):
            return len(d) - 1 - k, UP if b > 0 else DOWN
    return None


def _signal(sid: str, title: str, value: str, reading: str, rule: str, vote, show: list[str], **extra) -> dict:
    return {
        "id": sid, "title": title, "value": value, "reading": reading, "rule": rule,
        "vote": vote, "vote_label": VOTE_LABELS[vote], "show": show, **extra,
    }


# ─── Сигналы в момент прогноза (только видимая часть) ────────────────────────

def trend_signal(close: np.ndarray, ma_fast: np.ndarray, ma_slow: np.ndarray, atr: float) -> dict | None:
    c, m1, m2 = close[-1], ma_fast[-1], ma_slow[-1]
    if not _finite(m1, m2, ma_fast[-6]):
        return None
    f, s = config.MA_PERIODS
    slope = (ma_fast[-1] - ma_fast[-6]) / atr
    if c > m1 > m2 and slope > 0:
        vote, reading = UP, f"Цена выше MA {f} и MA {s}, а MA {f} растёт — восходящий тренд."
    elif c < m1 < m2 and slope < 0:
        vote, reading = DOWN, f"Цена ниже MA {f} и MA {s}, а MA {f} снижается — нисходящий тренд."
    elif c > max(m1, m2):
        why = f"MA {f} ниже MA {s}" if m1 < m2 else f"MA {f} не растёт"
        vote, reading = None, (f"Цена выше обеих средних, но тренда по ним ещё нет: {why}. "
                               "Это может быть начало разворота вверх, а может быть просто отскок.")
    elif c < min(m1, m2):
        why = f"MA {f} выше MA {s}" if m1 > m2 else f"MA {f} не снижается"
        vote, reading = None, (f"Цена ниже обеих средних, но тренда по ним ещё нет: {why}. "
                               "Это может быть начало разворота вниз, а может быть просто откат.")
    else:
        vote, reading = None, f"Цена между MA {f} и MA {s} — явного тренда нет."
    cross = _recent_cross(ma_fast - ma_slow, 10)
    if cross:
        ago, way = cross
        reading += (f" {_bars_ago(ago).capitalize()} MA {f} пересекла MA {s} "
                    + ("снизу вверх." if way == UP else "сверху вниз."))
    return _signal(
        "trend", f"Тренд · MA {f}/{s}",
        f"{_pct((c / m1 - 1) * 100)} к MA {f} · {_pct((c / m2 - 1) * 100)} к MA {s}",
        reading,
        "Цена выше обеих средних и они растут — тренд вверх; ниже и падают — вниз. "
        "Средние запаздывают: на развороте они ещё какое-то время показывают старый тренд.",
        vote, ["ma1", "ma2"],
    )


# RSI: зона без сигнала шире, чем «около 50», — иначе 45 и 43 дают разные
# выводы на ровном месте. У самых границ 30/70 честно пишем, что край рядом.
RSI_HIGH, RSI_LOW = 70, 30
RSI_BULL, RSI_BEAR = 60, 40
RSI_NEAR = 5  # «рукой подать» до перекупленности / перепроданности


def rsi_signal(rsi: np.ndarray) -> dict | None:
    r = float(rsi[-1])
    if not _finite(r):
        return None
    extreme = r >= RSI_HIGH or r <= RSI_LOW
    if r >= RSI_HIGH:
        vote, reading = DOWN, "Выше 70 — перекупленность: цена быстро выросла, за этим часто следует откат."
    elif r <= RSI_LOW:
        vote, reading = UP, "Ниже 30 — перепроданность: после резкого падения часто бывает отскок."
    elif r >= RSI_HIGH - RSI_NEAR:
        vote, reading = UP, ("У покупателей перевес, но до перекупленности (70) рукой подать — "
                             "запас роста по RSI небольшой.")
    elif r <= RSI_LOW + RSI_NEAR:
        vote, reading = DOWN, ("У продавцов перевес, но до перепроданности (30) рукой подать — "
                               "запас падения по RSI небольшой.")
    elif r >= RSI_BULL:
        vote, reading = UP, "Выше 60 — у покупателей заметный перевес, до перекупленности (70) ещё есть запас."
    elif r <= RSI_BEAR:
        vote, reading = DOWN, "Ниже 40 — у продавцов заметный перевес, до перепроданности (30) ещё есть запас."
    else:
        vote, reading = None, "Между 40 и 60 — явного перевеса ни у покупателей, ни у продавцов нет."
    return _signal(
        "rsi", f"RSI · {config.RSI_PERIOD}", f"RSI {r:.0f}", reading,
        "Выше 70 — перекупленность, ниже 30 — перепроданность: возможен откат. "
        "Выше 60 — перевес покупателей, ниже 40 — продавцов, между 40 и 60 сигнала нет. "
        "В сильном тренде RSI может долго держаться у края — это ещё не сигнал к развороту.",
        vote, ["rsi"], extreme=bool(extreme), level=round(r, 1),
    )


def macd_signal(macd: np.ndarray, signal: np.ndarray, hist: np.ndarray, atr: float) -> dict | None:
    m, s, h = macd[-1], signal[-1], hist[-1]
    if not _finite(m, s, h, hist[-3]):
        return None
    if abs(h) < 0.03 * atr:
        vote, reading = None, "Линия MACD почти слилась с сигнальной — импульса нет."
    else:
        vote = UP if h > 0 else DOWN
        reading = "MACD выше сигнальной — импульс вверх" if h > 0 else "MACD ниже сигнальной — импульс вниз"
        cross = _recent_cross(hist, 5)
        if cross and cross[1] == vote:
            reading += f", пересечение {_bars_ago(cross[0])}"
        reading += ("; столбики растут — импульс крепнет." if abs(h) > abs(hist[-3])
                    else "; столбики уменьшаются — импульс выдыхается.")
    fast, slow, sig = config.MACD_PARAMS
    return _signal(
        "macd", f"MACD · {fast}/{slow}/{sig}", f"MACD {_plain(m)} · сигнальная {_plain(s)}", reading,
        "Линия MACD выше сигнальной — импульс вверх, ниже — вниз; пересечение линий — смена импульса. "
        "Столбики — расстояние между линиями: растут — движение ускоряется, уменьшаются — выдыхается.",
        vote, ["macd"],
    )


# Боллинджер: доля высоты коридора. У самой границы — сигнал на возврат,
# в верхней/нижней трети — только описание положения, без голоса.
BB_EDGE_HIGH, BB_EDGE_LOW = 0.9, 0.1
BB_PART_HIGH, BB_PART_LOW = 0.65, 0.35


def bollinger_signal(close: np.ndarray, upper: np.ndarray, mid: np.ndarray, lower: np.ndarray) -> dict | None:
    c, up, md, lo = close[-1], upper[-1], mid[-1], lower[-1]
    if not _finite(up, md, lo) or up <= lo:
        return None
    pos = (c - lo) / (up - lo)
    widths = (upper - lower) / mid
    widths = widths[np.isfinite(widths)]
    width = (up - lo) / md
    squeeze = len(widths) >= 20 and width <= np.percentile(widths, 20)
    extreme = pos > BB_EDGE_HIGH or pos < BB_EDGE_LOW
    if pos > BB_EDGE_HIGH:
        vote = DOWN
        reading = ("Цена вышла за верхнюю границу коридора" if pos > 1 else "Цена у верхней границы коридора")
        reading += " — перерастянута вверх, её часто тянет обратно к середине."
    elif pos < BB_EDGE_LOW:
        vote = UP
        reading = ("Цена вышла за нижнюю границу коридора" if pos < 0 else "Цена у нижней границы коридора")
        reading += " — перерастянута вниз, её часто тянет обратно к середине."
    else:
        vote = None
        if pos >= BB_PART_HIGH:
            reading = "Цена в верхней части коридора — выше средней линии, но до верхней границы ещё есть место."
        elif pos <= BB_PART_LOW:
            reading = "Цена в нижней части коридора — ниже средней линии, но до нижней границы ещё есть место."
        else:
            reading = "Цена около средней линии коридора — перекоса нет."
    if squeeze:
        if vote is None:
            vote = MOVE
        reading += (" Коридор сжат сильнее, чем в 80% видимой части: после такого затишья часто бывает "
                    "сильное движение, но в какую сторону — сжатие не подсказывает.")
    n, k = config.BB_PARAMS
    return _signal(
        "bb", "Боллинджер",
        f"{pos * 100:.0f}% высоты коридора · ширина {width * 100:.1f}%", reading,
        f"Коридор — средняя за {n} свечей ± {k:g} стандартных отклонения. У верхней границы цена «дорогая» "
        "относительно недавнего прошлого, у нижней — «дешёвая», и её часто тянет к середине; "
        "но в сильном тренде цена может долго идти вдоль границы. "
        "Сжатие коридора — затишье, после которого часто бывает сильное движение в любую сторону.",
        vote, ["bb"], extreme=bool(extreme), squeeze=bool(squeeze),
    )


def volume_signal(close: np.ndarray, volume: np.ndarray, atr: float) -> dict | None:
    base = float(np.median(volume))
    if base <= 0 or len(close) < 6:
        return None
    ratio = float(np.mean(volume[-5:])) / base
    move = (close[-1] - close[-6]) / atr
    vote = None
    if ratio >= 1.5 and abs(move) >= 1:
        vote = UP if move > 0 else DOWN
        reading = (f"Последние 5 свечей — {'рост' if move > 0 else 'падение'} на объёме в {ratio:.1f}× "
                   "выше обычного: движение поддержано деньгами.")
    elif ratio >= 1.5:
        reading = f"Объём вырос в {ratio:.1f}×, а цена почти стоит — идёт борьба покупателей и продавцов."
    elif ratio <= 0.7:
        reading = "Объём ниже обычного — у рынка мало интереса, движения слабые."
    else:
        reading = "Объём обычный — подсказок нет."
    return _signal(
        "vol", "Объём", f"{ratio:.1f}× от обычного", reading,
        "Объём — сколько акций сменило владельца за свечу. Движение на растущем объёме надёжнее: "
        "за ним стоят деньги. Рост на падающем объёме слабый и легко ломается.",
        vote, ["vol"],
    )


LEVELS_PART_HIGH, LEVELS_PART_LOW = 0.75, 0.25  # верхняя / нижняя четверть диапазона окна


def levels_signal(close: np.ndarray, high: np.ndarray, low: np.ndarray, atr: float) -> dict | None:
    c = close[-1]
    hi, lo = float(high.max()), float(low.min())
    prior_hi, prior_lo = float(high[:-3].max()), float(low[:-3].min())
    if hi <= lo:
        return None
    pos = (c - lo) / (hi - lo)
    to_hi, to_lo = (hi - c) / atr, (c - lo) / atr
    vote = None
    if c > prior_hi:
        vote, reading = UP, "Цена пробила максимум всего окна — после пробоя движение часто продолжается."
    elif c < prior_lo:
        vote, reading = DOWN, "Цена пробила минимум всего окна — после пробоя движение часто продолжается."
    elif to_hi < 1:
        reading = (f"Цена в {to_hi:.1f} ATR от максимума окна — это сопротивление: "
                   "дальше либо пробой, либо откат.")
    elif to_lo < 1:
        reading = (f"Цена в {to_lo:.1f} ATR от минимума окна — это поддержка: "
                   "дальше либо отскок, либо пробой вниз.")
    elif pos >= LEVELS_PART_HIGH:
        reading = (f"Цена в верхней части диапазона окна: до максимума {to_hi:.1f} ATR — "
                   "это ближайшее сопротивление.")
    elif pos <= LEVELS_PART_LOW:
        reading = (f"Цена в нижней части диапазона окна: до минимума {to_lo:.1f} ATR — "
                   "это ближайшая поддержка.")
    else:
        reading = (f"Цена в середине диапазона окна: до максимума {to_hi:.1f} ATR, "
                   f"до минимума {to_lo:.1f} ATR.")
    return _signal(
        "levels", "Уровни", f"{pos * 100:.0f}% диапазона окна", reading,
        "Максимумы и минимумы прошлого — уровни, где цена уже разворачивалась. У уровня цена часто тормозит, "
        "а если пробивает — движение нередко ускоряется. Уровни можно рисовать инструментом «Уровень».",
        vote, ["levels"], lines=[round(hi, 4), round(lo, 4)],
    )


def signals(rd: RoundData) -> list[dict]:
    """Все сигналы на последней видимой свече. Будущее сюда не попадает."""
    v = rd.visible
    close, high, low, volume = (v[k].to_numpy(dtype=float) for k in ("close", "high", "low", "volume"))
    ind = rd.indicators_visible
    atr = max(rd.atr, 1e-9)
    found = [
        trend_signal(close, ind["ma1"], ind["ma2"], atr),
        rsi_signal(ind["rsi"]),
        macd_signal(ind["macd"], ind["macd_signal"], ind["macd_hist"], atr),
        bollinger_signal(close, ind["bb_upper"], ind["bb_mid"], ind["bb_lower"]),
        volume_signal(close, volume, atr),
        levels_signal(close, high, low, atr),
    ]
    return [s for s in found if s]


def worked(vote, actual: str) -> bool | None:
    if vote is None:
        return None
    if vote == MOVE:
        return actual != FLAT
    return vote == actual


def consensus(sigs: list[dict], actual: str) -> dict:
    votes = [s["vote"] for s in sigs]
    up, down, move = votes.count(UP), votes.count(DOWN), votes.count(MOVE)
    if up > down and up >= 2:
        lean = UP
    elif down > up and down >= 2:
        lean = DOWN
    else:
        lean = None
    if lean:
        text = f"Перевес сигналов — {VOTE_LABELS[lean]}: {max(up, down)} против {min(up, down)}."
    else:
        text = "Явного перевеса не было: сигналы спорили друг с другом или молчали."
    return {
        "up": up, "down": down, "move": move, "neutral": votes.count(None),
        "lean": lean, "matched": None if lean is None else lean == actual, "text": text,
    }


# ─── Что случилось в будущем ──────────────────────────────────────────────────

def story(rd: RoundData) -> dict:
    """Ключевые моменты будущего: экстремумы, сильные свечи, события, пробои."""
    c = rd.candles
    close, high, low = (c[k].to_numpy(dtype=float) for k in ("close", "high", "low"))
    last, atr = rd.last_close, max(rd.atr, 1e-9)
    end = H + F - 1
    rel = lambda i: int(i - (H - 1))  # номер свечи будущего: 1..F  # noqa: E731
    items: list[dict] = []

    # Экстремумы пути; на последней свече их уже покрывает строка итога.
    k_hi = H + int(np.argmax(high[H:]))
    k_lo = H + int(np.argmin(low[H:]))
    up_pct, dn_pct = (high[k_hi] / last - 1) * 100, (low[k_lo] / last - 1) * 100
    if high[k_hi] - last >= 0.5 * atr and k_hi < end:
        items.append({"bar": rel(k_hi), "tone": "pos",
                      "text": f"Самая высокая точка: {_pct(up_pct)} от цены прогноза."})
    if last - low[k_lo] >= 0.5 * atr and k_lo < end:
        items.append({"bar": rel(k_lo), "tone": "neg",
                      "text": f"Самая низкая точка: {_pct(dn_pct)} от цены прогноза."})

    steps = close[H:] - close[H - 1:end]
    k_big = int(np.argmax(np.abs(steps)))
    big = None
    if abs(steps[k_big]) >= BIG_BAR_ATR * atr:
        i = H + k_big
        big = {"bar": rel(i), "pct": (close[i] / close[i - 1] - 1) * 100, "atr": steps[k_big] / atr}
        items.append({"bar": big["bar"], "tone": "pos" if big["atr"] > 0 else "neg",
                      "text": f"Самая сильная свеча: {_pct(big['pct'])} за одну свечу "
                              f"({_num(big['atr'], 1, ' ATR')})."})

    reactions = []
    for ev in rd.events:
        b = ev["bar"]
        if b < H:
            continue
        j = min(b + REACTION_BARS - 1, end)
        chg = (close[j] / close[b - 1] - 1) * 100
        chg_atr = (close[j] - close[b - 1]) / atr
        n = j - b + 1
        title = ev["title"].rstrip(".")
        reactions.append({"bar": rel(b), "type": ev["type"], "title": title,
                          "pct": chg, "atr": chg_atr, "n": n})
        items.append({"bar": rel(b), "tone": "event",
                      "text": f"{title}. За {_bars(n)} с этого момента: {_pct(chg)}."})

    vis_hi, vis_lo = high[:H].max(), low[:H].min()
    breakout = None
    for i in range(H, end + 1):
        if close[i] > vis_hi:
            breakout = {"bar": rel(i), "dir": UP}
            items.append({"bar": rel(i), "tone": "pos", "text": "Закрытие выше максимума видимой части — пробой вверх."})
            break
        if close[i] < vis_lo:
            breakout = {"bar": rel(i), "dir": DOWN}
            items.append({"bar": rel(i), "tone": "neg", "text": "Закрытие ниже минимума видимой части — пробой вниз."})
            break

    f, s = config.MA_PERIODS
    diff = rd.indicators_full["ma1"] - rd.indicators_full["ma2"]
    for i in range(H, end + 1):
        a, b = diff[i - 1], diff[i]
        if np.isfinite(a) and np.isfinite(b) and b != 0 and np.sign(a) != np.sign(b):
            way = "снизу вверх" if b > 0 else "сверху вниз"
            items.append({"bar": rel(i), "tone": "pos" if b > 0 else "neg",
                          "text": f"MA {f} пересекла MA {s} {way} — смена тренда по средним."})
            break

    final = close[end]
    change_pct = (final / last - 1) * 100
    change_atr = (final - last) / atr
    actual = classify_move(last, final, rd.atr, config.SIDEWAYS_ATR_MULT)
    items.sort(key=lambda x: x["bar"])
    items.append({"bar": F, "tone": "pos" if change_pct > 0 else "neg" if change_pct < 0 else "event",
                  "text": f"Итог за {_bars(F)}: {_pct(change_pct)} ({_num(change_atr, 1, ' ATR')}) — "
                          f"{OUTCOME_LABELS[actual].lower()}.", "final": True})
    return {
        "items": items, "events": reactions, "big": big, "breakout": breakout,
        "change_pct": change_pct, "change_atr": change_atr, "actual": actual,
        # Как далеко цена уходила по пути — исход считается по закрытию последней свечи,
        # и боковик в итоге не значит, что цена всё время была в коридоре.
        "max_up_atr": float(high[H:].max() - last) / atr,
        "max_dn_atr": float(last - low[H:].min()) / atr,
    }


# ─── Объяснение и выводы ──────────────────────────────────────────────────────

def explain(sigs: list[dict], st: dict, cons: dict) -> tuple[str, str]:
    """Заголовок и главная версия того, что двигало ценой."""
    actual = st["actual"]
    by_id = {s["id"]: s for s in sigs}
    if actual == FLAT:
        band = config.SIDEWAYS_ATR_MULT
        up, dn = st.get("max_up_atr", 0.0), st.get("max_dn_atr", 0.0)
        result = f"итог за {_bars(F)} — {_num(st['change_atr'], 1, ' ATR')} при пороге ±{band:g} ATR"
        outside = [x for x in (f"вверх до {_num(up, 1, ' ATR')}" if up >= band else "",
                               f"вниз до {_num(-dn, 1, ' ATR')}" if dn >= band else "") if x]
        if outside:
            text = (f"По пути цену выносило за коридор — {' и '.join(outside)}, но движение не удержалось: "
                    f"{result}. Исход считается по закрытию последней свечи, поэтому итог — боковик.")
            if cons["lean"] is not None:
                text += f" Сигналы были {VOTE_LABELS[cons['lean']]}."
            return "Почему в итоге боковик", text
        text = f"Цена всё время держалась в коридоре: {result}."
        if cons["lean"] is None:
            text += " Сигналы и до этого спорили друг с другом — сильного импульса ждать было неоткуда."
        else:
            text += f" Сигналы были {VOTE_LABELS[cons['lean']]}, но силы на выход из коридора не хватило."
        return "Почему цена осталась в коридоре", text

    title = f"Почему цена пошла {MOVE_WORDS[actual]}"
    sign = 1 if actual == UP else -1

    for ev in st["events"]:
        share = ev["atr"] / st["change_atr"] if st["change_atr"] else 0
        if (ev["type"] in DRIVER_EVENTS and abs(ev["atr"]) >= BIG_BAR_ATR and np.sign(ev["atr"]) == sign
                and share >= EVENT_SHARE):
            return title, (
                f"Главное движение совпало с событием на свече +{ev['bar']}: {ev['title']}. "
                f"За {_bars(ev['n'])} цена изменилась на {_pct(ev['pct'])}. Индикаторы новости не предсказывают, "
                "но дата события была отмечена на графике заранее — это повод ставить уверенность пониже."
            )

    big = st["big"]
    share = big["atr"] / st["change_atr"] if big and st["change_atr"] else 0
    if big and abs(big["atr"]) >= SHOCK_BAR_ATR and share >= SHOCK_SHARE:
        lead = "Почти всё движение" if share >= 0.8 else "Больше половины движения"
        return title, (
            f"{lead} дала одна свеча +{big['bar']}: {_pct(big['pct'])} за раз. Такие рывки обычно "
            "вызывает новость, которой нет на графике, — по индикаторам их не предугадать."
        )

    trend, bb = by_id.get("trend"), by_id.get("bb")
    br = st["breakout"]
    breakout_note = ""
    if br and br["dir"] == actual:
        breakout_note = (f" На свече +{br['bar']} цена ещё и пробила "
                         f"{'максимум' if actual == UP else 'минимум'} видимой части.")

    if trend and trend["vote"] == actual:
        return title, ("Тренд продолжился: цена была " + ("выше" if actual == UP else "ниже")
                       + " обеих средних, и рынок пошёл дальше в ту же сторону." + breakout_note)
    if br and br["dir"] == actual:
        return title, (f"Пробой: на свече +{br['bar']} цена закрылась "
                       f"{'выше максимума' if actual == UP else 'ниже минимума'} видимой части, "
                       "и после этого движение продолжилось.")

    contra = [s for s in (by_id.get("rsi"), bb) if s and s.get("extreme") and s["vote"] == actual]
    if contra:
        what = []
        for s in contra:
            if s["id"] == "rsi":
                what.append(f"RSI был {s['level']:.0f}")
            else:
                what.append("цена стояла у " + ("нижней" if actual == UP else "верхней") + " границы коридора")
        return title, (f"Сработал откат от перегрева: {' и '.join(what)}. Цена убежала слишком далеко "
                       "и вернулась назад.")

    if bb and bb.get("squeeze"):
        return title, ("Перед прогнозом коридор Боллинджера был сжат — после такого затишья часто бывает "
                       f"сильное движение. Оно и случилось, но направление ({MOVE_WORDS[actual]}) "
                       "сжатие не подсказывало.")

    macd = by_id.get("macd")
    if macd and macd["vote"] == actual:
        return title, f"Сработал импульс: MACD показывал движение {MOVE_WORDS[actual]}, и оно продолжилось."

    if cons["lean"] and cons["lean"] != actual:
        return title, ("Цена пошла против большинства сигналов. Так бывает: индикаторы описывают прошлое "
                       "и дают перевес вероятностей, а не гарантию.")
    return title, "Явного перевеса сигналов не было — в таких ситуациях исход близок к монетке."


def quick_lessons(answer: dict, outcome: dict, cons: dict, sigs: list[dict], actual: str) -> list[str]:
    choice, conf, correct = answer["choice"], answer["confidence"], bool(outcome["correct"])
    lean = cons["lean"]
    out = []
    if correct and lean == choice:
        out.append("Ты прочитал график так же, как большинство сигналов, — и это сработало.")
    elif correct and lean is None:
        out.append("Угадал при спорных сигналах. Спроси себя: было ли основание или повезло?")
    elif correct:
        out.append("Угадал против перевеса сигналов. Если была своя причина — запомни её, если нет — это удача.")
    elif lean == actual:
        out.append(f"Большинство сигналов было {VOTE_LABELS[lean]}, и цена пошла туда. "
                   "Перед ответом сверяйся со всеми индикаторами, а не с одним.")
    elif lean is None:
        out.append("Сигналы спорили друг с другом. В таких раундах честнее ставить уверенность ближе к 50% — "
                   "промах обойдётся почти без потерь.")
    else:
        out.append("Сигналы указывали в одну сторону, а цена пошла в другую. Это нормально: "
                   "даже хороший перевес срабатывает не всегда.")

    if not correct and conf >= 80:
        out.append(f"Уверенность {conf}% обошлась в {abs(outcome['points'])} очков. Высокую уверенность стоит "
                   "ставить, только когда сигналы смотрят в одну сторону.")
    if actual == FLAT and choice != FLAT:
        out.append(f"Чтобы выйти из коридора ±{config.SIDEWAYS_ATR_MULT:g} ATR, нужен сильный импульс. "
                   "Боковик выпадает примерно в трети раундов — не забывай про него.")
    elif actual != FLAT and choice == FLAT:
        # Направленные подсказки и «будет сильное движение» — разные вещи, не смешиваем.
        name = lambda s: s["title"].split(" · ")[0]  # noqa: E731
        directed = [name(s) for s in sigs if s["vote"] == actual]
        moves = [name(s) for s in sigs if s["vote"] == MOVE]
        parts = []
        if directed:
            parts.append(f"движение {MOVE_WORDS[actual]} подсказывали: {', '.join(directed)}")
        if moves:
            parts.append(f"что будет сильное движение (без направления), предупреждал{'и' if len(moves) > 1 else ''}: "
                         f"{', '.join(moves)}")
        if parts:
            out.append(f"Ты ждал боковика, а {'; '.join(parts)}.")
    return out[:3]


def typical_move(rd: RoundData, long: bool, against: bool) -> float | None:
    """Медиана хода цены за F свечей против позиции (against) или в её сторону, в ATR.

    Считается только по видимой части: для каждой видимой свечи — насколько
    цена уходила вниз и вверх за следующие F свечей. Это «обычный ход» именно
    этой бумаги в этом окне — игрок мог оценить его до входа, поэтому
    сравнивать с ним стоп и тейк честно (и подсказывать его до ответа).
    """
    v = rd.visible
    close, high, low = (v[k].to_numpy(dtype=float) for k in ("close", "high", "low"))
    atr = max(rd.atr, 1e-9)
    moves = []
    for t in range(len(close) - F):
        nxt = slice(t + 1, t + 1 + F)
        down, up = close[t] - low[nxt].min(), high[nxt].max() - close[t]
        move = (down if against else up) if long else (up if against else down)
        moves.append(max(move, 0.0))
    if len(moves) < 10:
        return None
    return float(np.median(moves)) / atr


def typical_pullback(rd: RoundData, long: bool) -> float | None:
    """Обычный откат против позиции за F свечей (см. typical_move)."""
    return typical_move(rd, long, against=True)


def trade_lessons(rd: RoundData, answer: dict, outcome: dict, cons: dict) -> list[str]:
    long = answer["direction"] == "long"
    sign = 1 if long else -1
    entry, stop, take = answer["entry"], answer["stop"], answer["take"]
    risk = (entry - stop) * sign
    atr = max(rd.atr, 1e-9)
    fut = rd.future
    favorable = (fut["high"] if long else fut["low"]).to_numpy(dtype=float)
    k, reason, r = int(outcome["exit_bar"]), outcome["reason"], float(outcome["r"])
    stop_atr, take_atr = risk / atr, (take - entry) * sign / atr

    out = []
    side = "лонг" if long else "шорт"
    want = UP if long else DOWN
    if cons["lean"] and cons["lean"] != want:
        out.append(f"Ты зашёл в {side}, хотя перевес сигналов был {VOTE_LABELS[cons['lean']]}.")
    elif cons["lean"] == want:
        out.append("Направление сделки совпало с перевесом сигналов.")

    if reason == "stop":
        before = favorable[:k]
        mfe = float(((before - entry) * sign).max()) / risk if len(before) else 0.0
        later = favorable[k + 1:]
        noise = typical_pullback(rd, long)
        in_noise = stop_atr < 0.8 * noise if noise else stop_atr < 0.8
        noise_note = (f"в половине случаев цена за {_bars(F)} уходит против {side}а дальше, чем на "
                      f"{noise:.1f} ATR (по видимой части графика)" if noise
                      else "это меньше среднего размаха одной свечи")
        if len(later) and float(((later - take) * sign).max()) >= 0:
            if in_noise:
                out.append(f"Стоп выбило, а потом цена дошла до тейка. Стоп стоял в {stop_atr:.1f} ATR, а "
                           f"{noise_note}: его выбил обычный шум, а не разворот.")
            else:
                out.append(f"Стоп выбило, а потом цена всё-таки дошла до тейка: направление было верным, "
                           f"но откат вышел глубже {stop_atr:.1f} ATR. Так бывает — иногда помогает вход после отката.")
        elif in_noise:
            out.append(f"Стоп стоял в {stop_atr:.1f} ATR, а {noise_note}. "
                       "Такой стоп чаще выбивает шум, чем настоящий разворот.")
        elif mfe >= 1:
            out.append(f"До стопа цена успела побывать в плюсе на {_num(mfe, 1, 'R')} и развернулась. "
                       "Решай заранее, что делать с открытой прибылью: держать до тейка, фиксировать часть "
                       "или подтягивать стоп, — по одной сделке правило не выбрать.")
        else:
            out.append("Цена сразу пошла против позиции — стоп сделал свою работу и ограничил убыток.")
    elif reason == "take":
        out.append(f"Тейк сработал на свече +{k + 1}: риск в 1R принёс {_num(r, 1, 'R')}.")
    else:
        path = (favorable - entry) * sign
        mfe = float(path.max()) / risk
        run = typical_move(rd, long, against=False)
        far = take_atr > 1.5 * run if run else take_atr > 3
        if mfe >= 1 and r < mfe - 0.5:
            out.append(f"По ходу сделки цена была в плюсе на {_num(mfe, 1, 'R')}, а закрылась на {_num(r, 1, 'R')}: "
                       f"до тейка в {take_atr:.1f} ATR за {_bars(F)} не дошла.")
        elif far:
            out.append(f"Тейк в {take_atr:.1f} ATR — далеко для {_bars(F)}: в половине случаев цена за это время "
                       f"проходит в сторону {side}а не больше {run:.1f} ATR (по видимой части графика).")
        else:
            out.append(f"Ни стоп, ни тейк не сработали — сделка закрылась по времени на {_num(r, 1, 'R')}.")
    return out[:3]


def review(rd: RoundData, mode: str, answer: dict, outcome: dict) -> dict:
    """Полный разбор раунда. Вызывать только после ответа: здесь есть будущее."""
    sigs = signals(rd)
    st = story(rd)
    actual = st["actual"]
    for s in sigs:
        s["worked"] = worked(s["vote"], actual)
    cons = consensus(sigs, actual)
    title, why = explain(sigs, st, cons)
    lessons = (quick_lessons(answer, outcome, cons, sigs, actual) if mode == "quick"
               else trade_lessons(rd, answer, outcome, cons))
    return {
        "actual": actual,
        "actual_label": OUTCOME_LABELS[actual],
        "change_pct": round(float(st["change_pct"]), 2),
        "title": title,
        "why": why,
        "signals": sigs,
        "consensus": cons,
        "timeline": st["items"],
        "lessons": lessons,
    }
