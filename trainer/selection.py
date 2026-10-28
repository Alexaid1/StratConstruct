"""Отбор раундов: поменьше «рулетки».

generate_round берёт любое окно. Здесь из кандидатов чаще оставляем те, где
по графику есть что читать, и реже — те, где движение сделала новость или
цена ушла против явного перевеса сигналов (доли — в config.KEEP_*).

Будущее участвует только в решении «брать окно или нет» на сервере — игрок
его не видит, а сам раунд строится как обычно. Seed по-прежнему задаёт раунд
целиком: из него выводятся seed'ы кандидатов и монетки отбора.
"""

from __future__ import annotations

import numpy as np

from trainer import analysis as A
from trainer import config
from trainer.rounds import RoundData, RoundSpec, build_round, generate_round
from trainer.scoring import FLAT


def round_kind(rd: RoundData) -> dict:
    """Чем раунд неудобен для чтения графика."""
    sigs = A.signals(rd)
    st = A.story(rd)
    actual = st["actual"]
    lean = A.consensus(sigs, actual)["lean"]
    big = st["big"]
    share = big["atr"] / st["change_atr"] if big and st["change_atr"] else 0
    return {
        "no_lean": lean is None,
        "shock": bool(big and abs(big["atr"]) >= A.SHOCK_BAR_ATR and share >= A.SHOCK_SHARE),
        "against": lean is not None and actual != FLAT and lean != actual,
    }


def keep_chance(kind: dict) -> float:
    p = 1.0
    if kind["no_lean"]:
        p *= config.KEEP_NO_LEAN
    if kind["shock"]:
        p *= config.KEEP_SHOCK
    if kind["against"]:
        p *= config.KEEP_AGAINST
    return p


def pick_round(
    seed: int | None = None,
    tickers: list[str] | None = None,
    timeframes: list[str] | None = None,
) -> tuple[RoundSpec, RoundData]:
    """Раунд с отбором. Если за PICK_MAX_TRIES кандидатов никто не прошёл — берём последний."""
    if seed is None:
        seed = int(np.random.default_rng().integers(0, 2**31 - 1))
    rng = np.random.default_rng(seed)
    spec = rd = None
    for _ in range(config.PICK_MAX_TRIES):
        spec = generate_round(seed=int(rng.integers(0, 2**31 - 1)), tickers=tickers, timeframes=timeframes)
        rd = build_round(spec)
        if rng.random() < keep_chance(round_kind(rd)):
            break
    return spec, rd
