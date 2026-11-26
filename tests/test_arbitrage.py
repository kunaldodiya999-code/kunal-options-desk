"""Option arbitrage scanner on a pretend FYERS with ONE planted discount (ABC 900 CE, 20% below value)."""

from datetime import date, datetime, timedelta

import pytest

from arbitrage.core import bucket_name, carry_ref, check
from arbitrage.costs import Costs
from arbitrage.history import Cache, Fetcher, Runner, Stop
from arbitrage.live import sweep
from arbitrage.report import build
from arbitrage.universe import Underlying, from_master, monthly, option_prefix, strike_of
from desk.candles import IST

TODAY = date(2026, 11, 26)
MONTHLY = [date(2026, 9, 29), date(2026, 10, 27), date(2026, 11, 24), date(2026, 12, 29)]
WEEKLY = [date(2026, 11, 3), date(2026, 11, 10), date(2026, 11, 17), date(2026, 11, 24), date(2026, 12, 1)]
PLANT_DAY = date(2026, 10, 20)


def ts(d, h, m):
    return int(datetime.combine(d, datetime.min.time(), IST).replace(hour=h, minute=m).timestamp())


def master():
    m = {}
    ex = lambda d: int(datetime.combine(d, datetime.min.time(), IST).timestamp())
    m["NSE:ABC26DECFUT"] = {"underSym": "ABC", "expiryDate": ex(date(2026, 12, 29)), "symTicker": "NSE:ABC26DECFUT",
                            "minLotSize": 100}
    m["NSE:NIFTY26DECFUT"] = {"underSym": "NIFTY", "expiryDate": ex(date(2026, 12, 29)),
                              "symTicker": "NSE:NIFTY26DECFUT", "minLotSize": 65}
    for k in range(700, 1301, 10):
        for t in ("CE", "PE"):
            s = f"NSE:ABC26DEC{k}{t}"
            m[s] = {"underSym": "ABC", "expiryDate": ex(date(2026, 12, 29)), "symTicker": s, "optType": t,
                    "strikePrice": k, "minLotSize": 100}
    for k in range(23000, 27001, 50):
        for t in ("CE", "PE"):
            s = f"NSE:NIFTY26D01{k}{t}"
            m[s] = {"underSym": "NIFTY", "expiryDate": ex(date(2026, 12, 1)), "symTicker": s, "optType": t,
                    "strikePrice": k, "minLotSize": 65}
    return m


class FakeModel:
    def __init__(self):
        self.calls = 0

    def expiry_dates(self, data):
        self.calls += 1
        lo, hi = date.fromisoformat(data["range_from"]), date.fromisoformat(data["range_to"])
        return {"s": "ok", "data": [d.isoformat() for d in sorted(set(WEEKLY + MONTHLY)) if lo <= d <= hi]}

    def history_underlying_symbols(self, data):
        self.calls += 1
        return {"s": "ok", "data": []}          # pretend FYERS cannot list them: names are built on today's gap

    def _candles(self, sym, lo, hi):
        out = []
        d = lo
        while d <= hi:
            if d.weekday() < 5:
                for i in range(0, 375, 25):
                    t = ts(d, 9, 15) + i * 60
                    out.append((t, d))
            d += timedelta(days=1)
        rows = []
        und = 1000.0 if "ABC" in sym else 25000.0
        for t, d in out:
            if sym.endswith("FUT") or sym.endswith("INDEX"):
                rows.append([t, und, und + 1, und - 1, und, 5000])
                continue
            kind = sym[-2:]
            monthly_name = any(m in sym for m in ("SEP", "OCT", "NOV", "DEC"))
            k = strike_of(sym, kind) if monthly_name else float(sym[len("NSE:NIFTY26N17"):-2])
            intr = max(0.0, (und - k) if kind == "CE" else (k - und))
            px = intr + 2.0
            vol = 200
            if sym == "NSE:ABC26OCT900CE" and d == PLANT_DAY and t == ts(d, 10, 55):
                px = intr * 0.8                     # 80 for value 100: 20% below
            rows.append([t, px, px, px, px, vol])
        return rows

    def fno_historical_data(self, data):
        self.calls += 1
        sym = data["symbol"]
        rows = self._candles(sym, date.fromisoformat(data["range_from"]), date.fromisoformat(data["range_to"]))
        return {"s": "ok", "candles": rows}

    def history(self, data):
        return self.fno_historical_data(data)


@pytest.fixture()
def setup(tmp_path):
    uni = from_master({"NSE_FO": master()}, TODAY)
    model = FakeModel()
    cache = Cache(tmp_path / "cache.sqlite")
    f = Fetcher(model, cache, TODAY, gap=0, sleep=lambda s: None)
    return uni, model, cache, f


