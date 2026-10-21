/* Тренажёр трейдера — игровой компонент для Streamlit.
 *
 * Python ведёт раунд: присылает видимые свечи (фаза predict), получает ответ,
 * считает исход и только тогда присылает будущее (фаза reveal). Здесь — всё,
 * что видит и трогает игрок: график, туман будущего, рисование, панель
 * ответа, анимация раскрытия и экран результата.
 */
(() => {
  "use strict";

  const LC = window.LightweightCharts;

  // ─── Время: вместо дат — номера свечей ────────────────────────────────────
  const T0 = 1577836800;          // произвольная опора, на экране не видна
  const STEP = 86400;
  const tOf = (i) => T0 + i * STEP;
  const iOf = (t) => Math.round((t - T0) / STEP);

  const C = {
    up: "#2ee6a8", down: "#ff5c7a",
    upVol: "rgba(46,230,168,0.28)", downVol: "rgba(255,92,122,0.28)",
    ma1: "#ff9a3c", ma2: "#c77dff",
    bb: "rgba(189,180,236,0.55)", bbMid: "rgba(189,180,236,0.22)",
    rsi: "#ffd166", macd: "#5cc8ff", signal: "#ff9a3c",
    level: "#ffd166", trend: "#ff4fa8", preview: "rgba(255,79,168,0.6)",
    entry: "#f5f1ff", stop: "#ff5c7a", take: "#2ee6a8",
    text: "#8f86c8", grid: "rgba(170,150,255,0.06)", cross: "rgba(255,209,102,0.45)",
    event: { cbr_meeting: "#8b6cff", earnings: "#5cc8ff", dividend_cutoff: "#ffd166" },
  };
  const EVENT_SHORT = { cbr_meeting: "ЦБ", earnings: "Отч", dividend_cutoff: "Див" };

  const ICON = {
    up: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V5M5 12l7-7 7 7"/></svg>',
    down: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14M5 12l7 7 7-7"/></svg>',
    flat: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12h16M8 8l-4 4 4 4M16 8l4 4-4 4"/></svg>',
    lock: '<svg class="lock" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><rect x="5" y="11" width="14" height="10" rx="2.5"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg>',
    level: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M3 12h18" stroke-dasharray="3 3"/><circle cx="12" cy="12" r="2.2" fill="currentColor"/></svg>',
    trend: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M4 19L20 5"/><circle cx="6" cy="17" r="2" fill="currentColor"/><circle cx="18" cy="7" r="2" fill="currentColor"/></svg>',
    trash: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/></svg>',
    next: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M13 6l6 6-6 6"/></svg>',
    move: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4v16M8 8l4-4 4 4M8 16l4 4 4-4"/></svg>',
    dash: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round"><path d="M7 12h10"/></svg>',
    help: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M9.6 9.4a2.5 2.5 0 0 1 4.8.9c0 1.7-2.4 2.1-2.4 3.6"/><circle cx="12" cy="17.2" r=".7" fill="currentColor"/></svg>',
    sliders: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M4 7h9M18 7h2M4 17h3M12 17h8"/><circle cx="15.5" cy="7" r="2.3"/><circle cx="9.5" cy="17" r="2.3"/></svg>',
    eye: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="2.8"/></svg>',
    close: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>',
    flame: '<svg class="flame" viewBox="0 0 24 24"><defs><linearGradient id="fl" x1="0" y1="1" x2="0" y2="0"><stop offset="0" stop-color="#ff4fa8"/><stop offset=".55" stop-color="#ff9a3c"/><stop offset="1" stop-color="#ffd166"/></linearGradient></defs><path fill="url(#fl)" d="M12 2c1 3.2 4.6 5.2 4.6 9.6A4.6 4.6 0 0 1 12 16.2a4.6 4.6 0 0 1-4.6-4.6c0-1.7.7-3 1.6-4 .2 1.6 1 2.6 2 3C10.6 7.6 11 4.6 12 2zm0 22a7 7 0 0 1-7-7c0-1.4.4-2.7 1-3.8.5 3.2 3 5.4 6 5.4s5.5-2.2 6-5.4c.6 1.1 1 2.4 1 3.8a7 7 0 0 1-7 7z"/></svg>',
  };

  // ─── Хранилище браузера (только удобства, всё в try/catch) ────────────────
  const store = {
    get(k, d) { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* приватный режим */ } },
  };
  const PLAYER_KEY = "stratconstruct.trainer.player";
  const PREFS_KEY = "stratconstruct.trainer.prefs";
  const HOWTO_KEY = "stratconstruct.trainer.howto_seen";
  function playerId() {
    let id = store.get(PLAYER_KEY, null);
    if (!id) {
      id = (window.crypto && crypto.randomUUID) ? crypto.randomUUID()
        : Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
      store.set(PLAYER_KEY, id);
    }
    return id;
  }

  // ─── Протокол Streamlit ───────────────────────────────────────────────────
  const ST = {
    send(type, data) { window.parent.postMessage(Object.assign({ isStreamlitMessage: true, type }, data), "*"); },
    ready() { this.send("streamlit:componentReady", { apiVersion: 1 }); },
    height(h) { this.send("streamlit:setFrameHeight", { height: h }); },
    value(v) { this.send("streamlit:setComponentValue", { value: v, dataType: "json" }); },
  };
  function emit(event, data) {
    ST.value({
      event,
      eid: Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 8),
      round_id: S.roundId,
      player_id: S.player,
      data: data || {},
    });
  }

  // ─── Состояние ─────────────────────────────────────────────────────────────
  const S = {
    st: null,
    roundId: null,
    phase: null,
    mode: null,
    H: 100, F: 20,
    payload: null,
    labels: null,              // реальные даты (после раскрытия)
    shown: 0,                  // сколько свечей на графике
    prefs: Object.assign({ ind: ["ma1", "ma2", "vol"] }, store.get(PREFS_KEY, {})),
    tool: null,
    pendingTrend: null,
    drawings: [],
    levelLines: [],
    trendSeries: [],
    choice: null,
    confidence: 70,
    trade: { direction: "long", stop: null, take: null },
    tradeLines: null,
    drag: null,
    justDragged: false,
    waiting: false,
    revealing: false,
    revealDone: false,
    revealTimer: null,
    player: playerId(),
    lastErrorId: null,
    extra: null,               // доп. диапазон автошкалы (зоны, стоп/тейк)
    set: null,                 // фильтры раундов, пока открыты настройки
    aux: [],                   // уровни из разбора («показать на графике»)
  };

  const $ = (id) => document.getElementById(id);
  const el = {
    app: $("app"), modes: $("modes"), roundNo: $("roundNo"), mystery: $("mystery"), stats: $("stats"),
    toolbar: $("toolbar"), wrap: $("chartWrap"), chart: $("chart"), legend: $("legend"),
    fog: $("fog"), fogCap: $("fogCap"), now: $("nowLine"), overlay: $("overlay"), tip: $("tip"),
    hint: $("drawHint"), panel: $("panel"), confetti: $("confetti"),
    board: document.querySelector(".board"), review: $("review"), howto: $("howto"),
    howBtn: $("howBtn"), setBtn: $("setBtn"), settings: $("settings"),
  };
  el.howBtn.innerHTML = ICON.help + "Как играть";
  el.setBtn.innerHTML = ICON.sliders + "Настройки";
  el.setBtn.setAttribute("aria-label", "Настройки раундов");

  function shake(node) {
    node.classList.remove("shake");
    void node.offsetWidth;
    node.classList.add("shake");
  }

  const fmt = (x, d = 2) => (x == null || !isFinite(x) ? "—" : Number(x).toFixed(d));
  const sgn = (x, d = 2) => (x == null || !isFinite(x) ? "—" : (x > 0 ? "+" : x < 0 ? "−" : "") + Math.abs(x).toFixed(d));
  const pad2 = (n) => String(n).padStart(2, "0");
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const reduceMotion = () => window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ─── График ────────────────────────────────────────────────────────────────
  const chart = LC.createChart(el.chart, {
    autoSize: true,
    layout: {
      background: { type: LC.ColorType.Solid, color: "rgba(0,0,0,0)" },
      textColor: C.text,
      fontFamily: "Onest, system-ui, sans-serif",
      fontSize: 11,
      attributionLogo: false,     // ссылка на TradingView — в подвале страницы
      panes: { separatorColor: "rgba(170,150,255,0.12)", separatorHoverColor: "rgba(170,150,255,0.25)", enableResize: false },
    },
    grid: { vertLines: { color: C.grid }, horzLines: { color: "rgba(170,150,255,0.08)" } },
    rightPriceScale: { borderVisible: false, scaleMargins: { top: 0.12, bottom: 0.1 } },
    timeScale: {
      borderVisible: false,
      // fixRightEdge не ставим: он не даёт показать пустые слоты будущего справа.
      shiftVisibleRangeOnNewBar: false,
      lockVisibleTimeRangeOnResize: true,
      tickMarkFormatter: (t) => tickLabel(t),
    },
    crosshair: {
      mode: LC.CrosshairMode.Normal,
      vertLine: { color: C.cross, labelBackgroundColor: "#2a2270", style: LC.LineStyle.Dashed },
      horzLine: { color: C.cross, labelBackgroundColor: "#2a2270", style: LC.LineStyle.Dashed },
    },
    localization: { locale: "ru-RU", timeFormatter: (t) => crossLabel(t), priceFormatter: (p) => fmt(p) },
    handleScroll: false,
    handleScale: false,
  });

  function tickLabel(t) {
    const i = iOf(t);
    if (S.labels && S.labels[i]) {
      const lab = S.labels[i];                       // «дд.мм.гггг» или «дд.мм.гггг чч:мм»
      if (lab.length <= 10) return lab.slice(0, 6) + lab.slice(8, 10);   // дд.мм.гг
      const day = lab.slice(0, 5), prev = S.labels[i - 1];
      return !prev || prev.slice(0, 5) !== day ? day : lab.slice(11, 16); // дд.мм на смене дня, иначе чч:мм
    }
    const rel = i - (S.H - 1);
    return rel === 0 ? "сейчас" : (rel > 0 ? "+" + rel : "−" + Math.abs(rel));
  }
  // Подписи делений библиотека кэширует по времени, а «время» в каждом раунде
  // одно и то же (номера свечей). Новый форматтер сбрасывает кэш — иначе
  // в новом раунде остались бы даты прошлого.
  function refreshAxis() {
    chart.applyOptions({ timeScale: { tickMarkFormatter: (t) => tickLabel(t) } });
  }
  function crossLabel(t) {
    const i = iOf(t);
    if (S.labels && S.labels[i]) return S.labels[i];
    const rel = i - (S.H - 1);
    return rel === 0 ? "свеча 0 · сейчас" : "свеча " + (rel > 0 ? "+" + rel : "−" + Math.abs(rel));
  }

  // Невидимый «каркас» на все слоты: ось времени сразу знает про зону будущего.
  const spacer = chart.addSeries(LC.LineSeries, {
    lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false,
    autoscaleInfoProvider: () => null,
  });
  const candles = chart.addSeries(LC.CandlestickSeries, {
    upColor: C.up, downColor: C.down, borderVisible: false,
    wickUpColor: C.up, wickDownColor: C.down,
    priceLineVisible: false, lastValueVisible: true,
  });
  // Невидимая серия-«распорка»: две точки на границах зоны боковика или
  // стопа/тейка, чтобы автошкала держала их в кадре. Свой autoscaleInfoProvider
  // у свечей не годится — вместе с маркерами он уходит в бесконечную рекурсию.
  const extent = chart.addSeries(LC.LineSeries, {
    color: "rgba(0,0,0,0)", lineVisible: false, pointMarkersVisible: false,
    lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false,
  });
  const markers = LC.createSeriesMarkers(candles, []);
  const preview = chart.addSeries(LC.LineSeries, {
    color: C.preview, lineWidth: 2, lineStyle: LC.LineStyle.Dashed,
    lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false,
    autoscaleInfoProvider: () => null,
  });

  let ind = {};               // серии индикаторов

  function indData(key, count) {
    const arr = (S.payload && S.payload.indicators[key]) || [];
    const out = [];
    for (let i = 0; i < Math.min(count, arr.length); i++) {
      out.push(arr[i] == null ? { time: tOf(i) } : { time: tOf(i), value: arr[i] });
    }
    return out;
  }
  function volBar(c, i) {
    return { time: tOf(i), value: c[4] || 0, color: c[3] >= c[0] ? C.upVol : C.downVol };
  }
  function histBar(v, i) {
    return v == null ? { time: tOf(i) } : { time: tOf(i), value: v, color: v >= 0 ? "rgba(46,230,168,0.55)" : "rgba(255,92,122,0.55)" };
  }
  const lineOpts = (color, width = 2, extra = {}) => Object.assign({
    color, lineWidth: width, lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false,
  }, extra);

  function allBars() {
    const p = S.payload;
    return p.future ? p.candles.concat(p.future) : p.candles;
  }

  function buildIndicators() {
    Object.values(ind).forEach((s) => { try { chart.removeSeries(s); } catch (e) { /* уже удалена */ } });
    ind = {};
    if (!S.payload) return;
    const on = new Set(S.prefs.ind);
    const n = S.shown;
    const bars = allBars().slice(0, n);

    if (on.has("vol")) {
      ind.vol = chart.addSeries(LC.HistogramSeries, { priceScaleId: "vol", priceFormat: { type: "volume" }, lastValueVisible: false, priceLineVisible: false }, 0);
      chart.priceScale("vol", 0).applyOptions({ scaleMargins: { top: 0.82, bottom: 0 }, visible: false });
      ind.vol.setData(bars.map(volBar));
    }
    if (on.has("bb")) {
      ind.bbU = chart.addSeries(LC.LineSeries, lineOpts(C.bb, 1), 0);
      ind.bbM = chart.addSeries(LC.LineSeries, lineOpts(C.bbMid, 1, { lineStyle: LC.LineStyle.Dashed }), 0);
      ind.bbL = chart.addSeries(LC.LineSeries, lineOpts(C.bb, 1), 0);
      ind.bbU.setData(indData("bb_upper", n));
      ind.bbM.setData(indData("bb_mid", n));
      ind.bbL.setData(indData("bb_lower", n));
    }
    if (on.has("ma1")) { ind.ma1 = chart.addSeries(LC.LineSeries, lineOpts(C.ma1, 2), 0); ind.ma1.setData(indData("ma1", n)); }
    if (on.has("ma2")) { ind.ma2 = chart.addSeries(LC.LineSeries, lineOpts(C.ma2, 2), 0); ind.ma2.setData(indData("ma2", n)); }

    let pane = 1;
    if (on.has("rsi")) {
      ind.rsi = chart.addSeries(LC.LineSeries, lineOpts(C.rsi, 2, { lastValueVisible: true }), pane);
      ind.rsi.setData(indData("rsi", n));
      [70, 30].forEach((v) => ind.rsi.createPriceLine({ price: v, color: "rgba(189,180,236,0.35)", lineWidth: 1, lineStyle: LC.LineStyle.Dashed, axisLabelVisible: false, title: "" }));
      pane++;
    }
    if (on.has("macd")) {
      ind.macdH = chart.addSeries(LC.HistogramSeries, { lastValueVisible: false, priceLineVisible: false }, pane);
      ind.macd = chart.addSeries(LC.LineSeries, lineOpts(C.macd, 2), pane);
      ind.macdS = chart.addSeries(LC.LineSeries, lineOpts(C.signal, 1.5), pane);
      const h = (S.payload.indicators.macd_hist || []);
      ind.macdH.setData(h.slice(0, n).map(histBar));
      ind.macd.setData(indData("macd", n));
      ind.macdS.setData(indData("macd_signal", n));
    }
    const panes = chart.panes();
    panes.forEach((p, k) => p.setStretchFactor(k === 0 ? 3.2 : 1));
    fitWindow();
    requestLayout();
  }

  function pushBar(i) {
    const c = allBars()[i];
    if (!c) return;
    candles.update({ time: tOf(i), open: c[0], high: c[1], low: c[2], close: c[3] });
    const I = S.payload.indicators;
    const upd = (s, key) => { if (s && I[key] && I[key][i] != null) s.update({ time: tOf(i), value: I[key][i] }); };
    if (ind.vol) ind.vol.update(volBar(c, i));
    upd(ind.ma1, "ma1"); upd(ind.ma2, "ma2");
    upd(ind.bbU, "bb_upper"); upd(ind.bbM, "bb_mid"); upd(ind.bbL, "bb_lower");
    upd(ind.rsi, "rsi"); upd(ind.macd, "macd"); upd(ind.macdS, "macd_signal");
    if (ind.macdH && I.macd_hist && I.macd_hist[i] != null) ind.macdH.update(histBar(I.macd_hist[i], i));
  }

  // ─── Раскладка тумана и разметки поверх графика ───────────────────────────
  let layoutQueued = false;
  function requestLayout() {
    if (layoutQueued) return;
    layoutQueued = true;
    requestAnimationFrame(() => requestAnimationFrame(() => { layoutQueued = false; layout(); }));
  }

  function layout() {
    if (!S.payload) return;
    const ts = chart.timeScale();
    const right = ts.width();
    const bottom = el.chart.clientHeight - ts.height();
    const mainH = chart.paneSize(0).height;
    // logicalToCoordinate понимает только целые индексы — границу между свечами
    // берём как середину между соседними.
    const between = (i) => {
      const a = ts.logicalToCoordinate(i - 1), b = ts.logicalToCoordinate(i);
      return a == null || b == null ? null : (a + b) / 2;
    };
    const xNow = between(S.H);
    const xFog = S.shown >= S.H + S.F ? right : between(S.shown);
    if (xNow == null || xFog == null || right <= 0) return;
    el.wrap.classList.add("ready");

    // Туман — от последней показанной свечи до правого края.
    const fogW = Math.max(0, right - xFog);
    el.fog.style.left = xFog + "px";
    el.fog.style.width = fogW + "px";
    el.fog.style.height = bottom + "px";
    el.fog.classList.toggle("thin", fogW < 120);
    el.fog.classList.toggle("dim", S.mode === "trade");
    el.fog.classList.toggle("gone", fogW < 2);
    const left = S.H + S.F - S.shown;
    el.fogCap.textContent = left > 0 ? (left + " " + plural(left, "свеча", "свечи", "свечей") + " скрыто") : "";

    el.now.style.left = xNow + "px";
    el.now.style.height = bottom + "px";

    // Разметка в зоне будущего — шириной от «сейчас» до края.
    const zoneW = Math.max(0, right - xNow);
    const y = (p) => candles.priceToCoordinate(p);
    let html = "";
    const box = (cls, top, h, label, extraStyle = "") =>
      `<div class="zone ${cls}" style="left:${xNow}px;width:${zoneW}px;top:${Math.round(top)}px;height:${Math.max(0, Math.round(h))}px;${extraStyle}">${label ? `<span class="zl">${label}</span>` : ""}</div>`;

    const p = S.payload;
    if (S.mode === "quick" && p.atr) {
      const band = S.st.config.sideways_mult * p.atr;
      const yTop = y(p.last_close + band);
      const yBot = y(p.last_close - band);
      if (yTop != null && yBot != null) {
        const pct = (band / p.last_close * 100);
        const pick = (c) => (S.choice === c ? " pick" : "");
        html += box("upz" + pick("up"), 0, yTop, "ВВЕРХ ▲");
        html += box("band" + pick("flat"), yTop, yBot - yTop, `БОКОВИК ±${fmt(pct, 1)}%`);
        html += box("downz" + pick("down"), yBot, mainH - yBot, "ВНИЗ ▼");
      }
    }
    if (S.mode === "trade" && S.trade.stop != null) {
      const e = p.last_close, st = S.trade.stop, tk = S.trade.take;
      const yE = y(e), yS = y(st), yT = y(tk);
      if (yE != null && yS != null && yT != null) {
        const risk = Math.abs(e - st);
        const rr = Math.abs(tk - e) / risk;
        html += box("take", Math.min(yE, yT), Math.abs(yE - yT), `ТЕЙК +${fmt(rr, 1)}R`, "");
        html += box("stop", Math.min(yE, yS), Math.abs(yE - yS), "СТОП −1R", "");
      }
    }
    // События будущего, дата которых известна заранее (до ответа).
    if (S.phase === "predict" || (S.revealing && !S.revealDone)) {
      (p.events || []).filter((ev) => ev.bar >= S.shown).forEach((ev) => {
        const x = ts.logicalToCoordinate(ev.bar);
        if (x == null) return;
        const dist = ev.bar - (S.H - 1);
        html += `<div class="fevent" style="left:${x}px;height:${mainH}px"><span>${esc(EVENT_SHORT[ev.type] || "")} · через ${dist}</span></div>`;
      });
    }
    el.overlay.innerHTML = html;
  }

  // Окно графика всегда одно и то же: вся история + все слоты будущего.
  function fitWindow() {
    chart.timeScale().setVisibleLogicalRange({ from: -0.6, to: S.H + S.F - 0.4 });
  }

  chart.timeScale().subscribeSizeChange(() => { fitWindow(); requestLayout(); });
  chart.timeScale().subscribeVisibleLogicalRangeChange(requestLayout);
  new ResizeObserver(() => { requestLayout(); fitHeight(); }).observe(el.app);

  function plural(n, one, few, many) {
    const m10 = n % 10, m100 = n % 100;
    if (m10 === 1 && m100 !== 11) return one;
    if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
    return many;
  }

  function setExtraRange() {
    const p = S.payload;
    if (!p) { S.extra = null; return; }
    if (S.mode === "quick") {
      const band = S.st.config.sideways_mult * p.atr;
      S.extra = { min: p.last_close - band * 1.6, max: p.last_close + band * 1.6 };
    } else if (S.trade.stop != null) {
      S.extra = { min: Math.min(S.trade.stop, S.trade.take), max: Math.max(S.trade.stop, S.trade.take) };
    } else {
      S.extra = null;
    }
    extent.setData(S.extra
      ? [{ time: tOf(S.H), value: S.extra.min }, { time: tOf(S.H + 1), value: S.extra.max }]
      : []);
  }

  // ─── Легенда и подсказки ───────────────────────────────────────────────────
  function legendFor(i) {
    const bars = allBars();
    const c = bars[Math.max(0, Math.min(i, S.shown - 1))];
    if (!c) { el.legend.innerHTML = ""; return; }
    const k = Math.max(0, Math.min(i, S.shown - 1));
    const prev = k > 0 ? bars[k - 1][3] : c[0];
    const chg = (c[3] / prev - 1) * 100;
    el.legend.innerHTML =
      `<span>О <b>${fmt(c[0])}</b></span><span>М <b>${fmt(c[1])}</b></span>` +
      `<span>Н <b>${fmt(c[2])}</b></span><span>З <b>${fmt(c[3])}</b></span>` +
      `<span class="chg ${chg >= 0 ? "pos" : "neg"}">${sgn(chg)}%</span>`;
  }

  chart.subscribeCrosshairMove((param) => {
    if (!S.payload) return;
    const i = param.logical != null ? Math.round(param.logical) : S.shown - 1;
    legendFor(param.point ? i : S.shown - 1);

    // Превью трендовой линии. setData внутри обработчика курсора заставляет
    // библиотеку снова прислать событие курсора — обновляем на следующем кадре
    // и только если конец линии сдвинулся.
    if (S.tool === "trend" && S.pendingTrend && param.point && param.paneIndex === 0) {
      const price = candles.coordinateToPrice(param.point.y);
      const b = { i: clampBar(i), p: price };
      if (price != null && b.i !== S.pendingTrend.i) schedulePreview(b);
    }

    // Подсказка у маркера события
    const evs = (S.payload.events || []).filter((ev) => ev.bar === i && ev.bar < S.shown);
    if (param.point && evs.length) {
      el.tip.innerHTML = evs.map((ev) => `<span class="k">${esc(EVENT_SHORT[ev.type] || "")} · свеча ${relBar(ev.bar)}</span>${esc(ev.label)}`).join("<br>");
      const x = Math.min(param.point.x + 14, el.wrap.clientWidth - 270);
      el.tip.style.left = Math.max(8, x) + "px";
      el.tip.style.top = Math.max(8, param.point.y - 50) + "px";
      el.tip.classList.add("show");
    } else {
      el.tip.classList.remove("show");
    }
  });

  let previewNext = null, previewDrawn = null, previewQueued = false;
  function schedulePreview(b) {
    previewNext = b;
    if (previewQueued) return;
    previewQueued = true;
    requestAnimationFrame(() => {
      previewQueued = false;
      const a = S.pendingTrend, end = previewNext;
      if (!a || !end) return;
      if (previewDrawn && previewDrawn.i === end.i && Math.abs(previewDrawn.p - end.p) < 1e-6) return;
      previewDrawn = end;
      const [p1, p2] = a.i < end.i ? [a, end] : [end, a];
      preview.setData([{ time: tOf(p1.i), value: p1.p }, { time: tOf(p2.i), value: p2.p }]);
    });
  }

  const relBar = (bar) => { const r = bar - (S.H - 1); return r === 0 ? "0" : (r > 0 ? "+" + r : "−" + Math.abs(r)); };
  const clampBar = (i) => Math.max(0, Math.min(S.H + S.F - 1, i));

  // ─── Рисование ─────────────────────────────────────────────────────────────
  function addLevel(price, record = true) {
    const line = candles.createPriceLine({ price, color: C.level, lineWidth: 1, lineStyle: LC.LineStyle.Dashed, axisLabelVisible: true, title: "" });
    S.levelLines.push(line);
    if (record) S.drawings.push({ type: "level", price: +price.toFixed(4) });
  }
  function addTrend(a, b, record = true) {
    if (a.i === b.i) return;
    const [p1, p2] = a.i < b.i ? [a, b] : [b, a];
    const slope = (p2.p - p1.p) / (p2.i - p1.i);
    const end = S.H + S.F - 1;              // луч до конца зоны будущего
    const s = chart.addSeries(LC.LineSeries, lineOpts(C.trend, 2, { autoscaleInfoProvider: () => null }), 0);
    s.setData([{ time: tOf(p1.i), value: p1.p }, { time: tOf(end), value: p1.p + slope * (end - p1.i) }]);
    S.trendSeries.push(s);
    if (record) S.drawings.push({ type: "trend", i1: p1.i, p1: +p1.p.toFixed(4), i2: p2.i, p2: +p2.p.toFixed(4) });
  }
  function clearDrawings() {
    S.levelLines.forEach((l) => { try { candles.removePriceLine(l); } catch (e) { /* нет линии */ } });
    S.trendSeries.forEach((s) => { try { chart.removeSeries(s); } catch (e) { /* нет серии */ } });
    S.levelLines = []; S.trendSeries = []; S.drawings = []; S.pendingTrend = null;
    clearPreview();
  }
  function clearPreview() {
    previewNext = null;
    previewDrawn = null;
    preview.setData([]);
  }
  function restoreDrawings(list) {
    (list || []).forEach((d) => {
      if (d.type === "level") addLevel(d.price, false);
      if (d.type === "trend") addTrend({ i: d.i1, p: d.p1 }, { i: d.i2, p: d.p2 }, false);
    });
    S.drawings = (list || []).slice();
  }
  function setTool(tool) {
    S.tool = S.tool === tool ? null : tool;
    S.pendingTrend = null;
    clearPreview();
    renderToolbar();
    showHint();
  }
  function showHint() {
    const msg = S.tool === "level" ? "Кликни по графику — поставлю уровень · Esc — отмена"
      : S.tool === "trend" ? (S.pendingTrend ? "Теперь вторая точка" : "Кликни первую точку трендовой линии · Esc — отмена")
        : "";
    el.hint.textContent = msg;
    el.hint.classList.toggle("show", !!msg);
  }

  chart.subscribeClick((param) => {
    if (!param.point || param.paneIndex !== 0 || S.justDragged || !S.tool) return;
    const price = candles.coordinateToPrice(param.point.y);
    if (price == null || param.logical == null) return;
    const i = clampBar(Math.round(param.logical));
    if (S.tool === "level") {
      addLevel(price);
      setTool(null);
    } else if (S.tool === "trend") {
      if (!S.pendingTrend) {
        S.pendingTrend = { i, p: price };
        showHint();
      } else {
        const first = S.pendingTrend;
        S.pendingTrend = null;
        clearPreview();
        addTrend(first, { i, p: price });
        setTool(null);
      }
    }
  });

  // ─── Сделка: линии входа, стопа и тейка, перетаскивание ───────────────────
  function tradeDefaults() {
    const p = S.payload, cfg = S.st.config;
    const e = p.last_close, a = p.atr;
    const sign = S.trade.direction === "long" ? 1 : -1;
    S.trade.stop = round2(e - sign * cfg.stop_atr * a);
    S.trade.take = round2(e + sign * cfg.take_atr * a);
  }
  const round2 = (x) => Math.round(x * 100) / 100;
  const minDist = () => S.st.config.min_dist_atr * S.payload.atr;

  function ensureTradeLines() {
    if (S.mode !== "trade") { removeTradeLines(); return; }
    const e = S.payload.last_close;
    if (!S.tradeLines) {
      S.tradeLines = {
        entry: candles.createPriceLine({ price: e, color: C.entry, lineWidth: 1, lineStyle: LC.LineStyle.Dotted, axisLabelVisible: true, title: "вход" }),
        stop: candles.createPriceLine({ price: S.trade.stop, color: C.stop, lineWidth: 2, lineStyle: LC.LineStyle.Solid, axisLabelVisible: true, title: "стоп" }),
        take: candles.createPriceLine({ price: S.trade.take, color: C.take, lineWidth: 2, lineStyle: LC.LineStyle.Solid, axisLabelVisible: true, title: "тейк" }),
      };
    } else {
      S.tradeLines.entry.applyOptions({ price: e });
      S.tradeLines.stop.applyOptions({ price: S.trade.stop });
      S.tradeLines.take.applyOptions({ price: S.trade.take });
    }
  }
  function removeTradeLines() {
    if (!S.tradeLines) return;
    Object.values(S.tradeLines).forEach((l) => { try { candles.removePriceLine(l); } catch (e) { /* нет линии */ } });
    S.tradeLines = null;
  }

  function constrain(which, price) {
    const e = S.payload.last_close, d = minDist();
    const long = S.trade.direction === "long";
    if (which === "stop") return round2(long ? Math.min(price, e - d) : Math.max(price, e + d));
    return round2(long ? Math.max(price, e + d) : Math.min(price, e - d));
  }
  function setTradeLevel(which, price, fromInput = false) {
    S.trade[which] = constrain(which, price);
    ensureTradeLines();
    setExtraRange();
    updateTradeReadout(fromInput ? which : null);
    requestLayout();
  }

  function canEditTrade() { return S.mode === "trade" && S.phase === "predict" && !S.waiting; }
  function nearLine(y) {
    if (!S.tradeLines) return null;
    for (const which of ["stop", "take"]) {
      const ly = candles.priceToCoordinate(S.trade[which]);
      if (ly != null && Math.abs(ly - y) <= 7) return which;
    }
    return null;
  }
  el.wrap.addEventListener("pointerdown", (e) => {
    if (!canEditTrade() || S.tool) return;
    const r = el.wrap.getBoundingClientRect();
    const which = nearLine(e.clientY - r.top);
    if (!which) return;
    S.drag = which;
    el.wrap.setPointerCapture(e.pointerId);
    e.preventDefault();
  });
  el.wrap.addEventListener("pointermove", (e) => {
    const r = el.wrap.getBoundingClientRect();
    const yy = e.clientY - r.top;
    if (S.drag) {
      const price = candles.coordinateToPrice(yy);
      if (price != null) setTradeLevel(S.drag, price);
      return;
    }
    el.wrap.style.cursor = canEditTrade() && !S.tool && nearLine(yy) ? "ns-resize" : (S.tool ? "crosshair" : "");
  });
  const endDrag = (e) => {
    if (!S.drag) return;
    S.drag = null;
    S.justDragged = true;
    setTimeout(() => { S.justDragged = false; }, 60);
    try { el.wrap.releasePointerCapture(e.pointerId); } catch (err) { /* уже отпущен */ }
  };
  el.wrap.addEventListener("pointerup", endDrag);
  el.wrap.addEventListener("pointercancel", endDrag);

  // ─── Вкладки режимов и HUD ─────────────────────────────────────────────────
  function renderModes() {
    const modes = S.st.modes || [];
    el.modes.innerHTML = modes.map((m) => `
      <button class="mode${m.id === S.mode ? " active" : ""}${m.available ? "" : " locked"}" role="tab"
        aria-selected="${m.id === S.mode}" data-mode="${m.id}" ${m.available ? "" : 'aria-disabled="true" title="Скоро"'}>
        <span class="num">${m.number}</span>
        <span class="txt"><span class="title">${esc(m.title)}</span><span class="tag">${m.available ? esc(m.tagline) : "скоро"}</span></span>
        ${m.available ? "" : ICON.lock}
      </button>`).join("");
  }
  el.modes.addEventListener("click", (e) => {
    const b = e.target.closest(".mode");
    if (!b) return;
    const m = (S.st.modes || []).find((x) => x.id === b.dataset.mode);
    if (!m) return;
    if (!m.available) {
      shake(b);
      return;
    }
    if (m.id === S.mode || S.waiting || S.revealing) return;
    S.waiting = S.phase === "reveal";      // из результата — сразу новый раунд
    emit("mode", { mode: m.id, drawings: S.drawings });
  });

  let prevStats = "";
  function renderHUD() {
    const st = S.st;
    const showFinal = S.phase === "predict" || S.revealDone;
    const sum = (showFinal ? st.summary : st.summary_prev) || {};
    el.roundNo.textContent = pad2(st.round_no || 1);

    const ident = S.payload && S.payload.identity;
    if (ident && (S.revealDone || S.phase === "predict")) {
      el.mystery.className = "mystery revealed";
      el.mystery.innerHTML = `<span class="tk">${esc(ident.ticker)}</span><span>${esc(ident.name)}</span><span class="sep">·</span><span>${esc(ident.timeframe_label)}</span><span class="sep">·</span><span>${esc(ident.period)}</span>`;
    } else {
      el.mystery.className = "mystery";
      el.mystery.innerHTML = `<span class="q">??? · ???</span><span>тикер и даты скрыты</span>`;
    }

    const chips = [];
    chips.push(`<div class="stat fire" data-k="streak">${ICON.flame}<b>${sum.streak || 0}</b><span>серия</span></div>`);
    if (S.mode === "quick") {
      chips.push(`<div class="stat" data-k="acc"><span>точность</span><b>${sum.rounds ? sum.hits + "/" + sum.rounds : "—"}</b>${sum.rounds ? `<span>${sum.accuracy}%</span>` : ""}</div>`);
    } else {
      chips.push(`<div class="stat" data-k="r"><span>ΣR</span><b class="${(sum.total_r || 0) >= 0 ? "pos" : "neg"}">${sum.rounds ? sgn(sum.total_r) : "—"}</b></div>`);
      chips.push(`<div class="stat" data-k="wr"><span>в плюс</span><b>${sum.rounds ? sum.win_rate + "%" : "—"}</b></div>`);
    }
    chips.push(`<div class="stat" data-k="pts"><span>очки</span><b>${sum.rounds ? sgn(sum.points, 0) : "0"}</b></div>`);
    const html = chips.join("");
    if (html !== prevStats) {
      const old = {};
      el.stats.querySelectorAll(".stat").forEach((n) => { old[n.dataset.k] = n.textContent; });
      el.stats.innerHTML = html;
      if (prevStats) {
        el.stats.querySelectorAll(".stat").forEach((n) => {
          if (old[n.dataset.k] !== undefined && old[n.dataset.k] !== n.textContent) n.classList.add("bump");
        });
      }
      prevStats = html;
    }
  }

  // ─── Панель инструментов графика ───────────────────────────────────────────
  function renderToolbar() {
    const cfg = S.st.config;
    const on = new Set(S.prefs.ind);
    const indChip = (id, label, color) =>
      `<button class="chip${on.has(id) ? " on" : ""}" data-ind="${id}" style="color:${on.has(id) ? color : ""}" aria-pressed="${on.has(id)}"><span class="dot" style="background:${color}"></span>${label}</button>`;
    el.toolbar.innerHTML = `
      <div class="group" aria-label="Индикаторы">
        ${indChip("ma1", "MA " + cfg.ma[0], C.ma1)}
        ${indChip("ma2", "MA " + cfg.ma[1], C.ma2)}
        ${indChip("bb", "Боллинджер", "#bdb4ec")}
        ${indChip("vol", "Объём", C.up)}
        ${indChip("rsi", "RSI", C.rsi)}
        ${indChip("macd", "MACD", C.macd)}
      </div>
      <div class="spacer"></div>
      <div class="group" aria-label="Рисование">
        <button class="chip tool${S.tool === "level" ? " on" : ""}" data-tool="level" title="Горизонтальный уровень">${ICON.level}Уровень</button>
        <button class="chip tool${S.tool === "trend" ? " on" : ""}" data-tool="trend" title="Трендовая линия">${ICON.trend}Тренд</button>
        <button class="chip" data-act="clear" title="Стереть всё нарисованное">${ICON.trash}</button>
      </div>`;
  }
  el.toolbar.addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    if (b.dataset.ind) {
      const id = b.dataset.ind;
      const set = new Set(S.prefs.ind);
      set.has(id) ? set.delete(id) : set.add(id);
      S.prefs.ind = [...set];
      store.set(PREFS_KEY, S.prefs);
      buildIndicators();
      renderToolbar();
    } else if (b.dataset.tool) {
      setTool(b.dataset.tool);
    } else if (b.dataset.act === "clear") {
      clearDrawings();
      setTool(null);
    }
  });

  // ─── Панель ответа ─────────────────────────────────────────────────────────
  const CONF_WORDS = [[50, "монетка"], [60, "чуть лучше, чем наугад"], [70, "скорее да"], [80, "уверен"], [90, "очень уверен"], [100, "железно"]];
  const confWord = (v) => (CONF_WORDS.find(([t]) => v <= t) || CONF_WORDS[CONF_WORDS.length - 1])[1];
  const stakes = (v) => {
    const p = v / 100;
    return { win: Math.round((0.25 - (1 - p) ** 2) * 400), lose: Math.round((0.25 - p ** 2) * 400) };
  };

  function renderPanel(animate = true) {
    el.panel.classList.toggle("static", !animate);
    if (S.revealDone) return renderResult();
    if (S.revealing) return renderProgress();
    if (S.mode === "trade") return renderTradePanel();
    return renderQuickPanel();
  }

  function errorHtml() {
    return S.error ? `<div class="toast" role="alert">${esc(S.error)}</div>` : "";
  }

  function renderQuickPanel() {
    const p = S.payload;
    const band = S.st.config.sideways_mult * p.atr;
    const pct = fmt(band / p.last_close * 100, 1);
    const choice = (id, label, hint, key) => `
      <button class="choice ${id}${S.choice === id ? " sel" : ""}" data-choice="${id}" aria-pressed="${S.choice === id}">
        <span class="ico">${ICON[id]}</span>
        <span class="lbl"><b>${label}</b><small>${hint}</small></span>
        <kbd>${key}</kbd>
      </button>`;
    const st = stakes(S.confidence);
    el.panel.innerHTML = `
      <div><div class="eyebrow">Прогноз · ${S.F} свечей вперёд</div><h2 class="ptitle">Куда пойдёт цена?</h2></div>
      ${errorHtml()}
      <div class="choices">
        ${choice("up", "Вверх", "больше +" + pct + "%", "↑")}
        ${choice("flat", "Боковик", "в пределах ±" + pct + "%", "→")}
        ${choice("down", "Вниз", "больше −" + pct + "%", "↓")}
      </div>
      <div class="conf">
        <div class="row"><span>Уверенность</span><b id="confVal">${S.confidence}%</b></div>
        <input type="range" id="conf" min="50" max="100" step="5" value="${S.confidence}" aria-label="Уверенность" style="--fill:${(S.confidence - 50) * 2}%">
        <div class="word" id="confWord">${confWord(S.confidence)}</div>
        <div class="stakes"><span>угадаешь <b class="pos" id="stWin">${sgn(st.win, 0)}</b></span><span>промах <b class="neg" id="stLose">${sgn(st.lose, 0)}</b></span></div>
      </div>
      <button class="cta" id="submit" ${S.choice && !S.waiting ? "" : "disabled"}>
        ${S.waiting ? '<span class="spinner"></span>Раскрываем будущее' : "Зафиксировать прогноз"}
      </button>
      <p class="hint kb"><kbd>↑</kbd><kbd>→</kbd><kbd>↓</kbd> выбрать · <kbd>Enter</kbd> ответить</p>`;
  }

  function renderTradePanel() {
    const p = S.payload;
    const long = S.trade.direction === "long";
    el.panel.innerHTML = `
      <div><div class="eyebrow">Сделка · вход по ${fmt(p.last_close)}</div><h2 class="ptitle">Расставь стоп и тейк</h2></div>
      ${errorHtml()}
      <div class="seg" role="group" aria-label="Направление">
        <button class="long${long ? " on" : ""}" data-dir="long" aria-pressed="${long}">${ICON.up}Лонг</button>
        <button class="short${!long ? " on" : ""}" data-dir="short" aria-pressed="${!long}">${ICON.down}Шорт</button>
      </div>
      <div class="field stop"><label for="inStop">Стоп</label>
        <div class="stepper"><button data-step="stop" data-d="-1" aria-label="Стоп ниже">−</button><input id="inStop" type="number" step="0.01" value="${fmt(S.trade.stop)}"><button data-step="stop" data-d="1" aria-label="Стоп выше">+</button></div>
        <div class="meta" id="metaStop"></div>
      </div>
      <div class="field take"><label for="inTake">Тейк</label>
        <div class="stepper"><button data-step="take" data-d="-1" aria-label="Тейк ниже">−</button><input id="inTake" type="number" step="0.01" value="${fmt(S.trade.take)}"><button data-step="take" data-d="1" aria-label="Тейк выше">+</button></div>
        <div class="meta" id="metaTake"></div>
      </div>
      <div class="presets"><span class="k">стоп</span>
        ${[0.5, 1, 1.5, 2].map((a) => `<button class="chip" data-satr="${a}">${a} ATR</button>`).join("")}
      </div>
      <div class="presets"><span class="k">R:R</span>
        ${[1, 2, 3].map((r) => `<button class="chip" data-rr="${r}">1:${r}</button>`).join("")}
      </div>
      <div class="rr"><div class="bar"><i class="risk" id="rrRisk"></i><i class="reward" id="rrReward"></i></div>
        <div class="row"><span>риск : прибыль</span><b id="rrVal">1 : 2.0</b></div></div>
      <button class="cta" id="submit" ${S.waiting ? "disabled" : ""}>
        ${S.waiting ? '<span class="spinner"></span>Раскрываем будущее' : "Войти в сделку"}
      </button>
      <p class="hint">Линии стопа и тейка можно тянуть прямо на графике<span class="kb"> · <kbd>L</kbd>/<kbd>S</kbd> направление</span></p>`;
    updateTradeReadout();
  }

  function updateTradeReadout(skip) {
    if (S.mode !== "trade" || S.revealing || S.revealDone) return;
    const p = S.payload, e = p.last_close, a = p.atr;
    const risk = Math.abs(e - S.trade.stop), reward = Math.abs(S.trade.take - e);
    const rr = reward / risk;
    const set = (id, v) => { const n = $(id); if (n) n.textContent = v; };
    set("metaStop", `${sgn((S.trade.stop / e - 1) * 100)}% · ${fmt(risk / a, 1)} ATR`);
    set("metaTake", `${sgn((S.trade.take / e - 1) * 100)}% · ${fmt(reward / a, 1)} ATR`);
    set("rrVal", `1 : ${fmt(rr, 1)}`);
    const rk = $("rrRisk"), rw = $("rrReward");
    if (rk && rw) { rk.style.flex = String(1); rw.style.flex = String(Math.max(0.05, rr)); }
    if (skip !== "stop") { const n = $("inStop"); if (n) n.value = fmt(S.trade.stop); }
    if (skip !== "take") { const n = $("inTake"); if (n) n.value = fmt(S.trade.take); }
  }

  function renderProgress() {
    const isTrade = S.mode === "trade";
    el.panel.innerHTML = `
      <div><div class="eyebrow">Раскрытие</div><h2 class="ptitle">Будущее наступает…</h2></div>
      <div class="progress"><div class="track"><i id="progBar"></i></div></div>
      <div class="live"><span id="liveLbl">${isTrade ? "результат сейчас" : "изменение цены"}</span><b id="liveVal">0</b></div>
      <p class="hint">Свечи появляются одна за другой</p>`;
  }
  function updateProgress() {
    const k = S.shown - S.H;
    const bar = $("progBar");
    if (bar) bar.style.width = (k / S.F * 100) + "%";
    const v = $("liveVal");
    if (!v) return;
    const last = allBars()[S.shown - 1][3], e = S.payload.last_close;
    if (S.mode === "trade" && S.answer) {
      const sign = S.answer.direction === "long" ? 1 : -1;
      const risk = (S.answer.entry - S.answer.stop) * sign;
      const o = S.outcome;
      const closedAt = o ? S.H + o.exit_bar : Infinity;
      const r = S.shown - 1 >= closedAt ? o.r : (last - S.answer.entry) * sign / risk;
      v.textContent = sgn(r) + "R";
      v.className = r >= 0 ? "pos" : "neg";
      const lbl = $("liveLbl");
      if (lbl && S.shown - 1 >= closedAt) lbl.textContent = o.reason === "take" ? "тейк!" : o.reason === "stop" ? "стоп" : "закрыто";
    } else {
      const chg = (last / e - 1) * 100;
      v.textContent = sgn(chg) + "%";
      v.className = chg >= 0 ? "pos" : "neg";
    }
  }

  function renderResult() {
    const o = S.outcome || {}, a = S.answer || {}, p = S.payload, ident = p.identity || {};
    let stamp, big, facts;
    if (S.mode === "trade") {
      const cls = o.reason === "take" ? "win" : o.reason === "stop" ? "lose" : (o.r >= 0 ? "meh" : "lose");
      const word = o.reason === "take" ? "ТЕЙК!" : o.reason === "stop" ? "СТОП" : "ПО ЗАКРЫТИЮ";
      stamp = `<span class="stamp ${cls}">${word}</span>`;
      big = `<div class="big ${o.r >= 0 ? "pos" : "neg"}">${sgn(o.r)}R<small>${sgn(o.points, 0)} очков</small></div>`;
      const when = o.reason === "close" ? `по закрытию ${S.F}-й свечи` : `на ${o.exit_bar + 1}-й свече`;
      facts = [
        ["Сделка", `${a.direction === "long" ? "Лонг" : "Шорт"} · план 1:${fmt(o.planned_rr, 1)}`],
        ["Вход → выход", `${fmt(o.entry_real)} → ${fmt(o.exit_real)} ₽`],
        ["Чем закрылась", `${o.reason === "take" ? "тейк" : o.reason === "stop" ? "стоп" : "время вышло"} ${when}`],
        ["Результат", `${sgn(o.pnl_pct)}%`],
      ];
    } else {
      stamp = `<span class="stamp ${o.correct ? "win" : "lose"}">${o.correct ? "В ТОЧКУ" : "МИМО"}</span>`;
      big = `<div class="big ${o.points >= 0 ? "pos" : "neg"}">${sgn(o.points, 0)}<small>очков</small></div>`;
      facts = [
        ["Твой прогноз", `${esc(o.choice_label || "")} · ${a.confidence}%`],
        ["Как вышло", `${esc(o.actual_label || "")} · ${sgn(o.change_pct)}% (${sgn(o.change_atr, 1)} ATR)`],
        ["Порог боковика", `±${o.threshold_atr} ATR`],
        ["Brier", fmt(o.brier, 3)],
      ];
    }
    const evs = (p.events || []).map((ev) => `<li><i style="background:${C.event[ev.type] || C.macd}"></i><span>свеча ${relBar(ev.bar)}: ${esc(ev.label)}</span></li>`).join("");
    el.panel.innerHTML = `
      <div class="verdict">${stamp}${big}</div>
      <div class="who"><div class="tk">${esc(ident.ticker || "")}<small>${esc(ident.name || "")}</small></div>
        <div class="per">${esc(ident.timeframe_label || "")} · ${esc(ident.period || "")}</div></div>
      <div class="facts">${facts.map(([k, v]) => `<div class="fact"><span>${k}</span><b>${v}</b></div>`).join("")}</div>
      ${evs ? `<ul class="evlist">${evs}</ul>` : ""}
      ${S.st.review ? `<button class="chip link to-review" id="toReview">${ICON.down}Разбор: почему так вышло</button>` : ""}
      <button class="cta" id="next" ${S.waiting ? "disabled" : ""}>${S.waiting ? '<span class="spinner"></span>Готовим график' : "Следующий раунд " + ICON.next}</button>
      <p class="hint kb"><kbd>Enter</kbd> или <kbd>N</kbd> — дальше</p>`;
  }

  // Делегирование событий панели
  el.panel.addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    if (b.dataset.choice) { pickChoice(b.dataset.choice); return; }
    if (b.dataset.dir) { setDirection(b.dataset.dir); return; }
    if (b.dataset.step) {
      const step = Math.max(0.01, round2(S.payload.atr * 0.1));
      setTradeLevel(b.dataset.step, S.trade[b.dataset.step] + Number(b.dataset.d) * step);
      return;
    }
    if (b.dataset.satr) {
      const e0 = S.payload.last_close, sign = S.trade.direction === "long" ? 1 : -1;
      const rr = Math.abs(S.trade.take - e0) / Math.abs(e0 - S.trade.stop);
      setTradeLevel("stop", e0 - sign * Number(b.dataset.satr) * S.payload.atr);
      setTradeLevel("take", e0 + sign * rr * Math.abs(e0 - S.trade.stop));
      return;
    }
    if (b.dataset.rr) {
      const e0 = S.payload.last_close, sign = S.trade.direction === "long" ? 1 : -1;
      setTradeLevel("take", e0 + sign * Number(b.dataset.rr) * Math.abs(e0 - S.trade.stop));
      return;
    }
    if (b.id === "submit") { submit(); return; }
    if (b.id === "toReview") { el.review.scrollIntoView({ behavior: reduceMotion() ? "auto" : "smooth", block: "start" }); return; }
    if (b.id === "next") { nextRound(); }
  });
  el.panel.addEventListener("input", (e) => {
    if (e.target.id === "conf") {
      S.confidence = Number(e.target.value);
      e.target.style.setProperty("--fill", (S.confidence - 50) * 2 + "%");
      $("confVal").textContent = S.confidence + "%";
      $("confWord").textContent = confWord(S.confidence);
      const st = stakes(S.confidence);
      $("stWin").textContent = sgn(st.win, 0);
      $("stLose").textContent = sgn(st.lose, 0);
    }
  });
  el.panel.addEventListener("change", (e) => {
    if (e.target.id === "inStop" || e.target.id === "inTake") {
      const v = parseFloat(String(e.target.value).replace(",", "."));
      const which = e.target.id === "inStop" ? "stop" : "take";
      if (isFinite(v)) setTradeLevel(which, v);
      updateTradeReadout();
    }
  });

  function pickChoice(c) {
    if (S.phase !== "predict" || S.waiting) return;
    S.choice = c;
    el.panel.querySelectorAll(".choice").forEach((n) => {
      const on = n.dataset.choice === c;
      n.classList.toggle("sel", on);
      n.setAttribute("aria-pressed", on);
    });
    const btn = $("submit");
    if (btn) btn.disabled = false;
    requestLayout();
  }
  function setDirection(dir) {
    if (!canEditTrade() || S.trade.direction === dir) return;
    const e = S.payload.last_close;
    S.trade.direction = dir;
    // Зеркалим стоп и тейк относительно входа — расстояния сохраняются.
    const stop = 2 * e - S.trade.stop, take = 2 * e - S.trade.take;
    S.trade.stop = round2(stop); S.trade.take = round2(take);
    ensureTradeLines();
    setExtraRange();
    renderPanel(false);
    requestLayout();
  }

  function submit() {
    if (S.phase !== "predict" || S.waiting) return;
    if (S.mode === "quick" && !S.choice) return;
    S.waiting = true;
    S.error = null;
    if (S.mode === "quick") emit("answer", { choice: S.choice, confidence: S.confidence, drawings: S.drawings });
    else emit("answer", { direction: S.trade.direction, stop: S.trade.stop, take: S.trade.take, drawings: S.drawings });
    renderPanel(false);
  }
  function nextRound() {
    if (S.waiting || !S.revealDone) return;
    S.waiting = true;
    emit("next", { drawings: S.drawings });
    renderPanel(false);
    const again = $("next2");
    if (again) { again.disabled = true; again.innerHTML = '<span class="spinner"></span>Готовим график'; }
  }

  // ─── Настройки раундов ─────────────────────────────────────────────────────
  function syncSettings() {
    const st = S.st && S.st.settings;
    if (!st) return;
    S.set = {
      tickers: st.tickers.filter((t) => t.on).map((t) => t.id),
      timeframes: st.timeframes.filter((t) => t.on).map((t) => t.id),
      show_identity: !!st.show_identity,
    };
  }
  function renderSettings() {
    const st = S.st.settings, set = S.set;
    const pick = (attr, id, main, sub) => {
      const on = (attr === "tk" ? set.tickers : set.timeframes).includes(id);
      return `<button class="pick${on ? " on" : ""}" data-${attr}="${esc(id)}" aria-pressed="${on}"><b>${esc(main)}</b>${sub ? `<span>${esc(sub)}</span>` : ""}</button>`;
    };
    el.settings.innerHTML = `
      <div class="pop-head"><b>Настройки раундов</b><span>применятся со следующего раунда</span></div>
      <div class="pop-sec"><div class="k">Бумаги</div>
        <div class="picks">${st.tickers.map((t) => pick("tk", t.id, t.id, t.name)).join("")}</div></div>
      <div class="pop-sec"><div class="k">Таймфрейм</div>
        <div class="picks">${st.timeframes.map((t) => pick("tf", t.id, t.label, "")).join("")}</div></div>
      <div class="sw-row">
        <div><b>Тикер и даты сразу</b><small>Лёгкий режим: видно бумагу и период — память начнёт подсказывать</small></div>
        <button class="switch" role="switch" aria-checked="${set.show_identity}" aria-label="Показывать тикер и даты сразу" data-sw="identity"><i></i></button>
      </div>`;
  }
  function toggleSettings(open) {
    const willOpen = open == null ? el.settings.hidden : open;
    if (willOpen === !el.settings.hidden) return;
    if (willOpen) { syncSettings(); renderSettings(); }
    el.settings.hidden = !willOpen;
    el.setBtn.setAttribute("aria-expanded", String(willOpen));
    el.setBtn.classList.toggle("on", willOpen);
  }
  el.setBtn.addEventListener("click", (e) => { e.stopPropagation(); toggleSettings(); });
  el.settings.addEventListener("click", (e) => {
    // Панель перерисовывается по клику — без stopPropagation клик «снаружи» закрыл бы её.
    e.stopPropagation();
    const b = e.target.closest("button");
    if (!b || !S.set) return;
    const flip = (list, id) => (list.includes(id) ? list.filter((x) => x !== id) : list.concat(id));
    if (b.dataset.tk || b.dataset.tf) {
      const key = b.dataset.tk ? "tickers" : "timeframes";
      const next = flip(S.set[key], b.dataset.tk || b.dataset.tf);
      if (!next.length) { shake(b); return; }          // хотя бы одна бумага и один таймфрейм
      S.set[key] = next;
    } else if (b.dataset.sw === "identity") {
      S.set.show_identity = !S.set.show_identity;
    } else {
      return;
    }
    renderSettings();
    emit("settings", S.set);
  });
  document.addEventListener("click", (e) => {
    if (!el.settings.hidden && !e.target.closest(".set-wrap")) toggleSettings(false);
  });

  // ─── «Как играть» ──────────────────────────────────────────────────────────
  function howtoHtml() {
    const cfg = S.st.config, p = S.st.payload;
    const [m1, m2] = cfg.ma, [mf, ms, msig] = cfg.macd, [bn, bk] = cfg.bb;
    const levels = [50, 60, 70, 80, 90, 100];
    const stakeRow = (k, cls) => levels.map((v) => `<td class="${cls}">${sgn(stakes(v)[k], 0)}</td>`).join("");
    const ind = [
      [C.ma1, `MA ${m1} и MA ${m2}`, `Скользящие средние — средняя цена закрытия за ${m1} и ${m2} свечей.`,
        "Цена выше обеих и они растут — тренд вверх, ниже и падают — вниз. Разворот средние покажут с опозданием."],
      ["#bdb4ec", "Боллинджер", `Коридор: средняя за ${bn} свечей ± ${bk} стандартных отклонения.`,
        "У верхней границы цена «дорогая», у нижней — «дешёвая». Сжатый коридор — затишье перед сильным движением."],
      [C.up, "Объём", "Сколько бумаг купили и продали за свечу.",
        "Движение на большом объёме надёжнее. Рост на падающем объёме слабый и легко ломается."],
      [C.rsi, `RSI ${cfg.rsi}`, "Сила движений вверх против движений вниз, шкала от 0 до 100.",
        "Выше 70 — перекупленность, ниже 30 — перепроданность: возможен откат. Выше 50 — перевес покупателей."],
      [C.macd, `MACD ${mf}/${ms}/${msig}`, "Разница быстрой и медленной средних и её сигнальная линия.",
        "MACD выше сигнальной — импульс вверх, пересечение — смена импульса. Столбики растут — импульс крепнет."],
      [C.event.cbr_meeting, "События", "Заседания ЦБ, отчётность, дивидендные отсечки — метки на графике.",
        "Дата видна заранее, исход — нет. Перед событием цена может резко дёрнуться: повод снизить уверенность."],
    ];
    const sec = (n, title, body) =>
      `<section class="h-sec"><div class="h-num">${n}</div><div class="h-body"><h3>${title}</h3>${body}</div></section>`;
    return `
      <div class="howto-card" role="document">
        <button class="x" data-howto="close" aria-label="Закрыть">${ICON.close}</button>
        <header class="h-head">
          <div class="eyebrow">Правила · 2 минуты</div>
          <h2 id="howTitle">Как <span>играть</span></h2>
          <p>Тренажёр учит читать график, а не вспоминать историю: тикер и даты скрыты до ответа.
            Это настоящие котировки Мосбиржи, а не случайные линии.</p>
        </header>
        ${sec("01", "Смотри на график", `<p>Перед тобой ${p.history} свечей. Цены пересчитаны так, что первое закрытие = 100, — по ним бумагу не узнать.
          Индикаторы включаются кнопками над графиком, уровни и тренды можно рисовать прямо на нём.</p>`)}
        ${sec("02", "Сделай прогноз", `<div class="h-modes">
          <div class="h-mode"><b>01 · Быстрый</b><p>Куда цена уйдёт за ${p.future_slots} свечей: вверх, вниз или останется в коридоре — это «боковик».
            Коридор шириной ±${cfg.sideways_mult} ATR подсвечен на графике.</p></div>
          <div class="h-mode"><b>02 · Сделка</b><p>Выбери лонг или шорт и поставь стоп и тейк — их можно тянуть прямо на графике.
            Результат считается в R: сколько своих рисков ты заработал или потерял.</p></div>
        </div>`)}
        ${sec("03", "Уверенность — это ставка", `<p>Чем увереннее прогноз, тем больше очков за попадание — и тем дороже промах.
          При 50% ты ничем не рискуешь. Выгоднее всего ставить ровно ту уверенность, которую чувствуешь.</p>
          <table class="h-stakes"><thead><tr><th>уверенность</th>${levels.map((v) => `<th>${v}%</th>`).join("")}</tr></thead>
          <tbody><tr><th>угадал</th>${stakeRow("win", "pos")}</tr><tr><th>промах</th>${stakeRow("lose", "neg")}</tr></tbody></table>`)}
        ${sec("04", "Как читать индикаторы", `<div class="h-ind">${ind.map(([col, name, what, how]) => `
          <div class="h-card" style="--c:${col}"><b><i></i>${name}</b><p>${what}</p><p class="how">${how}</p></div>`).join("")}</div>`)}
        ${sec("05", "Разбери раунд", `<p>После ответа будущее раскроется свеча за свечой, а под графиком появится разбор:
          что показывал каждый индикатор, какие сигналы сработали и что происходило с ценой.</p>`)}
        <div class="h-gloss">
          <span><b>ATR</b> — средний размах свечи за ${cfg.atr} свечей, мерило обычного шума</span>
          <span><b>R</b> — риск сделки: расстояние от входа до стопа</span>
        </div>
        <button class="cta" data-howto="close">Понятно, играем</button>
      </div>`;
  }
  // Фокус переносим только при работе с клавиатуры — от мыши рамка фокуса лишняя.
  function openHowto(fromKeyboard) {
    if (!S.st) return;
    toggleSettings(false);
    el.howto.innerHTML = howtoHtml();
    el.howto.hidden = false;
    const x = el.howto.querySelector(".x");
    if (x && fromKeyboard) x.focus({ preventScroll: true });
  }
  function closeHowto(fromKeyboard) {
    if (el.howto.hidden) return;
    el.howto.hidden = true;
    if (fromKeyboard) el.howBtn.focus({ preventScroll: true });
  }
  // detail === 0 — «клик» с клавиатуры (Enter/пробел на кнопке).
  el.howBtn.addEventListener("click", (e) => openHowto(e.detail === 0));
  el.howto.addEventListener("click", (e) => {
    if (e.target === el.howto || e.target.closest("[data-howto=close]")) closeHowto(e.detail === 0);
  });

  // ─── Разбор раунда ─────────────────────────────────────────────────────────
  const SIG_COLOR = { trend: C.ma1, rsi: C.rsi, macd: C.macd, bb: "#bdb4ec", vol: C.up, levels: C.trend };
  const RES_TEXT = { ok: "✓ сработал", miss: "✕ не сработал", idle: "сигнала не было" };

  function sigCard(s) {
    const cls = s.worked === true ? "ok" : s.worked === false ? "miss" : "idle";
    const v = s.vote || "none";
    const icon = { up: ICON.up, down: ICON.down, move: ICON.move, none: ICON.dash }[v];
    return `
      <article class="sig ${cls}">
        <header><span class="dot" style="background:${SIG_COLOR[s.id] || C.text};color:${SIG_COLOR[s.id] || C.text}"></span>
          <b>${esc(s.title)}</b><span class="vote v-${v}">${icon}${esc(s.vote_label)}</span></header>
        <div class="val">${esc(s.value)}</div>
        <p class="read">${esc(s.reading)}</p>
        <details><summary>Как читать</summary><p>${esc(s.rule)}</p></details>
        <footer><span class="res">${RES_TEXT[cls]}</span>
          <button class="chip mini" data-show="${esc(s.id)}">${ICON.eye}на графике</button></footer>
      </article>`;
  }

  function renderReview() {
    const rv = S.st && S.st.review;
    if (!rv || !S.revealDone) {
      el.review.hidden = true;
      el.review.innerHTML = "";
      return;
    }
    const c = rv.consensus;
    const parts = [["up", "за рост", c.up], ["down", "за падение", c.down], ["move", "за сильное движение", c.move], ["none", "без сигнала", c.neutral]]
      .filter((x) => x[2] > 0);
    const badge = c.matched === true ? '<span class="badge ok">совпало с итогом</span>'
      : c.matched === false ? '<span class="badge miss">цена пошла иначе</span>' : "";
    const tl = rv.timeline.map((it) => `
      <li class="t-${it.tone}${it.final ? " final" : ""}"><span class="b">+${it.bar}</span><span class="t">${esc(it.text)}</span></li>`).join("");
    el.review.innerHTML = `
      <header class="rv-head">
        <div class="rv-title">
          <div class="eyebrow">Разбор раунда</div>
          <h2>${esc(rv.title)}</h2>
          <p class="why">${esc(rv.why)}</p>
        </div>
        <div class="rv-outcome ${rv.actual}"><span class="ico">${ICON[rv.actual]}</span>
          <span><b>${esc(rv.actual_label)}</b><small>${sgn(rv.change_pct)}% за ${S.F} свечей</small></span></div>
      </header>
      <div class="rv-grid">
        <div class="rv-col">
          <div class="rv-sub"><span class="n">01</span>Что показывал график в момент прогноза</div>
          <div class="cons">
            <div class="cons-bar">${parts.map(([k, , n]) => `<i class="${k}" style="flex:${n}"></i>`).join("")}</div>
            <div class="cons-legend">${parts.map(([k, label, n]) => `<span><i class="${k}"></i>${label}: ${n}</span>`).join("")}</div>
            <div class="cons-text">${esc(c.text)}${badge}</div>
          </div>
          <div class="sigs">${rv.signals.map(sigCard).join("")}</div>
        </div>
        <div class="rv-col">
          <div class="rv-sub"><span class="n">02</span>Что случилось за ${S.F} свечей</div>
          <ol class="tl">${tl}</ol>
          <div class="rv-sub"><span class="n">03</span>Вывод</div>
          <ul class="lessons">${rv.lessons.map((l) => `<li>${esc(l)}</li>`).join("")}</ul>
          <button class="cta" id="next2">Следующий раунд ${ICON.next}</button>
        </div>
      </div>
      <p class="rv-note">Индикаторы описывают прошлое и дают перевес вероятностей, а не гарантию.
        Настоящих причин движения не знает никто — разбор опирается только на график и календарь событий.</p>`;
    el.review.hidden = false;
  }

  function clearAux() {
    S.aux.forEach((l) => { try { candles.removePriceLine(l); } catch (e) { /* нет линии */ } });
    S.aux = [];
  }
  function showOnChart(id) {
    const rv = S.st && S.st.review;
    const sig = rv && rv.signals.find((s) => s.id === id);
    if (!sig) return;
    if (sig.lines) {
      clearAux();
      const [hi, lo] = sig.lines;
      const opts = { color: C.trend, lineWidth: 1, lineStyle: LC.LineStyle.LargeDashed, axisLabelVisible: true };
      S.aux.push(candles.createPriceLine(Object.assign({ price: hi, title: "макс окна" }, opts)));
      S.aux.push(candles.createPriceLine(Object.assign({ price: lo, title: "мин окна" }, opts)));
    } else {
      const set = new Set(S.prefs.ind);
      sig.show.forEach((k) => set.add(k));
      S.prefs.ind = [...set];
      store.set(PREFS_KEY, S.prefs);
      buildIndicators();
      renderToolbar();
    }
    el.board.scrollIntoView({ behavior: reduceMotion() ? "auto" : "smooth", block: "center" });
    el.board.classList.remove("pulse");
    void el.board.offsetWidth;
    el.board.classList.add("pulse");
  }
  el.review.addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    if (b.dataset.show) showOnChart(b.dataset.show);
    else if (b.id === "next2") {
      el.app.scrollIntoView({ block: "start" });
      nextRound();
    }
  });

  // ─── Клавиатура ────────────────────────────────────────────────────────────
  document.addEventListener("keydown", (e) => {
    if (!el.howto.hidden) { if (e.key === "Escape") closeHowto(true); return; }
    if (e.key === "Escape" && !el.settings.hidden) { toggleSettings(false); return; }
    if (e.target && (e.target.tagName === "INPUT" && e.target.type === "number")) return;
    // Enter на кнопке разбора или настроек — это её собственный клик, а не «дальше».
    if (e.target && e.target.closest && e.target.closest("#review, #settings")) return;
    if (e.key === "Escape") { if (S.tool) setTool(null); return; }
    if (S.revealDone) {
      if (e.key === "Enter" || e.code === "KeyN") { e.preventDefault(); nextRound(); }
      return;
    }
    if (S.phase !== "predict" || S.waiting) return;
    if (S.mode === "quick") {
      if (e.key === "ArrowUp") { e.preventDefault(); pickChoice("up"); }
      else if (e.key === "ArrowDown") { e.preventDefault(); pickChoice("down"); }
      else if (e.key === "ArrowRight" || e.key === "0") { e.preventDefault(); pickChoice("flat"); }
      else if (e.key === "Enter") { e.preventDefault(); submit(); }
    } else {
      if (e.code === "KeyL") setDirection("long");
      else if (e.code === "KeyS") setDirection("short");
      else if (e.key === "Enter") { e.preventDefault(); submit(); }
    }
  });

  // ─── Раунд: подготовка, раскрытие, итог ────────────────────────────────────
  function eventMarkers(upTo) {
    return (S.payload.events || [])
      .filter((ev) => ev.bar < upTo)
      .map((ev) => ({ time: tOf(ev.bar), position: "aboveBar", shape: "circle", color: C.event[ev.type] || C.macd, text: EVENT_SHORT[ev.type] || "", size: 1 }));
  }

  function setupRound(st) {
    clearTimeout(S.revealTimer);
    S.payload = st.payload;
    S.roundId = st.payload.round_id;
    S.H = st.payload.history;
    S.F = st.payload.future_slots;
    S.phase = st.phase;
    S.labels = st.payload.labels && st.phase === "predict" ? padLabels(st.payload.labels) : null;
    refreshAxis();
    S.choice = null;
    S.waiting = false;
    S.revealing = false;
    S.revealDone = false;
    S.error = null;
    S.answer = st.answer;
    S.outcome = st.outcome;
    S.trade = { direction: (st.answer && st.answer.direction) || "long", stop: null, take: null };

    clearDrawings();
    removeTradeLines();
    clearAux();
    markers.setMarkers([]);
    renderReview();

    const final = st.phase === "reveal";
    S.shown = final ? S.H + S.F : S.H;
    const bars = allBars().slice(0, S.shown);
    spacer.setData(Array.from({ length: S.H + S.F }, (_, i) => ({ time: tOf(i) })));
    candles.setData(bars.map((c, i) => ({ time: tOf(i), open: c[0], high: c[1], low: c[2], close: c[3] })));
    buildIndicators();
    fitWindow();

    if (S.answer && S.mode === "trade") { S.trade.stop = S.answer.stop; S.trade.take = S.answer.take; }
    else tradeDefaults();
    if (S.answer && S.mode === "quick") { S.choice = S.answer.choice; S.confidence = S.answer.confidence; }
    ensureTradeLines();
    setExtraRange();
    restoreDrawings(st.drawings);

    if (final) {
      finishReveal(false);
    } else {
      markers.setMarkers(eventMarkers(S.H));
      renderPanel(true);
    }
    legendFor(S.shown - 1);
    requestLayout();
  }

  function padLabels(labels) {
    // До ответа (если игрок включил показ дат) — подписи только у видимой части.
    return labels.slice();
  }

  function startReveal(st) {
    S.payload = st.payload;
    S.phase = "reveal";
    S.answer = st.answer;
    S.outcome = st.outcome;
    S.waiting = false;
    S.revealing = true;
    S.error = null;
    if (S.tool) setTool(null);
    if (S.mode === "trade" && S.answer) {
      S.trade.stop = S.answer.stop; S.trade.take = S.answer.take; S.trade.direction = S.answer.direction;
      ensureTradeLines();
    }
    // Индикаторы теперь из полного расчёта — значения видимой части те же.
    buildIndicators();
    renderPanel(true);

    const ms = reduceMotion() ? 0 : (st.config.reveal_ms || 150);
    const exitAt = S.mode === "trade" && S.outcome ? S.H + S.outcome.exit_bar : -1;
    const step = () => {
      const i = S.shown;
      pushBar(i);
      S.shown = i + 1;
      if (i === exitAt) flashZone(S.outcome.reason);
      updateProgress();
      legendFor(S.shown - 1);
      layout();
      if (S.shown < S.H + S.F) S.revealTimer = setTimeout(step, ms);
      else S.revealTimer = setTimeout(() => finishReveal(true), ms ? 380 : 0);
    };
    S.revealTimer = setTimeout(step, ms ? 260 : 0);
  }

  function flashZone(reason) {
    // Разметка пересобирается на каждой свече, поэтому вспышка — отдельный слой.
    if (reason !== "take" && reason !== "stop") return;
    const z = el.overlay.querySelector(".zone." + reason);
    if (!z) return;
    const f = z.cloneNode(true);
    f.classList.add("flash");
    f.style.color = reason === "take" ? C.take : C.stop;
    f.style.zIndex = "4";
    el.wrap.appendChild(f);
    setTimeout(() => f.remove(), 750);
  }

  function finishReveal(celebrate) {
    S.revealing = false;
    S.revealDone = true;
    S.labels = S.payload.labels || null;
    refreshAxis();

    const m = eventMarkers(S.H + S.F);
    if (S.mode === "trade" && S.outcome && S.answer) {
      const long = S.answer.direction === "long";
      m.push({ time: tOf(S.H - 1), position: long ? "belowBar" : "aboveBar", shape: long ? "arrowUp" : "arrowDown", color: C.entry, text: "вход" });
      const ex = S.H + S.outcome.exit_bar;
      const col = S.outcome.r >= 0 ? C.take : C.stop;
      m.push({ time: tOf(ex), position: long ? "aboveBar" : "belowBar", shape: "circle", color: col, text: sgn(S.outcome.r) + "R" });
    } else if (S.outcome) {
      const end = S.H + S.F - 1;
      m.push({ time: tOf(end), position: S.outcome.change_pct >= 0 ? "aboveBar" : "belowBar", shape: "circle", color: S.outcome.correct ? C.take : C.stop, text: sgn(S.outcome.change_pct) + "%" });
    }
    m.sort((a, b) => a.time - b.time);
    markers.setMarkers(m);

    renderPanel(true);
    renderReview();
    renderHUD();
    requestLayout();
    if (celebrate && S.outcome && S.outcome.win && !reduceMotion()) confetti();
  }

  // ─── Конфетти (короткий праздничный залп) ─────────────────────────────────
  function confetti() {
    const cv = el.confetti, ctx = cv.getContext("2d");
    const dpr = window.devicePixelRatio || 1;
    const W = el.app.clientWidth, Hh = el.app.clientHeight;
    cv.width = W * dpr; cv.height = Hh * dpr;
    cv.style.width = W + "px"; cv.style.height = Hh + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const pr = el.panel.getBoundingClientRect(), ar = el.app.getBoundingClientRect();
    const ox = pr.left - ar.left + 80, oy = pr.top - ar.top + 40;
    const cols = ["#2ee6a8", "#ffd166", "#ff9a3c", "#ff4fa8", "#8b6cff", "#5cc8ff"];
    const parts = Array.from({ length: 70 }, () => ({
      x: ox, y: oy,
      vx: (Math.random() - 0.3) * 9, vy: -Math.random() * 9 - 3,
      r: 3 + Math.random() * 4, a: Math.random() * Math.PI, va: (Math.random() - 0.5) * 0.4,
      c: cols[(Math.random() * cols.length) | 0], life: 1,
    }));
    let last = performance.now();
    const tick = (now) => {
      const dt = Math.min(32, now - last) / 16.7; last = now;
      ctx.clearRect(0, 0, W, Hh);
      let alive = 0;
      parts.forEach((q) => {
        q.vy += 0.32 * dt; q.vx *= 0.99; q.x += q.vx * dt; q.y += q.vy * dt; q.a += q.va * dt; q.life -= 0.012 * dt;
        if (q.life <= 0) return;
        alive++;
        ctx.save(); ctx.globalAlpha = Math.max(0, q.life); ctx.translate(q.x, q.y); ctx.rotate(q.a);
        ctx.fillStyle = q.c; ctx.fillRect(-q.r, -q.r / 2, q.r * 2, q.r); ctx.restore();
      });
      if (alive) requestAnimationFrame(tick); else ctx.clearRect(0, 0, W, Hh);
    };
    requestAnimationFrame(tick);
  }

  // ─── Высота iframe ─────────────────────────────────────────────────────────
  let lastH = 0;
  function fitHeight() {
    const h = Math.ceil(el.app.getBoundingClientRect().height) + 4;
    if (Math.abs(h - lastH) > 1) { lastH = h; ST.height(h); }
  }

  // ─── Приём данных из Python ────────────────────────────────────────────────
  function onRender(args) {
    const st = args && args.state;
    if (!st || !st.payload) return;
    const first = !S.st;
    S.st = st;
    const modeChanged = st.mode !== S.mode;
    S.mode = st.mode;

    if (first) {
      renderToolbar();
      // Python узнаёт id браузера — по нему он находит журнал игрока.
      emitHello();
    }
    renderModes();

    const newRound = st.payload.round_id !== S.roundId;
    if (newRound) {
      setupRound(st);
    } else if (st.phase === "reveal" && S.phase === "predict") {
      startReveal(st);
    } else if (modeChanged && st.phase === "predict") {
      S.choice = null;
      tradeDefaults();
      ensureTradeLines();
      setExtraRange();
      renderPanel(true);
      requestLayout();
    }

    if (st.error && st.error_id && st.error_id !== S.lastErrorId) {
      S.lastErrorId = st.error_id;
      S.waiting = false;
      S.error = st.error;
      renderPanel(false);
    }
    renderHUD();
    // Первый заход — сразу правила (дальше они по кнопке «Как играть»).
    if (first && !store.get(HOWTO_KEY, false)) {
      store.set(HOWTO_KEY, true);
      openHowto();
    }
    fitHeight();
  }

  let helloSent = false;
  function emitHello() {
    if (helloSent) return;
    helloSent = true;
    emit("hello", {});
  }

  window.addEventListener("message", (e) => {
    if (e.data && e.data.type === "streamlit:render") onRender(e.data.args);
  });

  // Шрифты для холста графика подгружаются асинхронно — перерисуем, когда готовы.
  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(() => {
      chart.applyOptions({ layout: { fontFamily: "Onest, system-ui, sans-serif" } });
      requestLayout();
      fitHeight();
    });
  }

  // Хук для отладки и автотестов в браузере.
  window.__trainer = { chart, candles, S, layout };

  ST.ready();
  fitHeight();
})();
