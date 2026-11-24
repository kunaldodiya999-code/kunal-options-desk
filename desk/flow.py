"""Price-side studies for the chart (futures candles; the index has no volume, so futures volume is used).

Buying - selling (estimated): each candle's volume is split by where it CLOSED in its range:
  bull = volume x (close - low) / (high - low),  bear = volume - bull.
It is estimated from where each candle closed, not from real buy and sell orders (the tick-based version comes in
phase 2 from the recorded ticks).
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Optional, Sequence

from desk.candles import IST, Candle, local


def split_volume(c: Candle) -> tuple[float, float]:
    rng = c.high - c.low
    bull = c.volume * ((c.close - c.low) / rng if rng > 0 else 0.5)
    return bull, c.volume - bull


def ema(values: Sequence[float], length: int) -> list[Optional[float]]:
    out, k, cur = [], 2 / (length + 1), None
    for i, v in enumerate(values):
        if i + 1 < length:
            out.append(None)
            continue
        cur = sum(values[i + 1 - length:i + 1]) / length if cur is None else v * k + cur * (1 - k)
        out.append(cur)
    return out


def kama(values: Sequence[float], length: int = 10, fast: int = 2, slow: int = 30) -> list[Optional[float]]:
    """Kaufman adaptive average: fast when the series trends, slow when it chops ('adaptive average')."""
    fc, sc = 2 / (fast + 1), 2 / (slow + 1)
    out: list[Optional[float]] = []
    cur = None
    for i, v in enumerate(values):
        if i < length:
            out.append(None)
            cur = v
            continue
        change = abs(v - values[i - length])
        noise = sum(abs(values[j] - values[j - 1]) for j in range(i - length + 1, i + 1))
        er = change / noise if noise else 0.0
        a = (er * (fc - sc) + sc) ** 2
        cur = cur + a * (v - cur)
        out.append(cur)
    return out


def buy_sell(bars: Sequence[Candle]) -> dict:
    """Per candle: bull, bear, net; running net per day (resets each day); bull shares; adaptive average."""
    rows, run, day = [], 0.0, None
    for c in bars:
        d = local(c.ts).date()
        if d != day:
            day, run = d, 0.0
        b, s = split_volume(c)
        run += b - s
        rows.append({"time": c.ts, "bull": b, "bear": s, "net": b - s, "cum": run})
    cums = [r["cum"] for r in rows]
    avg = kama(cums)
    for r, a in zip(rows, avg):
        r["avg"] = a
    today = [r for r in rows if rows and local(r["time"]).date() == local(rows[-1]["time"]).date()]
    last20 = rows[-20:]
    share = lambda rs: (sum(r["bull"] for r in rs) / max(1e-9, sum(r["bull"] + r["bear"] for r in rs)))
    bull_day = sum(r["bull"] for r in today)
    bear_day = sum(r["bear"] for r in today)
    return {"rows": rows, "today": today[-1]["cum"] if today else 0.0, "this_candle": rows[-1]["net"] if rows else 0,
            "share_day": share(today) if today else None, "share_20": share(last20) if last20 else None,
            "ratio": bull_day / bear_day if bear_day else None,
            "avg": rows[-1]["avg"] if rows else None, "above_avg": bool(rows and rows[-1]["avg"] is not None and
                                                                      rows[-1]["cum"] > rows[-1]["avg"])}


def divergences(bars: Sequence[Candle], flow_rows: list[dict], lookback: int = 12) -> list[dict]:
    """BEARISH: price makes a new high of the last ``lookback`` candles but buying - selling does not follow (and the
    mirror image for BULLISH). Same-day candles only."""
    out = []
    for i in range(lookback, len(bars)):
        if local(bars[i].ts).date() != local(bars[i - lookback].ts).date():
            continue
        win = bars[i - lookback:i]
        cum = [r["cum"] for r in flow_rows[i - lookback:i]]
        t = local(bars[i].ts).strftime("%H:%M")
        if bars[i].high > max(b.high for b in win) and flow_rows[i]["cum"] < max(cum):
            out.append({"ts": bars[i].ts, "kind": "bearish_div",
                        "text": f"{t} BEARISH DIVERGENCE: price made a new high for the last {lookback} candles, but "
                                "buying minus selling did not follow. Buying is weakening. It is estimated from "
                                "where each candle closed in its range, not from real buy and sell orders."})
        elif bars[i].low < min(b.low for b in win) and flow_rows[i]["cum"] > min(cum):
            out.append({"ts": bars[i].ts, "kind": "bullish_div",
                        "text": f"{t} BULLISH DIVERGENCE: price made a new low for the last {lookback} candles, but "
                                "selling did not follow. Selling is weakening (estimated from candle closes)."})
    return out


def vwap(bars: Sequence[Candle]) -> list[Optional[float]]:
    out, day, pv, vol = [], None, 0.0, 0.0
    for c in bars:
        d = local(c.ts).date()
        if d != day:
            day, pv, vol = d, 0.0, 0.0
        if c.volume > 0:
            pv += (c.high + c.low + c.close) / 3 * c.volume
            vol += c.volume
        out.append(pv / vol if vol else None)
    return out


def day_levels(minutes: Sequence[Candle], today: date) -> dict:
    """Day's open, previous session high / low / close, first 30-minute range (from 1-minute candles)."""
    days = sorted({local(c.ts).date() for c in minutes})
    prev = [d for d in days if d < today]
    out: dict = {}
    if prev:
        p = [c for c in minutes if local(c.ts).date() == prev[-1]]
        out.update(prev_high=max(c.high for c in p), prev_low=min(c.low for c in p), prev_close=p[-1].close)
    t = [c for c in minutes if local(c.ts).date() == today]
    if t:
        out["open"] = t[0].open
        first = [c for c in t if local(c.ts).time() < time(9, 45)]
        if first:
            out.update(or_high=max(c.high for c in first), or_low=min(c.low for c in first))
    return out


def avg_daily_move(minutes: Sequence[Candle], today: date, sessions: int = 4) -> Optional[float]:
    """Average high-low range of the last ``sessions`` finished sessions (the video's 'moved 88 points a day')."""
    days = sorted({local(c.ts).date() for c in minutes if local(c.ts).date() < today})[-sessions:]
    ranges = []
    for d in days:
        cs = [c for c in minutes if local(c.ts).date() == d]
        ranges.append(max(c.high for c in cs) - min(c.low for c in cs))
    return sum(ranges) / len(ranges) if ranges else None


__all__ = ["avg_daily_move", "buy_sell", "day_levels", "divergences", "ema", "kama", "split_volume", "vwap"]
