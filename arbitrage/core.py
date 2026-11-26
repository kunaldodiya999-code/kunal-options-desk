"""The arbitrage maths on prices (no FYERS here, so every rule can be tested).

Reference price ("fair underlying") for an option expiring on day E:
  * same-expiry future exists (all stock options, index monthly options): the future itself;
  * index WEEKLY options (no future that day): index + (future - index) x time to E / time to the future's expiry
    (the carry for the shorter time).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from arbitrage.costs import Costs

THRESHOLD = 0.05          # owner: below 5% is useless
MIN_ITM = 0.02            # the option must be at least 2% in the money (else "intrinsic" is tiny and noisy)
BUCKETS = [(0.05, 0.10), (0.10, 0.15), (0.15, 0.20), (0.20, 0.30), (0.30, 0.50), (0.50, 10.0)]


def bucket_name(d: float) -> str:
    for lo, hi in BUCKETS:
        if lo <= d < hi:
            return f"{lo * 100:.0f}%+" if hi > 1 else f"{lo * 100:.0f}-{hi * 100:.0f}%"
    return "below 5%"


def carry_ref(spot: Optional[float], fut: float, t: int, opt_expiry_ts: int, fut_expiry_ts: int) -> float:
    if spot is None or fut_expiry_ts <= opt_expiry_ts:
        return fut
    left_fut = max(1, fut_expiry_ts - t)
    left_opt = max(0, opt_expiry_ts - t)
    return spot + (fut - spot) * left_opt / left_fut


def check(kind: str, strike: float, price: float, ref: float, units: int, costs: Costs, index: bool,
          threshold: float = THRESHOLD, min_itm: float = MIN_ITM) -> Optional[dict]:
    """One option price against the reference. Returns the opportunity (5%+ below intrinsic and a profit after
    every charge) or None."""
    if price is None or price <= 0 or ref is None or ref <= 0:
        return None
    intrinsic = (ref - strike) if kind == "CE" else (strike - ref)
    if intrinsic <= ref * min_itm:
        return None
    discount = (intrinsic - price) / intrinsic
    if discount < threshold:
        return None
    gross = (intrinsic - price) * units
    charges = costs.round_trip(price, intrinsic, ref, units)
    net = gross - charges
    if net <= 0:
        return None
    capital = costs.capital(price, ref, units, index)
    return {"kind": kind, "strike": strike, "price": round(price, 2), "ref": round(ref, 2),
            "intrinsic": round(intrinsic, 2), "discount": discount, "gross": gross, "charges": charges, "net": net,
            "capital": capital, "ret": net / capital if capital else 0.0, "bucket": bucket_name(discount)}


@dataclass
class Event:
    """Minutes in a row (gaps up to 2 minutes) where one option traded 5%+ below intrinsic."""
    underlying: str
    expiry: str
    kind: str
    strike: float
    start: int
    end: int
    minutes: int = 0
    lots_traded: float = 0.0
    sure: bool = False            # even the option's HIGH against the least favourable underlying of the minute
    best: dict = field(default_factory=dict)

    def as_row(self) -> dict:
        b = self.best
        return {"underlying": self.underlying, "expiry": self.expiry, "option": f"{self.strike:g} {self.kind}",
                "start": self.start, "end": self.end, "minutes": self.minutes, "lots_traded": round(self.lots_traded, 1),
                "sure": self.sure, "discount": round(b["discount"] * 100, 2), "bucket": b["bucket"],
                "price": b["price"], "fair": b["intrinsic"], "ref": b["ref"], "net_per_lot": round(b["net"], 0),
                "charges_per_lot": round(b["charges"], 0), "capital_per_lot": round(b["capital"], 0),
                "return_pct": round(b["ret"] * 100, 2)}


def scan_option(underlying: str, expiry: str, kind: str, strike: float, candles: list, refs: dict, units: int,
                costs: Costs, index: bool, volume_in_lots: bool = False, threshold: float = THRESHOLD) -> list[Event]:
    """candles: option 1-minute (ts, o, h, l, c, v); refs: ts -> (low, close, high) of the reference that minute.
    Only minutes in which the option really TRADED count (volume > 0)."""
    events: list[Event] = []
    cur: Optional[Event] = None
    for c in candles:
        ts, h, close, vol = c[0], c[2], c[4], c[5]
        r = refs.get(ts)
        if not vol or r is None:
            continue
        lo, rc, hi = r
        hit = check(kind, strike, close, rc, units, costs, index, threshold)
        if not hit:
            continue
        worst_ref = lo if kind == "CE" else hi
        sure = check(kind, strike, h, worst_ref, units, costs, index, threshold) is not None
        lots = vol if volume_in_lots else vol / max(1, units)
        if cur and ts - cur.end <= 180:
            cur.end, cur.minutes = ts, cur.minutes + 1
        else:
            cur = Event(underlying, expiry, kind, strike, ts, ts)
            cur.minutes = 1
            events.append(cur)
        cur.lots_traded += lots
        cur.sure = cur.sure or sure
        if not cur.best or hit["net"] > cur.best["net"]:
            cur.best = hit
    return events


__all__ = ["BUCKETS", "Event", "MIN_ITM", "THRESHOLD", "bucket_name", "carry_ref", "check", "scan_option"]
