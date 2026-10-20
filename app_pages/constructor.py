import hashlib
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import date

from data.fetcher import fetch_ohlcv, SUPPORTED_TIMEFRAMES
from strategy.models import Condition, Rule, IndicatorConfig, Strategy, OPERATORS
from strategy.compiler import compile_strategy
from strategy.validator import validate, ValidationIssue
from backtester.engine import run_backtest
from ai.analyzer import analyze_strategy
from analytics.telegram import track, send_feedback

# Загрузка .env, секреты, set_page_config и событие «зашёл» — в роутере app.py.

# ─── Design polish ───────────────────────────────────────────────────────────
# Глобальный CSS, доводящий стандартные виджеты Streamlit до «ощущения качества».
# Принципы из скилла make-interfaces-feel-better, адаптированные под генерируемый
# Streamlit'ом DOM: тени вместо границ, концентрические скругления, tabular-nums,
# scale-on-press, плавные переходы по конкретным свойствам (никогда `all`).

_ACCENT = "#00e5a0"

def inject_css() -> None:
    st.markdown(
        f"""
        <style>
        /* №8 — сглаживание шрифта для более чёткого текста */
        .stApp {{
            -webkit-font-smoothing: antialiased;
            -moz-osx-font-smoothing: grayscale;
        }}

        /* №10 — заголовки переносятся «сбалансированно», без висячих слов */
        h1, h2, h3 {{ text-wrap: balance; }}

        /* №3 + №1 — карточки (st.container(border=True)): мягкая тень вместо
           жёсткой рамки, концентрическое скругление, внутренний отступ */
        div[data-testid="stVerticalBlockBorderWrapper"] {{
            border: 1px solid rgba(255, 255, 255, 0.06) !important;
            border-radius: 16px !important;
            padding: 20px 22px !important;
            box-shadow:
                0 1px 2px rgba(0, 0, 0, 0.30),
                0 4px 16px rgba(0, 0, 0, 0.22);
        }}

        /* Метрики → карточки-поверхности (№3 тени, №1 радиус, №9 tabular-nums) */
        div[data-testid="stMetric"] {{
            background: #111418;
            border-radius: 12px;
            padding: 12px 12px 10px;
            min-height: 104px;  /* единая высота: подписи в 2 строки не ломают ряд */
            box-shadow:
                0 1px 2px rgba(0, 0, 0, 0.30),
                0 6px 18px rgba(0, 0, 0, 0.18);
            transition-property: transform, box-shadow;
            transition-duration: 160ms;
            transition-timing-function: cubic-bezier(0.2, 0, 0, 1);
        }}
        div[data-testid="stMetric"]:hover {{
            transform: translateY(-2px);
            box-shadow:
                0 2px 4px rgba(0, 0, 0, 0.32),
                0 10px 26px rgba(0, 0, 0, 0.26);
        }}
        /* Значение: меньше кегль + НЕ обрезаем (7 узких карточек в ряд) */
        div[data-testid="stMetricValue"] {{
            font-variant-numeric: tabular-nums;  /* №9 — цифры не прыгают */
            font-size: 1.75rem !important;
            line-height: 1.2;
            overflow: visible !important;
            text-overflow: clip !important;
            white-space: nowrap;
        }}
        div[data-testid="stMetricDelta"] {{
            font-variant-numeric: tabular-nums;
        }}
        /* Подпись: разрешаем перенос в 2 строки вместо многоточия */
        div[data-testid="stMetricLabel"],
        div[data-testid="stMetricLabel"] * {{
            overflow: visible !important;
            text-overflow: clip !important;
            white-space: normal !important;
        }}
        div[data-testid="stMetricLabel"] p {{
            font-size: 0.78rem;
            line-height: 1.25;
        }}

        /* №14 + №12 — кнопки: переходы по конкретным свойствам, hover-подъём,
           тактильный scale(0.96) при нажатии, концентрический радиус */
        div[data-testid="stButton"] button,
        div[data-testid="stFormSubmitButton"] button {{
            border-radius: 10px !important;
            transition-property: transform, box-shadow, background-color, border-color, color;
            transition-duration: 150ms;
            transition-timing-function: cubic-bezier(0.2, 0, 0, 1);
            will-change: transform;  /* №15 — только compositable-свойство */
        }}
        div[data-testid="stButton"] button:hover,
        div[data-testid="stFormSubmitButton"] button:hover {{
            transform: translateY(-1px);
        }}
        div[data-testid="stButton"] button:active,
        div[data-testid="stFormSubmitButton"] button:active {{
            transform: scale(0.96);  /* №12 — ровно 0.96, ниже 0.95 выглядит утрированно */
        }}

        /* Акцентное свечение на главных призывах к действию (CTA):
           делает кнопки «Загрузить пример / Запустить / AI / Отправить» заметными
           (фидбэк тестировщиков: онбординг теряется, кнопка AI не выглядит как CTA) */
        div[data-testid="stButton"] button[kind="primary"],
        div[data-testid="stFormSubmitButton"] button[kind="secondaryFormSubmit"] {{
            background: {_ACCENT} !important;
            color: #06231a !important;
            border: none !important;
            font-weight: 600;
            box-shadow:
                0 1px 2px rgba(0, 0, 0, 0.25),
                0 6px 20px rgba(0, 229, 160, 0.28);
        }}
        div[data-testid="stButton"] button[kind="primary"]:hover,
        div[data-testid="stFormSubmitButton"] button[kind="secondaryFormSubmit"]:hover {{
            transform: translateY(-1px);
            box-shadow:
                0 2px 4px rgba(0, 0, 0, 0.28),
                0 10px 28px rgba(0, 229, 160, 0.40);
        }}
        div[data-testid="stButton"] button[kind="primary"]:disabled {{
            background: rgba(255, 255, 255, 0.08) !important;
            color: rgba(232, 237, 245, 0.40) !important;
            box-shadow: none;
        }}

        /* Sidebar: чуть плотнее по вертикали, чтобы панель не «воровала» внимание
           (фидбэк: левая колонка конкурирует с контентом) */
        section[data-testid="stSidebar"] div[data-testid="stVerticalBlockBorderWrapper"] {{
            box-shadow: none;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )

inject_css()

# ─── AI cost protection ──────────────────────────────────────────────────────
# Приложение публичное, а AI-анализ ходит в Claude по нашему ключу — значит
# каждый клик стоит денег. Три рубежа защиты от слива кредитов:
#   1) кэш одинаковых запросов — повтор того же анализа бесплатен;
#   2) лимит на сессию — один посетитель не зальёт спамом;
#   3) глобальный дневной потолок — общий предохранитель на бюджет.

AI_DAILY_LIMIT   = 150   # макс. вызовов AI в сутки на всё приложение
AI_SESSION_LIMIT = 5     # макс. вызовов AI на одну пользовательскую сессию


@st.cache_resource
def _ai_store() -> dict:
    """Состояние, общее для всех сессий (Streamlit Cloud = один процесс):
    дневной счётчик вызовов и кэш результатов по сигнатуре стратегии."""
    return {"date": "", "count": 0, "cache": {}}


def ai_budget_left() -> int:
    """Сколько вызовов AI осталось на сегодня (счётчик сбрасывается в полночь)."""
    store = _ai_store()
    today = str(date.today())
    if store["date"] != today:
        store["date"], store["count"] = today, 0
    return AI_DAILY_LIMIT - store["count"]

# ─── Constants ────────────────────────────────────────────────────────────────

ASSETS = [
    "BTC/USDT",  "ETH/USDT",  "SOL/USDT",  "BNB/USDT",  "XRP/USDT",
    "DOGE/USDT", "ADA/USDT",  "AVAX/USDT", "DOT/USDT",  "MATIC/USDT",
    "LINK/USDT", "UNI/USDT",  "ATOM/USDT", "LTC/USDT",  "BCH/USDT",
    "FIL/USDT",  "NEAR/USDT", "APT/USDT",  "ARB/USDT",  "OP/USDT",
    "SUI/USDT",  "TON/USDT",  "TRX/USDT",  "ETC/USDT",  "INJ/USDT",
]

EXCHANGES = {
    "Binance":  "binance",
    "OKX":      "okx",
    "Kraken":   "kraken",
    "Bybit":    "bybit",
    "Gate.io":  "gateio",
}
OHLCV_COLS = ["open", "high", "low", "close", "volume"]

INDICATOR_PARAMS: dict[str, list[tuple]] = {
    "RSI":        [("period",      "int",   14,  2,   100)],
    "MACD":       [("fast",        "int",   12,  2,    50),
                   ("slow",        "int",   26,  2,   100),
                   ("signal",      "int",    9,  2,    50)],
    "EMA":        [("period",      "int",   20,  2,   500)],
    "SMA":        [("period",      "int",   20,  2,   500)],
    "BB":         [("period",      "int",   20,  2,   100),
                   ("std",       "float",  2.0, 0.5,   5.0)],
    "Stochastic": [("k",           "int",   14,  2,    50),
                   ("d",           "int",    3,  1,    20)],
    "ATR":        [("period",      "int",   14,  2,   100)],
    "VolumeSMA":  [("period",      "int",   20,  2,   200)],
    "CCI":        [("period",      "int",   20,  2,   100)],
    "Supertrend": [("period",      "int",    7,  2,    50),
                   ("multiplier", "float",  3.0, 0.5,  10.0)],
}

OP_LABELS = {
    "<":             "< меньше",
    ">":             "> больше",
    "<=":            "≤ меньше или равно",
    ">=":            "≥ больше или равно",
    "==":            "= равно",
    "crosses_above": "↑ пересекает вверх",
    "crosses_below": "↓ пересекает вниз",
}

# ─── Example strategy ────────────────────────────────────────────────────────

EXAMPLE_STRATEGY = {
    "indicators": [
        {"name": "EMA", "params": {"period": 20}},
        {"name": "EMA", "params": {"period": 50}},
    ],
    "entry_conditions": [
        {"indicator": "EMA_20", "operator": "crosses_above", "value": "EMA_50"},
    ],
    "entry_logic": "AND",
    "exit_conditions": [
        {"indicator": "EMA_20", "operator": "crosses_below", "value": "EMA_50"},
    ],
    "exit_logic": "AND",
    "tp_pct": 0.0,
    "sl_pct": 2.0,
    "sel_asset": "BTC/USDT",
    "sel_timeframe": "1h",
}

# ─── Session state ────────────────────────────────────────────────────────────

def _init_state():
    defaults = {
        "indicators":       [],   # list of {"name": str, "params": dict}
        "entry_conditions": [],   # list of {"indicator", "operator", "value"}
        "exit_conditions":  [],
        "result":           None,
        "enriched_df":      None,
        "ohlcv_df":         None,
        "ai_comment":       None,
        "ai_strategy_hash": None,
        "ai_calls":         0,    # счётчик AI-вызовов в этой сессии (лимит расхода)
        # sidebar widget state
        "sel_asset":        "BTC/USDT",
        "sel_timeframe":    "1h",
        "tp_pct":           0.0,
        "sl_pct":           0.0,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()

# ─── Helpers ──────────────────────────────────────────────────────────────────

def get_indicator_columns(name: str, params: dict) -> list[str]:
    p = params
    if name == "RSI":
        return [f"RSI_{p['period']}"]
    if name == "MACD":
        return [f"MACD_{p['fast']}_{p['slow']}_{p['signal']}",
                f"MACDs_{p['fast']}_{p['slow']}_{p['signal']}",
                f"MACDh_{p['fast']}_{p['slow']}_{p['signal']}"]
    if name == "EMA":
        return [f"EMA_{p['period']}"]
    if name == "SMA":
        return [f"SMA_{p['period']}"]
    if name == "BB":
        s = str(p["std"]).replace(".", "_")
        return [f"BB_upper_{p['period']}_{s}",
                f"BB_mid_{p['period']}_{s}",
                f"BB_lower_{p['period']}_{s}"]
    if name == "Stochastic":
        return [f"STOCHk_{p['k']}_{p['d']}_3", f"STOCHd_{p['k']}_{p['d']}_3"]
    if name == "ATR":
        return [f"ATR_{p['period']}"]
    if name == "VolumeSMA":
        return [f"VolSMA_{p['period']}"]
    if name == "CCI":
        return [f"CCI_{p['period']}"]
    if name == "Supertrend":
        m = str(p["multiplier"]).replace(".", "_")
        return [f"ST_{p['period']}_{m}", f"ST_dir_{p['period']}_{m}"]
    return []


def available_columns() -> list[str]:
    cols = OHLCV_COLS.copy()
    for ind in st.session_state.indicators:
        cols.extend(get_indicator_columns(ind["name"], ind["params"]))
    return cols


def fmt_condition(c: dict) -> str:
    op = OP_LABELS.get(c["operator"], c["operator"])
    return f"{c['indicator']}  {op}  {c['value']}"


# ─── Chart builder ────────────────────────────────────────────────────────────

def build_chart(df: pd.DataFrame, result, enriched: pd.DataFrame) -> go.Figure:
    entries      = [t["entry_time"]  for t in result.trades]
    exits        = [t["exit_time"]   for t in result.trades]
    entry_prices = [t["entry_price"] for t in result.trades]
    exit_prices  = [t["exit_price"]  for t in result.trades]

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        row_heights=[0.65, 0.35],
        vertical_spacing=0.04,
        subplot_titles=("Цена", "Кривая доходности"),
    )

    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["open"], high=df["high"],
        low=df["low"],   close=df["close"],
        increasing_line_color="#26a69a",
        decreasing_line_color="#ef5350",
        name="Цена", showlegend=False,
    ), row=1, col=1)

    if entries:
        fig.add_trace(go.Scatter(
            x=entries, y=entry_prices,
            mode="markers",
            marker=dict(symbol="triangle-up", size=13, color="#26a69a",
                        line=dict(color="white", width=1)),
            name="Вход",
        ), row=1, col=1)

    if exits:
        fig.add_trace(go.Scatter(
            x=exits, y=exit_prices,
            mode="markers",
            marker=dict(symbol="triangle-down", size=13, color="#ef5350",
                        line=dict(color="white", width=1)),
            name="Выход",
        ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=result.equity_curve.index,
        y=result.equity_curve.values,
        fill="tozeroy",
        fillcolor="rgba(38,166,154,0.12)",
        line=dict(color="#26a69a", width=1.5),
        name="Капитал",
    ), row=2, col=1)

    fig.update_layout(
        height=660,
        template="plotly_dark",
        xaxis_rangeslider_visible=False,
        margin=dict(l=0, r=0, t=30, b=0),
        legend=dict(orientation="h", y=1.02, x=0),
    )
    return fig


# ─── Condition builder (reusable) ─────────────────────────────────────────────

def condition_builder(prefix: str, cols: list[str]) -> dict | None:
    """
    Renders a single row of widgets for building one condition.
    Returns a condition dict on submit, else None.
    """
    c1, c2, c3, c4, c5 = st.columns([3, 2, 1.2, 2.5, 1])

    left = c1.selectbox("Колонка", cols, key=f"{prefix}_left", label_visibility="collapsed")
    op   = c2.selectbox("Оператор", list(OP_LABELS.keys()),
                        format_func=lambda x: OP_LABELS[x],
                        key=f"{prefix}_op", label_visibility="collapsed")
    vtype = c3.radio("Тип", ["123", "col"], key=f"{prefix}_vtype",
                     horizontal=True, label_visibility="collapsed")

    if vtype == "123":
        val = c4.number_input("Значение", value=30.0, key=f"{prefix}_num",
                              label_visibility="collapsed")
    else:
        val = c4.selectbox("Колонка", cols, key=f"{prefix}_col",
                           label_visibility="collapsed")

    added = c5.button("＋ Добавить", key=f"{prefix}_add", use_container_width=True)
    return {"indicator": left, "operator": op, "value": val} if added else None


def render_condition_list(conditions: list[dict], logic: str, del_key: str):
    for i, c in enumerate(conditions):
        cc1, cc2 = st.columns([7, 1])
        prefix = f"**{logic}**  " if i > 0 else ""
        cc1.markdown(f"{prefix}`{fmt_condition(c)}`")
        if cc2.button("✕", key=f"{del_key}_{i}"):
            conditions.pop(i)
            st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════════════════════

# Consume pending values from the example button BEFORE widgets are instantiated.
# Direct assignment to a keyed widget's session_state after instantiation raises
# StreamlitAPIException — so we transfer via a "pending_*" intermediary.
for _pending, _key in [("pending_asset", "sel_asset"), ("pending_timeframe", "sel_timeframe")]:
    if _pending in st.session_state:
        st.session_state[_key] = st.session_state.pop(_pending)

with st.sidebar:
    st.title("⚙️ Настройки")

    exchange_name = st.selectbox("Биржа", list(EXCHANGES.keys()), index=1)
    exchange_id   = EXCHANGES[exchange_name]

    asset     = st.selectbox("Актив", ASSETS, key="sel_asset")
    timeframe = st.selectbox("Таймфрейм", SUPPORTED_TIMEFRAMES, key="sel_timeframe")

    st.markdown("**Период данных**")
    d1, d2 = st.columns(2)
    start_date = d1.date_input("С",  value=date(2024, 1, 1),  label_visibility="collapsed")
    d1.caption("Начало")
    end_date   = d2.date_input("По", value=date(2024, 12, 31), label_visibility="collapsed")
    d2.caption("Конец")

    st.divider()
    capital    = float(st.number_input("Начальный капитал ($)", value=10_000,
                                        min_value=100, step=500))
    commission = st.number_input("Комиссия (%)", value=0.10, min_value=0.0,
                                  max_value=2.0, step=0.01, format="%.2f") / 100

    st.divider()
    if st.button("🗑 Сбросить стратегию", use_container_width=True):
        for key in ["indicators", "entry_conditions", "exit_conditions", "result", "enriched_df", "ohlcv_df"]:
            st.session_state[key] = [] if isinstance(st.session_state[key], list) else None
        st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

st.title("📈 Конструктор торговых стратегий")
st.caption("Собери стратегию из блоков, запусти бэктест, получи аналитику.")

with st.container(border=True):
    st.markdown(
        "### 👋 Первый раз здесь?\n"
        "Загрузи готовый пример и сразу запусти бэктест — "
        "**EMA-кроссовер (20/50) на BTC/USDT**"
    )
    if st.button("▶ Загрузить пример и запустить", type="primary", use_container_width=True):
        ex = EXAMPLE_STRATEGY
        st.session_state.indicators       = [dict(i) for i in ex["indicators"]]
        st.session_state.entry_conditions = [dict(c) for c in ex["entry_conditions"]]
        st.session_state.exit_conditions  = [dict(c) for c in ex["exit_conditions"]]
        st.session_state.entry_logic      = ex["entry_logic"]
        st.session_state.exit_logic       = ex["exit_logic"]
        st.session_state.tp_pct           = ex["tp_pct"]
        st.session_state.sl_pct           = ex["sl_pct"]
        st.session_state["pending_asset"]     = ex["sel_asset"]
        st.session_state["pending_timeframe"] = ex["sel_timeframe"]
        st.session_state.result           = None
        st.session_state.ai_comment       = None
        track("example_loaded", "EMA 20/50, BTC/USDT 1h")
        st.rerun()

st.divider()

# ── 1. Indicators ─────────────────────────────────────────────────────────────

st.subheader("1 · Индикаторы")

sel_ind = st.selectbox("Индикатор", list(INDICATOR_PARAMS.keys()), key="sel_ind",
                        label_visibility="collapsed")

param_defs = INDICATOR_PARAMS[sel_ind]
pcols = st.columns([2] + [1] * len(param_defs) + [1])

pcols[0].markdown(f"**{sel_ind}**")
new_params: dict = {}
for i, (pname, ptype, default, pmin, pmax) in enumerate(param_defs):
    with pcols[i + 1]:
        if ptype == "int":
            new_params[pname] = st.number_input(
                pname, value=int(default), min_value=int(pmin), max_value=int(pmax),
                step=1, key=f"ip_{sel_ind}_{pname}")
        else:
            new_params[pname] = st.number_input(
                pname, value=float(default), min_value=float(pmin), max_value=float(pmax),
                step=0.1, format="%.1f", key=f"ip_{sel_ind}_{pname}")

if pcols[-1].button("＋", key="add_ind", use_container_width=True):
    st.session_state.indicators.append({"name": sel_ind, "params": dict(new_params)})
    st.rerun()

if st.session_state.indicators:
    for i, ind in enumerate(st.session_state.indicators):
        params_str = ", ".join(f"{k}={v}" for k, v in ind["params"].items())
        a, b = st.columns([7, 1])
        a.markdown(f"🔹 `{ind['name']}({params_str})`")
        if b.button("✕", key=f"del_ind_{i}"):
            st.session_state.indicators.pop(i)
            st.rerun()
else:
    st.caption("Добавьте хотя бы один индикатор")

st.divider()

# ── 2. Entry conditions ───────────────────────────────────────────────────────

st.subheader("2 · Условие входа в позицию")

cols = available_columns()
has_indicators = bool(st.session_state.indicators)

if not has_indicators:
    st.info("Сначала добавьте индикаторы в разделе выше")
else:
    entry_logic = st.radio("Логика между условиями", ["AND", "OR"],
                            horizontal=True, key="entry_logic")

    new_ec = condition_builder("ec", cols)
    if new_ec:
        st.session_state.entry_conditions.append(new_ec)
        st.rerun()

    render_condition_list(st.session_state.entry_conditions, entry_logic, "del_ec")

    if not st.session_state.entry_conditions:
        st.caption("Добавьте хотя бы одно условие входа")

st.divider()

# ── 3. Exit conditions ────────────────────────────────────────────────────────

st.subheader("3 · Условие выхода из позиции")

tp_col, sl_col = st.columns(2)
take_profit = tp_col.number_input("Тейк-профит (%)", min_value=0.0,
                                   max_value=500.0, step=0.5, format="%.1f",
                                   help="0 = не использовать", key="tp_pct")
stop_loss   = sl_col.number_input("Стоп-лосс (%)",   min_value=0.0,
                                   max_value=100.0,  step=0.5, format="%.1f",
                                   help="0 = не использовать", key="sl_pct")

if has_indicators:
    exit_logic = st.radio("Логика между условиями", ["AND", "OR"],
                           horizontal=True, key="exit_logic")

    new_xc = condition_builder("xc", cols)
    if new_xc:
        st.session_state.exit_conditions.append(new_xc)
        st.rerun()

    render_condition_list(st.session_state.exit_conditions, exit_logic, "del_xc")

    if not st.session_state.exit_conditions and take_profit == 0 and stop_loss == 0:
        st.caption("Укажите хотя бы одно условие выхода или TP/SL")

st.divider()

# ── Run ───────────────────────────────────────────────────────────────────────

can_run = (has_indicators and bool(st.session_state.entry_conditions)
           and start_date < end_date)

run_btn = st.button("▶ Запустить бэктест", type="primary",
                     use_container_width=True, disabled=not can_run)

if not can_run and has_indicators:
    st.caption("Нужно: хотя бы одно условие входа + корректный диапазон дат")

if run_btn:
    # ── Pre-flight validation ─────────────────────────────────────────────
    indicators_cfg = [IndicatorConfig(i["name"], i["params"]) for i in st.session_state.indicators]
    entry_conds    = [Condition(c["indicator"], c["operator"], c["value"])
                      for c in st.session_state.entry_conditions]
    exit_conds     = [Condition(c["indicator"], c["operator"], c["value"])
                      for c in st.session_state.exit_conditions]
    entry_rule_obj = Rule(entry_conds, logic=st.session_state.get("entry_logic", "AND"))
    exit_rule_obj  = Rule(exit_conds,  logic=st.session_state.get("exit_logic",  "AND")) if exit_conds else None

    issues = validate(
        indicators_cfg, entry_rule_obj, exit_rule_obj,
        str(start_date), str(end_date), timeframe,
    )

    errors   = [i for i in issues if i.level == "error"]
    warnings = [i for i in issues if i.level == "warning"]

    for w in warnings:
        st.warning(w.message)

    if errors:
        for e in errors:
            st.error(e.message)
        st.stop()

    # ── Fetch data ────────────────────────────────────────────────────────
    try:
        with st.spinner(f"Загрузка {asset} {timeframe} с {exchange_name}…"):
            df = fetch_ohlcv(asset, timeframe, str(start_date), str(end_date), exchange_id=exchange_id)
    except ValueError as exc:
        st.error(f"Данные не получены: {exc}")
        st.stop()
    except Exception as exc:
        st.error(f"Ошибка соединения с биржей: {exc}\n\nПроверьте интернет-соединение и попробуйте снова.")
        st.stop()

    if len(df) < 10:
        st.error(
            f"Загружено слишком мало свечей ({len(df)} шт.). "
            "Возможно, монета ещё не торговалась в этот период — попробуйте более поздние даты."
        )
        st.stop()

    # ── Compile & backtest ────────────────────────────────────────────────
    strategy = Strategy(
        indicators=indicators_cfg,
        entry_rule=entry_rule_obj,
        exit_rule=exit_rule_obj,
        take_profit_pct=take_profit if take_profit > 0 else None,
        stop_loss_pct=stop_loss     if stop_loss   > 0 else None,
    )

    with st.spinner("Расчёт индикаторов и бэктест…"):
        try:
            entry_sig, exit_sig, enriched = compile_strategy(df, strategy)
        except KeyError as exc:
            st.error(
                f"Колонка {exc} не найдена. "
                "Убедитесь, что параметры индикаторов в условиях совпадают с добавленными индикаторами."
            )
            st.stop()
        except Exception as exc:
            st.error(f"Ошибка компиляции стратегии: {exc}")
            st.stop()

        result = run_backtest(
            enriched, entry_sig, exit_sig,
            take_profit_pct=strategy.take_profit_pct,
            stop_loss_pct=strategy.stop_loss_pct,
            commission=commission,
            initial_capital=capital,
        )

    st.session_state.result      = result
    st.session_state.enriched_df = enriched
    st.session_state.ohlcv_df    = df
    st.session_state.ai_comment  = None
    st.session_state.feedback_sent = False
    track(
        "backtest_run",
        f"{asset} {timeframe} | {exchange_name} | сделок: {result.num_trades} | "
        f"доходность: {result.total_return_pct:+.1f}%",
    )
    st.rerun()

# ── Results ───────────────────────────────────────────────────────────────────

if st.session_state.result is not None:
    result  = st.session_state.result
    ohlcv   = st.session_state.ohlcv_df
    enriched = st.session_state.enriched_df

    st.subheader("📊 Результаты бэктеста")

    if result.num_trades == 0:
        st.warning(
            "Стратегия не открыла ни одной сделки. "
            "Попробуйте ослабить условия входа или расширить диапазон дат."
        )
    else:
        color = "normal" if result.total_return_pct >= 0 else "inverse"
        # Два ряда по 4 колонки: широкие карточки, значения и подписи не обрезаются.
        # Ряд 1 — итог и риск; ряд 2 — статистика по сделкам (4-я ячейка пустая
        # ради выравнивания ширины карточек с верхним рядом).
        r1 = st.columns(4)
        r1[0].metric("Доходность",     f"{result.total_return_pct:+.2f}%", delta_color=color,
                  help="Итоговый прирост или убыток капитала за весь период бэктеста.")
        r1[1].metric("Сделок",         result.num_trades,
                  help="Общее количество открытых и закрытых позиций.")
        r1[2].metric("Макс. просадка", f"{result.max_drawdown_pct:.2f}%",
                  help="Максимальное падение капитала от пика до дна в процентах. Показывает худший сценарий потерь, который пережил бы трейдер.")
        r1[3].metric("Sharpe",         f"{result.sharpe_ratio:.3f}",
                  help="Коэффициент Шарпа — доходность относительно риска. До 1: слабо, 1–2: хорошо, выше 2: отлично. Отрицательный — стратегия хуже депозита.")

        r2 = st.columns(4)
        r2[0].metric("Прибыльных",     f"{result.win_rate_pct:.1f}%",
                  help="Доля сделок, закрытых с прибылью. Выше 50% означает, что стратегия чаще угадывает направление.")
        r2[1].metric("Ср. выигрыш",    f"{result.avg_win_pct:+.2f}%",
                  help="Средний процент прибыли на одну прибыльную сделку.")
        r2[2].metric("Ср. проигрыш",   f"{result.avg_loss_pct:+.2f}%",
                  help="Средний процент убытка на одну убыточную сделку. Сравни с «Ср. выигрышем»: если выигрыш больше — стратегия имеет положительное матожидание.")

        st.plotly_chart(build_chart(ohlcv, result, enriched), use_container_width=True)

        with st.expander(f"Список сделок ({result.num_trades} шт.)"):
            trades_df = pd.DataFrame(result.trades)
            trades_df["pnl_pct"] = trades_df["pnl_pct"].round(3)
            st.dataframe(trades_df, use_container_width=True)

        # ── AI Analysis ───────────────────────────────────────────────────────
        st.divider()
        st.subheader("🤖 AI-анализ стратегии")

        if st.session_state.ai_comment:
            st.markdown(st.session_state.ai_comment)
            if st.button("Обновить анализ", key="ai_refresh"):
                st.session_state.ai_comment = None
                st.rerun()
        else:
            ai_btn = st.button("Получить AI-анализ", type="primary", key="ai_run")
            st.caption("Claude проанализирует метрики, найдёт слабые места и даст рекомендации.")

            if ai_btn:
                strategy_obj = Strategy(
                    indicators=[IndicatorConfig(i["name"], i["params"])
                                for i in st.session_state.indicators],
                    entry_rule=Rule(
                        [Condition(c["indicator"], c["operator"], c["value"])
                         for c in st.session_state.entry_conditions],
                        logic=st.session_state.get("entry_logic", "AND"),
                    ),
                    exit_rule=Rule(
                        [Condition(c["indicator"], c["operator"], c["value"])
                         for c in st.session_state.exit_conditions],
                        logic=st.session_state.get("exit_logic", "AND"),
                    ) if st.session_state.exit_conditions else None,
                    take_profit_pct=take_profit if take_profit > 0 else None,
                    stop_loss_pct=stop_loss     if stop_loss   > 0 else None,
                )

                # Сигнатура входных данных AI: тот же набор → тот же ответ.
                sig_src = repr([
                    st.session_state.indicators,
                    st.session_state.entry_conditions,
                    st.session_state.exit_conditions,
                    st.session_state.get("entry_logic"),
                    st.session_state.get("exit_logic"),
                    take_profit, stop_loss, asset, timeframe,
                    str(start_date), str(end_date), capital,
                ])
                sig = hashlib.sha256(sig_src.encode()).hexdigest()
                store = _ai_store()

                if sig in store["cache"]:
                    # Рубеж 1: точно такой анализ уже делали — отдаём из кэша даром.
                    st.session_state.ai_comment = store["cache"][sig]
                    st.rerun()
                elif st.session_state.ai_calls >= AI_SESSION_LIMIT:
                    # Рубеж 2: лимит на одну сессию.
                    st.warning(
                        f"Достигнут лимит AI-анализов на сессию ({AI_SESSION_LIMIT}). "
                        "Обнови страницу, чтобы начать заново."
                    )
                elif ai_budget_left() <= 0:
                    # Рубеж 3: общий дневной потолок исчерпан.
                    st.warning(
                        "На сегодня лимит AI-анализов исчерпан 🙏 Загляни завтра — "
                        "счётчик обнулится. (Бэктест работает без ограничений.)"
                    )
                else:
                    with st.spinner("Claude анализирует стратегию…"):
                        try:
                            comment = analyze_strategy(
                                result=result,
                                strategy=strategy_obj,
                                asset=asset,
                                timeframe=timeframe,
                                start_date=str(start_date),
                                end_date=str(end_date),
                                initial_capital=capital,
                            )
                            # Учитываем расход: и в общий счётчик, и в кэш, и в сессию.
                            store["count"] += 1
                            store["cache"][sig] = comment
                            st.session_state.ai_calls += 1
                            st.session_state.ai_comment = comment
                            track("ai_analysis", f"{asset} {timeframe}")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Ошибка AI-анализа: {exc}")

    # ── Feedback ────────────────────────────────────────────────────────────────
    st.divider()
    if st.session_state.get("feedback_sent"):
        st.success("Спасибо! Твой отзыв получен 🙌")
    else:
        with st.container(border=True):
            st.markdown("#### Был ли инструмент полезен?")
            with st.form("feedback_form", clear_on_submit=True):
                rating  = st.radio(
                    "Оценка", ["👍 Да, полезно", "👎 Нет / непонятно"],
                    horizontal=True, label_visibility="collapsed",
                )
                comment = st.text_input(
                    "Комментарий",
                    placeholder="Что понравилось или чего не хватило? (необязательно)",
                    label_visibility="collapsed",
                )
                if st.form_submit_button("Отправить отзыв", use_container_width=True):
                    ctx = f"{asset} {timeframe}, сделок: {result.num_trades}"
                    send_feedback("👍" if rating.startswith("👍") else "👎", comment, ctx)
                    st.session_state.feedback_sent = True
                    st.rerun()
