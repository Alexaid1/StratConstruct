"""Журнал попыток (SQLite + CSV) и статистика игрока."""

import pytest

from trainer.journal import Journal
from trainer.scoring import quick_brier
from trainer.stats import breakdown, history_table, quick_stats, trade_stats, wilson


def quick_attempt(i, choice, actual, conf, player="p1", ticker="SBER", tf="1d"):
    correct = choice == actual
    p = conf / 100
    brier = (p - correct) ** 2
    return {
        "id": f"q{i}-{player}", "player_id": player, "ts": f"2026-10-20T10:{i:02d}:00", "mode": "quick",
        "ticker": ticker, "timeframe": tf, "start_time": "2020-01-01 00:00:00", "seed": i,
        "period": "01.01.2020 — 01.06.2020", "show_identity": False,
        "answer": {"choice": choice, "confidence": conf},
        "outcome": {"actual": actual, "actual_label": actual, "correct": correct, "win": correct,
                    "brier": brier, "points": round((0.25 - brier) * 400), "change_pct": 1.0},
        "drawings": [{"type": "level", "price": 101.5}],
    }


def trade_attempt(i, r, reason, player="p1", ticker="LKOH"):
    return {
        "id": f"t{i}-{player}", "player_id": player, "ts": f"2026-10-20T11:{i:02d}:00", "mode": "trade",
        "ticker": ticker, "timeframe": "1h", "start_time": "2024-01-01 10:00:00", "seed": i,
        "period": "", "show_identity": False,
        "answer": {"direction": "long", "entry": 100, "stop": 99, "take": 102},
        "outcome": {"r": r, "reason": reason, "win": r > 0, "points": round(r * 100),
                    "planned_rr": 2.0, "pnl_pct": r},
        "drawings": [],
    }


# ─── Журнал ───────────────────────────────────────────────────────────────────

@pytest.fixture
def journal(tmp_path):
    return Journal(tmp_path / "j.sqlite")


def test_add_and_read_back(journal):
    a = quick_attempt(1, "up", "up", 70)
    journal.add(a)
    [b] = journal.attempts("p1")
    assert b["answer"] == a["answer"] and b["outcome"]["correct"] is True
    assert b["drawings"] == a["drawings"] and b["win"] is True and b["points"] == a["outcome"]["points"]


def test_players_are_isolated(journal):
    journal.add(quick_attempt(1, "up", "up", 70, player="p1"))
    journal.add(quick_attempt(2, "up", "down", 70, player="p2"))
    assert len(journal.attempts("p1")) == 1 and len(journal.attempts("p2")) == 1


def test_duplicate_id_is_ignored(journal):
    a = quick_attempt(1, "up", "up", 70)
    journal.add(a)
    journal.add(a)
    assert journal.count("p1") == 1


def test_update_drawings(journal):
    a = quick_attempt(1, "up", "up", 70)
    journal.add(a)
    journal.update_drawings(a["id"], [{"type": "trend", "i1": 1, "p1": 100, "i2": 5, "p2": 102}])
    assert journal.attempts("p1")[0]["drawings"][0]["type"] == "trend"


def test_csv_roundtrip_restores_journal(journal, tmp_path):
    for i, (c, act) in enumerate([("up", "up"), ("down", "flat"), ("flat", "flat")]):
        journal.add(quick_attempt(i, c, act, 60 + i * 10))
    journal.add(trade_attempt(9, -1.0, "stop"))
    data = journal.export_csv("p1")
    assert data.startswith("﻿".encode("utf-8"))      # Excel открывает кириллицу

    fresh = Journal(tmp_path / "other.sqlite")
    assert fresh.import_csv("new-browser", data) == 4
    assert fresh.import_csv("new-browser", data) == 0      # повторная загрузка не дублирует
    restored = fresh.attempts("new-browser")
    assert [a["id"] for a in restored] == [a["id"] for a in journal.attempts("p1")]
    assert restored[-1]["outcome"]["reason"] == "stop"


def test_import_rejects_foreign_csv(journal):
    with pytest.raises(ValueError, match="нет колонок"):
        journal.import_csv("p1", "a,b\n1,2\n".encode("utf-8"))


# ─── Статистика ───────────────────────────────────────────────────────────────

def test_wilson_interval():
    lo, hi = wilson(5, 10)
    assert lo == pytest.approx(0.237, abs=0.01) and hi == pytest.approx(0.763, abs=0.01)
    assert wilson(0, 0) is None
    lo, hi = wilson(10, 10)
    assert hi == 1.0 and lo > 0.6


