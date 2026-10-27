"""Блок статистики под игрой: плитки, графики, разбивки и журнал.

Цвета графиков — отдельная палитра, проверенная валидатором на тёмной
поверхности (#110d33): светлота 0.48–0.67, различимость при дальтонизме.
Яркие неоновые цвета остаются за игровым экраном, здесь — спокойные шаги.
"""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from trainer import stats as S
from trainer.scoring import OUTCOME_LABELS, OUTCOMES

SURFACE = "#110d33"
GAIN, LOSS = "#15aa7b", "#b03058"          # прибыль / убыток (ΔE CVD 12.9)
ACCENT, ACCENT_2 = "#8b6cff", "#d9741a"    # основная серия / второй акцент
RAMP = ["#6a4fd9", "#8a6ef5", "#b09cff", "#d9d0ff"]  # последовательная шкала (мало → много)
INK, INK_2, INK_3 = "#f5f1ff", "#bdb4ec", "#8279bd"
GRID = "rgba(170,150,255,0.10)"


def css() -> str:
    return """
<style>
.tr-sec { margin: 34px 0 14px; display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.tr-sec .num { font-family: var(--tr-mono); font-size: 11px; font-weight: 700; letter-spacing: .18em; color: var(--tr-gold); }
.tr-sec h2 { margin: 6px 0 0; padding: 0; font-family: var(--tr-display); font-weight: 700; font-size: 30px; line-height: 1.05; letter-spacing: -.01em; color: var(--tr-text); }
.tr-sec p { margin: 0; max-width: 460px; font-size: 13px; line-height: 1.5; color: var(--tr-text-3); text-wrap: pretty; }
.tr-tiles { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin: 6px 0 4px; }
.tr-tile {
  position: relative; padding: 16px 16px 14px; border-radius: 16px;
  background: linear-gradient(180deg, rgba(31,25,87,.55), rgba(17,13,51,.9));
  box-shadow: 0 0 0 1px var(--tr-line), 0 10px 30px rgba(4,2,18,.35);
}
.tr-tile .lbl { font-size: 12px; color: var(--tr-text-3); }
.tr-tile .val { margin-top: 6px; font-family: var(--tr-ui); font-weight: 600; font-size: 30px; line-height: 1.05; color: var(--tr-text); letter-spacing: -.01em; }
.tr-tile .val small { font-size: 14px; font-weight: 500; color: var(--tr-text-3); margin-left: 4px; }
.tr-tile .sub { margin-top: 8px; font-size: 12px; line-height: 1.4; color: var(--tr-text-2); }
.tr-tile .sub b { font-weight: 600; color: var(--tr-text); }
.tr-tile .tag { display: inline-flex; align-items: center; gap: 6px; margin-top: 8px; padding: 3px 9px; border-radius: 999px; font-size: 11px; font-weight: 600; background: rgba(255,255,255,.05); color: var(--tr-text-2); box-shadow: inset 0 0 0 1px var(--tr-line); }
.tr-tile .tag i { width: 7px; height: 7px; border-radius: 50%; display: inline-block; }
.tr-empty {
  padding: 34px 24px; border-radius: 18px; text-align: center;
  background: rgba(17,13,51,.6); box-shadow: 0 0 0 1px var(--tr-line);
  color: var(--tr-text-2); font-size: 14px;
}
.tr-empty b { display: block; margin-bottom: 6px; font-family: var(--tr-display); font-size: 18px; color: var(--tr-text); }
.tr-cap { font-size: 12px; color: var(--tr-text-3); margin: 2px 0 8px; }
.tr-chart-title { margin: 14px 0 0; font-weight: 600; font-size: 14px; color: var(--tr-text); }
.tr-chart-sub { margin: 2px 0 0; font-size: 12px; color: var(--tr-text-3); }
div[data-testid="stTabs"] button[role="tab"] p { font-family: var(--tr-display); font-size: 13px; letter-spacing: .04em; }
div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] p { color: var(--tr-gold); }
div[data-testid="stTabs"] div[data-baseweb="tab-highlight"] { background-color: var(--tr-gold); }
@media (max-width: 900px) { .tr-tiles { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
"""


def section(num: str, title: str, text: str) -> None:
    st.html(f'<div class="tr-sec"><div><div class="num">{num}</div><h2>{title}</h2></div><p>{text}</p></div>')


