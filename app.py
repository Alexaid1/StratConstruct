import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import date
from dotenv import load_dotenv

from data.fetcher import fetch_ohlcv, SUPPORTED_TIMEFRAMES
from strategy.models import Condition, Rule, IndicatorConfig, Strategy, OPERATORS
from strategy.compiler import compile_strategy
from strategy.validator import validate, ValidationIssue
from backtester.engine import run_backtest
from ai.analyzer import analyze_strategy

load_dotenv()

# ─── Page config ─────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Конструктор стратегий",
    page_icon="📈",
    layout="wide",
)

# ─── Constants ────────────────────────────────────────────────────────────────

ASSETS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT", "DOGE/USDT", "ADA/USDT"]
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

with st.sidebar:
    st.title("⚙️ Настройки")

    asset     = st.selectbox("Актив", ASSETS)
    timeframe = st.selectbox("Таймфрейм", SUPPORTED_TIMEFRAMES,
                             index=SUPPORTED_TIMEFRAMES.index("1h"))

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
take_profit = tp_col.number_input("Тейк-профит (%)", value=0.0, min_value=0.0,
                                   max_value=500.0, step=0.5, format="%.1f",
                                   help="0 = не использовать")
stop_loss   = sl_col.number_input("Стоп-лосс (%)",   value=0.0, min_value=0.0,
                                   max_value=100.0,  step=0.5, format="%.1f",
                                   help="0 = не использовать")

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
        with st.spinner(f"Загрузка {asset} {timeframe} с Bybit…"):
            df = fetch_ohlcv(asset, timeframe, str(start_date), str(end_date))
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
        m1, m2, m3, m4, m5, m6 = st.columns(6)
        m1.metric("Доходность",      f"{result.total_return_pct:+.2f}%", delta_color=color)
        m2.metric("Сделок",          result.num_trades)
        m3.metric("Прибыльных",      f"{result.win_rate_pct:.1f}%")
        m4.metric("Макс. просадка",  f"{result.max_drawdown_pct:.2f}%")
        m5.metric("Sharpe Ratio",    f"{result.sharpe_ratio:.3f}")
        m6.metric("Ср. выигрыш / проигрыш",
                  f"{result.avg_win_pct:+.2f}% / {result.avg_loss_pct:+.2f}%")

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
                        st.session_state.ai_comment = comment
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Ошибка AI-анализа: {exc}")
