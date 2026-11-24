"""The option chain: FYERS answer -> one Snapshot (prices, OI, OI change, Greeks per strike), saved every minute.

Readings (last N minutes, per strike and side), the video's rule of thumb:
  buying     OI up,   premium up        writing    OI up,   premium down
  covering   OI down, premium up        unwinding  OI down, premium down
It is inferred from price and OI; who actually traded is never known.
OI is shown in LOTS. FYERS gives quantity: when every OI is a multiple of the lot size it is divided by it.
"""

from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Optional

from desk.black76 import greeks, implied_forward, implied_vol
from desk.candles import IST

READINGS = ("buying", "writing", "covering", "unwinding")


def _num(v) -> Optional[float]:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


@dataclass
class Leg:
    symbol: str = ""
    ltp: Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    oi: float = 0.0                 # lots
    oi_change: float = 0.0          # lots, since the previous day's close (FYERS oich)
    volume: float = 0.0             # lots traded today
    ltp_change: Optional[float] = None   # premium change since the previous close
    iv: Optional[float] = None
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None


@dataclass
class Row:
    strike: float
    call: Leg = field(default_factory=Leg)
    put: Leg = field(default_factory=Leg)


@dataclass
class Snapshot:
    ts: int                          # epoch seconds
    index: str
    spot: Optional[float]
    forward: Optional[float]         # implied by the options (put-call parity at the ATM strike)
    atm: Optional[float]
    expiry: Optional[str]            # ISO date
    years: float                     # time to expiry (calendar years)
    lot_size: int
    rows: list[Row]

    def row(self, strike: float) -> Optional[Row]:
        return next((r for r in self.rows if r.strike == strike), None)

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @staticmethod
    def from_json(text: str) -> "Snapshot":
        d = json.loads(text)
        rows = [Row(r["strike"], Leg(**r["call"]), Leg(**r["put"])) for r in d.pop("rows")]
        return Snapshot(**d, rows=rows)


def expiry_close(expiry: date) -> datetime:
    return datetime.combine(expiry, time(15, 30), IST)


def _expiry_from(data: dict) -> Optional[date]:
    for e in data.get("expiryData") or []:
        if e.get("expiry"):
            try:
                return datetime.fromtimestamp(int(e["expiry"]), IST).date()
            except (TypeError, ValueError):
                pass
        if e.get("date"):
            for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d %b %Y"):
                try:
                    return datetime.strptime(str(e["date"]), fmt).date()
                except ValueError:
                    pass
    return None


def parse(answer: Any, *, index: str, lot_size: int, now: datetime) -> Snapshot:
    data = answer.get("data") if isinstance(answer, dict) else None
    if not isinstance(data, dict) or not isinstance(data.get("optionsChain"), list):
        raise ValueError(f"FYERS sent no option chain: {str(answer)[:200]}")
    rows: dict[float, Row] = {}
    spot = None
    for it in data["optionsChain"]:
        kind = str(it.get("option_type") or "").upper()
        k = _num(it.get("strike_price"))
        if kind not in ("CE", "PE") or not k or k <= 0:
            spot = _num(it.get("ltp")) or spot
            continue
        oi = _num(it.get("oi")) or 0.0
        ch = _num(it.get("oich"))
        if ch is None and _num(it.get("prev_oi")) is not None:
            ch = oi - _num(it.get("prev_oi"))
        leg = Leg(str(it.get("symbol") or ""), _num(it.get("ltp")), _num(it.get("bid")), _num(it.get("ask")), oi,
                  ch or 0.0, _num(it.get("volume")) or 0.0, _num(it.get("ltpch")))
        r = rows.setdefault(k, Row(k))
        if kind == "CE":
            r.call = leg
        else:
            r.put = leg
    ordered = [rows[k] for k in sorted(rows)]
    # quantity -> lots when FYERS sent quantities
    ois = [x for r in ordered for x in (r.call.oi, r.put.oi) if x]
    if lot_size > 1 and ois and all(abs(x / lot_size - round(x / lot_size)) < 1e-9 for x in ois):
        for r in ordered:
            for leg in (r.call, r.put):
                leg.oi, leg.oi_change, leg.volume = leg.oi / lot_size, leg.oi_change / lot_size, leg.volume / lot_size
    exp = _expiry_from(data)
    years = max((expiry_close(exp) - now).total_seconds(), 60) / (365 * 86400) if exp else 7 / 365
    snap = Snapshot(int(now.timestamp()), index, spot, None, None, exp.isoformat() if exp else None, years,
                    lot_size, ordered)
    add_greeks(snap)
    return snap


