"""Раздел «Тренажёр трейдера».

Страница держит состояние раунда и принимает события из игрового
компонента. Вся логика (раунды, исходы, режимы) — в пакете trainer/,
здесь только склейка с интерфейсом.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

import streamlit as st

from analytics.telegram import track
from trainer import analysis, config, ui_stats
from trainer.chart import game
from trainer.journal import Journal
from trainer.modes import MIN_DISTANCE_ATR, MODES, AnswerError, mode_cards
from trainer.rounds import identity, predict_payload, reveal_payload
from trainer.selection import pick_round
from trainer.ui import footer_html, hero_html, page_css

GAME_KEY = "trainer_game"
ss = st.session_state
log = logging.getLogger(__name__)


@st.cache_resource
def journal() -> Journal:
    """Одна база на процесс — общая для всех сессий, строки разделены по игрокам."""
    return Journal()


def set_player(player_id: str) -> None:
    """Браузер представился: подтянуть его журнал (и дописать туда то,
    что успели сыграть до знакомства)."""
    if not player_id or ss.tr_player == player_id:
        return
    ss.tr_player = player_id
    j = journal()
    for a in ss.tr_attempts:
        a["player_id"] = player_id
        j.add(a)
    ss.tr_attempts = j.attempts(player_id)


# ─── Состояние ────────────────────────────────────────────────────────────────

def init_state() -> None:
    defaults = {
        "tr_mode": "quick",
        "tr_attempts": [],          # все попытки игрока (из журнала + новые)
        "tr_last_eid": None,
        "tr_player": None,
        "tr_error": None,
        "tr_error_id": None,
        "tr_tickers": list(config.TICKERS),
        "tr_timeframes": list(config.TIMEFRAMES),
        "tr_show_identity": False,
        "tr_review": None,
    }
    for k, v in defaults.items():
        ss.setdefault(k, v)
    if "tr_round" not in ss:
        new_round()


def new_round() -> None:
    prev = ss.get("tr_round")
    if prev is not None:
        ss.tr_recent = ([prev.spec.ticker] + [t for t in ss.get("tr_recent", []) if t != prev.spec.ticker])[:3]
    pool = list(ss.tr_tickers or config.TICKERS)
    # Одна и та же бумага подряд выглядит как сбой: последние три пропускаем,
    # пока в фильтре остаётся из чего выбрать.
    fresh = [t for t in pool if t not in ss.get("tr_recent", [])]
    tickers = fresh or [t for t in pool if not ss.get("tr_recent") or t != ss.tr_recent[0]] or pool
    try:
        _, ss.tr_round = pick_round(tickers=tickers, timeframes=ss.tr_timeframes or None)
    except ValueError:
        # Под выбранные фильтры нет данных — играем на всех бумагах.
        _, ss.tr_round = pick_round()
    ss.tr_phase = "predict"
    ss.tr_answer = None
    ss.tr_outcome = None
    ss.tr_review = None
    ss.tr_drawings = []
    ss.tr_round_show_identity = ss.tr_show_identity


def mode_attempts(mode: str) -> list[dict]:
    return [a for a in ss.tr_attempts if a["mode"] == mode]


def apply_settings(data: dict) -> None:
    """Фильтры раундов из настроек в игре. Применяются со следующего раунда."""
    tickers = [t for t in data.get("tickers") or [] if t in config.TICKERS]
    timeframes = [tf for tf in data.get("timeframes") or [] if tf in config.TIMEFRAMES]
    ss.tr_tickers = tickers or list(config.TICKERS)
    ss.tr_timeframes = timeframes or list(config.TIMEFRAMES)
    ss.tr_show_identity = bool(data.get("show_identity"))


def settings_state() -> dict:
    return {
        "tickers": [{"id": t, "name": config.TICKER_NAMES.get(t, t), "on": t in ss.tr_tickers}
                    for t in config.TICKERS],
        "timeframes": [{"id": tf, "label": config.TIMEFRAME_LABELS[tf].capitalize(), "on": tf in ss.tr_timeframes}
                       for tf in config.TIMEFRAMES],
        "show_identity": bool(ss.tr_show_identity),
    }


def round_review(rd, mode: str, answer: dict, outcome: dict) -> dict | None:
    try:
        return analysis.review(rd, mode, answer, outcome)
    except Exception:
        # Разбор — подсказка, а не часть игры: его сбой не должен ломать раунд.
        log.exception("разбор раунда не собрался")
        return None


# ─── События из игры ──────────────────────────────────────────────────────────

def handle_event(ev: dict | None) -> bool:
    """Обработать событие один раз. True — состояние изменилось."""
    if not ev or ev.get("eid") == ss.tr_last_eid:
        return False
    ss.tr_last_eid = ev.get("eid")
    set_player(ev.get("player_id"))

    kind, data = ev.get("event"), ev.get("data") or {}
    rd = ss.tr_round
    same_round = ev.get("round_id") == rd.id
    if same_round and isinstance(data.get("drawings"), list):
        ss.tr_drawings = data["drawings"][:200]

    if kind == "settings":
        apply_settings(data)
    elif kind == "mode" and data.get("mode") in MODES:
        ss.tr_mode = data["mode"]
        if ss.tr_phase == "reveal":
            new_round()
    elif kind == "answer" and same_round and ss.tr_phase == "predict":
        mode = MODES[ss.tr_mode]
        try:
            answer = mode.parse_answer(data, rd)
        except AnswerError as exc:
            ss.tr_error, ss.tr_error_id = str(exc), uuid.uuid4().hex
            return True
        outcome = mode.evaluate(rd, answer)
        ss.tr_answer, ss.tr_outcome, ss.tr_phase = answer, outcome, "reveal"
        ss.tr_review = round_review(rd, ss.tr_mode, answer, outcome)
        ss.tr_error = None
        attempt = {
            "id": uuid.uuid4().hex,
            "ts": datetime.now().isoformat(timespec="seconds"),
            "player_id": ss.tr_player,
            "mode": ss.tr_mode,
            **rd.spec.to_dict(),
            "period": identity(rd)["period"],
            "show_identity": ss.tr_round_show_identity,
            "win": bool(outcome["win"]),
            "points": int(outcome["points"]),
            "answer": answer,
            "outcome": outcome,
            "drawings": ss.tr_drawings,
        }
        ss.tr_attempts.append(attempt)
        ss.tr_attempt_id = attempt["id"]
        if ss.tr_player:
            journal().add(attempt)
    elif kind == "next" and ss.tr_phase == "reveal":
        # Линии, дорисованные после раскрытия, тоже остаются в журнале.
        if same_round and ss.tr_attempts and ss.tr_attempts[-1]["id"] == ss.get("tr_attempt_id"):
            ss.tr_attempts[-1]["drawings"] = ss.tr_drawings
            if ss.tr_player:
                journal().update_drawings(ss.tr_attempt_id, ss.tr_drawings)
        new_round()
    return True


def import_journal(upload) -> None:
    """Загрузка CSV — один раз на файл (виджет возвращает его при каждом запуске)."""
    marker = (upload.name, upload.size)
    if ss.get("tr_imported") == marker:
        return
    ss.tr_imported = marker
    if not ss.tr_player:
        st.warning("Подожди секунду, пока игра загрузится, и попробуй ещё раз.")
        return
    try:
        added = journal().import_csv(ss.tr_player, upload.getvalue())
    except (ValueError, UnicodeDecodeError) as exc:
        st.error(f"Не получилось прочитать файл: {exc}")
        return
    ss.tr_attempts = journal().attempts(ss.tr_player)
    st.success(f"Готово: добавлено попыток — {added}." if added else "Все попытки из файла уже были в журнале.")


def typical_moves(rd) -> dict:
    """Медианный ход цены против позиции и в её сторону за раунд, в ATR (подсказка к стопу и тейку)."""
    def r1(x):
        return None if x is None else round(x, 1)
    return {
        side: {"against": r1(analysis.typical_move(rd, side == "long", against=True)),
               "with": r1(analysis.typical_move(rd, side == "long", against=False))}
        for side in ("long", "short")
    }


def game_state() -> dict:
    rd, mode = ss.tr_round, ss.tr_mode
    done = mode_attempts(mode)
    summary = MODES[mode].summary(done)
    reveal = ss.tr_phase == "reveal"
    return {
        "mode": mode,
        "modes": mode_cards(),
        "phase": ss.tr_phase,
        "round_no": len(done) + (0 if reveal else 1),
        "payload": reveal_payload(rd) if reveal else predict_payload(rd, ss.tr_round_show_identity),
        "answer": ss.tr_answer,
        "outcome": ss.tr_outcome,
        "summary": summary,
        "summary_prev": MODES[mode].summary(done[:-1]) if reveal else summary,
        # Разбор знает будущее — только после ответа.
        "review": ss.tr_review if reveal else None,
        "settings": settings_state(),
        # Обычный ход цены за раунд — по видимой части, поэтому можно показать до ответа.
        "moves": typical_moves(rd),
        "drawings": ss.tr_drawings,
        "error": ss.tr_error,
        "error_id": ss.tr_error_id,
        "config": {
            "reveal_ms": config.REVEAL_STEP_MS,
            "sideways_mult": config.SIDEWAYS_ATR_MULT,
            "stop_atr": config.DEFAULT_STOP_ATR,
            "take_atr": config.DEFAULT_TAKE_ATR,
            "min_dist_atr": MIN_DISTANCE_ATR * 1.02,  # запас на округление цен в браузере
            "ma": list(config.MA_PERIODS),
            "rsi": config.RSI_PERIOD,
            "macd": list(config.MACD_PARAMS),
            "bb": list(config.BB_PARAMS),
            "atr": config.ATR_PERIOD,
        },
    }


# ─── Страница ─────────────────────────────────────────────────────────────────

init_state()

if "tr_tracked" not in ss:
    ss.tr_tracked = True
    track("trainer_open", "Открыт тренажёр")

# Событие из прошлого запуска — обработать до отрисовки, чтобы игра сразу
# получила новое состояние (без лишнего круга перерисовки).
handle_event(ss.get(GAME_KEY))

# Боковой панели у тренажёра нет: меню разделов — в шапке (см. app.py),
# фильтры раундов — в настройках внутри игры.

# Стили — через st.markdown: st.html выбрасывает <style> с картинкой в data URI.
st.markdown(page_css(), unsafe_allow_html=True)
st.html(hero_html())

value = game(game_state(), key=GAME_KEY)
if handle_event(value):
    st.rerun()

export = journal().export_csv(ss.tr_player) if ss.tr_player and ss.tr_attempts else None
ui_stats.render(ss.tr_attempts, export, import_journal)

st.html(footer_html())
