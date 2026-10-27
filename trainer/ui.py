"""HTML/CSS страницы тренажёра вокруг игрового компонента: фон, заставка, подвал.

Заставка — сумеречный пейзаж в духе референсов: слоистые горы, солнце
и звёзды. Гребни гор — настоящие ценовые графики Мосбиржи, сглаженные:
это не просто картинка, а те самые котировки, на которых идёт игра.
"""

from __future__ import annotations

import base64
from functools import lru_cache

import numpy as np

from trainer import config
from trainer.dataset import available_series, load_series

FONTS = (
    "https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@500;700"
    "&family=Onest:wght@400;500;600;700&family=Unbounded:wght@500;700;900&display=swap"
)

W, H = 1600, 460

# (тикер, начало, конец, базовая линия, амплитуда, заливка сверху, снизу, прозрачность)
RIDGES = [
    ("LKOH", "2016-01-01", "2019-06-30", 285, 200, "#8a5ad6", "#3d2a86", 0.55),
    ("MGNT", "2018-01-01", "2021-12-31", 335, 175, "#5f3aae", "#2c1d6e", 0.78),
    ("SBER", "2022-06-01", "2025-06-30", 385, 140, "#3a2584", "#1c1250", 0.94),
    ("SBER", "2015-01-01", "2019-12-31", 440, 100, "#1c1450", "#0b0825", 1.0),
]


def _segment(ticker: str, start: str, end: str, n: int = 110) -> np.ndarray:
    """Закрытия за период → n точек, сглаженных скользящим средним."""
    if (ticker, "1d") not in available_series():
        rng = np.random.default_rng(len(ticker))
        values = np.cumsum(rng.normal(0, 1, 400))
    else:
        values = load_series(ticker, "1d").loc[start:end, "close"].to_numpy()
    x = np.linspace(0, len(values) - 1, n)
    v = np.interp(x, np.arange(len(values)), values)
    k = 3
    v = np.convolve(np.pad(v, k, mode="edge"), np.ones(2 * k + 1) / (2 * k + 1), mode="valid")
    return (v - v.min()) / (v.max() - v.min() + 1e-9)


def _ridge(values: np.ndarray, base: float, amp: float) -> tuple[str, str]:
    xs = np.linspace(-20, W + 20, len(values))
    ys = base - values * amp
    crest = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    return f"M-20,{H} L{crest} L{W + 20},{H} Z", f"M{crest.replace(' ', ' L')}"