def tiles(items: list[dict]) -> None:
    out = []
    for t in items:
        unit = "<small>%s</small>" % t["unit"] if t.get("unit") else ""
        sub = '<div class="sub">%s</div>' % t["sub"] if t.get("sub") else ""
        tag = ""
        if t.get("tag"):
            tag = '<div class="tag"><i style="background:%s"></i>%s</div>' % (t.get("tag_color", INK_3), t["tag"])
        out.append('<div class="tr-tile"><div class="lbl">%s</div><div class="val">%s%s</div>%s%s</div>'
                   % (t["label"], t["value"], unit, sub, tag))
    st.html('<div class="tr-tiles">%s</div>' % "".join(out))


def empty(title: str, text: str) -> None:
    st.html(f'<div class="tr-empty"><b>{title}</b>{text}</div>')


def _pct(x: float, nd: int = 0) -> str:
    return f"{x * 100:.{nd}f}%"


def _signed(x: float, nd: int = 2) -> str:
    return f"{x:+.{nd}f}".replace("-", "−")


def _layout(fig: go.Figure, height: int = 300, **kw) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=8, r=12, t=10, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Onest, system-ui, sans-serif", size=12, color=INK_2),
        hoverlabel=dict(bgcolor="#1f1957", bordercolor="#3d2f8f", font=dict(family="Onest", color=INK)),
        showlegend=False,
        **kw,
    )
    fig.update_xaxes(gridcolor=GRID, zeroline=False, linecolor=GRID, tickfont=dict(color=INK_3), title_font=dict(color=INK_3))
    fig.update_yaxes(gridcolor=GRID, zeroline=False, linecolor=GRID, tickfont=dict(color=INK_3), title_font=dict(color=INK_3))
    return fig


def _chart(fig: go.Figure, title: str, sub: str) -> None:
    st.html(f'<div class="tr-chart-title">{title}</div><div class="tr-chart-sub">{sub}</div>')
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


# ─── Быстрый режим ────────────────────────────────────────────────────────────

