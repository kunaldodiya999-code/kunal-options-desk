"""A pretend market (NOT real prices) so the page can be seen and checked without FYERS:
  python run.py --demo
The clock runs 6x faster from 09:45 of the last weekday; prices are a fixed random walk, option prices come from
Black-76, open interest builds up at the strikes the price stays away from."""

from __future__ import annotations

import math
import random
import time as _time
from datetime import date, datetime, timedelta

from desk.black76 import price
from desk.candles import IST, Candle

STEP = 50.0
LOT = 65
FUT = "NSE:NIFTY26NOVFUT"
NEXT = "NSE:NIFTY26DECFUT"


def _last_weekday() -> date:
    d = datetime.now(IST).date()
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


class DemoClock:
    def __init__(self, speed: float = 6.0) -> None:
        self.day = _last_weekday()
        self.start = datetime.combine(self.day, datetime.min.time(), IST).replace(hour=9, minute=45)
        self.t0 = _time.monotonic()
        self.speed = speed

    def __call__(self) -> datetime:
        now = self.start + timedelta(seconds=(_time.monotonic() - self.t0) * self.speed)
        return min(now, now.replace(hour=15, minute=29))


class DemoFyers:
    """Answers like desk.fyers.Fyers for the calls the desk makes."""

    def __init__(self, clock: DemoClock, base: float = 25400.0) -> None:
        self.clock = clock
        self.base = base
        self.path: dict[int, float] = {}
        rnd = random.Random(7)
        start = datetime.combine(clock.day - timedelta(days=8), datetime.min.time(), IST)
        px, t = base - 180, int(start.timestamp())
        end = int(datetime.combine(clock.day, datetime.min.time(), IST).replace(hour=15, minute=30).timestamp())
        while t <= end:
            px += rnd.gauss(0.0, 5.0)
            self.path[t] = px
            t += 60

    def _px(self, ts: int) -> float:
        return self.path.get(ts - ts % 60, self.base)

    def minutes(self, symbol: str, start: date, end: date) -> list[Candle]:
        now = int(self.clock().timestamp())
        out = []
        d = start
        while d <= end:
            if d.weekday() < 5:
                t = int(datetime.combine(d, datetime.min.time(), IST).replace(hour=9, minute=15).timestamp())
                for i in range(375):
                    ts = t + i * 60
                    if ts > now - 60:
                        break
                    o, c = self._px(ts - 60), self._px(ts)
                    if symbol.endswith("CE") or symbol.endswith("PE"):
                        k = float(symbol[-7:-2])
                        o, c = self._opt(o, k, symbol.endswith("CE"), ts), self._opt(c, k, symbol.endswith("CE"), ts)
                    elif symbol.endswith("INDEX"):
                        o, c = o - 20, c - 20
                    elif symbol == NEXT:
                        o, c = o + 140, c + 140
                    hi, lo = max(o, c) * 1.0004, min(o, c) * 0.9996
                    vol = 0 if symbol.endswith("INDEX") else 4000 + (ts // 60 % 13) * 900
                    out.append(Candle(ts, o, hi, lo, c, vol))
            d += timedelta(days=1)
        return out

    def _opt(self, fwd: float, k: float, call: bool, ts: int) -> float:
        exp = datetime.combine(self.clock.day, datetime.min.time(), IST).replace(hour=15, minute=30)
        years = max(60.0, exp.timestamp() - ts) / (365 * 86400)
        return round(price(fwd, k, years, 0.13, call), 2)

    def daily_oi(self, symbol: str, start: date, end: date) -> list:
        """Pretend OI at each day's close: 60% of today's level a week ago (quantity, like FYERS)."""
        k = float(symbol[-7:-2])
        base = 3000 + 40 * abs(k - self.base) / STEP
        out, d = [], start
        while d <= end:
            if d.weekday() < 5:
                out.append((d, base * LOT))
            d += timedelta(days=1)
        return out

    def option_chain(self, symbol: str, strikes: int = 15) -> dict:
        now = self.clock()
        ts = int(now.timestamp())
        fwd = self._px(ts)
        atm = round(fwd / STEP) * STEP
        open_ts = int(now.replace(hour=9, minute=15, second=0, microsecond=0).timestamp())
        done = max(0.0, min(1.0, (ts - open_ts) / (375 * 60)))
        exp = now.replace(hour=15, minute=30, second=0, microsecond=0)
        rows = [{"option_type": "", "strike_price": -1, "ltp": fwd - 20, "symbol": "NSE:NIFTY50-INDEX"}]
        for i in range(-strikes, strikes + 1):
            k = atm + i * STEP
            for t in ("CE", "PE"):
                away = (k - fwd) if t == "CE" else (fwd - k)
                base = 4000 + 60000 * math.exp(-((away - 200) / 180) ** 2) if away > 0 else 3000 + 500 * abs(i)
                wave = 1 + 0.08 * math.sin(ts / 900 + k / 100)
                ch = base * 0.5 * done * wave
                oi = base + ch
                rows.append({"option_type": t, "strike_price": k, "symbol": f"NSE:NIFTY26N17{int(k)}{t}",
                             "ltp": self._opt(fwd, k, t == "CE", ts), "oi": int(oi) * LOT, "oich": int(ch) * LOT,
                             "volume": int(ch * 3) * LOT, "bid": 0, "ask": 0, "ltpch": None})
        return {"s": "ok", "data": {"optionsChain": rows, "expiryData": [
            {"date": exp.strftime("%d-%m-%Y"), "expiry": str(int(exp.replace(hour=0, minute=0).timestamp()))}]}}


def demo_master(clock: DemoClock):
    exp = int(datetime.combine(clock.day, datetime.min.time(), IST).timestamp())
    fut_exp = int(datetime.combine(clock.day + timedelta(days=10), datetime.min.time(), IST).timestamp())

    def loader(name: str, today: date) -> dict:
        m = {FUT: {"underSym": "NIFTY", "expiryDate": fut_exp, "symTicker": FUT},
             NEXT: {"underSym": "NIFTY", "expiryDate": fut_exp + 35 * 86400, "symTicker": NEXT}}
        for k in range(23000, 28001, 50):
            for t in ("CE", "PE"):
                s = f"NSE:NIFTY26N17{k}{t}"
                m[s] = {"underSym": "NIFTY", "expiryDate": exp, "symTicker": s, "optType": t, "strikePrice": k,
                        "minLotSize": LOT}
        return m
    return loader


__all__ = ["DemoClock", "DemoFyers", "demo_master"]
