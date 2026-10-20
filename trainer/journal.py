"""Журнал попыток: SQLite + выгрузка и загрузка CSV.

Каждая попытка привязана к анонимному id браузера (его хранит игровой
компонент в localStorage), поэтому у каждого игрока своя статистика без
регистрации. На Streamlit Cloud файл базы живёт до перезапуска приложения —
для надёжности журнал можно выгрузить в CSV и потом загрузить обратно.
"""

from __future__ import annotations

import csv
import io
import json
import sqlite3
import threading
from pathlib import Path

from trainer import config

# Плоские колонки — для фильтров и сортировки; полные ответ, исход и
# рисунки лежат JSON-ом, так новые режимы не требуют миграций.
COLUMNS = [
    "id", "player_id", "ts", "mode", "ticker", "timeframe", "start_time", "seed",
    "period", "show_identity", "win", "points", "answer", "outcome", "drawings",
]
JSON_COLUMNS = {"answer", "outcome", "drawings"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS attempts (
    id            TEXT PRIMARY KEY,
    player_id     TEXT NOT NULL,
    ts            TEXT NOT NULL,
    mode          TEXT NOT NULL,
    ticker        TEXT NOT NULL,
    timeframe     TEXT NOT NULL,
    start_time    TEXT NOT NULL,
    seed          INTEGER,
    period        TEXT,
    show_identity INTEGER NOT NULL DEFAULT 0,
    win           INTEGER NOT NULL,
    points        INTEGER NOT NULL,
    answer        TEXT NOT NULL,
    outcome       TEXT NOT NULL,
    drawings      TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS attempts_player ON attempts (player_id, ts);
"""


class Journal:
    def __init__(self, path: Path | str = config.JOURNAL_DB):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(self.path, check_same_thread=False, timeout=10)
        self._db.row_factory = sqlite3.Row
        with self._lock:
            self._db.executescript(SCHEMA)

    # ─── запись ──────────────────────────────────────────────────────────────

    def add(self, attempt: dict) -> None:
        row = self._to_row(attempt)
        with self._lock, self._db:
            self._db.execute(
                f"INSERT OR IGNORE INTO attempts ({', '.join(COLUMNS)}) "
                f"VALUES ({', '.join('?' * len(COLUMNS))})",
                [row[c] for c in COLUMNS],
            )

    def update_drawings(self, attempt_id: str, drawings: list) -> None:
        with self._lock, self._db:
            self._db.execute("UPDATE attempts SET drawings = ? WHERE id = ?",
                             (json.dumps(drawings, ensure_ascii=False), attempt_id))

    # ─── чтение ──────────────────────────────────────────────────────────────

    def attempts(self, player_id: str) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM attempts WHERE player_id = ? ORDER BY ts, rowid", (player_id,)
            ).fetchall()
        return [self._from_row(dict(r)) for r in rows]

    # ─── CSV ─────────────────────────────────────────────────────────────────

    def export_csv(self, player_id: str) -> bytes:
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=COLUMNS)
        w.writeheader()
        for a in self.attempts(player_id):
            w.writerow(self._to_row(a))
        # BOM — чтобы Excel сразу открыл кириллицу правильно.
        return ("﻿" + buf.getvalue()).encode("utf-8")

    def import_csv(self, player_id: str, data: bytes) -> int:
        """Загрузить журнал из CSV в профиль игрока. Возвращает число новых попыток.

        Попытки с уже известным id пропускаются, поэтому повторная загрузка
        того же файла ничего не дублирует.
        """
        text = data.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        missing = set(COLUMNS) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"в файле нет колонок: {', '.join(sorted(missing))}")
        before = self.count(player_id)
        for raw in reader:
            attempt = self._from_row(dict(raw))
            attempt["player_id"] = player_id
            self.add(attempt)
        return self.count(player_id) - before

    def count(self, player_id: str) -> int:
        with self._lock:
            return self._db.execute("SELECT COUNT(*) FROM attempts WHERE player_id = ?",
                                    (player_id,)).fetchone()[0]

    # ─── преобразования ──────────────────────────────────────────────────────

    @staticmethod
    def _to_row(a: dict) -> dict:
        outcome = a.get("outcome") or {}
        row = {c: a.get(c) for c in COLUMNS}
        row["win"] = int(bool(a.get("win", outcome.get("win", False))))
        row["points"] = int(a.get("points", outcome.get("points", 0)) or 0)
        row["show_identity"] = int(bool(a.get("show_identity")))
        for c in JSON_COLUMNS:
            v = a.get(c)
            row[c] = v if isinstance(v, str) else json.dumps(v if v is not None else ([] if c == "drawings" else {}),
                                                             ensure_ascii=False)
        return row

    @staticmethod
    def _from_row(r: dict) -> dict:
        out = dict(r)
        for c in JSON_COLUMNS:
            v = out.get(c)
            out[c] = json.loads(v) if isinstance(v, str) and v else ([] if c == "drawings" else {})
        out["seed"] = int(out["seed"]) if out.get("seed") not in (None, "") else None
        out["show_identity"] = bool(int(out.get("show_identity") or 0))
        out["win"] = bool(int(out.get("win") or 0))
        out["points"] = int(out.get("points") or 0)
        return out