def quick_block(attempts: list[dict]) -> None:
    s = S.quick_stats(attempts)
    if not s["n"]:
        empty("Пока пусто", "Сыграй пару раундов в быстром режиме — здесь появятся точность, калибровка и разбор ошибок.")
        return

    lo, hi = s["ci"]
    beats_random = lo > s["base_random"]
    beats_major = s["accuracy"] > s["base_majority"]
    if beats_random:
        verdict, vcol = "лучше случайного — уверенно", GAIN
    elif s["accuracy"] > s["base_random"]:
        verdict, vcol = "выше 33%, но пока в пределах удачи", ACCENT_2
    else:
        verdict, vcol = "не лучше монетки", LOSS
    brier_good = s["brier"] < s["brier_ref"]
    tiles([
        {"label": "Точность", "value": _pct(s["accuracy"]),
         "sub": f'{s["hits"]} из {s["n"]} · 95% интервал <b>{_pct(lo)}–{_pct(hi)}</b>',
         "tag": verdict, "tag_color": vcol},
        {"label": "Базы для сравнения", "value": f'{_pct(s["base_random"])}<small>/ {_pct(s["base_majority"])}</small>',
         "sub": f'наугад / «всегда {s["majority_label"].lower()}»',
         "tag": "бьёшь обе" if beats_major and beats_random else ("бьёшь «наугад»" if s["accuracy"] > s["base_random"] else "пока нет"),
         "tag_color": GAIN if beats_major and beats_random else ACCENT_2},
        {"label": "Brier score", "value": f'{s["brier"]:.3f}',
         "sub": "0 — идеал, 0.25 — всегда «50 на 50»",
         "tag": "калибровка лучше монетки" if brier_good else "уверенность подводит", "tag_color": GAIN if brier_good else LOSS},
        {"label": "Очки", "value": _signed(s["points"], 0), "unit": "",
         "sub": f'{s["n"]} {"раунд" if s["n"] % 10 == 1 and s["n"] % 100 != 11 else "раундов"} · средняя уверенность {_pct(s["avg_confidence"])}'},
    ])

    c1, c2 = st.columns([1.15, 1], gap="large")
    with c1:
        cal = s["calibration"]
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=[0.5, 1], y=[0.5, 1], mode="lines", hoverinfo="skip",
                                 line=dict(color="rgba(189,180,236,0.45)", width=1)))
        fig.add_trace(go.Scatter(
            x=[c["confidence"] for c in cal], y=[c["hit_rate"] for c in cal],
            mode="markers+lines", line=dict(color=ACCENT, width=2, shape="linear"),
            marker=dict(size=12, color=ACCENT, line=dict(color=SURFACE, width=2)),
            customdata=[[c["bucket"], c["n"]] for c in cal],
            hovertemplate="Уверенность %{customdata[0]}<br>Попаданий: %{y:.0%}<br>Раундов: %{customdata[1]}<extra></extra>",
        ))
        fig.add_annotation(x=0.97, y=0.97, text="идеальная калибровка", showarrow=False,
                           xanchor="right", yanchor="bottom", font=dict(size=11, color=INK_3))
        _layout(fig, xaxis=dict(range=[0.48, 1.02], tickformat=".0%", title="заявленная уверенность"),
                yaxis=dict(range=[-0.02, 1.04], tickformat=".0%", title="доля попаданий"))
        _chart(fig, "Калибровка уверенности", "Точки ниже диагонали — ты увереннее, чем точен")
    with c2:
        z = [[s["confusion"][c][o] for o in OUTCOMES] for c in OUTCOMES]
        zmax = max(max(r) for r in z) or 1
        labels = [OUTCOME_LABELS[o] for o in OUTCOMES]
        fig = go.Figure(go.Heatmap(
            z=z, x=labels, y=labels, xgap=2, ygap=2,
            colorscale=[[0, "rgba(255,255,255,0.03)"], [0.0001, RAMP[0]], [0.4, RAMP[1]], [0.75, RAMP[2]], [1, RAMP[3]]],
            zmin=0, zmax=zmax, showscale=False,
            hovertemplate="Прогноз: %{y}<br>Факт: %{x}<br>Раундов: %{z}<extra></extra>",
        ))
        for i, row in enumerate(z):
            for j, v in enumerate(row):
                light = v / zmax > 0.6
                fig.add_annotation(x=labels[j], y=labels[i], text=str(v), showarrow=False,
                                   font=dict(size=15, color="#1a0b2e" if light else INK, family="Onest"))
        _layout(fig, height=300, xaxis=dict(title="как вышло", side="bottom", showgrid=False),
                yaxis=dict(title="твой прогноз", autorange="reversed", showgrid=False))
        _chart(fig, "Прогноз против факта", "Диагональ — попадания; строки покажут, куда ты перекошен")

    df = S.breakdown(attempts, "quick")
    st.html('<div class="tr-chart-title">По бумагам и таймфреймам</div>')
    st.dataframe(df, width="stretch", hide_index=True, column_config={
        "Попаданий": st.column_config.ProgressColumn("Попаданий, %", min_value=0, max_value=100, format="%d%%"),
        "Brier": st.column_config.NumberColumn("Brier", format="%.3f"),
    })


# ─── Режим «Сделка» ───────────────────────────────────────────────────────────

