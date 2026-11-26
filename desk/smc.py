"""Smart Money Concepts on the chart candles (owner 26 Nov 2026): our own simple, rule-based version.

  * swing highs / lows: a candle whose high (low) is the highest (lowest) of `length` candles on each side;
  * BOS (break of structure): a close beyond the last swing in the SAME direction as the trend;
    CHoCH (change of character): the first close beyond the last swing AGAINST the trend;
  * order block: the last opposite candle before the move that broke structure (bullish OB = last down candle
    before an up-break); it stays until price closes through it (mitigated);
  * fair value gap: three candles where candle 1's high and candle 3's low do not overlap (bullish) or the mirror;
    it stays until price trades back into it fully;
  * premium / discount: the range between the latest swing high and swing low; above 50% = premium,
    below = discount, 50% = equilibrium.
These are drawing aids, not signals.
"""

from __future__ import annotations

from typing import Sequence

from desk.candles import Candle


def smc(bars: Sequence[Candle], length: int = 5, keep: int = 3, fvg_keep: int = 4, max_ob: float = 0.006,
        min_gap: float = 0.0003) -> dict:
    n = len(bars)
    out = {"structure": [], "obs": [], "fvgs": [], "swings": [], "pd": None}
    if n < 2 * length + 3:
        return out
    hi_piv, lo_piv = [], []
    for i in range(length, n - length):
        win = bars[i - length:i + length + 1]
        if bars[i].high == max(c.high for c in win):
            hi_piv.append(i)
        if bars[i].low == min(c.low for c in win):
            lo_piv.append(i)
    trend = 0
    last_hi = last_lo = None            # (index, price, broken)
    hp = lp = 0
    obs: list[dict] = []
    for i in range(n):
        # a pivot is known only `length` candles after it
        while hp < len(hi_piv) and hi_piv[hp] + length <= i:
            last_hi = [hi_piv[hp], bars[hi_piv[hp]].high, False]
            out["swings"].append({"ts": bars[hi_piv[hp]].ts, "price": bars[hi_piv[hp]].high, "kind": "high"})
            hp += 1
        while lp < len(lo_piv) and lo_piv[lp] + length <= i:
            last_lo = [lo_piv[lp], bars[lo_piv[lp]].low, False]
            out["swings"].append({"ts": bars[lo_piv[lp]].ts, "price": bars[lo_piv[lp]].low, "kind": "low"})
            lp += 1
        c = bars[i]
        if last_hi and not last_hi[2] and c.close > last_hi[1]:
            kind = "CHoCH" if trend == -1 else "BOS"
            out["structure"].append({"kind": kind, "dir": "up", "price": last_hi[1], "from_ts": bars[last_hi[0]].ts,
                                     "to_ts": c.ts})
            start = last_lo[0] if last_lo and last_lo[0] < i else last_hi[0]
            downs = [j for j in range(start, i) if bars[j].close < bars[j].open]
            if downs and bars[downs[-1]].high - bars[downs[-1]].low <= c.close * max_ob:
                j = downs[-1]
                obs.append({"dir": "bull", "top": bars[j].high, "bottom": bars[j].low, "from_ts": bars[j].ts,
                            "end_ts": None})
            last_hi[2], trend = True, 1
        if last_lo and not last_lo[2] and c.close < last_lo[1]:
            kind = "CHoCH" if trend == 1 else "BOS"
            out["structure"].append({"kind": kind, "dir": "down", "price": last_lo[1], "from_ts": bars[last_lo[0]].ts,
                                     "to_ts": c.ts})
            start = last_hi[0] if last_hi and last_hi[0] < i else last_lo[0]
            ups = [j for j in range(start, i) if bars[j].close > bars[j].open]
            if ups and bars[ups[-1]].high - bars[ups[-1]].low <= c.close * max_ob:
                j = ups[-1]
                obs.append({"dir": "bear", "top": bars[j].high, "bottom": bars[j].low, "from_ts": bars[j].ts,
                            "end_ts": None})
            last_lo[2], trend = True, -1
        for ob in obs:                              # mitigation: a close through the block
            if ob["end_ts"] is None and c.ts > ob["from_ts"] and (
                    (ob["dir"] == "bull" and c.close < ob["bottom"]) or (ob["dir"] == "bear" and c.close > ob["top"])):
                ob["end_ts"] = c.ts
    recent = bars[-1].ts - (bars[-1].ts + 19800) % 86400 - 86400 * 3       # today and the last few sessions
    live = [o for o in obs if o["end_ts"] is None and o["from_ts"] >= recent]
    out["obs"] = [o for o in live if o["dir"] == "bull"][-keep:] + [o for o in live if o["dir"] == "bear"][-keep:]
    gaps = []
    for i in range(2, n):
        a, c = bars[i - 2], bars[i]
        for g in gaps:                              # filled: price traded all the way back through it
            if g["end_ts"] is None and ((g["dir"] == "bull" and c.low <= g["bottom"]) or
                                        (g["dir"] == "bear" and c.high >= g["top"])):
                g["end_ts"] = c.ts
        gap_size = c.close * min_gap
        if c.low - a.high > gap_size:
            gaps.append({"dir": "bull", "top": c.low, "bottom": a.high, "from_ts": bars[i - 1].ts, "end_ts": None})
        elif a.low - c.high > gap_size:
            gaps.append({"dir": "bear", "top": a.low, "bottom": c.high, "from_ts": bars[i - 1].ts, "end_ts": None})
    last_day = bars[-1].ts - (bars[-1].ts + 19800) % 86400           # today's gaps only (IST day)
    out["fvgs"] = [g for g in gaps if g["end_ts"] is None and g["from_ts"] >= last_day][-fvg_keep:]
    highs = [s for s in out["swings"] if s["kind"] == "high"]
    lows = [s for s in out["swings"] if s["kind"] == "low"]
    if highs and lows:
        h, l = highs[-1], lows[-1]
        top, bot = max(h["price"], bars[-1].high), min(l["price"], bars[-1].low)
        out["pd"] = {"top": top, "bottom": bot, "eq": (top + bot) / 2, "from_ts": min(h["ts"], l["ts"])}
    out["swings"] = out["swings"][-40:]
    out["structure"] = out["structure"][-20:]
    return out


__all__ = ["smc"]
