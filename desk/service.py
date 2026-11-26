"""The options desk server: FYERS login, the data loop, and the fast link to the page (this PC only).

Loop (for the index on the screen):
  * every 10 s   FYERS option chain (nearest expiry, 20 strikes each side) -> Snapshot (one kept per minute on disk)
                 -> every panel's numbers -> pushed to the page;
  * every minute 1-minute candles of the futures, the index and the ATM call / put (FYERS history);
  * live         FYERS price websocket: futures, index, ATM call and put -> page + tick recorder (data/ticks).
The page talks to this program over a websocket on 127.0.0.1 with a secret key and an origin check.
"""

from __future__ import annotations

import asyncio
import json
import secrets
import socket
import threading
import time as _time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional

from desk.analytics import (TrapBook, chain_table, hedging, lakh, oi_marks, option_maths, options_saying, pricing,
                            realized_vol, summary)
from desk.candles import IST, Candle, local, resample
from desk.chain import Snapshot, SnapshotStore, parse
from desk.flow import (avg_daily_move, bollinger, buy_sell, day_levels, day_profile, divergences, ema, split_volume,
                       vwap, vwap_bands)
from desk.fyers import (INDEXES, Fyers, auth_code_from, clear_token, credentials, data_dir, exchange_code, load_master,
                        login_url, nearest_contracts, save_token, saved_token, write_env)

LOGIN_WORDS = ("token", "authenticat", "unauthor", "'code': -8,", "'code': -15,", "'code': -16,", "'code': -17,",
               "invalid app id")


def login_problem(exc: Exception) -> bool:
    """FYERS refused because the login (token) is no longer valid: the page must ask for a fresh login."""
    text = str(exc).lower()
    return any(w in text for w in LOGIN_WORDS)
from desk.bigtrades import BigTrades
from desk.smc import smc
from desk.ticks import TickRecorder

WEB = Path(__file__).resolve().parent / "web"
LIB = Path(__file__).resolve().parents[1] / "static" / "lightweight-charts" / "lightweight-charts.standalone.production.js"
CHAIN_EVERY = 10.0
CHAIN_STRIKES = 20


