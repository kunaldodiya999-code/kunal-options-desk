"""Black-76 and the option chain: Greeks units, implied volatility, forward, lots, readings, minute store."""

from datetime import datetime, timedelta

import pytest

from desk.black76 import greeks, implied_forward, implied_vol, price
from desk.candles import IST
from desk.chain import SnapshotStore, changes, parse, reading
from tests.fake_market import LOT, chain_answer

NOW = datetime(2026, 11, 17, 10, 0, tzinfo=IST)


def test_implied_vol_round_trip_and_put_call_parity():
    years = 5.5 / 24 / 365
    c = price(25400, 25400, years, 0.21, True)
    p = price(25400, 25400, years, 0.21, False)
    assert implied_vol(c, 25400, 25400, years, True) == pytest.approx(0.21, abs=1e-4)
    assert c - p == pytest.approx(0.0, abs=1e-6)
    assert implied_forward(25400, c + 5, p) == pytest.approx(25405)
    assert implied_vol(0.0, 25400, 25400, years, True) is None


def test_greeks_in_screen_units_match_the_video_scale():
    years = 5.4 / 24 / 365                                # 5.4 hours to expiry, ATM, IV 21%
    g = greeks(25400, 25400, years, 0.21, True)
    assert 0.49 < g.delta < 0.51
    assert -140 < g.theta < -100                          # video: ATM theta about -117 points a day
    assert 0.002 < g.gamma < 0.004                        # video: 0.00298
    assert 1.5 < g.vega < 3.5                             # video: 2.46


def test_parse_converts_quantity_to_lots_and_finds_the_forward():
    snap = parse(chain_answer(), index="NIFTY", lot_size=LOT, now=NOW)
    assert snap.forward == pytest.approx(25400, abs=0.5) and snap.atm == 25400
    r = snap.row(25400)
    assert r.call.oi == 1000 and r.call.oi_change == 100           # lots, not quantity
    assert r.call.iv == pytest.approx(0.21, abs=1e-3) and r.put.delta == pytest.approx(r.call.delta - 1, abs=1e-6)
    assert snap.expiry == "2026-11-17" and snap.years == pytest.approx(5.5 / 24 / 365, rel=1e-3)


def test_readings_rule_of_thumb():
    assert reading(+10, +1) == "buying" and reading(+10, -1) == "writing"
    assert reading(-10, +1) == "covering" and reading(-10, -1) == "unwinding"
    assert reading(0, 1) == "·"


def test_minute_store_and_changes(tmp_path):
    store = SnapshotStore(tmp_path)
    a = parse(chain_answer(fwd=25400), index="NIFTY", lot_size=LOT, now=NOW)
    b = parse(chain_answer(fwd=25440, oi={(25400, "CE"): 1500}), index="NIFTY", lot_size=LOT,
              now=NOW + timedelta(minutes=15))
    store.put(a)
    store.put(b)
    again = SnapshotStore(tmp_path)                                   # from disk
    before = again.at("NIFTY", b.ts - 15 * 60)
    assert before is not None and before.ts == a.ts
    ch = changes(b, before)[(25400.0, "call")]
    assert ch["oi"] == pytest.approx(500) and ch["premium"] > 0 and ch["reading"] == "buying"
    assert [s.ts for s in again.series("NIFTY", NOW.date())] == [a.ts, b.ts]
