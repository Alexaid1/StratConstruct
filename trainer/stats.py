"""Статистика игрока по журналу попыток. Чистые функции — без Streamlit."""

from __future__ import annotations

import math
from collections import Counter

import pandas as pd

from trainer import config
from trainer.scoring import OUTCOME_LABELS, OUTCOMES

CONF_BUCKETS = [(50, 59), (60, 69), (70, 79), (80, 89), (90, 100)]


def wilson(hits: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """95% доверительный интервал доли (Уилсон) — честнее «±» на малых выборках."""
    if n == 0:
        return None
    p = hits / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


# ─── Быстрый режим ────────────────────────────────────────────────────────────

def quick_stats(attempts: list[dict]) -> dict:
    """Попадания против двух баз и калибровка уверенности.

    База 1 — случайное угадывание: 1/3 при трёх исходах.
    База 2 — «всегда называть самый частый исход» среди сыгранных раундов:
    если рынок в выборке чаще рос, это уже лучше 33%, и бить надо её.
    Brier — средний (уверенность − исход)², 0.25 у того, кто всегда ставит 50%.
    """
    rows = [a for a in attempts if a["mode"] == "quick"]
    n = len(rows)
    if n == 0:
        return {"n": 0}
    hits = sum(bool(a["outcome"]["correct"]) for a in rows)
    actual = Counter(a["outcome"]["actual"] for a in rows)
    majority, majority_n = actual.most_common(1)[0]
    brier = sum(a["outcome"]["brier"] for a in rows) / n

    calibration = []
    for lo, hi in CONF_BUCKETS:
        part = [a for a in rows if lo <= a["answer"]["confidence"] <= hi]
        if part:
            calibration.append({
                "bucket": f"{lo}–{hi}%",
                "confidence": sum(a["answer"]["confidence"] for a in part) / len(part) / 100,
                "hit_rate": sum(bool(a["outcome"]["correct"]) for a in part) / len(part),
                "n": len(part),
            })

    confusion = {c: {o: 0 for o in OUTCOMES} for c in OUTCOMES}
    for a in rows:
        confusion[a["answer"]["choice"]][a["outcome"]["actual"]] += 1

    return {
        "n": n,
        "hits": hits,
        "accuracy": hits / n,
        "ci": wilson(hits, n),
        "base_random": 1 / 3,
        "base_majority": majority_n / n,
        "majority": majority,
        "majority_label": OUTCOME_LABELS[majority],
        "brier": brier,
        "brier_ref": 0.25,
        "points": sum(a["outcome"]["points"] for a in rows),
        "avg_confidence": sum(a["answer"]["confidence"] for a in rows) / n / 100,
        "calibration": calibration,
        "confusion": confusion,
    }


# ─── Режим «Сделка» ───────────────────────────────────────────────────────────

def trade_stats(attempts: list[dict]) -> dict:
    rows = [a for a in attempts if a["mode"] == "trade"]
    n = len(rows)
    if n == 0:
        return {"n": 0}
    rs = [float(a["outcome"]["r"]) for a in rows]
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]
    gross_loss = -sum(losses)
    equity, total = [], 0.0
    for r in rs:
        total += r
        equity.append(round(total, 3))
    return {
        "n": n,
        "total_r": sum(rs),
        "avg_r": sum(rs) / n,
        "win_rate": len(wins) / n,
        "ci": wilson(len(wins), n),
        "avg_win": sum(wins) / len(wins) if wins else None,
        "avg_loss": sum(losses) / len(losses) if losses else None,
        "profit_factor": (sum(wins) / gross_loss) if gross_loss > 0 else None,
        "best": max(rs),
        "worst": min(rs),
        "equity": equity,
        "r_values": rs,
        "reasons": dict(Counter(a["outcome"]["reason"] for a in rows)),
        "points": sum(a["outcome"]["points"] for a in rows),
    }


# ─── Разбивка по тикеру и таймфрейму ──────────────────────────────────────────

def breakdown(attempts: list[dict], mode: str) -> pd.DataFrame:
    """Таблица по тикеру × таймфрейму для выбранного режима."""
    rows = [a for a in attempts if a["mode"] == mode]
    if not rows:
        return pd.DataFrame()
    recs = []
    for a in rows:
        o = a["outcome"]
        recs.append({
            "Тикер": a["ticker"],
            "Таймфрейм": config.TIMEFRAME_LABELS.get(a["timeframe"], a["timeframe"]),
            "win": bool(o["win"]),
            "points": o["points"],
            "brier": o.get("brier"),
            "r": o.get("r"),
        })
    df = pd.DataFrame(recs)
    g = df.groupby(["Тикер", "Таймфрейм"], as_index=False)
    if mode == "quick":
        out = g.agg(Раундов=("win", "size"), Попаданий=("win", "mean"),
                    Brier=("brier", "mean"), Очки=("points", "sum"))
        out["Попаданий"] = (out["Попаданий"] * 100).round(0)
        out["Brier"] = out["Brier"].round(3)
    else:
        out = g.agg(Сделок=("win", "size"), Прибыльных=("win", "mean"),
                    Средний_R=("r", "mean"), Сумма_R=("r", "sum"))
        out["Прибыльных"] = (out["Прибыльных"] * 100).round(0)
        out["Средний_R"] = out["Средний_R"].round(2)
        out["Сумма_R"] = out["Сумма_R"].round(2)
        out = out.rename(columns={"Средний_R": "Средний R", "Сумма_R": "Сумма R"})
    return out.sort_values(out.columns[2], ascending=False).reset_index(drop=True)


def history_table(attempts: list[dict]) -> pd.DataFrame:
    """Журнал для показа: свежие сверху, по-человечески подписанные колонки."""
    recs = []
    for a in reversed(attempts):
        o, ans = a["outcome"], a["answer"]
        if a["mode"] == "quick":
            guess = f"{OUTCOME_LABELS.get(ans.get('choice'), '?')} · {ans.get('confidence')}%"
            result = f"{o.get('actual_label', '')} {o.get('change_pct', 0):+.2f}%"
            score = f"{o['points']:+d} очк."
        else:
            guess = f"{'Лонг' if ans.get('direction') == 'long' else 'Шорт'} · R:R 1:{o.get('planned_rr', 0):.1f}"
            reason = {"take": "тейк", "stop": "стоп", "close": "по закрытию"}.get(o.get("reason"), "")
            result = f"{reason} · {o.get('pnl_pct', 0):+.2f}%"
            score = f"{o.get('r', 0):+.2f}R"
        recs.append({
            "Когда": a["ts"].replace("T", " ")[:16],
            "Режим": "Быстрый" if a["mode"] == "quick" else "Сделка",
            "Бумага": a["ticker"],
            "ТФ": config.TIMEFRAME_LABELS.get(a["timeframe"], a["timeframe"]),
            "Период": a.get("period") or "",
            "Прогноз": guess,
            "Итог": result,
            "Счёт": score,
            "✓": "✅" if a["win"] else "✖️",
        })
    return pd.DataFrame(recs)
