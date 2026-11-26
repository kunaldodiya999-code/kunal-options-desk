"""FYERS allows 5,000 REST calls a day (26 Nov 2026): counting, stopping, and the page still working on saved data."""

from datetime import datetime

import pytest

from desk import fyers
from desk.candles import IST
from desk.demo import DemoClock, DemoFyers, demo_master
from desk.fyers import Budget, DailyLimit, is_daily_limit, paced
from desk.service import DeskService

DAY_MSG = {"s": "error", "code": -360,
           "message": "You've reached the Standard plan limit of 5,000 requests/day. Upgrade to Prime"}
SEC_MSG = {"s": "error", "code": -360, "message": "You've reached the Standard plan limit of 5 requests/second."}


def test_counter_and_daily_limit_message():
    assert Budget.left() == 5000
    paced(lambda: {"s": "ok"})
    assert Budget.used() == 1
    assert is_daily_limit(DAY_MSG) and not is_daily_limit(SEC_MSG)
    with pytest.raises(DailyLimit):
        paced(lambda: DAY_MSG)
    assert Budget.left() == 0
    with pytest.raises(DailyLimit):                      # nothing more is sent to FYERS today
        paced(lambda: pytest.fail("must not call FYERS"))


class Limited(DemoFyers):
    def minutes(self, symbol, start, end):
        raise DailyLimit("FYERS daily limit (5,000 calls) is used up for today; it resets tomorrow")

    def option_chain(self, symbol, strikes=15):
        raise DailyLimit("FYERS daily limit (5,000 calls) is used up for today; it resets tomorrow")


def test_page_still_opens_on_saved_data_when_fyers_refuses(tmp_path):
    clock = DemoClock(speed=0)
    good = DeskService(folder=tmp_path, client=DemoFyers(clock), master_loader=demo_master(clock), start_feed=False,
                       clock=clock, port=8896)
    good.handle({"op": "view", "index": "NIFTY"})                  # saves candles and the chain on the PC
    bad = DeskService(folder=tmp_path, client=Limited(clock), master_loader=demo_master(clock), start_feed=False,
                      clock=clock, port=8895)
    out = bad.handle({"op": "view", "index": "NIFTY"})
    kinds = [o["type"] for o in out]
    assert "bars" in kinds and "analytics" in kinds and "status" in kinds
    bars = next(o for o in out if o["type"] == "bars")
    assert bars["bars"], "saved candles must still be drawn"
    assert "daily limit" in next(o for o in out if o["type"] == "status")["status"]
    assert bad.client is not None                                   # not logged out: it is a limit, not a bad login


def test_second_start_asks_fyers_for_today_only(tmp_path):
    clock = DemoClock(speed=0)
    asked = []

    class Spy(DemoFyers):
        def minutes(self, symbol, start, end):
            asked.append((symbol, start, end))
            return super().minutes(symbol, start, end)
    s1 = DeskService(folder=tmp_path, client=Spy(clock), master_loader=demo_master(clock), start_feed=False,
                     clock=clock, port=8894)
    s1.refresh_bars("NIFTY")
    first = list(asked)
    asked.clear()
    s2 = DeskService(folder=tmp_path, client=Spy(clock), master_loader=demo_master(clock), start_feed=False,
                     clock=clock, port=8893)
    s2.refresh_bars("NIFTY")
    assert any(a[1] < a[2] for a in first)                          # 6 days the first time
    assert all(a[1] == a[2] for a in asked)                         # today only after that


def test_live_ticks_build_the_minute_candle(tmp_path, monkeypatch):
    clock = DemoClock(speed=0)
    s = DeskService(folder=tmp_path, client=DemoFyers(clock), master_loader=demo_master(clock), start_feed=False,
                    clock=clock, port=8892)
    s.market("NIFTY")
    m = s.markets["NIFTY"]
    fixed = datetime(2026, 11, 26, 11, 0, 20, tzinfo=IST)

    class FakeDT(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed
    import desk.service as svc_mod
    monkeypatch.setattr(svc_mod, "datetime", FakeDT)
    s._on_tick(m.future, {"ltp": 25900.0, "vol": 1000})
    s._on_tick(m.future, {"ltp": 25910.0, "vol": 1130})
    s._on_tick(m.future, {"ltp": 25895.0, "vol": 1195})
    c = m.fut_min[-1]
    assert (c.open, c.high, c.low, c.close) == (25900.0, 25910.0, 25895.0, 25895.0) and c.volume == 195
    assert c.ts == int(fixed.timestamp()) // 60 * 60