def test_owner_example_and_threshold():
    hit = check("CE", 80, 10, 100, 500, Costs(), False)
    assert hit["discount"] == pytest.approx(0.5) and hit["net"] > 4800 and hit["bucket"] == "50%+"
    assert check("CE", 80, 19.2, 100, 500, Costs(), False) is None         # 4% below: useless (owner)
    assert check("CE", 80, 18.9, 100, 500, Costs(), False)["bucket"] == "5-10%"
    assert check("PE", 120, 15, 100, 500, Costs(), False)["discount"] == pytest.approx(0.25)
    assert check("CE", 99, 0.5, 100, 500, Costs(), False) is None          # only 1% in the money: not checked
    assert bucket_name(0.12) == "10-15%" and bucket_name(0.73) == "50%+"


def test_charges_eat_tiny_lots():
    assert check("CE", 80, 18.9, 100, 1, Costs(), False) is None           # 1 unit: Rs 1.1 profit < charges


def test_weekly_reference_uses_the_carry():
    t, opt, fut = 0, 2 * 86400, 20 * 86400
    assert carry_ref(25000, 25200, t, opt, fut) == pytest.approx(25020)
    assert carry_ref(None, 25200, t, opt, fut) == 25200


def test_one_year_finds_only_the_planted_discount_and_resumes(setup, tmp_path):
    uni, model, cache, f = setup
    r = Runner(f, uni, Costs(), days=90, log=lambda s: None)
    jobs = r.jobs()
    assert {j[0] for j in jobs} == {"ABC", "NIFTY"}
    r.run(jobs, cache)
    events = [e for x in cache.results() for e in x["events"]]
    assert len(events) == 1
    e = events[0]
    assert e["underlying"] == "ABC" and e["option"] == "900 CE" and e["expiry"] == "2026-10-27"
    assert e["discount"] == pytest.approx(20.0) and e["sure"] and e["lots_traded"] == 2.0 and e["net_per_lot"] > 1800
    used = model.calls
    f2 = Fetcher(model, cache, TODAY, gap=0, sleep=lambda s: None)
    Runner(f2, uni, Costs(), days=90, log=lambda s: None).run(jobs, cache)
    assert model.calls - used == f2.calls and f2.calls < used / 4        # finished expiries are not asked again
    text = build(cache.results(), tmp_path / "report", 90)
    assert "EVENTS FOUND: 1" in text and "ABC" in text and (tmp_path / "report" / "report.html").exists()


def test_stops_at_the_call_limit(setup):
    uni, model, cache, f = setup
    f.max_calls = 5
    r = Runner(f, uni, Costs(), days=90, log=lambda s: None)
    with pytest.raises(Stop):
        r.run(r.jobs(), cache)


def test_monthly_picks_the_last_expiry_of_each_month():
    assert monthly(WEEKLY + MONTHLY)[-2:] == [date(2026, 11, 24), date(2026, 12, 29)]


class FakeQuotes:
    def quotes(self, symbols):
        out = {}
        for s in symbols:
            if s.endswith("FUT"):
                out[s] = {"ltp": 1000.0, "bid": 999.0, "ask": 1001.0}
            elif "ABC" in s:
                k, kind = float(s[-5:-2]) if s[-6].isalpha() else float(s[-6:-2]), s[-2:]
                intr = max(0.0, (999.0 - k) if kind == "CE" else (k - 1001.0))
                ask = intr * 0.9 if s == "NSE:ABC26DEC850CE" else intr + 3
                out[s] = {"ltp": ask, "bid": ask - 1, "ask": ask}
        return out


def test_live_sweep_uses_the_ask_and_the_future_bid():
    from arbitrage.live import plan
    uni = from_master({"NSE_FO": master()}, TODAY)
    jobs = [j for j in plan(uni, TODAY) if j["u"].name == "ABC"]
    hits, checked = sweep(FakeQuotes(), jobs, Costs(), datetime(2026, 11, 26, 11, 0, tzinfo=IST))
    assert checked > 10 and [h["symbol"] for h in hits] == ["NSE:ABC26DEC850CE"]
    assert hits[0]["discount"] == pytest.approx(0.10) and hits[0]["future_px"] == 999.0


def test_strike_never_takes_the_date_digits():
    n = Underlying("NIFTY", "NSE", "NSE:NIFTY50-INDEX", 65, True)
    pre = option_prefix(n, date(2026, 11, 17), False)
    assert pre == "NSE:NIFTY26N17" and strike_of("NSE:NIFTY26N1725000CE", "CE", pre) == 25000
    assert strike_of("NSE:ABC26OCT900CE", "CE") == 900 and strike_of("NSE:ABC26OCT12.5PE", "PE") == 12.5


def test_history_stops_cleanly_at_the_fyers_daily_limit(setup):
    uni, model, cache, f = setup

    class Refuses(FakeModel):
        def fno_historical_data(self, data):
            return {"s": "error", "code": -360, "message": "Standard plan limit of 5,000 requests/day"}
    f.model = Refuses()
    r = Runner(f, uni, Costs(), days=90, log=lambda s: None)
    with pytest.raises(Stop) as e:
        r.run(r.jobs(), cache)
    assert "tomorrow" in str(e.value) and f.calls < 10
