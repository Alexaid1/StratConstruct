"""Игровой компонент тренажёра (двусторонний custom component Streamlit).

Фронтенд — статические файлы в frontend/: index.html, style.css, main.js
и библиотека TradingView Lightweight Charts (Apache 2.0, лежит рядом —
без npm, сборки и CDN). Python → JS: состояние раунда; JS → Python:
события игрока (ответ, следующий раунд, смена режима).
"""

from __future__ import annotations

from pathlib import Path

import streamlit.components.v1 as components

_FRONTEND = Path(__file__).resolve().parent / "frontend"
_game = components.declare_component("trainer_game", path=str(_FRONTEND))


def game(state: dict, key: str = "trainer_game"):
    """Нарисовать игру. Возвращает последнее событие игрока (или None)."""
    return _game(state=state, key=key, default=None)
