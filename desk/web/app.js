// Kunal Options Desk - the page. Data comes from the desk program (FYERS) over a local websocket.
(() => {
  "use strict";
  const SHIFT = 19800;                        // show Indian time on the chart axis
  const $ = id => document.getElementById(id);
  const fmt = (v, n = 2) => (v === null || v === undefined || isNaN(v)) ? "-" :
    Number(v).toLocaleString("en-IN", { minimumFractionDigits: n, maximumFractionDigits: n });
  const lk = x => {
    if (x === null || x === undefined || isNaN(x)) return "-";
    const a = Math.abs(x);
    const s = a >= 1e7 ? (a / 1e7).toFixed(2) + " Cr" : a >= 1e5 ? (a / 1e5).toFixed(2) + " L" :
      a >= 1e3 ? (a / 1e3).toFixed(1) + "K" : a.toFixed(0);
    return (x < 0 ? "-" : "") + s;
  };
  const sg = x => (x === null || x === undefined || isNaN(x)) ? "-" : (x > 0 ? "+" : "") + lk(x);
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const store = {
    get(k, d) { try { const v = localStorage.getItem("kod_" + k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem("kod_" + k, JSON.stringify(v)); } catch (e) { } }
  };

  // ------------------------------------------------------------------ settings remembered in this browser
  const toggles = store.get("toggles", {});
  document.querySelectorAll("[data-t]").forEach(cb => {
    if (cb.dataset.t in toggles) cb.checked = toggles[cb.dataset.t];
    cb.onchange = () => { toggles[cb.dataset.t] = cb.checked; store.set("toggles", toggles); applyToggles(); };
  });
  const T = k => { const el = document.querySelector(`[data-t="${k}"]`); return el ? el.checked : false; };
  const view = Object.assign({ index: "NIFTY", tf: 5, instrument: "INDEX", each_side: 8, ema1: 9, ema2: 21, strike: null },
    store.get("view2", {}));
  $("index").value = view.index; $("tf").value = String(view.tf); $("instrument").value = view.instrument;
  $("each").value = String(view.each_side); $("s_ema1").value = view.ema1; $("s_ema2").value = view.ema2;
  const prefs = Object.assign({ pw: 160, pv: true, align: false, explainer: true, greeks: true, opt: true }, store.get("prefs", {}));
  $("s_pw").value = prefs.pw; $("s_pv").checked = prefs.pv; $("s_align").checked = prefs.align;
  $("explainer").checked = prefs.explainer; $("greeks").checked = prefs.greeks; $("opt_panel").checked = prefs.opt;

  // ------------------------------------------------------------------ charts
  const charts = [];
  function mk(el) {
    const c = LightweightCharts.createChart(el, {
      autoSize: true, crosshair: { mode: 0 }, rightPriceScale: { minimumWidth: 92 },
      timeScale: { timeVisible: true, secondsVisible: false, rightOffset: 8 }
    });
    charts.push(c);
    return c;
  }
  const line = (c, color, width = 2, style = 0) => c.addLineSeries({
    color, lineWidth: width, lineStyle: style, lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false
  });
  const main = mk($("main"));
  const candles = main.addCandlestickSeries({ upColor: "#089981", downColor: "#f23645", borderVisible: false,
    wickUpColor: "#089981", wickDownColor: "#f23645" });
  const vol = main.addHistogramSeries({ priceScaleId: "vol", priceFormat: { type: "volume" }, lastValueVisible: false, priceLineVisible: false });
  main.priceScale("vol").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
  const vwapS = line(main, "#2962ff"), bvwS = line(main, "#089981", 1, 2), svwS = line(main, "#f23645", 1, 2);
  const u1S = line(main, "rgba(38,198,218,.85)", 2, 2), l1S = line(main, "rgba(38,198,218,.85)", 2, 2);
  const u2S = line(main, "rgba(255,167,38,.8)", 2, 2), l2S = line(main, "rgba(255,167,38,.8)", 2, 2);
  const bbU = line(main, "rgba(179,157,219,.75)", 1), bbL = line(main, "rgba(179,157,219,.75)", 1), bbM = line(main, "rgba(179,157,219,.45)", 1, 2);
  const ema1S = line(main, "#ff9800", 1), ema2S = line(main, "#9c27b0", 1);
  const futLine = color => main.addLineSeries({ color, lineWidth: 2, lastValueVisible: true, priceLineVisible: false,
    crosshairMarkerVisible: false });
  const nearS = futLine("#ff6d00"), nextS = futLine("#00acc1");

  const flowC = mk($("flow"));
  const netS = flowC.addHistogramSeries({ lastValueVisible: false, priceLineVisible: false });
  const cumS = flowC.addLineSeries({ color: "#2962ff", lineWidth: 2, priceLineVisible: false });
  const avgS = line(flowC, "#ff9800", 2);

  function optChart(key) {
    const c = mk($(key + "chart"));
    const candle = c.addCandlestickSeries({ upColor: "#089981", downColor: "#f23645", borderVisible: false, wickUpColor: "#089981", wickDownColor: "#f23645" });
    const volS = c.addHistogramSeries({ priceScaleId: "ov", priceFormat: { type: "volume" }, lastValueVisible: false, priceLineVisible: false });
    c.priceScale("ov").applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
    const vw = line(c, "rgba(41,98,255,.85)", 1);
    const o = { key, c, candle, volS, vw, bars: [], symbol: "" };
    c.subscribeCrosshairMove(p => optLegend(o, p && p.time));
    c.timeScale().subscribeVisibleLogicalRangeChange(() => drawOptProfile(o));
    new ResizeObserver(() => drawOptProfile(o)).observe($(key + "chart"));
    return o;
  }
  const OPT = { ce: optChart("ce"), pe: optChart("pe") };
  const ceC = OPT.ce.c, peC = OPT.pe.c;
  function optLegend(o, t) {
    const el = $(o.key + "leg");
    if (!o.bars.length) { el.innerHTML = o.symbol ? `<b>${esc(o.symbol)}</b> no candles yet` : ""; return; }
    const i = t ? o.bars.findIndex(b => b.t + SHIFT === t) : -1, b = o.bars[i < 0 ? o.bars.length - 1 : i];
    const tot = (b.bv + b.sv) || 1;
    el.innerHTML = `<b>${esc(o.symbol)}</b> · O ${fmt(b.o)} H ${fmt(b.h)} L ${fmt(b.l)} C ${fmt(b.c)} · Vol ${lk(b.v)}` +
      ` (<span class="g">bull ${Math.round(b.bv / tot * 100)}%</span> · <span class="r">bear ${Math.round(b.sv / tot * 100)}%</span>)` +
      (o.vwapNow ? ` · <span class="b">VWAP ${fmt(o.vwapNow)}</span>` : "");
  }
  function setOpt(o, data) {
    o.symbol = data ? data.symbol : ""; o.bars = data ? data.bars : []; o.big = data && data.big ? data.big : [];
    const t = o.bars.map(b => b.t + SHIFT);
    o.candle.setData(o.bars.map((b, i) => ({ time: t[i], open: b.o, high: b.h, low: b.l, close: b.c })));
    o.volS.setData(o.bars.map((b, i) => ({ time: t[i], value: b.v, color: b.c >= b.o ? "rgba(8,153,129,.35)" : "rgba(242,54,69,.35)" })));
    let pv = 0, v = 0, day = null;                       // VWAP of the option, from today's candles
    const vwv = o.bars.map(b => { const d = Math.floor((b.t + SHIFT) / 86400); if (d !== day) { day = d; pv = 0; v = 0; }
      if (b.v > 0) { pv += (b.h + b.l + b.c) / 3 * b.v; v += b.v; } return v ? pv / v : null; });
    o.vwapNow = vwv.length ? vwv[vwv.length - 1] : null;
    o.vw.setData(series(vwv, t));
    optLegend(o); drawOptProfile(o);
  }
  // volume profile (total volume, 70% value area, sky blue) + delta profile (bull - bear volume) on an option chart
  function drawOptProfile(o) {
    const cv = $(o.key + "prof"), el = $(o.key + "chart"); if (!cv || !el) return;
    const w = el.clientWidth, h = el.clientHeight, dpr = window.devicePixelRatio || 1;
    cv.width = w * dpr; cv.height = h * dpr; cv.style.width = w + "px"; cv.style.height = h + "px";
    const ctx = cv.getContext("2d"); ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, w, h);
    if (T("big") && o.bars.length) for (const t of o.big || []) {
      const x = o.c.timeScale().timeToCoordinate(bucket(t.ts, B ? B.tf : 1)), y = o.candle.priceToCoordinate(t.price);
      if (x === null || y === null) continue;
      const r = Math.max(4, Math.min(14, 3 + 3 * Math.sqrt(t.value / 50e5))), buy = t.side === "buy";
      ctx.fillStyle = buy ? "rgba(8,153,129,.28)" : "rgba(242,54,69,.28)"; ctx.strokeStyle = buy ? "rgba(8,153,129,.9)" : "rgba(242,54,69,.9)";
      ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
    }
    if (!o.bars.length || (!T("opt_vp") && !T("opt_dp"))) return;
    const lo = Math.min(...o.bars.map(b => b.l)), hi = Math.max(...o.bars.map(b => b.h));
    if (!(hi > lo)) return;
    const n = 40, step = (hi - lo) / n, vol = new Array(n).fill(0), del = new Array(n).fill(0);
    for (const b of o.bars) {                           // spread each candle's volume over its range
      const a = Math.max(0, Math.floor((b.l - lo) / step)), z = Math.min(n - 1, Math.floor((b.h - lo) / step)), k = z - a + 1;
      for (let i = a; i <= z; i++) { vol[i] += b.v / k; del[i] += (b.bv - b.sv) / k; }
    }
    const total = vol.reduce((x, y) => x + y, 0); if (!total) return;
    let poc = vol.indexOf(Math.max(...vol)), va = new Set([poc]), sum = vol[poc], up = poc + 1, dn = poc - 1;
    while (sum < total * 0.7 && (up < n || dn >= 0)) {
      const vu = up < n ? vol[up] : -1, vd = dn >= 0 ? vol[dn] : -1;
      if (vu >= vd) { va.add(up); sum += vu; up++; } else { va.add(dn); sum += vd; dn--; }
    }
    const right = w - o.c.priceScale("right").width() - 4, maxV = Math.max(...vol), maxD = Math.max(...del.map(Math.abs), 1e-9);
    const vpW = right * 0.28, dpW = right * 0.12, dpX = T("opt_vp") ? right - vpW - 8 : right;
    for (let i = 0; i < n; i++) {
      const y1 = o.candle.priceToCoordinate(lo + step * (i + 1)), y0 = o.candle.priceToCoordinate(lo + step * i);
      if (y1 === null || y0 === null) continue;
      const top = Math.min(y0, y1) + .5, bh = Math.max(1, Math.abs(y0 - y1) - 1);
      if (T("opt_vp")) { ctx.fillStyle = va.has(i) ? "rgba(135,206,235,.30)" : "rgba(135,206,235,.12)";
        const len = vol[i] / maxV * vpW; ctx.fillRect(right - len, top, len, bh); }
      if (T("opt_dp")) { ctx.fillStyle = del[i] >= 0 ? "rgba(8,153,129,.35)" : "rgba(242,54,69,.35)";
        const len = Math.abs(del[i]) / maxD * dpW; ctx.fillRect(dpX - len, top, len, bh); }
    }
    if (T("opt_vp")) {
      const lvl = (price, color, text) => { const y = o.candle.priceToCoordinate(price); if (y === null) return;
        ctx.strokeStyle = color; ctx.setLineDash([3, 3]); ctx.beginPath(); ctx.moveTo(right - vpW, y); ctx.lineTo(right, y); ctx.stroke(); ctx.setLineDash([]);
        ctx.fillStyle = color; ctx.font = "10px sans-serif"; ctx.textAlign = "right"; ctx.fillText(text, right - 2, y - 3); ctx.textAlign = "left"; };
      lvl(lo + step * (Math.max(...va) + 1), "rgba(135,206,235,.9)", "VAH");
      lvl(lo + step * (poc + .5), "rgba(135,206,235,1)", "POC");
      lvl(lo + step * Math.min(...va), "rgba(135,206,235,.9)", "VAL");
    }
  }
  const oiC = mk($("oichart"));
  const oiCalls = oiC.addLineSeries({ color: "#f23645", lineWidth: 2 }), oiPuts = oiC.addLineSeries({ color: "#089981", lineWidth: 2 });

  // one time axis for the price chart and the buying - selling pane
  let syncing = false;
  [[main, flowC], [flowC, main]].forEach(([a, b]) => a.timeScale().subscribeVisibleLogicalRangeChange(r => {
    if (syncing || !r) return; syncing = true; b.timeScale().setVisibleLogicalRange(r); syncing = false; drawProfile(); drawStrip();
  }));

  let dark = store.get("dark", true);
  function applyTheme() {
    document.documentElement.classList.toggle("dark", dark);
    const cs = getComputedStyle(document.documentElement), v = n => cs.getPropertyValue(n).trim();
    charts.forEach(ch => ch.applyOptions({
      layout: { background: { color: v("--card") }, textColor: v("--text"), fontSize: 11 },
      grid: { vertLines: { color: v("--grid") }, horzLines: { color: v("--grid") } },
      rightPriceScale: { borderColor: v("--line") }, timeScale: { borderColor: v("--line") }
    }));
    drawProfile(); drawStrip(); if (typeof drawHedge === "function" && A) drawHedge();
  }
  $("theme").onclick = () => { dark = !dark; store.set("dark", dark); applyTheme(); };

  // ------------------------------------------------------------------ data
  let B = null, A = null, ws = null, lastCandle = null;
  const bucket = (t, tf) => {                         // the candle (from 09:15) that an epoch second belongs to
    const s = t + SHIFT, day = Math.floor(s / 86400) * 86400, open = day + 9 * 3600 + 15 * 60;
    return tf === 1 ? s - (s % 60) : open + Math.floor((s - open) / (tf * 60)) * tf * 60;
  };
  const series = (arr, times) => arr.map((v, i) => v === null ? null : { time: times[i], value: v }).filter(Boolean);

  // Heikin-Ashi (display only: every indicator still uses the real prices)
  const heikin = bars => { const out = []; let po = null, pc = null;
    for (const b of bars) { const c = (b.o + b.h + b.l + b.c) / 4, o = po === null ? (b.o + b.c) / 2 : (po + pc) / 2;
      out.push({ t: b.t, o, h: Math.max(b.h, o, c), l: Math.min(b.l, o, c), c }); po = o; pc = c; }
    return out; };
  const shown = bars => prefs.ctype === "ha" ? heikin(bars) : bars;
  function renderBars(d) {
    B = d;
    const times = d.bars.map(b => b.t + SHIFT);
    candles.setData(shown(d.bars).map((b, i) => ({ time: times[i], open: b.o, high: b.h, low: b.l, close: b.c })));
    vol.setData(T("volume") ? d.bars.map((b, i) => ({ time: times[i], value: b.v,
      color: b.c >= b.o ? "rgba(8,153,129,.45)" : "rgba(242,54,69,.45)" })) : []);
    vwapS.setData(T("vwap") ? series(d.vwap, times) : []);
    const vb = d.vwap_bands || {}, bb = d.bb || {};
    u1S.setData(T("vwap1") && vb.u1 ? series(vb.u1, times) : []); l1S.setData(T("vwap1") && vb.l1 ? series(vb.l1, times) : []);
    u2S.setData(T("vwap2") && vb.u2 ? series(vb.u2, times) : []); l2S.setData(T("vwap2") && vb.l2 ? series(vb.l2, times) : []);
    bbU.setData(T("bb") && bb.up ? series(bb.up, times) : []); bbL.setData(T("bb") && bb.lo ? series(bb.lo, times) : []);
    bbM.setData(T("bb") && bb.mid ? series(bb.mid, times) : []);
    bvwS.setData(T("bbvwap") ? series(d.bull_vwap, times) : []);
    svwS.setData(T("bbvwap") ? series(d.bear_vwap, times) : []);
    ema1S.setData(T("ema1") ? series(d.ema1, times) : []);
    ema2S.setData(T("ema2") ? series(d.ema2, times) : []);
    const fl = f => f && f.line ? f.line.map(([t, c]) => ({ time: t + SHIFT, value: c })) : [];
    nearS.setData(T("near_line") ? fl(d.near) : []);
    nextS.setData(T("next_line") ? fl(d.next) : []);
    netS.setData(d.flow_rows.map((r, i) => ({ time: times[i], value: r.net, color: r.net >= 0 ? "rgba(8,153,129,.6)" : "rgba(242,54,69,.6)" })));
    cumS.setData(d.flow_rows.map((r, i) => ({ time: times[i], value: r.cum })));
    avgS.setData(T("adaptive") ? series(d.flow_rows.map(r => r.avg), times) : []);
    lastCandle = d.bars.length ? Object.assign({}, d.bars[d.bars.length - 1]) : null;
    setOpt(OPT.ce, d.options.ce); setOpt(OPT.pe, d.options.pe);
    if (!renderBars.fitted || renderBars.key !== d.symbol + d.tf) {
      renderBars.fitted = true; renderBars.key = d.symbol + d.tf;
      main.timeScale().setVisibleLogicalRange({ from: Math.max(0, d.bars.length - 120), to: d.bars.length + 8 });
      ceC.timeScale().fitContent(); peC.timeScale().fitContent();
    }
    legend(); flowLegend(); priceLines(); marks(); drawStrip(); drawProfile();
  }

  function legend(t) {
    if (!B || !B.bars.length) return;
    const i = t ? B.bars.findIndex(b => b.t + SHIFT === t) : B.bars.length - 1, b = B.bars[i < 0 ? B.bars.length - 1 : i];
    const tot = (b.bv + b.sv) || 1, day = (B.bull_day + B.bear_day) || 1;
    const fut = (key, f, color) => T(key) && f && f.symbol && f.line.length ?
      ` · <span style="color:${color}">${esc(f.symbol)} ${fmt(f.line[f.line.length - 1][1])}</span>` : "";
    $("legend").innerHTML = `<b>${esc(B.symbol)} · ${B.tf} min${prefs.ctype === "ha" ? " · Heikin-Ashi (values below are real prices)" : ""}</b>${fut("near_line", B.near, "#ff6d00")}${fut("next_line", B.next, "#00acc1")}<br>O ${fmt(b.o)} H ${fmt(b.h)} L ${fmt(b.l)} C ${fmt(b.c)} · Vol ${lk(b.v)}` +
      (T("bullbear") ? ` (<span class="g">bull ${lk(b.bv)} ${Math.round(b.bv / tot * 100)}%</span> · <span class="r">bear ${lk(b.sv)} ${Math.round(b.sv / tot * 100)}%</span>)` : "") +
      (T("vwap") ? `<br><span class="b">VWAP ${fmt(B.vwap[i < 0 ? B.vwap.length - 1 : i])}</span>` : "") +
      (T("bullbear") ? `<br>Today so far: <span class="g">bull volume ${lk(B.bull_day)} (${Math.round(B.bull_day / day * 100)}%)</span> · <span class="r">bear volume ${lk(B.bear_day)} (${Math.round(B.bear_day / day * 100)}%)</span>` : "");
  }
  flowC.subscribeCrosshairMove(p => {
    const tip = $("flowtip");
    if (!B || !p || !p.point || !p.time) { tip.style.display = "none"; return; }
    const i = B.bars.findIndex(b => b.t + SHIFT === p.time);
    if (i < 0) { tip.style.display = "none"; return; }
    const r = B.flow_rows[i], b = B.bars[i];
    tip.innerHTML = `<div class="t">${hhmm(p.time)} · buying − selling</div>` +
      `<div class="row"><span>This candle</span><b class="${r.net >= 0 ? "pos" : "neg"}">${sg(r.net)}</b></div>` +
      `<div class="row"><span><i class="dot" style="background:#2962ff"></i>Running total today</span><b>${sg(r.cum)}</b></div>` +
      (r.avg !== null ? `<div class="row"><span><i class="dot" style="background:#ff9800"></i>Adaptive average</span><b>${sg(r.avg)}</b></div>` : "") +
      `<div class="row"><span>Bull / bear volume</span><b><span class="pos">${lk(r.bull)}</span> / <span class="neg">${lk(r.bear)}</span></b></div>` +
      `<div class="row"><span>Close</span><b>${fmt(b.c)}</b></div>`;
    const box = $("flow"), wd = box.clientWidth;
    tip.style.display = "block";
    tip.style.left = (p.point.x + 220 > wd ? p.point.x - 210 : p.point.x + 16) + "px";
    tip.style.top = (box.offsetTop + 2) + "px";
  });
  function flowLegend() {
    const f = B.flow;
    $("flowlegend").innerHTML = `Buying − selling, today: <b class="${f.today >= 0 ? "g" : "r"}">${sg(f.today)}</b> · this candle ${sg(f.this_candle)}<br>` +
      `Bull share — day ${f.share_day === null ? "-" : Math.round(f.share_day * 100) + "%"} · last 20 candles ${f.share_20 === null ? "-" : Math.round(f.share_20 * 100) + "%"} · ratio ${fmt(f.ratio)} bull : 1 bear` +
      (T("adaptive") ? ` · <span class="a">adaptive average ${lk(f.avg)}</span>, line ${f.above_avg ? "above" : "below"} it` : "") +
      ` <span class="muted">(estimated from where each candle closed, not from real orders)</span>`;
  }

  let lines = [];
  function priceLines() {
    lines.forEach(l => candles.removePriceLine(l)); lines = [];
    const add = (price, color, title) => { if (price) lines.push(candles.createPriceLine({ price, color, lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title })); };
    if (B) {
      const L = B.levels;
      if (T("dayopen")) add(L.open, "#787b86", "open");
      if (T("prevday")) { add(L.prev_high, "#787b86", "prev high"); add(L.prev_close, "#787b86", "prev close"); add(L.prev_low, "#787b86", "prev low"); }
      if (T("first5")) { add(L.or5_high, "#26c6da", "5m high"); add(L.or5_low, "#26c6da", "5m low"); }
      if (T("first15")) { add(L.or15_high, "#7e57c2", "15m high"); add(L.or15_low, "#7e57c2", "15m low"); }
      if (T("first30")) { add(L.or_high, "#5b8cff", "30m high"); add(L.or_low, "#5b8cff", "30m low"); }
    }
    if (A && !A.empty) for (const l of A.levels) {
      if ((l.kind === "call_wall" || l.kind === "put_wall") && !T("oiwalls")) continue;
      if (l.kind === "hedging" || l.kind === "trapped") continue;      // shown as dots (hover) + side panel
      add(l.price + shift(), { call_wall: "#f23645", put_wall: "#089981", hedging: "#7b1fa2", trapped: "#9c27b0" }[l.kind], l.title);
    }
  }

  // marks on the chart + hover text
  let markIndex = {}, dotHits = [];
  function marks() {
    if (!B) return;
    const out = [], idx = {};
    const want = { lean: "m_lean", calls_added: "m_calls_added", calls_exiting: "m_calls_exiting", puts_added: "m_puts_added",
      puts_exiting: "m_puts_exiting", bearish_div: "m_div", bullish_div: "m_div", trapped: "m_trapped" };
    const all = (A && !A.empty ? A.marks : []).concat(B.divergences);
    const first = B.bars.length ? B.bars[0].t + SHIFT : 0;
    for (const m of all) {
      if (!T(want[m.kind])) continue;
      const time = bucket(m.ts, B.tf);
      if (time < first) continue;
      (idx[time] = idx[time] || []).push(m.text);
      const up = /bullish|BOUGHT|added/.test(m.kind + m.text) && !/calls_added.*WRITTEN/.test(m.kind + m.text);
      const shape = m.kind === "trapped" || m.kind === "lean" ? "square" : m.kind.endsWith("div") ? (m.kind === "bullish_div" ? "arrowUp" : "arrowDown") : "circle";
      const color = m.kind === "trapped" ? "#9c27b0" : m.kind === "lean" ? "#787b86" : m.kind === "bullish_div" ? "#089981" :
        m.kind === "bearish_div" ? "#f23645" : /BOUGHT/.test(m.text) === m.kind.startsWith("calls") ? "#089981" : "#f23645";
      out.push({ time, position: m.kind === "bullish_div" ? "belowBar" : "aboveBar", color, shape, size: 1 });
    }
    out.sort((a, b) => a.time - b.time);
    candles.setMarkers(out);
    markIndex = idx;
  }
  main.subscribeCrosshairMove(p => {
    const tip = $("tip");
    legend(p && p.time);
    const hit = p && p.point && (dotHits.find(d => Math.abs(d.x - p.point.x) <= 8 && Math.abs(d.y - p.point.y) <= 8) ||
      bigHits.find(d => Math.hypot(d.x - p.point.x, d.y - p.point.y) <= d.r + 2));
    const texts = hit ? [hit.text] : p && p.time && markIndex[p.time];
    if (!texts || !p.point) { tip.style.display = "none"; return; }
    tip.innerHTML = texts.map(esc).join("<br><br>");
    tip.style.display = "block";
    tip.style.left = Math.min(p.point.x + 20, $("main").clientWidth - 370) + "px";
    tip.style.top = (p.point.y + 30) + "px";
  });

  // bull / bear strip under the candles
  function drawStrip() {
    const cv = $("strip"); if (!cv) return;
    const w = cv.clientWidth, h = 10, dpr = window.devicePixelRatio || 1;
    cv.width = w * dpr; cv.height = h * dpr;
    const ctx = cv.getContext("2d"); ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, w, h);
    if (!B || !T("strip")) return;
    const ts = main.timeScale(), bw = Math.max(2, (ts.options().barSpacing || 6) * 0.9);
    B.bars.forEach(b => {
      const x = ts.timeToCoordinate(b.t + SHIFT); if (x === null) return;
      const s = b.bv / ((b.bv + b.sv) || 1);
      ctx.fillStyle = s > 0.55 ? "rgba(8,153,129,.85)" : s < 0.45 ? "rgba(242,54,69,.85)" : "rgba(120,123,134,.5)";
      ctx.fillRect(x - bw / 2, 0, bw, h);
    });
  }

  // ------------------------------------------------------------------ OI profile (Total OI and / or OI change)
  const shift = () => (prefs.align && A && !A.empty && B && B.bars.length && A.live.forward) ?
    (B.bars[B.bars.length - 1].c - A.live.forward) : 0;
  let bigHits = [];
  function drawOverlays(ctx, w, h) {
    const ts = main.timeScale(), right = w - main.priceScale("right").width();
    const X = t => { const x = ts.timeToCoordinate(t + SHIFT); return x === null ? null : x; };
    const Y = p => candles.priceToCoordinate(p);
    const first = B.bars.length ? B.bars[0].t : 0, x0 = t => { const x = X(Math.max(t, first)); return x === null ? 0 : x; };
    const lastX = B.bars.length ? (X(B.bars[B.bars.length - 1].t) ?? right) : right, endX = Math.min(right, lastX + 24);
    const box = (t0, t1, top, bot, fill, stroke, label) => {
      const a = x0(t0), b = t1 ? (X(t1) ?? endX) : endX, y1 = Y(top), y2 = Y(bot);
      if (y1 === null || y2 === null || b < 0) return;
      ctx.fillStyle = fill; ctx.fillRect(a, Math.min(y1, y2), Math.max(1, b - a), Math.abs(y2 - y1));
      if (stroke) { ctx.strokeStyle = stroke; ctx.lineWidth = 1; ctx.strokeRect(a + .5, Math.min(y1, y2) + .5, Math.max(1, b - a), Math.abs(y2 - y1)); }
      if (label) { ctx.fillStyle = stroke || fill; ctx.font = "10px sans-serif"; ctx.fillText(label, a + 3, Math.min(y1, y2) + 10); }
    };
    const S = B.smc || {};
    if (T("smc_pd") && S.pd) {
      const r = S.pd.top - S.pd.bottom;
      box(S.pd.from_ts, null, S.pd.top, S.pd.top - r * 0.25, "rgba(242,54,69,.05)", null, null);
      box(S.pd.from_ts, null, S.pd.bottom + r * 0.25, S.pd.bottom, "rgba(8,153,129,.05)", null, null);
      const y = Y(S.pd.eq), a = x0(S.pd.from_ts);
      ctx.font = "10px sans-serif";
      ctx.fillStyle = "rgba(242,54,69,.75)"; const yt = Y(S.pd.top); if (yt !== null) ctx.fillText("Premium", a + 3, yt + 11);
      ctx.fillStyle = "rgba(8,153,129,.8)"; const yb = Y(S.pd.bottom); if (yb !== null) ctx.fillText("Discount", a + 3, yb - 4);
      if (y !== null) { ctx.strokeStyle = "rgba(149,152,161,.6)"; ctx.setLineDash([4, 4]); ctx.beginPath(); ctx.moveTo(a, y); ctx.lineTo(endX, y); ctx.stroke(); ctx.setLineDash([]);
        ctx.fillStyle = "rgba(149,152,161,.9)"; ctx.fillText("Equilibrium", a + 3, y - 3); }
    }
    if (T("smc_fvg")) for (const g of S.fvgs || [])
      box(g.from_ts, g.end_ts, g.top, g.bottom, g.dir === "bull" ? "rgba(41,98,255,.09)" : "rgba(255,152,0,.09)", null, "FVG");
    if (T("smc_ob")) for (const o of S.obs || [])
      box(o.from_ts, o.end_ts, o.top, o.bottom, o.dir === "bull" ? "rgba(8,153,129,.10)" : "rgba(242,54,69,.10)",
        o.dir === "bull" ? "rgba(8,153,129,.6)" : "rgba(242,54,69,.6)", o.dir === "bull" ? "Bull OB" : "Bear OB");
    if (T("smc_struct")) for (const e of S.structure || []) {
      const a = X(e.from_ts), b = X(e.to_ts), y = Y(e.price);
      if (b === null || y === null) continue;
      const col = e.dir === "up" ? "rgba(8,153,129,.85)" : "rgba(242,54,69,.85)", xa = a === null ? 0 : a;
      ctx.strokeStyle = col; ctx.lineWidth = 1; ctx.setLineDash(e.kind === "CHoCH" ? [] : [4, 3]);
      ctx.beginPath(); ctx.moveTo(xa, y); ctx.lineTo(b, y); ctx.stroke(); ctx.setLineDash([]);
      ctx.fillStyle = col; ctx.font = e.kind === "CHoCH" ? "bold 10px sans-serif" : "10px sans-serif"; ctx.textAlign = "center";
      ctx.fillText(e.kind, (xa + b) / 2, e.dir === "up" ? y - 4 : y + 11); ctx.textAlign = "left";
    }
    const vp = B.vp_day;
    if (T("vp_day") && vp) {                         // today's volume profile, anchored at today's first candle
      const a = X(vp.from_ts);
      if (a !== null) {
        const width = Math.max(40, Math.min(right * 0.22, right - a - 10)), maxV = Math.max(...vp.vol), va = new Set(vp.va);
        vp.vol.forEach((v, i) => {
          const y1 = Y(vp.low + vp.step * (i + 1)), y2 = Y(vp.low + vp.step * i);
          if (y1 === null || y2 === null) return;
          ctx.fillStyle = va.has(i) ? "rgba(135,206,235,.30)" : "rgba(135,206,235,.12)";
          ctx.fillRect(a, Math.min(y1, y2) + .5, v / maxV * width, Math.max(1, Math.abs(y2 - y1) - 1));
        });
        for (const [p, name] of [[vp.vah, "VAH"], [vp.poc, "POC"], [vp.val, "VAL"]]) {
          const y = Y(p); if (y === null) continue;
          ctx.strokeStyle = name === "POC" ? "rgba(135,206,235,.95)" : "rgba(135,206,235,.6)"; ctx.setLineDash(name === "POC" ? [] : [3, 3]);
          ctx.beginPath(); ctx.moveTo(a, y); ctx.lineTo(a + width, y); ctx.stroke(); ctx.setLineDash([]);
          ctx.fillStyle = "rgba(135,206,235,.95)"; ctx.font = "10px sans-serif"; ctx.fillText(`${name} ${fmt(p, 0)}`, a + width + 3, y + 3);
        }
      }
    }
    if (T("big")) for (const t of B.big || []) {     // big trades: circle size grows with the rupee value
      const x = X(bucket(t.ts, B.tf) - SHIFT), y = Y(t.y);
      if (x === null || y === null) continue;
      const r = Math.max(5, Math.min(18, 4 + 3 * Math.sqrt(t.value / 50e5)));
      const buy = t.side === "buy";
      ctx.fillStyle = buy ? "rgba(8,153,129,.28)" : "rgba(242,54,69,.28)"; ctx.strokeStyle = buy ? "rgba(8,153,129,.9)" : "rgba(242,54,69,.9)";
      ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill(); ctx.lineWidth = 1.2; ctx.stroke();
      bigHits.push({ x, y, r, text: `BIG ${buy ? "BUY" : "SELL"} (hit the ${buy ? "offer" : "bid"}) · ${t.symbol} · ${fmt(t.qty, 0)} qty @ ${fmt(t.price)} = ₹${lk(t.value)} · ${new Date(t.ts * 1000).toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour12: false })}` });
    }
  }
  function drawProfile() {
    const cv = $("profile"), el = $("main");
    const w = el.clientWidth, h = el.clientHeight, dpr = window.devicePixelRatio || 1;
    cv.style.top = el.offsetTop + "px"; cv.width = w * dpr; cv.height = h * dpr; cv.style.width = w + "px"; cv.style.height = h + "px";
    const ctx = cv.getContext("2d"); ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, w, h);
    bigHits = [];
    if (B) drawOverlays(ctx, w, h);
    // the profiles, right to left, each in its own column so they never overlap (owner 26 Nov)
    const PROFILES = [["oi_total", "OI", "call_oi", "put_oi"], ["oi_change", "OI chg", "call_ch", "put_ch"],
      ["prof_dex", "Delta", "call_dex", "put_dex"], ["prof_gex", "GEX", "call_gex", "put_gex"]].filter(c => T(c[0]));
    dotHits = [];
    if (!A || A.empty) return;
    const right = w - main.priceScale("right").width() - 4, gap = 10, n = PROFILES.length;
    const colW = n ? Math.max(36, Math.min(Number(prefs.pw) || 110, (right * 0.34 - gap * (n - 1)) / n)) : 0;
    const dotX = (n ? right - n * (colW + gap) + gap : right) - 14;
    const dot = (price, color, text, diamond) => {
      const y = candles.priceToCoordinate(price + shift());
      if (y === null || y < 4 || y > h - 4) return;
      const same = dotHits.filter(d => Math.abs(d.y - y) < 2).length, x = dotX - same * 13;
      ctx.fillStyle = color; ctx.strokeStyle = "#fff"; ctx.lineWidth = 1.5; ctx.beginPath();
      if (diamond) { ctx.moveTo(x, y - 6); ctx.lineTo(x + 6, y); ctx.lineTo(x, y + 6); ctx.lineTo(x - 6, y); ctx.closePath(); }
      else ctx.arc(x, y, 5, 0, Math.PI * 2);
      ctx.fill(); ctx.stroke();
      dotHits.push({ x, y, text });
    };
    if (T("trapped")) for (const r of A.trapped.rows.slice(0, 6))
      dot(r.strike, r.option === "CALL" || /call/i.test(r.option) ? "#e040fb" : "#ab47bc",
        `TRAPPED ${r.option.toUpperCase()} ${r.who.toUpperCase()} at ${fmt(r.strike, 0)}: ${fmt(r.lots, 0)} lots built at about ${fmt(r.built_at)}, now ${fmt(r.now)}, ${Math.round(r.under_water * 100)}% under water (about ₹${lk(r.money)}).`);
    if (T("hedging") && A.hedging.heaviest) dot(A.hedging.heaviest, "#7b1fa2",
      `HEAVIEST HEDGING at ${fmt(A.hedging.heaviest, 0)}: a 50-point rise makes option writers buy about ${lk(A.hedging.buy_on_rise)} lots; a fall makes them sell about ${lk(A.hedging.sell_on_fall)}.`, true);
    if (!A.profile.length || !n) return;
    const ys = A.profile.map(p => candles.priceToCoordinate(p.strike + shift()));
    const vis = A.profile.map((p, i) => [p, ys[i]]).filter(([p, y]) => y !== null && y > 0 && y < h);
    if (!vis.length) return;
    const step = vis.length > 1 ? Math.abs(vis[1][1] - vis[0][1]) : 20, th = Math.max(2, Math.min(9, step * 0.38));
    ctx.font = "10px sans-serif"; ctx.textBaseline = "middle";
    const bar = (xr, len, y, color, hollow, label) => {
      const x = xr - len;
      if (hollow) { ctx.strokeStyle = color; ctx.lineWidth = 1; ctx.strokeRect(x + .5, y + .5, len, th - 1); }
      else { ctx.fillStyle = color; ctx.fillRect(x, y, len, th); }
      if (prefs.pv && len > 34 && th >= 7) { ctx.fillStyle = textCol; ctx.fillText(label, x + 3, y + th / 2 + .5); }
    };
    const textCol = getComputedStyle(document.documentElement).getPropertyValue("--text");
    const COL = { oi_total: ["rgba(242,54,69,.42)", "rgba(8,153,129,.42)"], oi_change: ["rgba(242,54,69,.28)", "rgba(8,153,129,.28)"],
      prof_dex: ["rgba(41,98,255,.40)", "rgba(255,152,0,.40)"], prof_gex: ["rgba(171,71,188,.40)", "rgba(0,188,212,.40)"] };
    const muted = getComputedStyle(document.documentElement).getPropertyValue("--muted");
    PROFILES.forEach(([key, title, ck, pk], i) => {
      const xr = right - i * (colW + gap);
      const max = Math.max(...vis.map(([p]) => Math.max(Math.abs(p[ck] || 0), Math.abs(p[pk] || 0))), 1e-9);
      ctx.fillStyle = muted; ctx.textAlign = "right"; ctx.fillText(title, xr, 8); ctx.textAlign = "left";
      ctx.strokeStyle = "rgba(120,123,134,.25)"; ctx.beginPath(); ctx.moveTo(xr + .5, 14); ctx.lineTo(xr + .5, h); ctx.stroke();
      for (const [p, y] of vis) {
        const c = p[ck] || 0, u = p[pk] || 0;
        const label = v => key === "oi_change" || key === "prof_dex" ? sg(v) : lk(v);
        const hollowC = key === "oi_change" && c < 0, hollowP = key === "oi_change" && u < 0;
        bar(xr, Math.abs(c) / max * colW, y - th, hollowC ? "rgba(242,54,69,.7)" : COL[key][0], hollowC, label(c));
        bar(xr, Math.abs(u) / max * colW, y, hollowP ? "rgba(8,153,129,.7)" : COL[key][1], hollowP, label(u));
      }
    });
  }
  new ResizeObserver(() => { drawProfile(); drawStrip(); }).observe($("main"));

  // ------------------------------------------------------------------ panels from the option chain
  const card = c => `<div class="cardtxt ${c.tone || "neutral"}"><b>${esc(c.title)}</b>${prefs.explainer ? esc(c.text) : ""}</div>`;
  function renderAnalytics(d) {
    A = d;
    if (d.empty) return;
    const s = d.summary;
    $("optmeta").textContent = ` ${d.index} · expiry ${d.expiry} · price implied by the options ${fmt(s.forward)} · ${d.strikes_read} strikes read · history ${d.history_minutes} min`;
    $("saying").innerHTML = `<div class="head">WHAT THE OPTIONS ARE SAYING <span class="leanbadge ${d.saying.lean}">Lean: ${d.saying.lean}</span><span class="muted">${esc(d.saying.agree)}</span></div>` +
      `<div class="cards">${d.saying.cards.map(card).join("")}</div><p class="muted small">These are the usual rules of thumb applied to the numbers below. They are not tested signals, and open interest never says who traded.</p>`;
    const k = (l, v) => `<div><span>${l}</span><b>${v}</b></div>`;
    $("strip_summary").innerHTML = k("PUT / CALL OI", fmt(s.pcr)) + k("CALL OI TODAY", sg(s.call_oi_today)) + k("PUT OI TODAY", sg(s.put_oi_today)) +
      k("CALL WALL ABOVE", fmt(s.call_wall, 0)) + k("PUT WALL BELOW", fmt(s.put_wall, 0)) + k("ATM IMPLIED VOL", s.atm_iv ? fmt(s.atm_iv * 100, 1) + "%" : "-") +
      k("ATM STRADDLE", fmt(s.straddle)) + k("TO EXPIRY", fmt(s.hours_to_expiry, 1) + " hours");
    const om = new Map();                              // one point per minute (the latest reading of that minute)
    d.oi_series.forEach(x => om.set(x.time - (x.time % 60) + SHIFT, x));
    const ot = [...om.keys()].sort((a, b) => a - b);
    oiCalls.setData(ot.map(t => ({ time: t, value: om.get(t).calls })));
    oiPuts.setData(ot.map(t => ({ time: t, value: om.get(t).puts })));
    renderChain(d);
    const t = d.trapped;
    $("trapmeta").textContent = ` ${t.pockets} pockets under water · about ₹${lk(t.total)} of value against them · recorded today`;
    $("trapcards").innerHTML = t.cards.map(c => card(Object.assign({ tone: "bearish" }, c))).join("");
    $("traptable").innerHTML = `<tr><th>STRIKE</th><th>OPTION</th><th>WHO</th><th class="num">LOTS</th><th class="num">BUILT AT</th><th class="num">NOW</th><th class="num">UNDER WATER</th><th class="num">MONEY</th></tr>` +
      t.rows.map(r => `<tr><td>${fmt(r.strike, 0)}</td><td>${r.option}</td><td class="${r.who === "buyers" ? "buying" : "writing"}">${r.who}</td><td class="num">${fmt(r.lots, 0)}</td>` +
        `<td class="num">${fmt(r.built_at)}</td><td class="num">${fmt(r.now)}</td><td class="num neg">${Math.round(r.under_water * 100)}%</td><td class="num">₹${lk(r.money)}</td></tr>`).join("");
    const m = d.maths;
    $("mathmeta").textContent = ` at the money ${fmt(m.atm, 0)} · ${m.hours} hours to expiry` + (m.avg_daily_move ? ` · the index has moved ${fmt(m.avg_daily_move, 0)} points a session on average over the last 4` : "");
    $("mathcards").innerHTML = m.cards.map(card).join("");
    $("mathtable").innerHTML = `<tr><th>MEASURE</th><th>NOW</th><th>15 MIN AGO</th><th>AT THE OPEN</th><th>WHAT IT MEANS</th></tr>` +
      m.table.map(r => `<tr><td>${esc(r.measure)}</td><td><b>${esc(r.now)}</b></td><td>${esc(r.m15)}</td><td>${esc(r.open)}</td><td class="muted">${esc(r.meaning)}</td></tr>`).join("");
    const hg = d.hedging;
    $("hedgemeta").textContent = hg.heaviest ? ` heaviest at ${fmt(hg.heaviest, 0)} · ${lk(hg.buy_on_rise)} lots bought on a 50-point rise, ${lk(hg.sell_on_fall)} sold on a fall` : "";
    $("hedgecards").innerHTML = hg.cards.map(card).join("");
    drawHedge();
    if (d.log) $("log").textContent = d.log.join("\n");
    const sw = d.summary, lv = [];
    if (sw.call_wall) lv.push(`<div class="lvl"><b class="neg">Call wall ${fmt(sw.call_wall, 0)}</b><span>${lk(sw.call_wall_oi)} lots open</span></div>`);
    if (sw.put_wall) lv.push(`<div class="lvl"><b class="pos">Put wall ${fmt(sw.put_wall, 0)}</b><span>${lk(sw.put_wall_oi)} lots open</span></div>`);
    if (d.hedging.heaviest) lv.push(`<div class="lvl"><b class="hedge">◆ Heaviest hedging ${fmt(d.hedging.heaviest, 0)}</b><span>${lk(d.hedging.buy_on_rise)} lots bought per 50-pt rise</span></div>`);
    d.trapped.rows.slice(0, 6).forEach(r => lv.push(`<div class="lvl"><b class="trap">● Trapped ${esc(r.option.toLowerCase())} ${esc(r.who)} ${fmt(r.strike, 0)}</b>` +
      `<span>${fmt(r.lots, 0)} lots · ${Math.round(r.under_water * 100)}% down · built ${fmt(r.built_at)}, now ${fmt(r.now)}</span>` +
      `<span class="stake">At stake ₹${lk(r.lots * d.lot * r.built_at)} · ${r.who === "buyers" ? "loss" : "loss so far"} ₹${lk(r.money)}</span></div>`));
    $("levels").innerHTML = lv.join("") || `<span class="muted">Nothing yet.</span>`;
    renderPricing(d.pricing || {});
    const L = d.live;
    $("live").innerHTML = `<span>${esc((B && B.symbol) || L.future || "Chart")}</span><span class="big" id="lv_fut">${fmt(lastCandle ? lastCandle.c : null)}</span>` +
      `<span>ATM strike</span><b>${fmt(L.atm, 0)}</b><span>${esc(L.ce || "ATM call")}</span><b id="lv_ce">${fmt(L.ce_ltp)}</b>` +
      `<span>${esc(L.pe || "ATM put")}</span><b id="lv_pe">${fmt(L.pe_ltp)}</b><span>Index</span><b id="lv_spot">${fmt(L.spot)}</b><span>${esc(L.future || "Near future")}</span><b id="lv_near">${fmt(B && B.near && B.near.line.length ? B.near.line[B.near.line.length - 1][1] : null)}</b>` +
      `<span>Price implied by options</span><b>${fmt(L.forward)}</b><span>Lot size</span><b>${d.lot}</b><span>Expiry</span><b>${esc(d.expiry || "-")}</b>`;
    const sel = $("strike"), cur = sel.value;
    sel.innerHTML = `<option value="">ATM (follows the price)</option>` + d.chain.map(r => `<option value="${r.strike}">${fmt(r.strike, 0)}</option>`).join("");
    sel.value = cur;
    priceLines(); marks(); drawProfile(); applyToggles(true);
  }
  function renderPricing(q) {
    if (!q.ready) { $("pricing").innerHTML = `<span class="muted">Waiting for prices${q.error ? " (" + esc(q.error) + ")" : ""}.</span>`; return; }
    const tone = q.bias === "CALL SIDE" ? "pos" : q.bias === "PUT SIDE" ? "neg" : "muted";
    const dear = q.dear === "calls" ? `<b class="neg">Calls are expensive</b>, puts cheap` : q.dear === "puts" ?
      `<b class="pos">Puts are expensive</b>, calls cheap` : q.dear === "even" ? "Calls and puts priced evenly" : "Waiting for the future's price";
    const rng = v => v ? `₹${fmt(Math.max(0, v[0]), 0)}–${fmt(Math.max(0, v[1]), 0)}` : "-";
    const rows = (q.horizons || []).map(h => `<tr><td>${esc(h.label)}</td><td>±${fmt(h.move, 0)}</td><td class="pos">${rng(h.ce)}</td><td class="neg">${rng(h.pe)}</td></tr>`).join("");
    $("pricing").innerHTML = `<div class="bias ${tone}">Bias: ${esc(q.bias)}</div><div>${dear}` +
      (q.parity_gap !== undefined ? ` <span class="muted">(${q.parity_gap >= 0 ? "+" : ""}${fmt(q.parity_gap, 1)} pts: options' price ${fmt(q.options_forward)} vs fair ${fmt(q.fair_forward)})</span>` : "") + `</div>` +
      `<ul class="why">${(q.reasons || []).map(r => `<li>${esc(r)}</li>`).join("")}</ul>` +
      `<div class="muted">Volatility used ${q.sigma ? fmt(q.sigma * 100, 1) + "%" : "-"} (ATM implied ${q.iv ? fmt(q.iv * 100, 1) + "%" : "-"}, last hour ${q.realized ? fmt(q.realized * 100, 1) + "%" : "-"})</div>` +
      `<table class="mv"><tr><th></th><th>Index</th><th>${fmt(q.atm, 0)} CE</th><th>${fmt(q.atm, 0)} PE</th></tr>${rows}</table>` +
      `<div class="muted small">Option ₹ = gain if the index moves half to one expected move in its favour, after time decay. ` +
      `About 2 times in 3 the index stays inside ±one expected move. Maths, not a forecast of direction.</div>`;
  }

  function renderChain(d) {
    const g = prefs.greeks, rows = d.chain;
    const mx = k => Math.max(...rows.map(r => Math.max(Math.abs(r.call[k] || 0), Math.abs(r.put[k] || 0))), 1e-9);
    const M = { value: mx("value"), oi: mx("oi"), week: mx("week"), day: mx("day"), m15: mx("m15"), dex: mx("dex"), gex: mx("gex") };
    const SIDE = { call: "rgba(242,54,69,.55)", put: "rgba(8,153,129,.55)" }, GREY = "rgba(120,123,134,.55)";
    // every bar starts at the right edge of its cell and grows left, on both sides (owner 25 Nov)
    const bc = (v, k, color, text, cls, title) => v === null || v === undefined ? `<td class="bc">·</td>` :
      `<td class="bc" ${title ? `title="${esc(title)}"` : ""}><i style="width:${Math.round(Math.abs(v) / M[k] * 100)}%;background:${color}"></i><span class="${cls || ""}">${text}</span></td>`;
    const chg = (x, k, side, title) => bc(x[k], k, (x[k] || 0) >= 0 ? SIDE[side] : GREY, sg(x[k]), (x[k] || 0) >= 0 ? "pos" : "neg", title);
    const leg = (x, side) => {
      const arrow = x.arrow === "up" ? ` <b class="arw up" title="3 or more strikes in a row: call writers buying back">▲</b>` :
        x.arrow === "down" ? ` <b class="arw down" title="3 or more strikes in a row: put writers buying back">▼</b>` : "";
      const read = `<td class="rd"><span class="${x.reading === "covering" ? "sc" : x.reading}">${esc(x.label)}</span>${arrow}</td>`;
      const cells = [bc(x.oi, "oi", SIDE[side], lk(x.oi)), bc(x.value, "value", "rgba(255,183,77,.45)", "₹" + lk(x.value), "", "Outstanding value: OI x lot x premium"),
        chg(x, "week", side, d.week_from ? `OI change since the close of ${d.week_from} (start of this series)` : ""),
        chg(x, "day", side), chg(x, "m15", side, x.premium15 === null || x.premium15 === undefined ? "" : `premium over 15 min ${fmt(x.premium15)}`),
        read,
        bc(x.dex, "dex", "rgba(41,98,255,.45)", sg(x.dex), "", "DEX: delta x open interest (lots of index)"),
        bc(x.gex, "gex", "rgba(156,39,176,.45)", lk(x.gex), "", "GEX: rupees of index the hedgers trade for a 1% move")];
      const gk = g ? [`<td>${x.iv ? fmt(x.iv * 100, 1) : "-"}</td>`, `<td title="gamma ${x.gamma ? x.gamma.toFixed(5) : "-"} · vega ${fmt(x.vega)}">${fmt(x.delta)}</td>`, `<td>${fmt(x.theta, 1)}</td>`] : [];
      const price = `<td><b>${fmt(x.price)}</b></td>`;
      return side === "call" ? [...cells, ...gk, price].join("") : [price, ...gk.slice().reverse(), ...cells.slice().reverse()].join("");
    };
    const head = ["OI", "Value", "Week", "Day", "15 min", "Reading", "DEX", "GEX", ...(g ? ["IV", "Delta", "Theta"] : []), "Price"];
    const tip = { Week: "OI change since the start of this weekly series", Day: "OI change today", "15 min": "OI change in the last 15 minutes",
      Reading: "Last 15 minutes. Short Cov = OI down, premium up (writers buying back). Arrow = 3+ strikes in a row",
      DEX: "Delta x OI, in lots of the index", GEX: "Gamma exposure: rupees hedged for a 1% move" };
    const th = h => `<th title="${esc(tip[h] || "")}">${h}</th>`;
    $("chain").innerHTML = `<tr><th colspan="${head.length}" style="text-align:center">CALLS</th><th></th><th colspan="${head.length}" style="text-align:center">PUTS</th></tr>` +
      `<tr>${head.map(th).join("")}<th style="text-align:center">Strike</th>${head.slice().reverse().map(th).join("")}</tr>` +
      rows.map(r => `<tr class="${r.atm ? "atm" : ""}">${leg(r.call, "call")}<td class="k">${fmt(r.strike, 0)}</td>${leg(r.put, "put")}</tr>`).join("");
  }

  // ------------------------------------------------------------------ hover card on the OI-added-today lines
  const hhmm = t => { const d = new Date((t - SHIFT) * 1000); return d.toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", hour12: false }); };
  oiC.subscribeCrosshairMove(p => {
    const tip = $("oitip");
    const c = p && p.seriesData && p.seriesData.get(oiCalls), u = p && p.seriesData && p.seriesData.get(oiPuts);
    if (!p || !p.point || !p.time || !c || !u) { tip.style.display = "none"; return; }
    const diff = u.value - c.value;
    tip.innerHTML = `<div class="t">${hhmm(p.time)} · OI added today</div><div class="m">${esc(A && A.index || "")} · expiry ${esc(A && A.expiry || "-")}</div>` +
      `<div class="row"><span><i class="dot" style="background:#f23645"></i>Calls</span><b>${sg(c.value)} lots</b></div>` +
      `<div class="row"><span><i class="dot" style="background:#089981"></i>Puts</span><b>${sg(u.value)} lots</b></div>` +
      `<div class="row"><span>Puts − calls</span><b class="${diff >= 0 ? "pos" : "neg"}">${sg(diff)}</b></div>` +
      `<div class="m">${diff >= 0 ? "More puts than calls added (put writers busier)" : "More calls than puts added (call writers busier)"}</div>`;
    const box = $("oichart"), w = box.clientWidth;
    tip.style.display = "block";
    tip.style.left = (p.point.x + 230 > w ? p.point.x - 220 : p.point.x + 18) + "px";
    tip.style.top = (box.offsetTop + 2) + "px";
  });

  // ------------------------------------------------------------------ hedging pressure: strikes across, bars up
  let hedgeBars = [];
  function drawHedge() {
    const cv = $("hedgechart"); if (!cv || !A || A.empty) return;
    const rows = A.hedging.rows, w = cv.clientWidth, h = cv.clientHeight, dpr = window.devicePixelRatio || 1;
    if (!w) return;
    cv.width = w * dpr; cv.height = h * dpr;
    const ctx = cv.getContext("2d"); ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, w, h);
    const css = getComputedStyle(document.documentElement), v = n => css.getPropertyValue(n).trim();
    const left = 8, right = w - 8, top = 22, bottom = h - 34, n = rows.length;
    if (!n) return;
    const step = (right - left) / n, bw = Math.max(3, step * 0.7), max = Math.max(...rows.map(r => r.lots), 1);
    ctx.font = "11px sans-serif"; ctx.textAlign = "center"; ctx.textBaseline = "alphabetic";
    ctx.strokeStyle = v("--grid"); ctx.beginPath(); ctx.moveTo(left, bottom + .5); ctx.lineTo(right, bottom + .5); ctx.stroke();
    hedgeBars = [];
    const every = Math.max(1, Math.ceil(46 / step));
    const xs = rows.map((r, i) => left + step * i + step / 2);
    rows.forEach((r, i) => {
      const x = xs[i], bh = r.lots / max * (bottom - top);
      ctx.fillStyle = r.top ? (r.side === "call" ? "#f23645" : "#089981") : v("--bar");
      ctx.fillRect(x - bw / 2, bottom - bh, bw, bh);
      hedgeBars.push({ x0: x - step / 2, x1: x + step / 2, r });
    });
    // labels that never overlap: the top 5 first (value above the bar on two levels if crowded, strike below)
    const taken = [[], [], [], []], fits = (lvl, a, b) => !taken[lvl].some(([p, q]) => a < q + 4 && b > p - 4);
    const put = (lvl, text, x, y, color) => {
      const half = ctx.measureText(text).width / 2;
      if (!fits(lvl, x - half, x + half)) return false;
      taken[lvl].push([x - half, x + half]); ctx.fillStyle = color; ctx.fillText(text, x, y); return true;
    };
    const order = rows.map((r, i) => i).sort((a, b) => (rows[a].top || 99) - (rows[b].top || 99));
    for (const i of order) {
      const r = rows[i], x = xs[i], bh = r.lots / max * (bottom - top);
      if (r.top && !put(0, `#${r.top} ${lk(r.lots)}`, x, bottom - bh - 5, v("--text"))) put(1, `#${r.top} ${lk(r.lots)}`, x, bottom - bh - 18, v("--text"));
      if (r.top) { if (!put(2, fmt(r.strike, 0), x, bottom + 15, v("--text"))) put(3, fmt(r.strike, 0), x, bottom + 28, v("--text")); }
      else if (i % every === 0) put(2, fmt(r.strike, 0), x, bottom + 15, v("--muted"));
    }
    const price = A.hedging.price;
    if (price && n > 1) {
      const k0 = rows[0].strike, k1 = rows[n - 1].strike, x = left + step / 2 + (price - k0) / (k1 - k0) * (step * (n - 1));
      ctx.strokeStyle = v("--blue"); ctx.setLineDash([4, 4]); ctx.beginPath(); ctx.moveTo(x, top - 12); ctx.lineTo(x, bottom); ctx.stroke(); ctx.setLineDash([]);
      ctx.fillStyle = v("--blue"); ctx.fillText(`price ${fmt(price, 0)}`, x, top - 14 + 10);
    }
  }
  $("hedgechart").addEventListener("mousemove", e => {
    const tip = $("hedgetip"), rect = e.target.getBoundingClientRect(), x = e.clientX - rect.left;
    const b = hedgeBars.find(b => x >= b.x0 && x < b.x1);
    if (!b) { tip.style.display = "none"; return; }
    const r = b.r, tot = r.lots || 1;
    tip.innerHTML = `<div class="t">Strike ${fmt(r.strike, 0)}${r.top ? ` · #${r.top}` : ""}</div><div class="m">lots of futures hedged for a 50-point move</div>` +
      `<div class="row"><span>Total</span><b>${fmt(r.lots, 0)}</b></div>` +
      `<div class="row"><span><i class="dot" style="background:#f23645"></i>From call writers</span><b>${fmt(r.call_lots, 0)} (${Math.round(r.call_lots / tot * 100)}%)</b></div>` +
      `<div class="row"><span><i class="dot" style="background:#089981"></i>From put writers</span><b>${fmt(r.put_lots, 0)} (${Math.round(r.put_lots / tot * 100)}%)</b></div>` +
      `<div class="row"><span>Share of the heaviest</span><b>${Math.round(r.share * 100)}%</b></div>`;
    tip.style.display = "block";
    tip.style.left = Math.min(x + 14, rect.width - 240) + "px"; tip.style.top = "10px";
  });
  $("hedgechart").addEventListener("mouseleave", () => { $("hedgetip").style.display = "none"; });
  new ResizeObserver(() => drawHedge()).observe($("hedgechart"));

  function applyToggles(noRender) {
    $("cpcard").style.display = T("cpcharts") ? "" : "none";
    $("trapcard").style.display = T("trapped") && prefs.opt ? "" : "none";
    $("mathcard").style.display = T("maths") && prefs.opt ? "" : "none";
    $("hedgecard").style.display = T("hedging") && prefs.opt ? "" : "none";
    $("optcard").style.display = prefs.opt ? "" : "none";
    $("striprow").style.display = T("strip") ? "" : "none";
    if (!noRender && B) renderBars(B);
    else { drawProfile(); }
  }

  function onBig(t) {
    if (!B) return;
    if (B.instrument === "INDEX" && A && !A.empty && t.symbol === A.live.future && t.spot) { (B.big = B.big || []).push(Object.assign({ y: t.spot }, t)); drawProfile(); }
    else if (t.symbol === B.symbol) { (B.big = B.big || []).push(Object.assign({ y: t.price }, t)); drawProfile(); }
    for (const k of ["ce", "pe"]) if (OPT[k].symbol === t.symbol) { (OPT[k].big = OPT[k].big || []).push(t); drawOptProfile(OPT[k]); }
  }

  // ------------------------------------------------------------------ live ticks
  function onTick(m) {
    if (B && m.symbol === B.symbol && lastCandle) {
      const t = bucket(Math.floor(m.rx || Date.now() / 1000), B.tf);
      const lc = lastCandle;
      if (lc.t + SHIFT === t) { lc.h = Math.max(lc.h, m.ltp); lc.l = Math.min(lc.l, m.ltp); lc.c = m.ltp; }
      else if (t > lc.t + SHIFT) { Object.assign(lc, { t: t - SHIFT, o: m.ltp, h: m.ltp, l: m.ltp, c: m.ltp }); }
      if (prefs.ctype === "ha" && B.bars.length) {
        const all = B.bars.slice(0, -1).concat([lc]); B.bars = all;
        const hb = heikin(all.slice(-2)), x = hb[hb.length - 1];
        const prev = heikin(all)[all.length - 2];
        const o = prev ? (prev.o + prev.c) / 2 : x.o, c = (lc.o + lc.h + lc.l + lc.c) / 4;
        candles.update({ time: lc.t + SHIFT, open: o, high: Math.max(lc.h, o, c), low: Math.min(lc.l, o, c), close: c });
      } else candles.update({ time: lc.t + SHIFT, open: lc.o, high: lc.h, low: lc.l, close: lc.c });
      const el = $("lv_fut"); if (el) el.textContent = fmt(m.ltp);
    }
    if (A && !A.empty && m.symbol === A.live.future) { const el = $("lv_near"); if (el) el.textContent = fmt(m.ltp); }
    if (A && !A.empty) {
      if (m.symbol === A.live.ce) { const el = $("lv_ce"); if (el) el.textContent = fmt(m.ltp); }
      if (m.symbol === A.live.pe) { const el = $("lv_pe"); if (el) el.textContent = fmt(m.ltp); }
    }
  }

  // ------------------------------------------------------------------ link to the desk program
  const send = m => { if (ws && ws.readyState === 1) ws.send(JSON.stringify(m)); };
  const sendView = () => { store.set("view2", view); send(Object.assign({ op: "view" }, view)); };
  function connect() {
    ws = new WebSocket(`ws://${location.host}/ws?k=${encodeURIComponent(window.DESK_KEY)}`);
    ws.onopen = () => { $("status").textContent = "connected"; send({ op: "login_info" }); };
    ws.onclose = () => { $("status").textContent = "reconnecting..."; setTimeout(connect, 1500); };
    ws.onmessage = ev => {
      const m = JSON.parse(ev.data);
      if (m.type === "tick") onTick(m);
      else if (m.type === "bars") { if (m.index === view.index) renderBars(m); }
      else if (m.type === "bigtrade") onBig(m);
      else if (m.type === "analytics") { if (m.index === view.index) { renderAnalytics(m); $("status").textContent = "live · FYERS"; } }
      else if (m.type === "login") login(m);
      else if (m.type === "status") $("status").textContent = m.status;
      else if (m.type === "result") { if (!m.ok) { $("l_msg").textContent = m.msg; $("status").textContent = m.msg; } }
    };
  }
  function login(m) {
    if (m.logged_in) { $("login").style.display = "none"; sendView(); return; }
    $("login").style.display = "flex";
    $("appbox").style.display = m.has_app ? "none" : "";
    $("loginbox2").style.display = m.has_app ? "" : "none";
    if (m.client_id) $("l_id").value = m.client_id;
    if (m.redirect) $("l_redirect").value = m.redirect;
    if (m.url) $("l_link").href = m.url;
    if (m.error) $("l_msg").textContent = m.error;
  }
  $("l_save").onclick = () => send({ op: "save_app", client_id: $("l_id").value, secret: $("l_secret").value, redirect: $("l_redirect").value });
  $("l_go").onclick = () => { $("l_msg").textContent = "checking with FYERS..."; send({ op: "authorize", url: $("l_url").value }); };

  // ------------------------------------------------------------------ controls
  $("index").onchange = () => { view.index = $("index").value; view.strike = null; renderBars.fitted = false; sendView(); };
  $("ctype").value = prefs.ctype || "candles";
  $("ctype").onchange = () => { prefs.ctype = $("ctype").value; store.set("prefs", prefs); if (B) renderBars(B); };
  $("tf").onchange = () => { view.tf = Number($("tf").value); renderBars.fitted = false; sendView(); };
  $("instrument").onchange = () => { view.instrument = $("instrument").value; renderBars.fitted = false; sendView(); };
  $("each").onchange = () => { view.each_side = Number($("each").value); sendView(); };
  $("strike").onchange = () => { view.strike = $("strike").value ? Number($("strike").value) : null; sendView(); };
  $("s_ema1").onchange = () => { view.ema1 = Number($("s_ema1").value) || 9; sendView(); };
  $("s_ema2").onchange = () => { view.ema2 = Number($("s_ema2").value) || 21; sendView(); };
  const savePrefs = () => { store.set("prefs", prefs); if (A) renderAnalytics(A); drawProfile(); };
  $("s_pw").onchange = () => { prefs.pw = Number($("s_pw").value) || 160; savePrefs(); };
  $("s_pv").onchange = () => { prefs.pv = $("s_pv").checked; savePrefs(); };
  $("s_align").onchange = () => { prefs.align = $("s_align").checked; savePrefs(); };
  $("explainer").onchange = () => { prefs.explainer = $("explainer").checked; savePrefs(); };
  $("greeks").onchange = () => { prefs.greeks = $("greeks").checked; savePrefs(); };
  $("opt_panel").onchange = () => { prefs.opt = $("opt_panel").checked; store.set("prefs", prefs); applyToggles(true); };
  setInterval(() => { $("clock").textContent = new Date().toLocaleString("en-IN", { timeZone: "Asia/Kolkata", hour12: false }) + " IST"; }, 1000);
  window.deskDebug = { profileY: k => candles.priceToCoordinate(k) };
  applyTheme(); applyToggles(true); connect();
})();
