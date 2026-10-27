"""Игровые режимы.

Режим знает три вещи: как проверить ответ игрока, как посчитать исход
раунда и как подвести итог серии попыток. Интерфейс в браузере, раунды
и журнал общие для всех режимов, поэтому новый режим («Событие»,
«Задача дня», «Человек против алгоритма») — это новый класс здесь
плюс кнопка в компоненте.
"""

from __future__ import annotations

from dataclasses import dataclass

from trainer import config
from trainer.rounds import RoundData
from trainer.scoring import (
    CONF_MAX,
    CONF_MIN,
    OUTCOME_LABELS,
    OUTCOMES,
    classify_move,
    quick_brier,
    quick_points,
    trade_outcome,
)

# Стоп и тейк ближе 0.25 ATR — почти гарантированный шум и абсурдные R.
MIN_DISTANCE_ATR = 0.25
MAX_DISTANCE_ATR = 15.0


class AnswerError(ValueError):
    """Ответ игрока не прошёл проверку (сообщение — для показа игроку)."""


@dataclass(frozen=True)
class ModeInfo:
    id: str
    number: str
    title: str
    tagline: str
    available: bool = True


class Mode:
    info: ModeInfo

    def parse_answer(self, data: dict, rd: RoundData) -> dict:
        raise NotImplementedError

    def evaluate(self, rd: RoundData, answer: dict) -> dict:
        raise NotImplementedError

    def summary(self, attempts: list[dict]) -> dict:
        raise NotImplementedError


def _streaks(wins: list[bool]) -> tuple[int, int]:
    """Текущая и лучшая серия побед подряд."""
    best = cur = 0
    for w in wins:
        cur = cur + 1 if w else 0
        best = max(best, cur)
    return cur, best


# ─── Быстрый режим ────────────────────────────────────────────────────────────

class QuickMode(Mode):
    info = ModeInfo("quick", "01", "Быстрый", "Вверх, вниз или боковик?")

    def parse_answer(self, data: dict, rd: RoundData) -> dict:
        choice = data.get("choice")
        if choice not in OUTCOMES:
            raise AnswerError("Выбери направление: вверх, вниз или боковик")
        try:
            confidence = int(data.get("confidence", 0))
        except (TypeError, ValueError):
            raise AnswerError(f"Уверенность — число от {CONF_MIN} до {CONF_MAX}") from None
        if not CONF_MIN <= confidence <= CONF_MAX:
            raise AnswerError(f"Уверенность — от {CONF_MIN} до {CONF_MAX}%")
        return {"choice": choice, "confidence": confidence}

    def evaluate(self, rd: RoundData, answer: dict) -> dict:
        last = rd.last_close
        final = float(rd.future["close"].iloc[-1])
        mult = config.SIDEWAYS_ATR_MULT
        actual = classify_move(last, final, rd.atr, mult)
        correct = bool(answer["choice"] == actual)
        brier = quick_brier(answer["confidence"], correct)
        return {
            "actual": actual,
            "actual_label": OUTCOME_LABELS[actual],
            "choice_label": OUTCOME_LABELS[answer["choice"]],
            "correct": correct,
            "win": correct,
            "brier": round(brier, 4),
            # Правильное правило очков: 0 у ответа «наугад» (33%), +100 за уверенное
            # попадание, −200 за уверенный промах. Переоценивать себя невыгодно.
            "points": quick_points(answer["confidence"], correct),
            "change_pct": round((final / last - 1) * 100, 2),
            "change_atr": round((final - last) / rd.atr, 2),
            "threshold_atr": mult,
            "band": [round(last - mult * rd.atr, 4), round(last + mult * rd.atr, 4)],
        }

    def summary(self, attempts: list[dict]) -> dict:
        wins = [a["outcome"]["win"] for a in attempts]
        cur, best = _streaks(wins)
        n = len(attempts)
        return {
            "rounds": n,
            "hits": sum(wins),
            "accuracy": round(sum(wins) / n * 100) if n else None,
            "points": sum(a["outcome"]["points"] for a in attempts),
            "streak": cur,
            "best_streak": best,
        }


