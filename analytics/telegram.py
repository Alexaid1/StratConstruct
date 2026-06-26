"""
Лёгкая аналитика и обратная связь через Telegram-бота.

Зачем: пока у проекта нет пользователей, важно из каждого визита что-то узнавать —
куда дошёл человек по воронке и что он думает. Полноценная аналитика тут избыточна,
а Telegram-бот не требует базы, OAuth и переживает эфемерную ФС Streamlit Cloud.

Ключевой принцип: аналитика НИКОГДА не должна ронять приложение. Любая ошибка
(нет токена, нет сети, таймаут) — тихо проглатывается, пользователь её не видит.
"""

from __future__ import annotations

import os
import threading

import requests

_TIMEOUT = 4  # сек — короткий, чтобы не подвешивать UI даже при синхронной отправке


def _credentials() -> tuple[str | None, str | None]:
    """Токен и chat_id из окружения (.env локально, secrets на Streamlit Cloud)."""
    return os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")


def _post(text: str) -> None:
    """Синхронная отправка. Все ошибки глушим — аналитика не критична."""
    token, chat_id = _credentials()
    if not token or not chat_id:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
            timeout=_TIMEOUT,
        )
    except Exception:
        pass  # намеренно: сбой отправки не должен влиять на пользователя


def _send_async(text: str) -> None:
    """Отправка в фоновом потоке — UI не ждёт сеть."""
    threading.Thread(target=_post, args=(text,), daemon=True).start()


def track(event: str, detail: str = "") -> None:
    """Событие воронки. Пример: track('backtest_run', 'BTC/USDT 1h')."""
    msg = f"📊 {event}"
    if detail:
        msg += f"\n{detail}"
    _send_async(msg)


def send_feedback(rating: str, comment: str = "", context: str = "") -> None:
    """Отзыв пользователя. rating — '👍'/'👎', comment — свободный текст."""
    msg = f"💬 Отзыв: {rating}"
    if context:
        msg += f"\nКонтекст: {context}"
    if comment:
        msg += f"\nКомментарий: {comment}"
    _send_async(msg)
