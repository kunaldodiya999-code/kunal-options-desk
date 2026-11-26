"""Live option arbitrage scanner (market hours). Information only: it never places an order.

Every sweep (about a minute for all F&O stocks + NIFTY / BANK NIFTY / SENSEX at FYERS' 5 requests a second):
  * quotes of every near-month future and the 3 indexes;
  * quotes (best bid / ask) of every option 2%-15% in the money (indexes 2%-6%), nearest expiry;
  * CALL: what you PAY = the option's ASK, the future you SELL at its BID; PUT: option ASK, future bought at its ASK;
  * 5%+ below value after every charge -> on screen (with a beep), data/arbitrage/live_hits.csv, live.html.
"""

from __future__ import annotations

import csv
import html
import time as _time
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Callable, Optional

from arbitrage.core import MIN_ITM, carry_ref, check
from arbitrage.costs import Costs
from arbitrage.history import DEPTH, close_ts
from arbitrage.universe import Underlying, monthly
from desk.candles import IST
from desk.fyers import RESERVE, Budget, DailyLimit


def market_open(now: datetime) -> bool:
    return now.weekday() < 5 and time(9, 15) <= now.time() <= time(15, 30)


def plan(universe: dict[str, Underlying], today: date) -> list[dict]:
    """Per underlying: nearest option expiry, its option symbols, the future used as reference."""
    out = []
    for name, u in universe.items():
        exps = sorted(e for e in u.current if e >= today)
        futs = sorted(e for e in u.futures if e >= today)
        if not exps or not futs:
            continue
        e = exps[0]
        fe = next((f for f in futs if f >= e), futs[0])
        out.append({"u": u, "expiry": e, "fut_expiry": fe, "future": u.futures[fe], "chain": u.current[e]})
    return out


def sweep(client: Any, jobs: list[dict], costs: Costs, now: datetime, threshold: float = 0.05) -> tuple[list, int]:
    """One pass over the market. Returns (hits, options checked)."""
    base = [j["future"] for j in jobs] + [j["u"].spot for j in jobs if j["u"].index]
    q = client.quotes(base)
    wanted: dict[str, tuple] = {}
    for j in jobs:
        f = q.get(j["future"])
        if not f:
            continue
        u, mid = j["u"], f["ltp"]
        depth = DEPTH[u.index]
        for (k, kind), sym in j["chain"].items():
            ok = (mid * (1 - depth) <= k <= mid * (1 - MIN_ITM)) if kind == "CE" else \
                (mid * (1 + MIN_ITM) <= k <= mid * (1 + depth))
            if ok:
                wanted[sym] = (j, k, kind)
    oq = client.quotes(list(wanted))
    hits = []
    t = int(now.timestamp())
    for sym, (j, k, kind) in wanted.items():
        o = oq.get(sym)
        f = q.get(j["future"])
        if not o or not f or o.get("ask", 0) <= 0:
            continue
        u = j["u"]
        fut_px = (f.get("bid") or f["ltp"]) if kind == "CE" else (f.get("ask") or f["ltp"])
        spot = q.get(u.spot, {}).get("ltp") if j["fut_expiry"] != j["expiry"] else None
        ref = carry_ref(spot, fut_px, t, close_ts(j["expiry"]), close_ts(j["fut_expiry"]))
        hit = check(kind, k, o["ask"], ref, u.lot, costs, u.index, threshold)
        if hit:
            hit.update(time=now.strftime("%H:%M:%S"), underlying=u.name, symbol=sym, expiry=j["expiry"].isoformat(),
                       future=j["future"], future_px=fut_px, bid=o.get("bid"), ltp=o.get("ltp"), lot=u.lot)
            hits.append(hit)
    hits.sort(key=lambda h: -h["net"])
    return hits, len(wanted)


