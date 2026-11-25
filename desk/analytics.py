"""What the option chain says, section by section (the video's panels), from minute snapshots.

Everything here is a rule of thumb applied to the numbers - not a tested signal - and open interest never says who
traded. Every function returns plain dicts/lists, ready to send to the page.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from desk.black76 import greeks
from desk.candles import IST
from desk.chain import Row, Snapshot, changes, reading

BULL = {("put", "writing"), ("call", "covering"), ("call", "buying"), ("put", "unwinding")}
BEAR = {("call", "writing"), ("put", "covering"), ("put", "buying"), ("call", "unwinding")}


def lakh(x: float) -> str:
    a = abs(x)
    s = f"{a / 1e7:.2f} Cr" if a >= 1e7 else f"{a / 1e5:.2f} L" if a >= 1e5 else f"{a / 1e3:.1f}K" if a >= 1e3 \
        else f"{a:.0f}"
    return ("-" if x < 0 else "") + s


def near(snap: Snapshot, each_side: int) -> list[Row]:
    if snap.atm is None:
        return snap.rows
    ks = [r.strike for r in snap.rows]
    i = min(range(len(ks)), key=lambda j: abs(ks[j] - snap.atm))
    return snap.rows[max(0, i - each_side): i + each_side + 1]


def atm_row(snap: Snapshot) -> Optional[Row]:
    return snap.row(snap.atm) if snap.atm is not None else None


def straddle(snap: Optional[Snapshot]) -> Optional[float]:
    r = atm_row(snap) if snap else None
    return round(r.call.ltp + r.put.ltp, 2) if r and r.call.ltp and r.put.ltp else None


def atm_iv(snap: Optional[Snapshot]) -> Optional[float]:
    r = atm_row(snap) if snap else None
    ivs = [x for x in (r.call.iv, r.put.iv) if x] if r else []
    return sum(ivs) / len(ivs) if ivs else None


# ------------------------------------------------------------------ summary strip
def summary(snap: Snapshot, now: datetime) -> dict:
    calls = sum(r.call.oi for r in snap.rows)
    puts = sum(r.put.oi for r in snap.rows)
    price = snap.forward or snap.spot or 0
    above = [r for r in snap.rows if r.strike > price]
    below = [r for r in snap.rows if r.strike < price]
    call_wall = max(above, key=lambda r: r.call.oi).strike if above else None
    put_wall = max(below, key=lambda r: r.put.oi).strike if below else None
    exp = snap.years * 365 * 24
    return {"pcr": round(puts / calls, 2) if calls else None,
            "call_oi_today": sum(r.call.oi_change for r in snap.rows),
            "put_oi_today": sum(r.put.oi_change for r in snap.rows),
            "call_wall": call_wall, "put_wall": put_wall,
            "call_wall_oi": snap.row(call_wall).call.oi if call_wall else None,
            "put_wall_oi": snap.row(put_wall).put.oi if put_wall else None,
            "atm_iv": atm_iv(snap), "straddle": straddle(snap),
            "hours_to_expiry": round(exp, 1), "forward": snap.forward, "spot": snap.spot, "atm": snap.atm}


# ------------------------------------------------------------------ option chain table
LABELS = {("call", "buying"): "Call Buying", ("call", "writing"): "Call Writing", ("call", "covering"): "Short Cov",
          ("call", "unwinding"): "Long Unwind", ("put", "buying"): "Put Buying", ("put", "writing"): "Put Writing",
          ("put", "covering"): "Short Cov", ("put", "unwinding"): "Long Unwind"}
RUN = 3        # owner: 3 or more strikes in a row showing Short Cov -> arrow on each of them


def chain_table(snap: Snapshot, before15: Optional[Snapshot], each_side: int,
                week_base: Optional[dict] = None) -> list[dict]:
    """One row per strike near ATM. Per side: OI, Week (vs the previous expiry's close), Day, 15 min, reading
    (Call Buying / Call Writing / Short Cov / Long Unwind ...), DEX, GEX, IV, delta, theta, price.

    DEX = delta x OI (lots of the index the open options amount to; puts negative).
    GEX = gamma x OI x lot x price^2 x 1% (rupees of index the hedgers trade for a 1% move).
    Short Cov on 3+ strikes in a row: calls -> arrow UP (call writers buying back, bullish), puts -> arrow DOWN."""
    ch15 = changes(snap, before15) if before15 else {}
    price = snap.forward or snap.spot or 0.0
    out = []
    for r in near(snap, each_side):
        row = {"strike": r.strike, "atm": r.strike == snap.atm}
        for side in ("call", "put"):
            leg = getattr(r, side)
            c = ch15.get((r.strike, side), {})
            rd = c.get("reading", "·")
            base = (week_base or {}).get(f"{r.strike:g}|{side}")
            row[side] = {"oi": leg.oi, "week": (leg.oi - base) if base is not None else None, "day": leg.oi_change,
                         "m15": c.get("oi") if before15 else None, "reading": rd,
                         "label": LABELS.get((side, rd), "·"), "arrow": None,
                         "dex": (leg.delta * leg.oi) if leg.delta is not None else None,
                         "gex": (leg.gamma * leg.oi * snap.lot_size * price * price * 0.01)
                         if leg.gamma is not None and price else None,
                         "iv": leg.iv, "delta": leg.delta, "theta": leg.theta, "gamma": leg.gamma, "vega": leg.vega,
                         "price": leg.ltp, "symbol": leg.symbol, "premium15": c.get("premium")}
        out.append(row)
    for side, arrow in (("call", "up"), ("put", "down")):
        i = 0
        while i < len(out):
            j = i
            while j < len(out) and out[j][side]["reading"] == "covering":
                j += 1
            if j - i >= RUN:
                for k in range(i, j):
                    out[k][side]["arrow"] = arrow
            i = max(j, i + 1)
    return out


# ------------------------------------------------------------------ what the options are saying
def _lean(groups: dict) -> tuple[str, float, float]:
    bull = sum(v for k, v in groups.items() if k in BULL)
    bear = sum(v for k, v in groups.items() if k in BEAR)
    if bull > 1.2 * bear and bull > 0:
        return "BULLISH", bull, bear
    if bear > 1.2 * bull and bear > 0:
        return "BEARISH", bull, bear
    return "MIXED", bull, bear


def _groups(rows: list, side_readings) -> dict:
    g: dict = {}
    for side, rd, lots in side_readings:
        if rd in ("buying", "writing", "covering", "unwinding"):
            g[(side, rd)] = g.get((side, rd), 0.0) + abs(lots)
    return g


def _describe(title: str, lean: str, n: int, atm: float, g: dict, oi_c: float, oi_p: float) -> dict:
    parts = []
    for side, rd, word in (("call", "writing", "calls written"), ("call", "buying", "calls bought"),
                           ("call", "covering", "call writers covering"), ("call", "unwinding", "call buyers leaving"),
                           ("put", "writing", "puts written"), ("put", "buying", "puts bought"),
                           ("put", "covering", "put writers covering"), ("put", "unwinding", "put buyers leaving")):
        if g.get((side, rd)):
            parts.append(f"{word} {lakh(g[(side, rd)])} lots")
    side_txt = {"BULLISH": "The larger changes are on the bullish side: puts being written, calls being bought, "
                           "or call writers covering.",
                "BEARISH": "The larger changes are on the bearish side: calls being written, puts being bought, "
                           "or put writers covering.",
                "MIXED": "Bullish and bearish changes are about the same size."}[lean]
    text = (f"{n} strikes around {atm:,.0f}: " + "; ".join(parts or ["no clear change"]) +
            f". Call OI {'+' if oi_c >= 0 else ''}{lakh(oi_c)} lots, put OI {'+' if oi_p >= 0 else ''}{lakh(oi_p)} "
            f"lots. " + side_txt)
    return {"title": f"{title}: LEANS {lean}", "tone": lean.lower(), "text": text}


def options_saying(snap: Snapshot, before15: Optional[Snapshot], each_side: int = 5) -> dict:
    rows = near(snap, each_side)
    n = len(rows)
    cards = []
    ch15 = changes(snap, before15) if before15 else {}
    g15 = _groups(rows, [(s, ch15.get((r.strike, s), {}).get("reading"), ch15.get((r.strike, s), {}).get("oi", 0))
                         for r in rows for s in ("call", "put")])
    lean15, _, _ = _lean(g15)
    gday = _groups(rows, [(s, reading(getattr(r, s).oi_change, getattr(r, s).ltp_change), getattr(r, s).oi_change)
                          for r in rows for s in ("call", "put")])
    leanday, _, _ = _lean(gday)
    c15 = sum(ch15.get((r.strike, "call"), {}).get("oi", 0) for r in rows)
    p15 = sum(ch15.get((r.strike, "put"), {}).get("oi", 0) for r in rows)
    cards.append(_describe("Last 15 minutes", lean15, n, snap.atm or 0, g15, c15, p15) if before15 else
                 {"title": "Last 15 minutes: not enough history yet", "tone": "mixed",
                  "text": "The 15-minute view fills in once the desk has been running for 15 minutes."})
    cday_oi = sum(r.call.oi_change for r in rows)
    pday_oi = sum(r.put.oi_change for r in rows)
    cards.append(_describe("Since yesterday's close", leanday, n, snap.atm or 0, gday, cday_oi, pday_oi))
    overall = lean15 if (lean15 == leanday or not before15) else "MIXED"
    agree = ("both the last 15 minutes and the day agree" if before15 and lean15 == leanday else
             "the last 15 minutes and the day disagree" if before15 else "from the day's changes only")
    if cday_oi > 0 and pday_oi > 0:
        cards.append({"title": "Both call and put OI are building", "tone": "neutral",
                      "text": "New positions are being opened in both calls and puts, so there is no one-sided "
                              "pattern. If most of it is writing (see the readings), the market is being sold as a "
                              "range, and a break of either wall would trap one side."})
    calls = sum(r.call.oi for r in snap.rows)
    puts = sum(r.put.oi for r in snap.rows)
    prev_c = sum(r.call.oi - r.call.oi_change for r in snap.rows)
    prev_p = sum(r.put.oi - r.put.oi_change for r in snap.rows)
    if calls and prev_c:
        pcr, pcr0 = puts / calls, (prev_p / prev_c if prev_c else None)
        rising = pcr0 is not None and pcr > pcr0
        cards.append({"title": f"Put/call ratio {pcr:.2f} (yesterday {pcr0:.2f})" if pcr0 else
                      f"Put/call ratio {pcr:.2f}", "tone": "bullish" if rising else "bearish",
                      "text": "It is rising: put writing is growing faster than call writing (supportive)." if rising
                      else "It is falling: call writing is growing faster than put writing (capping)."})
    s = summary(snap, datetime.now(IST))
    for side, key, word, where in (("call", "call_wall", "Most call OI above the price", "resistance"),
                                   ("put", "put_wall", "Most put OI below the price", "support")):
        k = s[key]
        if k is None:
            continue
        leg = getattr(snap.row(k), side)
        d15 = ch15.get((k, side), {}).get("oi") if before15 else None
        pct = (d15 / (leg.oi - d15) * 100) if d15 is not None and leg.oi - d15 else None
        state = ("reinforced" if pct and pct > 1 else "thinning" if pct and pct < -1 else "steady")
        dist = abs(k - (snap.forward or k))
        cards.append({"title": f"{word}: {k:,.0f}", "tone": "neutral",
                      "text": f"{k:,.0f}, {dist:,.0f} points {'above' if side == 'call' else 'below'} the price, "
                              f"with {lakh(leg.oi)} lots. Writers there are defending it as {where}. "
                              + (f"Its OI {'rose' if pct >= 0 else 'fell'} {abs(pct):.0f}% in 15 minutes: the wall "
                                 f"is {state}." if pct is not None else "")})
    a = atm_row(snap)
    if a and a.call.delta is not None and a.put.delta is not None:
        st = straddle(snap) or 0
        iv_now, iv_then = atm_iv(snap), atm_iv(before15)
        if iv_now:
            dv = (iv_now - iv_then) * 100 if iv_then else None
            cards.append({"title": f"Implied volatility {iv_now * 100:.1f}%" + (
                f", {'up' if dv > 0.3 else 'down' if dv < -0.3 else 'steady'} over 15 minutes" if dv is not None
                else ""), "tone": "neutral",
                "text": f"The options price in a move of about {st:,.0f} points by expiry. Vega: each point of "
                        f"implied volatility is worth about {a.call.vega:.1f} points on an ATM option "
                        f"(Rs {a.call.vega * snap.lot_size:,.0f} a lot)."})
        cards.append({"title": f"Expected range to expiry: {a.strike - st:,.0f} to {a.strike + st:,.0f}",
                      "tone": "neutral",
                      "text": f"The {a.strike:,.0f} straddle costs {st:.1f}. Its buyers need price beyond these two "
                              "levels to profit; writers keep it all if it stays inside."})
        cards.append({"title": f"Delta: call {a.call.delta:.2f}, put {a.put.delta:.2f}", "tone": "neutral",
                      "text": f"The {a.strike:,.0f} call moves about {abs(a.call.delta) * 10:.1f} points for every "
                              f"10 points on the index; the put about {abs(a.put.delta) * 10:.1f}."})
        hour = abs(a.call.theta or 0) / 24
        cards.append({"title": f"Theta: about {hour:.1f} points an hour on the ATM call", "tone": "bearish",
                      "text": f"If price and volatility stand still for the next hour, the call loses about "
                              f"{hour:.1f} points (Rs {hour * snap.lot_size:,.0f} a lot, "
                              f"{hour / (a.call.ltp or 1) * 100:.0f}% of its price). Time works against buyers."})
        move = abs(a.call.gamma or 0) * 50
        risk = "HIGH" if move >= 0.2 else "MEDIUM" if move >= 0.1 else "LOW"
        hrs = snap.years * 365 * 24
        cards.append({"title": f"Gamma blast risk: {risk} ({hrs:.0f} hours to expiry)",
                      "tone": "bearish" if risk == "HIGH" else "neutral",
                      "text": f"A 50-point move changes the ATM delta by about {move:.2f}. Premiums speed up "
                              f"noticeably on a move of 100 points or more. The levels where writers start to hurt "
                              f"are {a.strike + st:,.0f} above and {a.strike - st:,.0f} below."})
    return {"lean": overall, "agree": agree, "cards": cards}


# ------------------------------------------------------------------ option maths
def _bem(snap: Optional[Snapshot]) -> dict:
    a = atm_row(snap) if snap else None
    if not a or a.call.theta is None or a.put.theta is None or not a.call.delta or not a.put.delta:
        return {}
    th = abs(a.call.theta) + abs(a.put.theta)
    gm = (a.call.gamma or 0) + (a.put.gamma or 0)
    return {"straddle_bem": math.sqrt(2 * th / gm) if gm else None,
            "call_bem": abs(a.call.theta) / abs(a.call.delta), "put_bem": abs(a.put.theta) / abs(a.put.delta),
            "d_theta_c": abs(a.call.delta) / abs(a.call.theta), "d_theta_p": abs(a.put.delta) / abs(a.put.theta),
            "g_theta": (a.call.gamma or 0) / abs(a.call.theta), "v_theta": (a.call.vega or 0) / abs(a.call.theta),
            "delta_c": a.call.delta, "delta_p": a.put.delta, "theta_c": a.call.theta, "theta_p": a.put.theta,
            "gamma": a.call.gamma, "vega": a.call.vega, "iv": atm_iv(snap), "straddle": straddle(snap)}


def _straddle_story(now: Snapshot, then: Optional[Snapshot], label: str) -> Optional[dict]:
    if not then:
        return None
    k = now.atm
    a, b = now.row(k), then.row(k)
    if not a or not b or not (a.call.ltp and a.put.ltp and b.call.ltp and b.put.ltp):
        return None
    p_now, p_then = a.call.ltp + a.put.ltp, b.call.ltp + b.put.ltp
    oi_now, oi_then = a.call.oi + a.put.oi, b.call.oi + b.put.oi
    rd = reading(oi_now - oi_then, p_now - p_then)
    word = {"writing": "being WRITTEN", "buying": "being BOUGHT", "covering": "writers COVERING",
            "unwinding": "buyers LEAVING"}.get(rd, "quiet")
    meaning = {"writing": "New positions are being sold at this strike while the premium falls. Writers are backing "
                          "a range, and they are the side with the bigger book here.",
               "buying": "New positions are being bought while the premium rises: buyers expect a move.",
               "covering": "Writers are closing while the premium rises: they are buying back in a hurry.",
               "unwinding": "Buyers are closing while the premium falls: they are giving up."}.get(rd, "")
    return {"title": f"The {k:,.0f} straddle, {label}: {word}", "tone": "bearish" if rd == "writing" else "neutral",
            "text": f"{p_then:.1f} → {p_now:.1f} ({(p_now / p_then - 1) * 100:+.1f}%), open interest "
                    f"{'+' if oi_now >= oi_then else ''}{lakh(oi_now - oi_then)} lots "
                    f"({(oi_now / oi_then - 1) * 100 if oi_then else 0:+.1f}%). {meaning}"}


def option_maths(snap: Snapshot, before15: Optional[Snapshot], at_open: Optional[Snapshot],
                 avg_daily_move: Optional[float], sessions: int = 4) -> dict:
    now, m15, op = _bem(snap), _bem(before15), _bem(at_open)
    cards = [c for c in (_straddle_story(snap, at_open, "since the open"),
                         _straddle_story(snap, before15, "in the last 15 minutes")) if c]
    if now.get("straddle_bem"):
        edge = ""
        if avg_daily_move:
            edge = (f" Over the last {sessions} sessions the index has actually moved {avg_daily_move:,.0f} points "
                    f"a day on average, so {'WRITING' if avg_daily_move < now['straddle_bem'] else 'BUYING'} has "
                    f"had the edge.")
        cards.append({"title": f"Break-even move: {now['straddle_bem']:,.0f} points a day", "tone": "bearish",
                      "text": f"An option buyer at the {snap.atm:,.0f} strike needs the index to move about "
                              f"{now['straddle_bem']:,.0f} points in a day, either way, just to cover one day of "
                              f"time decay. A call buyer needs {now['call_bem']:,.0f} points up; a put buyer needs "
                              f"{now['put_bem']:,.0f} points down." + edge})
        cards.append({"title": f"Delta per point of decay: call {now['d_theta_c']:.3f}, put {now['d_theta_p']:.3f}",
                      "tone": "neutral",
                      "text": "For every point of premium the clock takes each day, this is the movement per index "
                              "point you get back. Higher = a directional view is worth more against the cost of "
                              "waiting."})
        cards.append({"title": f"Gamma per point of decay: {now['g_theta']:.5f}", "tone": "neutral",
                      "text": "How much delta the call picks up per index point, for each point of decay paid. High "
                              "numbers make a fast move pay for a buyer; low numbers mean the clock wins."})
        cards.append({"title": f"Vega per point of decay: {now['v_theta']:.2f}", "tone": "neutral",
                      "text": f"A 1-point rise in implied volatility is worth about {now['vega']:.1f} points on the "
                              f"call (Rs {now['vega'] * snap.lot_size:,.0f} a lot), against "
                              f"{abs(now['theta_c']):.1f} points lost per day."})

    def row(name, key, fmt, meaning, pair=None):
        def f(d):
            if not d or d.get(key) is None:
                return "-"
            return fmt(d[key]) if pair is None else f"call {fmt(d[key])} · put {fmt(d[pair])}"
        return {"measure": name, "now": f(now), "m15": f(m15), "open": f(op), "meaning": meaning}

    pts = lambda x: f"{x:,.0f} pts/day"
    table = [
        row("Break-even move, straddle", "straddle_bem", pts, "How far the index must move in a day, either way, "
            "to pay for one day of decay."),
        row("Break-even move, call", "call_bem", pts, "How far it must rise in a day for a call buyer to stand still."),
        row("Break-even move, put", "put_bem", pts, "How far it must fall in a day for a put buyer to stand still."),
        row("Delta ÷ theta", "d_theta_c", lambda x: f"{x:.3f}", "Movement per index point against one point of "
            "daily decay. Higher favours a directional buyer.", "d_theta_p"),
        row("Gamma ÷ theta", "g_theta", lambda x: f"{x:.5f}", "How much delta is picked up per index point, per "
            "point of decay. Higher means a fast move pays quickly."),
        row("Vega ÷ theta", "v_theta", lambda x: f"{x:.2f}", "What a 1-point rise in implied volatility pays against "
            "a day of decay. Matters before events."),
        row("Delta", "delta_c", lambda x: f"{x:.2f}", "Premium move per 1 index point.", "delta_p"),
        row("Theta, per day", "theta_c", lambda x: f"{x:.1f}", "Points of premium the clock takes each day.",
            "theta_p"),
        row("Gamma", "gamma", lambda x: f"{x:.5f}", "Delta gained per index point."),
        row("Vega", "vega", lambda x: f"{x:.2f}", "Points gained per 1 point of implied volatility."),
        row("Implied volatility", "iv", lambda x: f"{x * 100:.1f}%", "What the options are charging, in volatility "
            "terms."),
        row("Straddle", "straddle", lambda x: f"{x:.1f}", "Call plus put at the money."),
    ]
    return {"atm": snap.atm, "hours": round(snap.years * 365 * 24, 1), "avg_daily_move": avg_daily_move,
            "cards": cards, "table": table}


# ------------------------------------------------------------------ trapped positions
@dataclass
class Pocket:
    strike: float
    side: str                  # call / put
    who: str                   # buyers / writers
    lots: float = 0.0
    value: float = 0.0         # lots x premium paid / received
    biggest_add: float = 0.0
    biggest_ts: int = 0
    biggest_px: float = 0.0

    @property
    def built_at(self) -> float:
        return self.value / self.lots if self.lots else 0.0


@dataclass
class TrapBook:
    """Each minute's rise in OI is filed as buying or writing (premium up or down that minute) and remembered at
    that premium; a fall in OI takes lots out of both books in proportion. Comparing build prices with the price now
    shows which pockets are losing."""
    pockets: dict = field(default_factory=dict)

    def update(self, before: Snapshot, now: Snapshot) -> None:
        for (k, side), c in changes(now, before).items():
            leg = getattr(now.row(k), side)
            if leg.ltp is None or c["premium"] is None:
                continue
            if c["oi"] > 0 and c["premium"] != 0:
                who = "buyers" if c["premium"] > 0 else "writers"
                p = self.pockets.setdefault((k, side, who), Pocket(k, side, who))
                p.lots += c["oi"]
                p.value += c["oi"] * leg.ltp
                if c["oi"] > p.biggest_add:
                    p.biggest_add, p.biggest_ts, p.biggest_px = c["oi"], now.ts, leg.ltp
            elif c["oi"] < 0:
                books = [self.pockets[x] for x in ((k, side, "buyers"), (k, side, "writers")) if x in self.pockets]
                total = sum(b.lots for b in books)
                for b in books:
                    cut = min(b.lots, -c["oi"] * b.lots / total) if total else 0
                    price = b.built_at
                    b.lots -= cut
                    b.value = b.lots * price

    def report(self, snap: Snapshot, top: int = 8, min_lots: float = 1.0) -> dict:
        rows = []
        for p in self.pockets.values():
            r = snap.row(p.strike)
            leg = getattr(r, p.side) if r else None
            if not leg or leg.ltp is None or p.lots < min_lots or not p.built_at:
                continue
            diff = (p.built_at - leg.ltp) if p.who == "buyers" else (leg.ltp - p.built_at)
            if diff <= 0:
                continue
            rows.append({"strike": p.strike, "option": p.side.title(), "who": p.who, "lots": round(p.lots),
                         "built_at": round(p.built_at, 2), "now": leg.ltp, "under_water": diff / p.built_at,
                         "money": diff * p.lots * snap.lot_size, "biggest_ts": p.biggest_ts,
                         "biggest_px": p.biggest_px})
        rows.sort(key=lambda x: -x["money"])
        groups: dict = {}
        for x in rows:
            key = f"{x['option'].lower()} {x['who']}"
            groups[key] = groups.get(key, 0.0) + x["money"]
        worst = rows[0] if rows else None
        heavy = max(groups, key=groups.get) if groups else None
        total = sum(groups.values())
        cards = []
        if worst:
            cards.append({"title": f"Worst pocket: {worst['option'].lower()} {worst['who']} at {worst['strike']:,.0f}",
                          "text": f"{worst['lots']:,} lots were {'bought' if worst['who'] == 'buyers' else 'written'} "
                                  f"at an average of {worst['built_at']}; the option is now {worst['now']}, so that "
                                  f"side is {'down' if worst['who'] == 'buyers' else 'losing'} "
                                  f"{worst['under_water'] * 100:.0f}%, about Rs {lakh(worst['money'])}. If they give "
                                  f"up, their exit pushes price "
                                  f"{'down' if (worst['who'] == 'buyers') == (worst['option'] == 'Call') else 'up'}."})
        if heavy:
            cards.append({"title": f"Most money under water: {heavy}",
                          "text": f"Across all strikes, {heavy} are carrying the largest loss, about "
                                  f"Rs {lakh(groups[heavy])} of the Rs {lakh(total)} that is under water in total."})
        return {"pockets": len(rows), "total": total, "cards": cards, "rows": rows[:top]}


def replay(series: list[Snapshot]) -> TrapBook:
    book = TrapBook()
    for a, b in zip(series, series[1:]):
        book.update(a, b)
    return book


# ------------------------------------------------------------------ hedging pressure
def _book_delta(snap: Snapshot, fwd: float) -> float:
    """Writers' delta in lots at forward ``fwd`` (writers are short every open option: rule of thumb)."""
    total = 0.0
    for r in snap.rows:
        for leg, call in ((r.call, True), (r.put, False)):
            if leg.iv and leg.oi:
                total -= leg.oi * greeks(fwd, r.strike, snap.years, leg.iv, call).delta
    return total


def hedging(snap: Snapshot, move: float = 50.0) -> dict:
    f = snap.forward or snap.spot
    if not f:
        return {"rows": [], "cards": []}
    rows = []
    for r in snap.rows:
        g = (r.call.gamma or 0) * r.call.oi + (r.put.gamma or 0) * r.put.oi
        rows.append({"strike": r.strike, "lots": g * move})
    top = max((x["lots"] for x in rows), default=0) or 1
    for x in rows:
        x["share"] = x["lots"] / top
    now = _book_delta(snap, f)
    up = _book_delta(snap, f + move)
    dn = _book_delta(snap, f - move)
    buy_on_rise, sell_on_fall = now - up, dn - now
    heavy = max(rows, key=lambda x: x["lots"]) if rows else None
    cards = [{"title": f"A {move:.0f}-point move forces writers to trade {lakh(max(buy_on_rise, sell_on_fall))} lots",
              "text": f"If the index rises {move:.0f} points, the writers' hedging makes them BUY about "
                      f"{lakh(buy_on_rise)} lots of futures; if it falls {move:.0f}, they SELL about "
                      f"{lakh(sell_on_fall)} lots. "
                      + ("The two sides are close to even, so hedging is not pushing either way."
                         if abs(buy_on_rise - sell_on_fall) < 0.1 * max(buy_on_rise, sell_on_fall, 1)
                         else "The bigger side is where hedging adds fuel to the move.")}]
    if heavy:
        d = heavy["strike"] - f
        cards.append({"title": f"Hedging is heaviest at {heavy['strike']:,.0f}, {abs(d):,.0f} points "
                               f"{'above' if d > 0 else 'below'} the price",
                      "text": "This is the strike with the most gamma times open interest. Price tends to be drawn "
                              "to it and to move in smaller steps near it, because that is where writers are "
                              "re-hedging most often. A clean break away from it usually means faster movement."})
    cards.append({"title": f"Writers are carrying {lakh(abs(now))} lots of {'short' if now < 0 else 'long'} delta",
                  "text": f"Their book is {'short' if now < 0 else 'long'}, so a {'rise' if now < 0 else 'fall'} "
                          f"leaves them {'buying' if now < 0 else 'selling'} futures into it. This is their "
                          "exposure as it stands, not a forecast."})
    return {"heaviest": heavy["strike"] if heavy else None, "buy_on_rise": buy_on_rise,
            "sell_on_fall": sell_on_fall, "writers_delta": now, "rows": rows, "cards": cards}


# ------------------------------------------------------------------ OI marks for the chart
def oi_marks(series: list[Snapshot], window: int = 5, pct: float = 3.0, each_side: int = 2) -> list[dict]:
    """CALLS / PUTS ADDED or EXITING: near-the-money OI change over ``window`` minutes beyond ``pct`` %."""
    marks = []
    for i in range(window, len(series)):
        now, before = series[i], series[i - window]
        rows = near(now, each_side)
        for side, word in (("call", "CALLS"), ("put", "PUTS")):
            oi_now = sum(getattr(r, side).oi for r in rows)
            oi_then = sum(getattr(before.row(r.strike), side).oi for r in rows if before.row(r.strike))
            if not oi_then:
                continue
            ch = (oi_now / oi_then - 1) * 100
            if abs(ch) < pct:
                continue
            px_now = sum(getattr(r, side).ltp or 0 for r in rows)
            px_then = sum((getattr(before.row(r.strike), side).ltp or 0) for r in rows if before.row(r.strike))
            how = "being BOUGHT (premium rising)" if px_now > px_then else "being WRITTEN (premium falling)"
            if ch < 0:
                how = "being closed by writers (premium rising)" if px_now > px_then else \
                      "being closed by buyers (premium falling)"
            t = datetime.fromtimestamp(now.ts, IST).strftime("%H:%M")
            kind = f"{side}s_{'added' if ch > 0 else 'exiting'}"
            if marks and marks[-1]["kind"] == kind and now.ts - marks[-1]["ts"] < window * 60:
                continue
            marks.append({"ts": now.ts, "kind": kind,
                          "text": f"{t} {word} {'ADDED' if ch > 0 else 'EXITING'}: {side} OI near the money "
                                  f"{ch:+.1f}% in {window} minutes ({'+' if ch > 0 else ''}{lakh(oi_now - oi_then)} "
                                  f"lots), {how}. Price then {now.forward or now.spot:,.1f}."})
    return marks


__all__ = ["TrapBook", "atm_iv", "chain_table", "hedging", "lakh", "near", "oi_marks", "option_maths",
           "options_saying", "replay", "straddle", "summary"]
