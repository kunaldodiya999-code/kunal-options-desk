"""One year (or any number of days) of option arbitrage, from FYERS 1-minute candles. Runs on the owner's PC.

For every expiry (newest first) and every underlying (NIFTY, BANK NIFTY, SENSEX, all F&O stocks):
  1. the reference: the same-expiry future (index weekly: index + carry from the monthly future), 1-minute;
  2. the in-the-money options worth checking (2% to 15% in the money for stocks, 2% to 6% for indexes);
  3. each option's 1-minute candles -> minutes where it TRADED 5%+ below its intrinsic value, after every charge.
Everything FYERS sends is kept in data/arbitrage/cache.sqlite, and every finished expiry is remembered, so the run
can be stopped (close the window) and started again: it carries on where it stopped.
"""

from __future__ import annotations

import json
import sqlite3
import time as _time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional

from arbitrage.core import MIN_ITM, Event, carry_ref, scan_option
from arbitrage.costs import Costs
from arbitrage.universe import (INDEX_NAMES, Underlying, find_dates, find_symbols, from_master, future_symbol, monthly,
                                option_prefix, option_symbol, strike_of, window)
from desk.candles import IST
from desk.fyers import RESERVE, Budget, is_daily_limit

DEPTH = {True: 0.06, False: 0.15}      # how far in the money to look (index, stock)
GAP = 0.34                              # seconds between FYERS calls (about 3 a second: safe under 5/s and 200/min)


class Stop(Exception):
    pass