def free_port(start: int = 8800) -> int:
    for port in range(start, start + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError("no free port")


@dataclass
class View:
    index: str = "NIFTY"
    instrument: str = "INDEX"        # INDEX (spot, default: owner 25 Nov), FUT (near) or NEXT (next month)
    tf: int = 5
    each_side: int = 8
    ema1: int = 9
    ema2: int = 21
    strike: Optional[float] = None   # None = ATM (follows the price)


@dataclass
class Market:
    index: str
    lot: int = 1
    expiry: Optional[date] = None
    future: Optional[str] = None
    next_future: Optional[str] = None
    calls: dict = field(default_factory=dict)
    puts: dict = field(default_factory=dict)
    fut_min: list = field(default_factory=list)
    idx_min: list = field(default_factory=list)
    nxt_min: list = field(default_factory=list)       # next month's future (line on the spot chart)
    week_base: dict = field(default_factory=dict)     # "strike|side" -> OI (lots) at the previous expiry's close
    week_tried: set = field(default_factory=set)
    future_expiry: Optional[date] = None
    opt_min: dict = field(default_factory=dict)       # symbol -> [Candle]
    series: list = field(default_factory=list)        # minute snapshots of today (last one = latest)
    book: TrapBook = field(default_factory=TrapBook)
    leans: list = field(default_factory=list)         # (ts, lean)
    last: Optional[dict] = None


class DeskService:
    def __init__(self, *, folder: Optional[Path] = None, client: Any = None,
                 master_loader: Optional[Callable[[str, date], dict]] = None, start_feed: bool = True,
                 port: Optional[int] = None, clock: Callable[[], datetime] = lambda: datetime.now(IST)) -> None:
        self.folder = Path(folder or data_dir())
        self.key = secrets.token_urlsafe(18)
        self.port = port or free_port()
        self.clock = clock
        self.client = client
        self.master_loader = master_loader or (lambda name, d: load_master(name, d))
        self.start_feed = start_feed
        self.store = SnapshotStore(self.folder / "chain")
        self.ticks = TickRecorder(self.folder / "ticks")
        self.big = BigTrades(self.folder / "bigtrades")
        self.last_ltp: dict[str, float] = {}
        self.view = View()
        self.markets: dict[str, Market] = {}
        self.lock = threading.RLock()
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.queues: set = set()
        self.feed = None
        self.log: list[str] = []
        self.status = "waiting for login"
        self._next_bars = 0.0
        self._threads = False

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/?k={self.key}"

    def note(self, text: str) -> None:
        self.log = ([f"{self.clock():%H:%M:%S} {text}"] + self.log)[:60]

    # ------------------------------------------------------------------ login
    def try_saved_login(self) -> bool:
        creds = credentials()
        token = saved_token(self.folder, creds["client_id"])
        if self.client is None and creds["client_id"] and token:
            self.connect(creds["client_id"], token)
        return self.client is not None

    def connect(self, client_id: str, token: str) -> None:
        self.client = Fyers(client_id, token)
        if self.start_feed:
            from desk.feed import Feed
            self.feed = Feed(client_id=client_id, token=token, client=self.client, on_quote=self._on_tick,
                             log=self.note, log_path=str(self.folder / "logs"))
            self.feed.start()
        self.status = "connected"
        self.note("FYERS connected")

    def logout(self, why: str) -> None:
        """The FYERS login stopped working (new day, or logged out elsewhere): forget it and show the login box."""
        self.client = None
        if self.feed:
            self.feed.stop()
            self.feed = None
        clear_token(self.folder)
        self.markets.clear()
        self.status = "please log in to FYERS again"
        self.note(f"FYERS login no longer valid ({why[:120]}); please log in again")
        self.broadcast(self.login_info())

    def login_info(self) -> dict:
        c = credentials()
        info = {"type": "login", "logged_in": self.client is not None, "has_app": bool(c["client_id"]),
                "client_id": c["client_id"], "redirect": c["redirect_uri"]}
        if c["client_id"] and c["secret_key"] and self.client is None:
            try:
                info["url"] = login_url(c)
            except Exception as exc:
                info["error"] = f"login link: {exc}"
        return info

    def authorize(self, pasted: str) -> dict:
        c = credentials()
        token = exchange_code(c, auth_code_from(pasted))
        save_token(token, self.folder)
        self.connect(c["client_id"], token)
        return {"type": "result", "op": "authorize", "ok": True, "msg": "Logged in to FYERS"}

    # ------------------------------------------------------------------ market data
    def market(self, index: str) -> Market:
        if index not in self.markets:
            info = INDEXES[index]
            today = self.clock().date()
            c = nearest_contracts(self.master_loader(info.master, today), info.underlying, today)
            m = Market(index, c.lot_size, c.expiry, c.future, c.next_future, c.calls, c.puts)
            m.future_expiry = c.future_expiry
            m.week_base = self._load_week(index, c.expiry)
            m.series = self.store.series(index, today)
            for a, b in zip(m.series, m.series[1:]):
                m.book.update(a, b)
            self.markets[index] = m
            self.note(f"{info.label}: expiry {c.expiry}, lot {c.lot_size}, future {c.future}, "
                      f"{len(m.series)} saved minutes today")
        return self.markets[index]

    def refresh_chain(self, index: str) -> Snapshot:
        m = self.market(index)
        now = self.clock()
        snap = parse(self.client.option_chain(INDEXES[index].spot, CHAIN_STRIKES), index=index, lot_size=m.lot,
                     now=now)
        minute = snap.ts // 60
        if m.series and m.series[-1].ts // 60 == minute:
            m.series[-1] = snap
        else:
            if len(m.series) >= 2:
                m.book.update(m.series[-2], m.series[-1])          # the finished minute
            m.series.append(snap)
        self.store.put(snap)
        return snap

    def refresh_bars(self, index: str) -> None:
        m = self.market(index)
        today = self.clock().date()
        start = today - timedelta(days=6)
        info = INDEXES[index]
        if m.future:
            m.fut_min = self.client.minutes(m.future, start, today)
        m.idx_min = self.client.minutes(info.spot, start, today)
        if m.next_future:
            m.nxt_min = self.client.minutes(m.next_future, start, today)
        for sym in self.atm_symbols(index):
            if sym:
                m.opt_min[sym] = self.client.minutes(sym, today, today)

    # ------------------------------------------------------------------ Week column (OI since the series began)
    def week_file(self, index: str, expiry) -> Path:
        return self.folder / "week" / f"{index}_{expiry}.json"

    def _load_week(self, index: str, expiry) -> dict:
        try:
            return json.loads(self.week_file(index, expiry).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def fill_week(self, index: str, budget: int = 3) -> int:
        """OI at the close of the previous expiry (= expiry - 7 days, or the trading day before it) for the strikes
        on the screen, a few symbols per call (FYERS daily candles with OI), saved on the PC for the whole series."""
        m = self.market(index)
        snap = m.series[-1] if m.series else None
        if not snap or not m.expiry or not hasattr(self.client, "daily_oi"):
            return 0
        base_day = m.expiry - timedelta(days=7)
        wanted = []
        for r in chain_table(snap, None, self.view.each_side + 2):
            for side, book in (("call", m.calls), ("put", m.puts)):
                key = f"{r['strike']:g}|{side}"
                sym = book.get(r["strike"])
                if sym and key not in m.week_base and key not in m.week_tried:
                    wanted.append((key, sym))
        done = 0
        for key, sym in wanted[:budget]:
            m.week_tried.add(key)
            try:
                days = self.client.daily_oi(sym, base_day - timedelta(days=30), self.clock().date())
            except Exception as exc:
                if login_problem(exc):
                    raise
                if len(m.week_tried) <= budget:
                    self.note(f"Week column: FYERS daily OI not available ({str(exc)[:100]})")
                continue
            before = [oi for d, oi in days if d <= base_day]
            m.week_base[key] = (before[-1] if before else 0.0) / max(1, m.lot)
            done += 1
        if done:
            path = self.week_file(index, m.expiry)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(m.week_base), encoding="utf-8")
        return done

    def atm_symbols(self, index: str) -> tuple[Optional[str], Optional[str]]:
        m = self.market(index)
        snap = m.series[-1] if m.series else None
        k = self.view.strike or (snap.atm if snap else None)
        if k is None:
            return None, None
        return m.calls.get(k), m.puts.get(k)

    # ------------------------------------------------------------------ payloads
    def analytics(self, index: str) -> dict:
        m = self.market(index)
        if not m.series:
            return {"type": "analytics", "index": index, "empty": True}
        snap = m.series[-1]
        before15 = next((s for s in reversed(m.series) if s.ts <= snap.ts - 15 * 60), None)
        at_open = m.series[0]
        saying = options_saying(snap, before15)
        if not m.leans or m.leans[-1][1] != saying["lean"]:
            m.leans.append((snap.ts, saying["lean"]))
        traps = m.book.report(snap)
        hedge = hedging(snap)
        s = summary(snap, self.clock())
        avg_move = avg_daily_move(m.fut_min or m.idx_min, self.clock().date())
        marks = oi_marks(m.series)
        marks += [{"ts": ts, "kind": "lean", "text": f"{datetime.fromtimestamp(ts, IST):%H:%M} LEAN {lean}"}
                  for ts, lean in m.leans]
        marks += [{"ts": r["biggest_ts"], "kind": "trapped",
                   "text": f"{datetime.fromtimestamp(r['biggest_ts'], IST):%H:%M} TRAPPED: the biggest block of "
                           f"{r['option'].lower()} {r['who']} at {r['strike']:,.0f} was built around here, at about "
                           f"{r['biggest_px']}. It is now {r['now']}, so that side is "
                           f"{r['under_water'] * 100:.0f}% under water on what it "
                           f"{'paid' if r['who'] == 'buyers' else 'sold'}."}
                  for r in traps["rows"][:3] if r["biggest_ts"]]
        levels = []
        if s["call_wall"]:
            levels.append({"price": s["call_wall"], "kind": "call_wall",
                           "title": "call wall"})
        if s["put_wall"]:
            levels.append({"price": s["put_wall"], "kind": "put_wall", "title": "put wall"})
        if hedge.get("heaviest"):
            levels.append({"price": hedge["heaviest"], "kind": "hedging",
                           "title": f"heaviest hedging {hedge['heaviest']:,.0f}"})
        for r in traps["rows"][:4]:
            levels.append({"price": r["strike"], "kind": "trapped",
                           "title": f"trapped {r['option'].lower()} {r['who']} {r['lots']:,} lots, "
                                    f"{r['under_water'] * 100:.0f}% down"})
        ce, pe = self.atm_symbols(index)
        a = snap.row(snap.atm) if snap.atm else None
        px = snap.forward or snap.spot or 0.0
        out = {
            "type": "analytics", "index": index, "ts": snap.ts, "expiry": snap.expiry, "lot": m.lot,
            "summary": s, "saying": saying,
            "chain": chain_table(snap, before15, self.view.each_side, m.week_base),
            "week_from": (m.expiry - timedelta(days=7)).isoformat() if m.expiry else None,
            "trapped": traps, "maths": option_maths(snap, before15, at_open, avg_move), "hedging": hedge,
            "oi_series": [{"time": x.ts, "calls": sum(r.call.oi_change for r in x.rows),
                           "puts": sum(r.put.oi_change for r in x.rows)} for x in m.series],
            "profile": [{"strike": r.strike, "call_oi": r.call.oi, "put_oi": r.put.oi, "call_ch": r.call.oi_change,
                         "put_ch": r.put.oi_change,
                         "call_dex": (r.call.delta or 0) * r.call.oi, "put_dex": (r.put.delta or 0) * r.put.oi,
                         "call_gex": (r.call.gamma or 0) * r.call.oi * snap.lot_size * px * px * 0.01,
                         "put_gex": (r.put.gamma or 0) * r.put.oi * snap.lot_size * px * px * 0.01}
                        for r in snap.rows],
            "pricing": self._pricing(m, snap, at_open, saying["lean"]),
            "marks": sorted(marks, key=lambda x: x["ts"]), "levels": levels,
            "live": {"future": m.future, "atm": snap.atm, "ce": ce, "pe": pe,
                     "ce_ltp": a.call.ltp if a else None, "pe_ltp": a.put.ltp if a else None,
                     "forward": snap.forward, "spot": snap.spot},
            "history_minutes": len(m.series), "strikes_read": len(snap.rows), "log": self.log[:30],
        }
        m.last = out
        return out

    def _pricing(self, m: Market, snap: Snapshot, at_open: Snapshot, lean: str) -> dict:
        today = self.clock().date()
        idx_today = [c.close for c in m.idx_min if local(c.ts).date() == today][-61:]
        fut = m.fut_min[-1].close if m.fut_min else None
        spot = snap.spot or (m.idx_min[-1].close if m.idx_min else None)
        fexp = int(datetime.combine(m.future_expiry, datetime.min.time(), IST).replace(hour=15, minute=30).timestamp()) \
            if m.future_expiry else None
        try:
            return pricing(snap, fut_price=fut, spot=spot, fut_expiry_ts=fexp, at_open=at_open,
                           realized=realized_vol(idx_today), lean=lean, now_ts=snap.ts)
        except Exception as exc:                       # never let this box break the page
            return {"ready": False, "error": str(exc)[:120]}

    def bars(self, index: str) -> dict:
        m = self.market(index)
        v = self.view
        use_next = v.instrument == "NEXT" and bool(m.nxt_min)
        use_fut = use_next or (v.instrument == "FUT" and bool(m.fut_min)) or not m.idx_min
        mins = m.nxt_min if use_next else m.fut_min if use_fut else m.idx_min
        if not use_fut and m.fut_min:            # index has no volume: use the futures' (owner rule)
            fv = {c.ts: c.volume for c in m.fut_min}
            mins = [Candle(c.ts, c.open, c.high, c.low, c.close, fv.get(c.ts, 0.0)) for c in mins]
        bars = resample(mins, v.tf) if v.tf > 1 else [c for c in resample(mins, 1)]
        flow = buy_sell(bars)
        bull_pv = bear_pv = bull_v = bear_v = 0.0
        day = None
        bvw, svw = [], []
        for c, r in zip(bars, flow["rows"]):
            if local(c.ts).date() != day:
                day, bull_pv, bear_pv, bull_v, bear_v = local(c.ts).date(), 0.0, 0.0, 0.0, 0.0
            tp = (c.high + c.low + c.close) / 3
            bull_pv, bull_v = bull_pv + tp * r["bull"], bull_v + r["bull"]
            bear_pv, bear_v = bear_pv + tp * r["bear"], bear_v + r["bear"]
            bvw.append(bull_pv / bull_v if bull_v else None)
            svw.append(bear_pv / bear_v if bear_v else None)
        closes = [c.close for c in bars]
        today = self.clock().date()
        today_bars = [r for c, r in zip(bars, flow["rows"]) if local(c.ts).date() == today]
        bull_day = sum(r["bull"] for r in today_bars)
        bear_day = sum(r["bear"] for r in today_bars)
        sym = (m.next_future if use_next else m.future if use_fut else INDEXES[index].spot) or INDEXES[index].spot

        def line_of(rows: list) -> list:
            return [[c.ts, c.close] for c in resample(rows, v.tf)] if rows else []
        ce, pe = self.atm_symbols(index)
        opt = {}
        for key, s in (("ce", ce), ("pe", pe)):
            if s and s in m.opt_min:
                opt[key] = {"symbol": s, "bars": [_bar(c) for c in resample(m.opt_min[s], v.tf)],
                            "big": self.big.today({s})}
        return {"type": "bars", "index": index, "symbol": sym, "tf": v.tf, "instrument": v.instrument,
                "bars": [_bar(c) for c in bars], "vwap": vwap(bars), "bull_vwap": bvw, "bear_vwap": svw,
                "vwap_bands": vwap_bands(bars), "bb": bollinger(closes),
                "ema1": ema(closes, v.ema1), "ema2": ema(closes, v.ema2), "ema_len": [v.ema1, v.ema2],
                "flow": {k: flow[k] for k in ("today", "this_candle", "share_day", "share_20", "ratio", "avg",
                                              "above_avg")},
                "flow_rows": [{"time": r["time"], "net": r["net"], "cum": r["cum"], "avg": r["avg"],
                               "bull": r["bull"], "bear": r["bear"]} for r in flow["rows"]],
                "divergences": divergences(bars, flow["rows"]),
                "levels": day_levels(mins, today), "bull_day": bull_day, "bear_day": bear_day, "options": opt,
                "smc": smc(bars), "vp_day": day_profile(mins, today),
                "big": self._big_for_chart(m, sym, use_fut),
                "near": {"symbol": m.future, "line": line_of(m.fut_min)},
                "next": {"symbol": m.next_future, "line": line_of(m.nxt_min)}}

    def _big_for_chart(self, m: Market, sym: str, use_fut: bool) -> list[dict]:
        """Big trades to draw on the main chart: the future's own (on a future chart, at the trade price), or the near
        future's placed at the index price of that moment (on the spot chart)."""
        if use_fut:
            return [dict(t, y=t["price"]) for t in self.big.today({sym})]
        return [dict(t, y=t["spot"]) for t in self.big.today({m.future}) if t.get("spot")]

    # ------------------------------------------------------------------ live ticks
    def _on_tick(self, symbol: str, q: dict) -> None:
        self.ticks.add(symbol, q)
        if q.get("ltp"):
            self.last_ltp[symbol] = q["ltp"]
        try:
            m = self.markets.get(self.view.index)
            spot = self.last_ltp.get(INDEXES[self.view.index].spot)
            t = self.big.on_tick(symbol, q, spot)
            if t and m:
                self.broadcast({"type": "bigtrade", **t})
        except Exception:
            pass
        self.broadcast({"type": "tick", "symbol": symbol, "ltp": q.get("ltp"), "rx": q.get("rx")})

    # ------------------------------------------------------------------ link to the page
    def broadcast(self, msg: dict) -> None:
        loop = self.loop
        if loop is None or not self.queues:
            return
        text = json.dumps(msg, default=str)
        for q in list(self.queues):
            try:
                loop.call_soon_threadsafe(q.put_nowait, text)
            except Exception:
                pass

    def handle(self, msg: dict) -> list[dict]:
        op = msg.get("op")
        if op == "login_info":
            return [self.login_info()]
        if op == "save_app":
            write_env({"FYERS_CLIENT_ID": msg.get("client_id", "").strip(),
                       "FYERS_SECRET_KEY": msg.get("secret", "").strip(),
                       "FYERS_REDIRECT_URI": msg.get("redirect", "").strip()})
            return [self.login_info()]
        if op == "authorize":
            try:
                return [self.authorize(msg.get("url", "")), self.login_info()]
            except Exception as exc:
                return [{"type": "result", "op": "authorize", "ok": False, "msg": f"Login failed: {exc}"}]
        if op == "view":
            with self.lock:
                for k in ("index", "instrument", "tf", "each_side", "ema1", "ema2", "strike"):
                    if k in msg:
                        setattr(self.view, k, msg[k])
                if self.client is None:
                    return [self.login_info()]
                self._next_bars = 0.0
                out = []
                try:
                    m = self.market(self.view.index)
                    if not m.fut_min:
                        self.refresh_bars(self.view.index)
                    if not m.series:
                        self.refresh_chain(self.view.index)
                    out = [self.bars(self.view.index), self.analytics(self.view.index)]
                except Exception as exc:
                    if login_problem(exc):
                        self.logout(str(exc))
                        return [self.login_info()]
                    out = [{"type": "result", "op": "view", "ok": False, "msg": f"{exc}"}]
                self._subscribe()
                return out
        return [{"type": "result", "op": op, "ok": False, "msg": "unknown command"}]

    def _subscribe(self) -> None:
        if not self.feed:
            return
        m = self.markets.get(self.view.index)
        syms = [INDEXES[self.view.index].spot] + ([m.future] if m and m.future else []) + \
               ([m.next_future] if m and m.next_future else []) + \
               [s for s in self.atm_symbols(self.view.index) if s]
        self.feed.subscribe(syms)

    def tick_loop(self) -> None:
        last_chain = 0.0
        while True:
            _time.sleep(0.5)
            try:
                self.ticks.flush()
                if self.client is None:
                    continue
                with self.lock:
                    idx = self.view.index
                    mono = _time.monotonic()
                    if mono >= self._next_bars:
                        self.refresh_bars(idx)
                        self._subscribe()
                        self.broadcast(self.bars(idx))
                        self._next_bars = mono + (60 - self.clock().second) + 3
                    if mono - last_chain >= CHAIN_EVERY:
                        last_chain = mono
                        self.refresh_chain(idx)
                        self.fill_week(idx)
                        self.broadcast(self.analytics(idx))
                self.status = "live"
            except Exception as exc:
                if login_problem(exc):
                    with self.lock:
                        self.logout(str(exc))
                    continue
                self.status = f"problem: {str(exc)[:160]}"
                self.note(self.status)
                self.broadcast({"type": "status", "status": self.status})
                _time.sleep(3)

    def app(self):
        from starlette.applications import Starlette
        from starlette.concurrency import run_in_threadpool
        from starlette.responses import HTMLResponse, PlainTextResponse, Response
        from starlette.routing import Route, WebSocketRoute
        from starlette.websockets import WebSocket, WebSocketDisconnect

        allowed = {f"http://127.0.0.1:{self.port}", f"http://localhost:{self.port}"}
        types = {"js": "application/javascript", "css": "text/css"}

        async def page(request):
            if request.query_params.get("k") != self.key:
                return PlainTextResponse("Start the desk with start_desk.bat (key missing).", status_code=403)
            return HTMLResponse((WEB / "index.html").read_text(encoding="utf-8").replace("__KEY__", self.key))

        async def asset(request):
            name = request.path_params["name"]
            if name == "lwc.js":
                return Response(LIB.read_bytes(), media_type=types["js"])
            p = WEB / name
            if name in ("app.js", "style.css") and p.exists():
                return Response(p.read_bytes(), media_type=types[name.rsplit(".", 1)[1]])
            return PlainTextResponse("not found", status_code=404)

        async def ws_endpoint(ws: WebSocket):
            origin = ws.headers.get("origin")
            if ws.query_params.get("k") != self.key or (origin and origin not in allowed):
                await ws.close(code=4403)
                return
            await ws.accept()
            self.loop = asyncio.get_running_loop()
            q: asyncio.Queue = asyncio.Queue(maxsize=5000)
            self.queues.add(q)

            async def sender():
                while True:
                    await ws.send_text(await q.get())

            task = asyncio.create_task(sender())
            try:
                while True:
                    msg = json.loads(await ws.receive_text())
                    try:
                        replies = await run_in_threadpool(self.handle, msg)
                    except Exception as exc:
                        replies = [{"type": "result", "op": msg.get("op"), "ok": False, "msg": f"error: {exc}"}]
                    for r in replies:
                        await ws.send_text(json.dumps(r, default=str))
            except (WebSocketDisconnect, RuntimeError):
                pass
            finally:
                task.cancel()
                self.queues.discard(q)

        return Starlette(routes=[Route("/", page), Route("/a/{name}", asset), WebSocketRoute("/ws", ws_endpoint)])

    def start(self, serve: bool = True) -> None:
        if self._threads:
            return
        self._threads = True
        self.try_saved_login()
        threading.Thread(target=self.tick_loop, name="desk-loop", daemon=True).start()
        if serve:
            import uvicorn
            server = uvicorn.Server(uvicorn.Config(self.app(), host="127.0.0.1", port=self.port, log_level="warning",
                                                   ws="auto"))
            threading.Thread(target=server.run, name="desk-server", daemon=True).start()


def _bar(c: Candle) -> dict:
    b, s = split_volume(c)
    return {"t": c.ts, "o": c.open, "h": c.high, "l": c.low, "c": c.close, "v": c.volume, "bv": b, "sv": s}


__all__ = ["DeskService", "View"]