def add_greeks(snap: Snapshot) -> None:
    priced = [r for r in snap.rows if r.call.ltp and r.put.ltp]
    if not priced:
        return
    ref = snap.spot or priced[len(priced) // 2].strike
    atm = min(priced, key=lambda r: abs(r.call.ltp - r.put.ltp) if r.call.ltp and r.put.ltp else 1e18)
    nearest = min(priced, key=lambda r: abs(r.strike - ref))
    atm = atm if abs(atm.strike - nearest.strike) <= 2 * _step(snap) else nearest
    fwd = implied_forward(atm.strike, atm.call.ltp, atm.put.ltp)
    snap.forward = round(fwd, 2)
    snap.atm = min((r.strike for r in snap.rows), key=lambda k: (abs(k - fwd), k))
    for r in snap.rows:
        for leg, call in ((r.call, True), (r.put, False)):
            if not leg.ltp:
                continue
            iv = implied_vol(leg.ltp, fwd, r.strike, snap.years, call)
            if iv is None:
                continue
            g = greeks(fwd, r.strike, snap.years, iv, call)
            leg.iv, leg.delta, leg.gamma, leg.theta, leg.vega = g.iv, g.delta, g.gamma, g.theta, g.vega


def _step(snap: Snapshot) -> float:
    ks = [r.strike for r in snap.rows]
    return min((b - a for a, b in zip(ks, ks[1:])), default=50.0)


def reading(oi_change: float, premium_change: Optional[float]) -> str:
    if not oi_change or premium_change is None or premium_change == 0:
        return "·"
    if oi_change > 0:
        return "buying" if premium_change > 0 else "writing"
    return "covering" if premium_change > 0 else "unwinding"


# ------------------------------------------------------------------ minute store
class SnapshotStore:
    """One snapshot per minute per index, in data/chain_<date>.sqlite (kept on the PC, never in git)."""

    def __init__(self, folder: Path) -> None:
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self._mem: dict[tuple[str, int], Snapshot] = {}

    def _db(self, day: date) -> sqlite3.Connection:
        db = sqlite3.connect(self.folder / f"chain_{day.isoformat()}.sqlite", timeout=30)
        db.execute("CREATE TABLE IF NOT EXISTS snap (idx TEXT, minute INTEGER, body TEXT, PRIMARY KEY (idx, minute))")
        return db

    def put(self, snap: Snapshot) -> None:
        minute = snap.ts // 60 * 60
        self._mem[(snap.index, minute)] = snap
        db = self._db(datetime.fromtimestamp(snap.ts, IST).date())
        try:
            with db:
                db.execute("INSERT OR REPLACE INTO snap VALUES (?,?,?)", (snap.index, minute, snap.to_json()))
        finally:
            db.close()

    def at(self, index: str, ts: int) -> Optional[Snapshot]:
        """The last snapshot at or before ``ts`` on that day."""
        minute = ts // 60 * 60
        for m in range(minute, minute - 45 * 60, -60):
            if (index, m) in self._mem:
                return self._mem[(index, m)]
        db = self._db(datetime.fromtimestamp(ts, IST).date())
        try:
            row = db.execute("SELECT body FROM snap WHERE idx=? AND minute<=? ORDER BY minute DESC LIMIT 1",
                             (index, minute)).fetchone()
        finally:
            db.close()
        return Snapshot.from_json(row[0]) if row else None

    def first(self, index: str, day: date) -> Optional[Snapshot]:
        db = self._db(day)
        try:
            row = db.execute("SELECT body FROM snap WHERE idx=? ORDER BY minute LIMIT 1", (index,)).fetchone()
        finally:
            db.close()
        return Snapshot.from_json(row[0]) if row else None

    def series(self, index: str, day: date) -> list[Snapshot]:
        db = self._db(day)
        try:
            rows = db.execute("SELECT body FROM snap WHERE idx=? ORDER BY minute", (index,)).fetchall()
        finally:
            db.close()
        return [Snapshot.from_json(r[0]) for r in rows]


def changes(now: Snapshot, before: Optional[Snapshot]) -> dict[tuple[float, str], dict]:
    """(strike, 'call'/'put') -> {'oi': lots added, 'premium': premium change, 'reading'} versus ``before``."""
    out = {}
    for r in now.rows:
        old = before.row(r.strike) if before else None
        for side in ("call", "put"):
            leg = getattr(r, side)
            prev = getattr(old, side) if old else None
            d_oi = leg.oi - prev.oi if prev else 0.0
            d_px = (leg.ltp - prev.ltp) if prev and leg.ltp is not None and prev.ltp is not None else None
            out[(r.strike, side)] = {"oi": d_oi, "premium": d_px, "reading": reading(d_oi, d_px)}
    return out


__all__ = ["Leg", "READINGS", "Row", "Snapshot", "SnapshotStore", "add_greeks", "changes", "expiry_close", "parse",
           "reading"]
