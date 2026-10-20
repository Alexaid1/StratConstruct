"""Раздел «Тренажёр трейдера».

Страница держит состояние раунда и принимает события из игрового
компонента. Вся логика (раунды, исходы, режимы) — в пакете trainer/,
здесь только склейка с интерфейсом.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import streamlit as st

from analytics.telegram import track
from trainer import config, ui_stats
from trainer.chart import game
from trainer.journal import Journal
from trainer.modes import MIN_DISTANCE_ATR, MODES, AnswerError, mode_cards
from trainer.rounds import build_round, generate_round, identity, predict_payload, reveal_payload
from trainer.ui import footer_html, hero_html, page_css

GAME_KEY = "trainer_game"
ss = st.session_state


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
    }
    for k, v in defaults.items():
        ss.setdefault(k, v)
    if "tr_round" not in ss:
        new_round()


def new_round() -> None:
    spec = generate_round(tickers=ss.tr_tickers or None, timeframes=ss.tr_timeframes or None)
    ss.tr_round = build_round(spec)
    ss.tr_phase = "predict"
    ss.tr_answer = None
    ss.tr_outcome = None
    ss.tr_drawings = []
    ss.tr_round_show_identity = ss.tr_show_identity


def mode_attempts(mode: str) -> list[dict]:
    return [a for a in ss.tr_attempts if a["mode"] == mode]


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

    if kind == "mode" and data.get("mode") in MODES:
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

with st.sidebar:
    st.markdown("### 🎯 Тренажёр")
    st.multiselect(
        "Тикеры", config.TICKERS, key="tr_tickers",
        format_func=lambda t: f"{t} · {config.TICKER_NAMES.get(t, t)}",
        help="Из каких бумаг брать раунды. Пусто — все.",
    )
    st.pills(
        "Таймфреймы", list(config.TIMEFRAMES), key="tr_timeframes", selection_mode="multi",
        format_func=lambda tf: config.TIMEFRAME_LABELS[tf].capitalize(),
    )
    st.toggle(
        "Показывать тикер и даты сразу", key="tr_show_identity",
        help="Лёгкий режим: видно, что за бумага и какой период. Память начнёт подсказывать.",
    )
    st.caption("Фильтры применяются со следующего раунда.")

# Стили — через st.markdown: st.html выбрасывает <style> с картинкой в data URI.
st.markdown(page_css(), unsafe_allow_html=True)
st.html(hero_html())

value = game(game_state(), key=GAME_KEY)
if handle_event(value):
    st.rerun()

export = journal().export_csv(ss.tr_player) if ss.tr_player and ss.tr_attempts else None
ui_stats.render(ss.tr_attempts, export, import_journal)

st.html(footer_html())