def test_quick_stats_baselines_and_brier():
    rows = [
        quick_attempt(1, "up", "up", 90),
        quick_attempt(2, "up", "up", 60),
        quick_attempt(3, "down", "up", 80),
        quick_attempt(4, "flat", "flat", 50),
    ]
    s = quick_stats(rows)
    assert s["n"] == 4 and s["hits"] == 3 and s["accuracy"] == 0.75
    assert s["base_random"] == pytest.approx(1 / 3)
    assert s["majority"] == "up"
    assert s["base_majority"] is None          # на 4 раундах база «всегда вверх» только путает
    # Brier пересчитывается по трём исходам из ответа — и для старых записей тоже.
    expected_brier = (quick_brier(90, True) + quick_brier(60, True) + quick_brier(80, False)
                      + quick_brier(50, True)) / 4
    assert s["brier"] == pytest.approx(expected_brier)
    assert s["brier_ref"] == pytest.approx(2 / 3)
    assert s["confusion"]["down"]["up"] == 1


def test_majority_baseline_appears_after_ten_rounds():
    rows = [quick_attempt(i, "up", "up" if i < 7 else "down", 60) for i in range(10)]
    assert quick_stats(rows)["base_majority"] == pytest.approx(0.7)


def test_rounds_to_prove_an_edge():
    from trainer.stats import rounds_to_prove

    assert rounds_to_prove(1, 5, 1 / 3) is None            # 20% — не лучше «наугад»
    m = rounds_to_prove(5, 10, 1 / 3)                      # 50% на 10 раундах — пока может быть везение
    assert m is not None and m > 10
    lo, _ = wilson(round(0.5 * m), m)
    assert lo > 1 / 3 and wilson(round(0.5 * (m - 1)), m - 1)[0] <= 1 / 3 + 0.02


def test_trade_stats_mean_interval():
    rows = [trade_attempt(i, r, "close") for i, r in enumerate([0.29, 0.86, 0.87])]   # сделки тестировщицы
    lo, hi = trade_stats(rows)["avg_r_ci"]
    assert lo < 0 < hi                                     # три сделки в плюс — ещё не система
    assert trade_stats(rows[:1])["avg_r_ci"] is None


def test_calibration_buckets():
    rows = [quick_attempt(i, "up", "up" if i % 2 else "down", 92) for i in range(10)]
    rows += [quick_attempt(20 + i, "up", "up", 55) for i in range(4)]
    cal = {c["bucket"]: c for c in quick_stats(rows)["calibration"]}
    assert cal["90–100%"]["n"] == 10 and cal["90–100%"]["hit_rate"] == 0.5   # самоуверенность
    assert cal["50–59%"]["hit_rate"] == 1.0
    assert "70–79%" not in cal


def test_trade_stats():
    rows = [trade_attempt(1, 2.0, "take"), trade_attempt(2, -1.0, "stop"), trade_attempt(3, -1.5, "stop"),
            trade_attempt(4, 0.5, "close")]
    s = trade_stats(rows)
    assert s["n"] == 4 and s["total_r"] == pytest.approx(0.0) and s["avg_r"] == pytest.approx(0.0)
    assert s["win_rate"] == 0.5
    assert s["profit_factor"] == pytest.approx(2.5 / 2.5)
    assert s["equity"] == [2.0, 1.0, -0.5, 0.0]
    assert s["reasons"] == {"take": 1, "stop": 2, "close": 1}


def test_empty_stats():
    assert quick_stats([])["n"] == 0 and trade_stats([])["n"] == 0
    assert breakdown([], "quick").empty


def test_breakdown_by_ticker_and_timeframe():
    rows = [quick_attempt(1, "up", "up", 70, ticker="SBER"), quick_attempt(2, "up", "down", 70, ticker="SBER"),
            quick_attempt(3, "up", "up", 70, ticker="YDEX", tf="1h")]
    df = breakdown(rows, "quick")
    sber = df[df["Тикер"] == "SBER"].iloc[0]
    assert sber["Раундов"] == 2 and sber["Попаданий"] == 50
    t = breakdown([trade_attempt(1, 2.0, "take"), trade_attempt(2, -1.0, "stop")], "trade")
    assert t.iloc[0]["Сумма R"] == 1.0


def test_history_table_newest_first():
    rows = [quick_attempt(1, "up", "up", 70), trade_attempt(2, -1.0, "stop")]
    for r in rows:
        r["win"], r["points"] = r["outcome"]["win"], r["outcome"]["points"]
    t = history_table(rows)
    assert list(t["Режим"]) == ["Сделка", "Быстрый"]
    assert t.iloc[0]["Счёт"] == "-1.00R"
