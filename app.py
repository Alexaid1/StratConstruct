"""Точка входа StratConstruct: общие настройки и навигация между разделами.

Разделы лежат в app_pages/ (не pages/ — эту папку Streamlit подхватывает
сам и рисует своё меню, а нам нужен контроль через st.navigation).
"""

import os

import streamlit as st
from dotenv import load_dotenv

from analytics.telegram import track

load_dotenv()

# На Streamlit Cloud .env не деплоится — креды берём из Secrets и пробрасываем в окружение,
# чтобы модуль аналитики (он не зависит от Streamlit) их увидел через os.getenv.
try:
    for _k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        if _k in st.secrets and not os.getenv(_k):
            os.environ[_k] = str(st.secrets[_k])
except Exception:
    pass  # secrets.toml может отсутствовать локально — это нормально

# Заголовок и иконку вкладки браузера каждый раздел берёт из своего st.Page.
st.set_page_config(layout="wide")

# Событие воронки «зашёл» — ровно один раз за сессию, на любом разделе.
if "tracked_session" not in st.session_state:
    st.session_state.tracked_session = True
    track("session_start", "Новый визит")

pages = [
    st.Page("app_pages/constructor.py", title="Конструктор стратегий", icon="📈", default=True),
    st.Page("app_pages/trainer.py", title="Тренажёр трейдера", icon="🎯", url_path="trainer"),
]
st.navigation(pages).run()