class Cache:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=60)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS answer (key TEXT PRIMARY KEY, body TEXT);
            CREATE TABLE IF NOT EXISTS done (underlying TEXT, expiry TEXT, status TEXT, options INTEGER,
                                             with_data INTEGER, events TEXT, PRIMARY KEY (underlying, expiry));""")

    def get(self, key: str) -> Optional[Any]:
        row = self.db.execute("SELECT body FROM answer WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, key: str, value: Any) -> None:
        self.db.execute("INSERT OR REPLACE INTO answer VALUES (?, ?)", (key, json.dumps(value)))
        self.db.commit()

    def is_done(self, u: str, e: date) -> bool:
        return self.db.execute("SELECT 1 FROM done WHERE underlying=? AND expiry=?", (u, e.isoformat())).fetchone() \
            is not None

    def finish(self, u: str, e: date, status: str, options: int, with_data: int, events: list[Event]) -> None:
        self.db.execute("INSERT OR REPLACE INTO done VALUES (?, ?, ?, ?, ?, ?)",
                        (u, e.isoformat(), status, options, with_data, json.dumps([x.as_row() for x in events])))
        self.db.commit()

    def results(self) -> list[dict]:
        rows = self.db.execute("SELECT underlying, expiry, status, options, with_data, events FROM done").fetchall()
        return [{"underlying": a, "expiry": b, "status": c, "options": d, "with_data": e, "events": json.loads(f)}
                for a, b, c, d, e, f in rows]


class Fetcher:
    """Every FYERS call: paced, retried on 'too many requests', counted, answers cached."""

    def __init__(self, model: Any, cache: Cache, today: date, *, max_calls: int = 4000,
                 log: Callable[[str], Any] = print, gap: float = GAP, sleep=_time.sleep,
                 use_budget: bool = True) -> None:
        self.model, self.cache, self.today, self.max_calls, self.log = model, cache, today, max_calls, log
        self.gap, self.sleep = gap, sleep
        self.use_budget = use_budget
        self.calls = 0
        self._last = 0.0

    def _call(self, fn, data: dict) -> Any:
        for attempt in range(6):
            if self.calls >= self.max_calls:
                raise Stop(f"reached {self.max_calls} FYERS calls for this run. "
                           "Run it again tomorrow: it carries on where it stopped.")
            if self.use_budget and Budget.left() <= RESERVE:
                raise Stop(f"only {Budget.left()} FYERS calls left today (FYERS allows 5,000 a day); keeping "
                           f"{RESERVE} for the desk. Run it again tomorrow: it carries on where it stopped.")
            wait = self.gap - (_time.monotonic() - self._last)
            if wait > 0:
                self.sleep(wait)
            self._last = _time.monotonic()
            self.calls += 1
            if self.use_budget:
                Budget.add()
            try:
                answer = fn(data)
            except Exception as exc:                       # network hiccup
                answer = {"s": "error", "message": str(exc)}
            if is_daily_limit(answer):
                if self.use_budget:
                    Budget.exhaust()
                raise Stop("FYERS says today's 5,000 calls are used up. Run it again tomorrow: it carries on where "
                           "it stopped.")
            text = str(answer)[:300].lower()
            if isinstance(answer, dict) and answer.get("s") != "ok" and ("limit" in text or "-429" in text or
                                                                         "too many" in text):
                self.log(f"   FYERS says too many requests: waiting {5 * (attempt + 1)} s")
                self.sleep(5 * (attempt + 1))
                self.gap = min(1.0, self.gap + 0.05)
                continue
            if isinstance(answer, dict) and any(w in text for w in ("authenticat", "token", "'code': -16",
                                                                     "'code': -15", "'code': -8,")):
                raise Stop("the FYERS login is not valid any more. Log in again (start_desk.bat), then run this again.")
            return answer
        return {"s": "error", "message": "too many requests, gave up"}

    def candles(self, symbol: str, start: date, end: date, expired: bool) -> list[list]:
        key = f"c|{symbol}|{start}|{end}"
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        data = {"symbol": symbol, "resolution": "1", "date_format": "1", "range_from": start.isoformat(),
                "range_to": end.isoformat()}
        if expired:
            answer = self._call(self.model.fno_historical_data, {**data, "include_oi": "0", "include_greeks": "0"})
        else:
            answer = self._call(lambda d: self.model.history(data=d), {**data, "cont_flag": "1"})
        rows = []
        if isinstance(answer, dict) and answer.get("s") in ("ok", "no_data"):
            for r in answer.get("candles") or []:
                if isinstance(r, (list, tuple)) and len(r) >= 6:
                    rows.append([int(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5] or 0)])
        rows.sort()
        # keep today's still-open day out of the cache (it is not finished)
        if not (end >= self.today):
            self.cache.put(key, rows)
        return rows

    def expiries(self, spot: str, start: date) -> set[date]:
        key = f"e|{spot}|{start}|{self.today}"
        hit = self.cache.get(key)
        if hit is not None:
            return {date.fromisoformat(x) for x in hit}
        found: set[date] = set()
        frm = start
        while frm <= self.today:                      # FYERS answers in pieces of a few months at most
            to = min(self.today, frm + timedelta(days=89))
            answer = self._call(lambda d: self.model.expiry_dates(data=d),
                                {"symbol": spot, "range_from": frm.isoformat(), "range_to": to.isoformat(),
                                 "date_format": "1"})
            found |= {d for d in find_dates(answer) if start <= d <= self.today}
            frm = to + timedelta(days=1)
        self.cache.put(key, sorted(x.isoformat() for x in found))
        return found

    def expired_symbols(self, u: Underlying, expiry: date) -> list[str]:
        key = f"s|{u.name}|{expiry}"
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        answer = self._call(lambda d: self.model.history_underlying_symbols(data=d),
                            {"symbol": u.spot, "expiry_date": expiry.isoformat()})
        syms = sorted(find_symbols(answer, f"{u.exchange}:{u.name}"))
        self.cache.put(key, syms)
        return syms


def ref_table(fut: list[list], spot: Optional[list[list]], opt_exp_ts: int, fut_exp_ts: int) -> dict:
    """ts -> (low, close, high) of the reference for each minute."""
    out = {}
    if spot is None:
        for ts, o, h, l, c, v in fut:
            out[ts] = (l, c, h)
        return out
    fut_by = {r[0]: r for r in fut}
    for ts, o, h, l, c, v in spot:
        f = fut_by.get(ts)
        if f is None:
            continue
        ref = carry_ref(c, f[4], ts, opt_exp_ts, fut_exp_ts)
        basis = ref - c
        out[ts] = (l + basis, ref, h + basis)
    return out


def rule_expiries(start: date, end: date) -> set[date]:
    """NSE weekly expiry days by rule (only when FYERS cannot list them): Thursday, Tuesday from 1 Sep 2025."""
    out, d = set(), start
    while d <= end:
        if d.weekday() == (1 if d >= date(2025, 9, 1) else 3):
            out.add(d)
        d += timedelta(days=1)
    return out


def close_ts(d: date) -> int:
    return int(datetime.combine(d, datetime.min.time(), IST).replace(hour=15, minute=30).timestamp())


class Runner:
    def __init__(self, fetcher: Fetcher, universe: dict[str, Underlying], costs: Costs, *, days: int = 365,
                 log: Callable[[str], Any] = print) -> None:
        self.f, self.u, self.costs, self.days, self.log = fetcher, universe, costs, days, log
        self.today = fetcher.today
        self.start = self.today - timedelta(days=days)

    # ------------------------------------------------------------------ expiries
    def expiry_lists(self) -> dict[str, list[date]]:
        lists: dict[str, list[date]] = {}
        for name in ("NIFTY", "SENSEX"):
            if name not in self.u:
                continue
            got = self.f.expiries(self.u[name].spot, self.start) | {e for e in self.u[name].current if e <= self.today}
            lists[name] = sorted(got)
        if "NIFTY" in lists and len(lists["NIFTY"]) < 4:
            self.log("FYERS did not list past NIFTY expiries: using the NSE calendar rule instead "
                     "(Thursday until Aug 2025, Tuesday from Sep 2025; holiday weeks may be missed)")
            lists["NIFTY"] = sorted(set(lists["NIFTY"]) | rule_expiries(self.start, self.today))
        nse_monthly = monthly(lists.get("NIFTY", []))
        for name, und in self.u.items():
            if name not in lists:
                lists[name] = nse_monthly                     # stocks and BANK NIFTY: NSE monthly expiries
        return lists

    def jobs(self, only: Optional[set] = None, indexes: bool = True, stocks: bool = True) -> list[tuple]:
        lists = self.expiry_lists()
        out = []
        for name, und in self.u.items():
            if only and name not in only:
                continue
            if (und.index and not indexes) or (not und.index and not stocks):
                continue
            exps = [e for e in lists.get(name, []) if e >= self.start]
            all_exps = lists.get(name, [])
            months = set(monthly(all_exps))
            for e in exps:
                i = all_exps.index(e)
                prev = all_exps[i - 1] if i else None
                fut_exp = e if e in months else next((m for m in sorted(months) if m >= e), None)
                out.append((e, not und.index, name, prev, e in months, fut_exp))
        out.sort(key=lambda j: (-j[0].toordinal(), j[1], j[2]))   # newest first, indexes first
        return [(name, e, prev, is_monthly, fut_exp) for e, _, name, prev, is_monthly, fut_exp in out]

    # ------------------------------------------------------------------ one expiry of one underlying
    def run_job(self, name: str, expiry: date, prev: Optional[date], is_monthly: bool,
                fut_exp: Optional[date]) -> tuple[str, int, int, list[Event]]:
        u = self.u[name]
        start, end = window(expiry, prev, 35 if is_monthly else 8)
        end = min(end, self.today)
        if fut_exp is None:
            return "no monthly future found", 0, 0, []
        fut_sym = u.futures.get(fut_exp) or future_symbol(u, fut_exp)
        fut = self.f.candles(fut_sym, start, end, expired=fut_exp < self.today)
        if not fut:
            return f"no candles for the future {fut_sym}", 0, 0, []
        spot = None
        if fut_exp != expiry:
            spot = self.f.candles(u.spot, start, end, expired=False)
            if not spot:
                return f"no candles for {u.spot}", 0, 0, []
        refs = ref_table(fut, spot, close_ts(expiry), close_ts(fut_exp))
        if not refs:
            return "no reference prices", 0, 0, []
        lo = min(r[0] for r in refs.values())
        hi = max(r[2] for r in refs.values())
        depth = DEPTH[u.index]
        want = lambda kind, k: (lo * (1 - depth) <= k <= hi * (1 - MIN_ITM)) if kind == "CE" else \
            (lo * (1 + MIN_ITM) <= k <= hi * (1 + depth))
        symbols: dict[tuple[float, str], str] = {}
        if expiry >= self.today and expiry in u.current:
            symbols = {key: s for key, s in u.current[expiry].items()}
        else:
            prefixes = (option_prefix(u, expiry, is_monthly), option_prefix(u, expiry, not is_monthly))
            for s in self.f.expired_symbols(u, expiry):
                kind = s[-2:]
                pre = next((p for p in prefixes if s.startswith(p)), None)
                if pre is None:                           # another expiry's contract in FYERS' answer
                    continue
                k = strike_of(s, kind, pre)
                if k is not None:
                    symbols[(k, kind)] = s
            if not symbols and u.step:                   # FYERS could not list them: build the names on today's gap
                k = (lo * (1 - depth) // u.step) * u.step
                while k <= hi * (1 + depth):
                    for kind in ("CE", "PE"):
                        symbols[(k, kind)] = option_symbol(u, expiry, k, kind, is_monthly)
                    k += u.step
        chosen = {key: s for key, s in symbols.items() if want(key[1], key[0])}
        events: list[Event] = []
        with_data = 0
        for (k, kind), sym in sorted(chosen.items()):
            rows = self.f.candles(sym, start, end, expired=expiry < self.today)
            if not rows:
                continue
            with_data += 1
            vols = [r[5] for r in rows if r[5]]
            in_lots = bool(vols) and u.lot > 1 and any(v % u.lot for v in vols)
            events += scan_option(name, expiry.isoformat(), kind, k, rows, refs, u.lot, self.costs, u.index,
                                  volume_in_lots=in_lots)
        return "ok", len(chosen), with_data, events

    def run(self, jobs: list[tuple], cache: Cache) -> int:
        todo = [j for j in jobs if not cache.is_done(j[0], j[1]) or j[1] >= self.today]
        self.log(f"{len(jobs)} expiry x underlying pieces in the last {self.days} days; {len(jobs) - len(todo)} done "
                 f"before, {len(todo)} to do now.")
        t0 = _time.monotonic()
        for n, (name, expiry, prev, is_monthly, fut_exp) in enumerate(todo, 1):
            status, options, with_data, events = self.run_job(name, expiry, prev, is_monthly, fut_exp)
            if expiry < self.today:                       # the running series is scanned again next time
                cache.finish(name, expiry, status, options, with_data, events)
            else:
                cache.finish(name, expiry, status + " (series still running)", options, with_data, events)
            took = _time.monotonic() - t0
            left = took / n * (len(todo) - n)
            self.log(f"[{n}/{len(todo)}] {name} {expiry}: {status}, {with_data}/{options} options had data, "
                     f"{len(events)} events. FYERS calls {self.f.calls}. About {left / 3600:.1f} h left.")
        return len(todo)


__all__ = ["Cache", "Fetcher", "Runner", "Stop", "ref_table"]