# ─── Режим «Сделка» ───────────────────────────────────────────────────────────

class TradeMode(Mode):
    info = ModeInfo("trade", "02", "Сделка", "Стоп, тейк и результат в R")

    def parse_answer(self, data: dict, rd: RoundData) -> dict:
        direction = data.get("direction")
        if direction not in ("long", "short"):
            raise AnswerError("Выбери направление сделки: лонг или шорт")
        try:
            stop = float(data["stop"])
            take = float(data["take"])
        except (KeyError, TypeError, ValueError):
            raise AnswerError("Укажи стоп и тейк") from None
        entry = rd.last_close
        sign = 1 if direction == "long" else -1
        risk = (entry - stop) * sign
        reward = (take - entry) * sign
        if risk <= 0:
            raise AnswerError("Стоп должен стоять " + ("ниже" if sign > 0 else "выше") + " цены входа")
        if reward <= 0:
            raise AnswerError("Тейк должен стоять " + ("выше" if sign > 0 else "ниже") + " цены входа")
        for name, dist in (("Стоп", risk), ("Тейк", reward)):
            if dist < MIN_DISTANCE_ATR * rd.atr:
                raise AnswerError(f"{name} слишком близко к входу — минимум {MIN_DISTANCE_ATR} ATR")
            if dist > MAX_DISTANCE_ATR * rd.atr:
                raise AnswerError(f"{name} слишком далеко — максимум {MAX_DISTANCE_ATR:g} ATR")
        return {"direction": direction, "entry": round(entry, 4), "stop": stop, "take": take}

    def evaluate(self, rd: RoundData, answer: dict) -> dict:
        future = rd.future[["open", "high", "low", "close"]].to_numpy()
        res = trade_outcome(answer["direction"], answer["entry"], answer["stop"], answer["take"], future)
        sign = 1 if answer["direction"] == "long" else -1
        risk = (answer["entry"] - answer["stop"]) * sign
        planned_rr = (answer["take"] - answer["entry"]) * sign / risk
        return {
            **res.to_dict(),
            "r": round(res.r, 3),
            "win": bool(res.r > 0),
            "points": round(res.r * 100),
            "planned_rr": round(planned_rr, 2),
            "pnl_pct": round((res.exit_price / answer["entry"] - 1) * 100 * sign, 2),
            "entry_real": round(answer["entry"] * rd.scale, 2),
            "exit_real": round(res.exit_price * rd.scale, 2),
        }

    def summary(self, attempts: list[dict]) -> dict:
        rs = [a["outcome"]["r"] for a in attempts]
        wins = [r > 0 for r in rs]
        cur, best = _streaks(wins)
        n = len(rs)
        return {
            "rounds": n,
            "total_r": round(sum(rs), 2),
            "avg_r": round(sum(rs) / n, 2) if n else None,
            "win_rate": round(sum(wins) / n * 100) if n else None,
            "points": sum(a["outcome"]["points"] for a in attempts),
            "streak": cur,
            "best_streak": best,
        }


# ─── Заготовки следующей итерации ─────────────────────────────────────────────

LOCKED = [
    ModeInfo("event", "03", "Событие", "Как рынок отыграет новость", available=False),
    ModeInfo("daily", "04", "Задача дня", "Один раунд на всех", available=False),
    ModeInfo("vs_algo", "05", "Против алгоритма", "Кто точнее — ты или робот", available=False),
]

MODES: dict[str, Mode] = {"quick": QuickMode(), "trade": TradeMode()}


def mode_cards() -> list[dict]:
    """Список режимов для вкладок в игре — доступные и «скоро»."""
    infos = [m.info for m in MODES.values()] + LOCKED
    return [{"id": i.id, "number": i.number, "title": i.title,
             "tagline": i.tagline, "available": i.available} for i in infos]
