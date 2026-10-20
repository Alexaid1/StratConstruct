"""Исходы раундов: классификация движения (быстрый режим) и сделка в R."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

UP, DOWN, FLAT = "up", "down", "flat"
OUTCOMES = (UP, FLAT, DOWN)
OUTCOME_LABELS = {UP: "Вверх", DOWN: "Вниз", FLAT: "Боковик"}


def classify_move(last_close: float, final_close: float, atr: float, mult: float) -> str:
    """Вверх / вниз / боковик по изменению цены за горизонт раунда.

    Боковик — если |изменение| меньше mult × ATR последней видимой свечи:
    порог в единицах волатильности, а не в процентах, поэтому одинаково
    честен для спокойного Сбера и дёрганого Яндекса, для дневок и часовиков.
    """
    change = final_close - last_close
    if abs(change) < mult * atr:
        return FLAT
    return UP if change > 0 else DOWN


@dataclass(frozen=True)
class TradeResult:
    exit_price: float
    exit_bar: int        # номер свечи будущего (0..N-1), на которой закрылись
    reason: str          # stop | take | close
    r: float             # результат в R (кратных риску)

    def to_dict(self) -> dict:
        return asdict(self)


def trade_outcome(
    direction: str,
    entry: float,
    stop: float,
    take: float,
    future: np.ndarray,
) -> TradeResult:
    """Что сработало первым — стоп, тейк или ни то ни другое.

    future — массив свечей будущего [[open, high, low, close], ...].
    Правила (консервативные):
      • стоп и тейк задеты одной свечой → считаем стоп (внутри свечи порядок неизвестен);
      • свеча открылась гэпом за стопом → выход по цене открытия (хуже стопа);
      • тейк исполняется ровно по уровню, даже если открылись гэпом за ним;
      • ничего не задето → выход по закрытию последней свечи.
    """
    if direction not in ("long", "short"):
        raise ValueError(f"direction: long или short, получено {direction!r}")
    sign = 1 if direction == "long" else -1
    risk = (entry - stop) * sign
    if risk <= 0:
        raise ValueError("стоп должен быть с убыточной стороны от входа")
    if (take - entry) * sign <= 0:
        raise ValueError("тейк должен быть с прибыльной стороны от входа")

    future = np.asarray(future, dtype=float)
    if future.ndim != 2 or len(future) == 0:
        raise ValueError("нет свечей будущего")

    for i, (o, h, l, c) in enumerate(future[:, :4]):
        if direction == "long":
            stop_hit, take_hit = l <= stop, h >= take
            stop_fill = min(stop, o)
        else:
            stop_hit, take_hit = h >= stop, l <= take
            stop_fill = max(stop, o)
        if stop_hit:
            return TradeResult(stop_fill, i, "stop", (stop_fill - entry) * sign / risk)
        if take_hit:
            return TradeResult(take, i, "take", (take - entry) * sign / risk)

    last_close = future[-1, 3]
    return TradeResult(last_close, len(future) - 1, "close", (last_close - entry) * sign / risk)