@lru_cache(maxsize=1)
def hero_svg() -> str:
    rng = np.random.default_rng(7)
    stars = "".join(
        f'<circle class="star{" tw" if i % 4 == 0 else ""}" cx="{x:.0f}" cy="{y:.0f}" r="{r:.1f}" '
        f'style="animation-delay:{d:.1f}s"/>'
        for i, (x, y, r, d) in enumerate(zip(
            rng.uniform(0, W, 70), rng.uniform(8, 210, 70), rng.uniform(0.6, 1.7, 70), rng.uniform(0, 4, 70)
        ))
    )
    # Полосы «synthwave» на нижней половине солнца.
    stripes = "".join(
        f'<rect x="0" y="{y}" width="{W}" height="{h}" fill="black"/>'
        for y, h in [(286, 4), (304, 6), (324, 8), (346, 10), (370, 12)]
    )
    layers = []
    for i, (t, s, e, base, amp, top, bottom, op) in enumerate(RIDGES):
        fill, crest = _ridge(_segment(t, s, e), base, amp)
        layers.append(
            f'<linearGradient id="rg{i}" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0" stop-color="{top}"/><stop offset="1" stop-color="{bottom}"/></linearGradient>'
            f'<path d="{fill}" fill="url(#rg{i})" opacity="{op}"/>'
        )
        if i == len(RIDGES) - 1:
            # Гребень ближней горы — светящаяся «ценовая линия».
            layers.append(
                f'<path d="{crest}" fill="none" stroke="url(#crest)" stroke-width="2.4" '
                f'filter="url(#glow)" class="crest"/>'
            )
        elif i == 2:
            layers.append(f'<path d="{crest}" fill="none" stroke="rgba(255,154,60,0.35)" stroke-width="1.2"/>')

    # Стили внутри SVG: он подключается картинкой (st.html вырезает инлайновый SVG),
    # и CSS страницы до него не дотягивается.
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMax slice">
  <style>
    .star {{ fill: #fff; opacity: .7; }}
    .tw {{ animation: tw 3.6s ease-in-out infinite; }}
    @keyframes tw {{ 0%, 100% {{ opacity: .25; }} 50% {{ opacity: .95; }} }}
    .crest {{ stroke-dasharray: 3200; stroke-dashoffset: 3200; animation: draw 2.4s cubic-bezier(.2,0,0,1) .2s forwards; }}
    @keyframes draw {{ to {{ stroke-dashoffset: 0; }} }}
    @media (prefers-reduced-motion: reduce) {{ .tw, .crest {{ animation: none; stroke-dashoffset: 0; }} }}
  </style>
  <defs>
    <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#090622"/>
      <stop offset="0.38" stop-color="#1d1462"/>
      <stop offset="0.62" stop-color="#4b1f7e"/>
      <stop offset="0.80" stop-color="#a8306f"/>
      <stop offset="1" stop-color="#ff8a4c"/>
    </linearGradient>
    <linearGradient id="sun" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#fff1b8"/>
      <stop offset="0.45" stop-color="#ffb347"/>
      <stop offset="1" stop-color="#ff4fa8"/>
    </linearGradient>
    <linearGradient id="crest" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#ff4fa8" stop-opacity="0.2"/>
      <stop offset="0.5" stop-color="#ff9a3c"/>
      <stop offset="1" stop-color="#ffd166"/>
    </linearGradient>
    <radialGradient id="halo" cx="0.5" cy="0.5" r="0.5">
      <stop offset="0" stop-color="#ff9a3c" stop-opacity="0.55"/>
      <stop offset="1" stop-color="#ff4fa8" stop-opacity="0"/>
    </radialGradient>
    <mask id="sunmask"><rect x="0" y="0" width="{W}" height="{H}" fill="white"/>{stripes}</mask>
    <filter id="glow" x="-10%" y="-50%" width="120%" height="200%">
      <feGaussianBlur stdDeviation="3" result="b"/>
      <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
  </defs>
  <rect width="{W}" height="{H}" fill="url(#sky)"/>
  <g class="stars">{stars}</g>
  <circle cx="1180" cy="300" r="250" fill="url(#halo)"/>
  <circle cx="1180" cy="300" r="150" fill="url(#sun)" mask="url(#sunmask)"/>
  {''.join(layers)}
</svg>"""


def page_css() -> str:
    return f"""
<style>
@import url('{FONTS}');

:root {{
  --tr-night: #0b0920;
  --tr-line: rgba(170, 150, 255, 0.14);
  --tr-text: #f5f1ff;
  --tr-text-2: #bdb4ec;
  --tr-text-3: #8279bd;
  --tr-gold: #ffd166;
  --tr-sun: #ff9a3c;
  --tr-pink: #ff4fa8;
  --tr-violet: #8b6cff;
  --tr-mint: #2ee6a8;
  --tr-coral: #ff5c7a;
  --tr-display: "Unbounded", "Onest", system-ui, sans-serif;
  --tr-ui: "Onest", system-ui, -apple-system, "Segoe UI", sans-serif;
  --tr-mono: "JetBrains Mono", ui-monospace, monospace;
  --tr-ease: cubic-bezier(0.2, 0, 0, 1);
}}

.stApp {{
  background:
    radial-gradient(1200px 600px at 15% -10%, rgba(139, 108, 255, 0.22), transparent 60%),
    radial-gradient(900px 500px at 100% 0%, rgba(255, 79, 168, 0.10), transparent 60%),
    var(--tr-night);
  font-family: var(--tr-ui);
  -webkit-font-smoothing: antialiased;
}}
/* Индикатор «выполняется / Stop» Streamlit в игре лишний: у неё свои индикаторы ожидания */
[data-testid="stStatusWidget"] {{ visibility: hidden; }}
/* ── Шапка с меню разделов (st.navigation position="top") ── */
[data-testid="stHeader"] {{
  background: rgba(11, 9, 32, 0.72);
  -webkit-backdrop-filter: blur(14px);
  backdrop-filter: blur(14px);
  box-shadow: 0 1px 0 var(--tr-line);
}}
a[data-testid="stTopNavLink"] {{
  border-radius: 999px;
  padding-left: 14px; padding-right: 14px;
  transition: background-color 150ms var(--tr-ease), box-shadow 150ms var(--tr-ease);
}}
a[data-testid="stTopNavLink"] [data-testid="stMarkdownContainer"] p {{
  font-family: var(--tr-ui); font-weight: 500; color: var(--tr-text-2);
}}
a[data-testid="stTopNavLink"]:hover {{ background: rgba(255, 255, 255, 0.06); }}
a[data-testid="stTopNavLink"][aria-current="page"] {{
  background: rgba(255, 209, 102, 0.10);
  box-shadow: inset 0 0 0 1px rgba(255, 209, 102, 0.40);
}}
a[data-testid="stTopNavLink"][aria-current="page"] [data-testid="stMarkdownContainer"] p {{ color: var(--tr-gold); font-weight: 600; }}
.block-container {{ padding-top: 4.6rem; max-width: 1480px; }}
h1, h2, h3 {{ text-wrap: balance; }}

/* ── Заставка ── */
.tr-hero {{
  position: relative;
  isolation: isolate;
  min-height: 330px;
  margin-bottom: 18px;
  border-radius: 28px;
  overflow: hidden;
  box-shadow: 0 0 0 1px var(--tr-line), 0 30px 80px rgba(4, 2, 18, 0.6);
}}
.tr-hero {{
  /* st.html вырезает и инлайновый SVG, и <img> с SVG — поэтому фоном через CSS */
  background: #0b0826 url("{hero_img_src()}") center bottom / cover no-repeat;
}}
.tr-hero::after {{
  /* затемнение слева, чтобы текст читался поверх неба */
  content: ""; position: absolute; inset: 0; z-index: -1;
  background: linear-gradient(90deg, rgba(9, 6, 34, 0.78) 0%, rgba(9, 6, 34, 0.35) 45%, transparent 70%);
}}
.tr-hero .inner {{
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 14px;
  max-width: 640px;
  padding: 36px 40px 34px;
}}
.tr-hero .kicker {{
  display: flex; align-items: center; gap: 10px;
  font-family: var(--tr-mono); font-size: 11px; font-weight: 700; letter-spacing: 0.18em;
  color: var(--tr-gold); text-transform: uppercase;
}}
.tr-hero .kicker i {{ width: 22px; height: 1px; background: var(--tr-gold); display: inline-block; }}
.tr-hero h1 {{
  margin: 0; padding: 0;
  font-family: var(--tr-display); font-weight: 900;
  font-size: clamp(38px, 6.2vw, 84px); line-height: 0.92; letter-spacing: -0.02em;
  color: var(--tr-text);
}}
.tr-hero h1 .l2 {{
  display: block;
  background: linear-gradient(100deg, #ffd166 0%, #ff9a3c 40%, #ff4fa8 100%);
  -webkit-background-clip: text; background-clip: text; color: transparent;
}}
.tr-hero h1 sup {{ font-size: 0.45em; vertical-align: top; position: relative; top: 0.1em; color: var(--tr-gold); -webkit-text-fill-color: var(--tr-gold); }}
.tr-hero .lead {{
  margin: 0; max-width: 520px;
  font-size: 16px; line-height: 1.5; color: #ddd6ff; text-wrap: pretty;
}}
.tr-hero .steps {{ display: flex; gap: 8px; flex-wrap: wrap; margin-top: 4px; }}
.tr-hero .step {{
  display: flex; align-items: center; gap: 8px;
  padding: 8px 14px 8px 10px; border-radius: 999px;
  background: rgba(9, 6, 34, 0.55); backdrop-filter: blur(6px);
  box-shadow: inset 0 0 0 1px var(--tr-line);
  font-size: 13px; color: var(--tr-text);
}}
.tr-hero .step b {{ font-family: var(--tr-mono); font-size: 11px; color: var(--tr-gold); }}
.tr-hero .side {{
  position: absolute; left: 14px; bottom: 26px;
  writing-mode: vertical-rl; transform: rotate(180deg);
  font-family: var(--tr-mono); font-size: 9px; letter-spacing: 0.3em; color: rgba(255, 255, 255, 0.35);
}}
.tr-hero .credit {{
  position: absolute; right: 18px; bottom: 14px;
  font-size: 11px; color: rgba(255, 255, 255, 0.55);
}}

/* ── Подвал ── */
.tr-footer {{
  margin: 28px 0 8px; padding-top: 16px;
  display: flex; justify-content: space-between; gap: 12px; flex-wrap: wrap;
  font-size: 12px; color: var(--tr-text-3);
  box-shadow: 0 -1px 0 var(--tr-line);
}}
.tr-footer a {{ color: var(--tr-text-2); text-decoration: none; box-shadow: 0 1px 0 var(--tr-line); }}
.tr-footer a:hover {{ color: var(--tr-gold); }}

@media (max-width: 760px) {{
  .tr-hero {{ min-height: 300px; border-radius: 22px; }}
  .tr-hero .inner {{ padding: 26px 22px 24px 30px; }}
  .tr-hero .lead {{ font-size: 14px; }}
  .tr-hero .credit {{ display: none; }}
}}
</style>
"""


@lru_cache(maxsize=1)
def hero_img_src() -> str:
    return "data:image/svg+xml;base64," + base64.b64encode(hero_svg().encode("utf-8")).decode("ascii")


def hero_html() -> str:
    first = config.DAILY_SINCE.year
    return f"""
<div class="tr-hero">
  <div class="inner">
    <div class="kicker"><i></i>Мосбиржа · {first}—2026 · игра</div>
    <h1>Тренажёр<span class="l2">трейдера<sup>*</sup></span></h1>
    <p class="lead">Видишь кусок графика — решаешь, что будет дальше. Тикер и&nbsp;даты скрыты
      до ответа, так что память не подскажет: только чтение графика.</p>
    <div class="steps">
      <span class="step"><b>01</b>Смотри</span>
      <span class="step"><b>02</b>Прогнозируй</span>
      <span class="step"><b>03</b>Раскрой будущее</span>
      <span class="step"><b>04</b>Разбери</span>
    </div>
  </div>
  <div class="side">SBER · LKOH · YDEX · MGNT</div>
  <div class="credit">* горы — это настоящие графики акций</div>
</div>
"""


def footer_html() -> str:
    return """
<div class="tr-footer">
  <span>Котировки — ISS Мосбиржи · заседания — cbr.ru · дивиденды — dohod.ru</span>
  <span>Графики — <a href="https://www.tradingview.com/" target="_blank" rel="noopener">TradingView Lightweight Charts</a></span>
</div>
"""
