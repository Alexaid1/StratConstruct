"""Подобрать порог «боковика» для быстрого режима.

    python scripts/calibrate_sideways.py [--samples 2000]

Генерирует случайные раунды (как в игре) и показывает, как часто выпадают
вверх / боковик / вниз при разных множителях ATR. Цель — боковик примерно
в трети раундов: тогда база «случайного угадывания» — честные 33%.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from trainer import config  # noqa: E402
from trainer.rounds import build_round, generate_round  # noqa: E402
from trainer.scoring import classify_move  # noqa: E402

MULTS = [0.8, 1.0, 1.2, 1.4, 1.6, 1.8, 2.0]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=2000)
    args = parser.parse_args()

    rows = []
    for tf in config.TIMEFRAMES:
        for seed in range(args.samples):
            rd = build_round(generate_round(seed=seed, timeframes=[tf]))
            final = float(rd.future["close"].iloc[-1])
            # Изменение в ATR — по нему считаются все пороги сразу.
            rows.append({"tf": tf, "ticker": rd.spec.ticker,
                         "move_atr": (final - rd.last_close) / rd.atr})
    df = pd.DataFrame(rows)

    print(f"Раундов: {len(df)} ({args.samples} на таймфрейм)\n")
    print("Доля исходов при пороге k × ATR(14):")
    print(f"{'k':>5} | {'таймфрейм':>9} | {'вверх':>6} {'боковик':>8} {'вниз':>6}")
    for k in MULTS:
        for tf, part in [("все", df)] + list(df.groupby("tf")):
            cls = [classify_move(0, m, 1, k) for m in part["move_atr"]]
            share = pd.Series(cls).value_counts(normalize=True)
            mark = "  ← сейчас" if k == config.SIDEWAYS_ATR_MULT and tf == "все" else ""
            print(f"{k:>5} | {tf:>9} | {share.get('up', 0):>6.1%} {share.get('flat', 0):>8.1%} "
                  f"{share.get('down', 0):>6.1%}{mark}")
        print()

    # Множитель, при котором боковик ровно треть: квантиль |изменения| в ATR.
    for tf, part in [("все", df)] + list(df.groupby("tf")):
        print(f"k для боковика = 1/3 ({tf}): {np.quantile(part['move_atr'].abs(), 1/3):.2f}")


if __name__ == "__main__":
    main()