def write_page(path: Path, hits_today: list[dict], status: str) -> None:
    cols = ["time", "underlying", "symbol", "discount", "price", "intrinsic", "future_px", "lot", "net", "capital", "ret"]
    def cell(h, c):
        v = h[c]
        if c in ("discount", "ret"):
            return f"{v * 100:.1f}%"
        if c in ("net", "capital"):
            return f"Rs {v:,.0f}"
        return html.escape(str(v))
    rows = "".join("<tr>" + "".join(f"<td>{cell(h, c)}</td>" for c in cols) + "</tr>" for h in hits_today[-300:][::-1])
    path.write_text(f"""<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="refresh" content="15">
<title>Option arbitrage live</title><style>body{{font:13px Segoe UI,sans-serif;margin:20px;background:#131722;color:#d1d4dc}}
table{{border-collapse:collapse}}td,th{{padding:4px 9px;border-bottom:1px solid #2a2e39;text-align:right}}th{{color:#868993}}
.s{{color:#868993}}</style></head><body><h2>Option arbitrage: live scanner</h2><p class="s">{html.escape(status)}</p>
<p class="s">Price = the option's ASK (what you would pay). Value = future - strike (calls) or strike - future (puts),
with the future at the price you would trade it. Net = after every charge, per lot. Information only: no orders.</p>
<table><tr>{''.join(f'<th>{c}</th>' for c in cols)}</tr>{rows or '<tr><td colspan=11>Nothing 5% or more yet today.</td></tr>'}
</table></body></html>""", encoding="utf-8")


def run(client: Any, load_universe: Callable[[date], dict], folder: Path, costs: Costs, *,
        clock: Callable[[], datetime] = lambda: datetime.now(IST), log: Callable[[str], Any] = print,
        sweeps: Optional[int] = None, sleep=_time.sleep, allowance: int = 1500) -> None:
    """allowance = FYERS calls this scanner may use in a day (FYERS allows 5,000 for everything). The pause between
    sweeps is worked out from it: about 120 calls a sweep -> roughly one sweep every 30 minutes."""
    folder.mkdir(parents=True, exist_ok=True)
    page, hits_csv = folder / "live.html", folder / "live_hits.csv"
    seen: dict[str, float] = {}
    today_hits: list[dict] = []
    day, jobs, n = None, [], 0
    while sweeps is None or n < sweeps:
        now = clock()
        if not market_open(now):
            write_page(page, today_hits, f"{now:%d %b %H:%M:%S}: market closed. Scanning runs 09:15-15:30 on weekdays.")
            if sweeps is not None:
                return
            sleep(30)
            continue
        if day != now.date():
            day, today_hits, seen = now.date(), [], {}
            jobs = plan(load_universe(day), day)
            log(f"{len(jobs)} underlyings to scan today")
        if Budget.left() <= RESERVE:
            write_page(page, today_hits, f"{now:%d %b %H:%M:%S}: stopped for today - only {Budget.left()} FYERS calls "
                                         f"left (FYERS allows 5,000 a day; {RESERVE} kept for the desk).")
            if sweeps is not None:
                return
            sleep(300)
            continue
        t0 = _time.monotonic()
        before = Budget.used()
        try:
            hits, checked = sweep(client, jobs, costs, now)
        except DailyLimit as exc:
            write_page(page, today_hits, f"{now:%d %b %H:%M:%S}: {exc}")
            if sweeps is not None:
                return
            sleep(600)
            continue
        cost = max(1, Budget.used() - before)
        n += 1
        new = []
        for h in hits:
            key = h["symbol"]
            if seen.get(key, 0) < h["discount"] - 0.005 or key not in seen:    # new, or noticeably bigger
                seen[key] = h["discount"]
                new.append(h)
        if new:
            exists = hits_csv.exists()
            with open(hits_csv, "a", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=list(new[0].keys()), extrasaction="ignore")
                if not exists:
                    w.writeheader()
                w.writerows(new)
            today_hits += new
            for h in new:
                log(f"\a{h['time']} {h['symbol']}: {h['discount'] * 100:.1f}% below value - pay {h['price']} for "
                    f"{h['intrinsic']}, net Rs {h['net']:,.0f} per lot ({h['ret'] * 100:.1f}% on Rs {h['capital']:,.0f})")
        status = (f"{now:%d %b %H:%M:%S}: sweep {n} checked {checked} options in {_time.monotonic() - t0:.0f} s; "
                  f"{len(hits)} at 5%+ now, {len(today_hits)} found today")
        sweeps_per_day = max(1, allowance // cost)
        pause = max(60.0, 375 * 60 / sweeps_per_day - (_time.monotonic() - t0))
        status += f"; next sweep in {pause / 60:.0f} min (this sweep used {cost} of the day's FYERS calls)"
        write_page(page, today_hits, status)
        log(status)
        if sweeps is None or n < sweeps:
            sleep(pause)


__all__ = ["market_open", "plan", "run", "sweep", "write_page"]
