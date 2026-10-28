"""Отбор раундов: меньше «рулетки», но seed по-прежнему задаёт раунд."""

import pytest

from trainer import config
from trainer.dataset import available_series
from trainer.selection import keep_chance, pick_round, round_kind


def test_keep_chance_multiplies_the_reasons():
    calm = {"no_lean": False, "shock": False, "against": False}
    assert keep_chance(calm) == 1.0
    assert keep_chance({**calm, "shock": True}) == config.KEEP_SHOCK
    assert keep_chance({"no_lean": False, "shock": True, "against": True}) == pytest.approx(
        config.KEEP_SHOCK * config.KEEP_AGAINST)


@pytest.mark.skipif(not available_series(), reason="нет данных Мосбиржи — запусти scripts/fetch_moex.py")
def test_pick_round_is_deterministic_and_respects_filters():
    a, _ = pick_round(seed=7, tickers=["SBER"], timeframes=["1d"])
    b, rd = pick_round(seed=7, tickers=["SBER"], timeframes=["1d"])
    assert a == b and a.ticker == "SBER" and a.timeframe == "1d"
    assert rd.spec == a


@pytest.mark.skipif(not available_series(), reason="нет данных Мосбиржи — запусти scripts/fetch_moex.py")
def test_pick_round_cuts_news_shocks():
    shocks = sum(round_kind(pick_round(seed=s)[1])["shock"] for s in range(60))
    assert shocks <= 5          # без отбора — около 13% (8 из 60)