def trade_block(attempts: list[dict]) -> None:
    s = S.trade_stats(attempts)
    if not s["n"]:
        empty("Сделок ещё нет", "Переключись на режим «Сделка» — здесь появятся средний R, кривая капитала в R и разбивка.")
        return
    lo, hi = s["ci"]
    pf = s["profit_factor"]
    tiles([
        {"label": "Средний R", "value": _signed(s["avg_r"]), "unit": "R",
         "sub": "матожидание одной сделки в единицах риска",
         "tag": "в плюс" if s["avg_r"] > 0 else "в минус", "tag_color": GAIN if s["avg_r"] > 0 else LOSS},
        {"label": "Суммарный R", "value": _signed(s["total_r"]), "unit": "R",
         "sub": f'лучшая {_signed(s["best"])}R · худшая {_signed(s["worst"])}R'},
        {"label": "Прибыльных", "value": _pct(s["win_rate"]),
         "sub": f'95% интервал <b>{_pct(lo)}–{_pct(hi)}</b>'},
        {"label": "Профит-фактор", "value": f"{pf:.2f}" if pf is not None else "—",
         "sub": f'{s["n"]} сделок · тейк {s["reasons"].get("take", 0)} · стоп {s["reasons"].get("stop", 0)} · '
                f'по времени {s["reasons"].get("close", 0)}'},
    ])

    c1, c2 = st.columns([1.15, 1], gap="large")
    with c1:
        xs = list(range(0, s["n"] + 1))
        ys = [0.0] + s["equity"]
        fig = go.Figure()
        fig.add_hline(y=0, line=dict(color="rgba(189,180,236,0.35)", width=1))
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode="lines", line=dict(color=ACCENT, width=2, shape="linear"),
            fill="tozeroy", fillcolor="rgba(139,108,255,0.10)",
            hovertemplate="Сделка %{x}<br>Итого: %{y:+.2f}R<extra></extra>",
        ))
        fig.add_trace(go.Scatter(x=[xs[-1]], y=[ys[-1]], mode="markers+text", hoverinfo="skip",
                                 marker=dict(size=10, color=ACCENT, line=dict(color=SURFACE, width=2)),
                                 text=[f"{_signed(ys[-1])}R"], textposition="middle left",
                                 textfont=dict(color=INK, size=12)))
        _layout(fig, xaxis=dict(title="сделка №", rangemode="tozero"), yaxis=dict(title="накоплено, R"))
        _chart(fig, "Кривая капитала в R", "Сумма результатов по порядку сделок")
    with c2:
        rs = s["r_values"]
        fig = go.Figure()
        fig.add_trace(go.Histogram(x=[r for r in rs if r <= 0], xbins=dict(size=0.5), marker=dict(color=LOSS, cornerradius=4),
                                   hovertemplate="%{x}R: %{y} сделок<extra>убыток</extra>"))
        fig.add_trace(go.Histogram(x=[r for r in rs if r > 0], xbins=dict(size=0.5), marker=dict(color=GAIN, cornerradius=4),
                                   hovertemplate="%{x}R: %{y} сделок<extra>прибыль</extra>"))
        fig.add_vline(x=0, line=dict(color="rgba(189,180,236,0.35)", width=1))
        _layout(fig, barmode="overlay", bargap=0.08, xaxis=dict(title="результат сделки, R"), yaxis=dict(title="сделок"))
        _chart(fig, "Распределение результатов", "Слева от нуля — убытки, справа — прибыль")

    df = S.breakdown(attempts, "trade")
    st.html('<div class="tr-chart-title">По бумагам и таймфреймам</div>')
    st.dataframe(df, width="stretch", hide_index=True, column_config={
        "Прибыльных": st.column_config.ProgressColumn("Прибыльных, %", min_value=0, max_value=100, format="%d%%"),
    })


# ─── Журнал ───────────────────────────────────────────────────────────────────

def journal_block(attempts: list[dict], export_bytes: bytes | None, on_import) -> None:
    if attempts:
        st.dataframe(S.history_table(attempts), width="stretch", hide_index=True, height=360)
    else:
        empty("Журнал пуст", "Каждая попытка сохраняется сюда: что было на графике, твой прогноз и чем всё кончилось.")

    c1, c2 = st.columns([1, 1.4], gap="large")
    with c1:
        st.download_button(
            "⬇ Выгрузить журнал (CSV)", data=export_bytes or b"", file_name="trader-journal.csv",
            mime="text/csv", width="stretch", disabled=not attempts,
        )
        st.html('<div class="tr-cap">Журнал привязан к этому браузеру и хранится на сервере. '
                'Сервер иногда перезапускается — выгружай CSV, чтобы ничего не потерять.</div>')
    with c2:
        up = st.file_uploader("Восстановить из CSV", type="csv", key="tr_import",
                              help="Файл, выгруженный кнопкой слева. Повторы не задвоятся.")
        if up is not None:
            on_import(up)


def render(attempts: list[dict], export_bytes: bytes | None, on_import) -> None:
    st.markdown(css(), unsafe_allow_html=True)
    section("02 / СТАТИСТИКА", "Твой журнал",
            "Точность против базы случайного угадывания, калибровка уверенности и результаты сделок в R. "
            "Каждая попытка сохраняется — это твой торговый журнал.")
    tab_q, tab_t, tab_j = st.tabs(["Быстрый", "Сделка", f"Журнал · {len(attempts)}"])
    with tab_q:
        quick_block(attempts)
    with tab_t:
        trade_block(attempts)
    with tab_j:
        journal_block(attempts, export_bytes, on_import)
