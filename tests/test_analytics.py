"""Analytics on a pretend market: summary strip, readings/lean, option maths vs the video's formulas, trapped
positions, hedging pressure, OI marks, buy-sell estimate, divergence, levels, tick recorder."""

from datetime import datetime, timedelta

import pytest

from desk.analytics import (TrapBook, chain_table, hedging, oi_marks, option_maths, options_saying, replay,
                            summary)
from desk.candles import IST, Candle
from desk.chain import parse
from desk.flow import avg_daily_move, buy_sell, day_levels, divergences, split_volume, vwap
from desk.ticks import TickRecorder, read_ticks
from tests.fake_market import LOT, chain_answer

NOW = datetime(2026, 11, 17, 10, 0, tzinfo=IST)


def snap(minutes=0, **kw):
    return parse(chain_answer(now=NOW + timedelta(minutes=minutes), **kw), index="NIFTY", lot_size=LOT,
                 now=NOW + timedelta(minutes=minutes))


def test_summary_strip_walls_pcr_straddle():
    oi = {(25500, "CE"): 9000, (25300, "PE"): 8000}
    s = summary(snap(oi=oi), NOW)
    assert s["call_wall"] == 25500 and s["put_wall"] == 25300
    assert s["pcr"] == pytest.approx(sum(1000 + abs(k - 25400) for k in range(24850, 25951, 50) if k != 25300) /
                                     sum(1000 + abs(k - 25400) for k in range(24850, 25951, 50) if k != 25500) *
                                     1, rel=0.2)
    assert s["straddle"] > 0 and 5 < s["hours_to_expiry"] < 6


def test_chain_readings_over_15_minutes_and_lean():
    before = snap(0)
    # calls: OI up and premium down (writing) above; puts OI up and premium down (writing) -> bullish put writing
    now = snap(15, fwd=25390, oi={(k, "PE"): 1000 + abs(k - 25400) + 800 for k in range(24850, 25951, 50)})
    table = chain_table(now, before, 8)
    atm = next(r for r in table if r["atm"])
    assert atm["put"]["m15"] == pytest.approx(800) and atm["put"]["reading"] == "buying"   # put premium rose
    lean = options_saying(now, before)
    assert lean["lean"] in ("BEARISH", "MIXED") and lean["cards"][0]["title"].startswith("Last 15 minutes")
    titles = " ".join(c["title"] for c in lean["cards"])
    assert "Expected range to expiry" in titles and "Gamma blast risk" in titles and "Theta" in titles


def test_option_maths_uses_the_video_formulas():
    m = option_maths(snap(), snap(-15), snap(-45), avg_daily_move=88)
    t = {r["measure"]: r for r in m["table"]}
    s = snap()
    a = s.row(s.atm)
    assert float(t["Break-even move, call"]["now"].split()[0].replace(",", "")) == \
        pytest.approx(abs(a.call.theta) / a.call.delta, abs=1)
    straddle_bem = (2 * (abs(a.call.theta) + abs(a.put.theta)) / (a.call.gamma + a.put.gamma)) ** 0.5
    assert float(t["Break-even move, straddle"]["now"].split()[0].replace(",", "")) == pytest.approx(straddle_bem, abs=1)
    assert any("WRITING has had the edge" in c["text"] for c in m["cards"])


def test_trapped_positions_buyers_and_writers():
    base = {(k, t): 1000 + abs(k - 25400) for k in range(24850, 25951, 50) for t in ("CE", "PE")}
    a = snap(0, fwd=25400, oi=base)
    b = snap(1, fwd=25450, oi={**base, (25450, "CE"): 1050 + 3000})   # call premium up + OI up = buyers at 25450
    c = snap(2, fwd=25380, oi={**base, (25450, "CE"): 1050 + 3000})   # price falls back: call buyers under water
    book = replay([a, b, c])
    rep = book.report(c)
    top = rep["rows"][0]
    assert (top["strike"], top["option"], top["who"]) == (25450, "Call", "buyers")
    assert top["lots"] == 3000 and top["now"] < top["built_at"] and top["money"] > 0
    assert rep["cards"][0]["title"] == "Worst pocket: call buyers at 25,450"


def test_hedging_pressure_heaviest_near_the_money():
    h = hedging(snap())
    assert h["heaviest"] in (25350, 25400, 25450) and h["buy_on_rise"] > 0 and h["sell_on_fall"] > 0
    assert max(r["share"] for r in h["rows"]) == 1.0


def test_oi_marks_calls_added():
    series = [snap(i) for i in range(6)] + [snap(6, oi={(k, "CE"): 1000 + abs(k - 25400) + 400
                                                        for k in range(24850, 25951, 50)})]
    marks = oi_marks(series)
    assert marks and marks[-1]["kind"] == "calls_added" and "CALLS ADDED" in marks[-1]["text"]


def bars(day, closes, vol=100):
    t0 = int(datetime(day.year, day.month, day.day, 9, 15, tzinfo=IST).timestamp())
    return [Candle(t0 + 60 * i, c, c + 2, c - 2, c + 1, vol) for i, c in enumerate(closes)]


def test_buy_sell_split_and_levels():
    c = Candle(0, 100, 110, 100, 108, 1000)
    assert split_volume(c) == pytest.approx((800, 200))
    d1, d2 = NOW.date() - timedelta(days=1), NOW.date()
    m = bars(d1, [100 + i for i in range(40)]) + bars(d2, [200 + i for i in range(40)])
    lv = day_levels(m, d2)
    assert lv["prev_close"] == m[39].close and lv["open"] == 200 and lv["or_high"] == max(x.high for x in m[40:70])
    assert avg_daily_move(m, d2) == pytest.approx(43)
    f = buy_sell(m)
    assert f["rows"][40]["cum"] == pytest.approx(f["rows"][40]["net"])        # resets each day
    assert vwap(m)[40] == pytest.approx((m[40].high + m[40].low + m[40].close) / 3)


def test_bearish_divergence_mark():
    d = NOW.date()
    closes = [100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111]
    m = bars(d, closes)
    m.append(Candle(m[-1].ts + 60, 111, 120, 108, 108.2, 100))           # new high, closes near the low
    f = buy_sell(m)
    assert divergences(m, f["rows"])[-1]["kind"] == "bearish_div"


def test_tick_recorder_appends(tmp_path):
    r = TickRecorder(tmp_path)
    r.add("NSE:NIFTY26NOVFUT", {"ltp": 25400.5, "bid": 25400, "ask": 25401}, NOW)
    r.add("NSE:NIFTY26NOVFUT", {"ltp": 25401}, NOW)
    r.flush()
    r.add("NSE:NIFTY26NOVFUT", {"ltp": 25402}, NOW)
    r.flush()
    assert [t["ltp"] for t in read_ticks(tmp_path, "NSE:NIFTY26NOVFUT", "2026-11-17")] == [25400.5, 25401, 25402]


def test_chain_labels_short_cov_arrows_week_dex_gex():
    before = snap(0)
    # calls 25450..25600: OI down 300 and the forward rises (premium up) -> Short Cov on 4 strikes in a row
    oi = {(k, "CE"): 1000 + abs(k - 25400) - (300 if 25450 <= k <= 25600 else 0) for k in range(24850, 25951, 50)}
    now = snap(15, fwd=25430, oi=oi)
    base = {f"{k:g}|call": 900.0 for k in range(24850, 25951, 50)}
    table = chain_table(now, before, 8, base)
    row = {r["strike"]: r for r in table}
    assert all(row[k]["call"]["label"] == "Short Cov" and row[k]["call"]["arrow"] == "up" for k in (25450, 25500, 25600))
    assert row[25400]["call"]["arrow"] is None
    assert all(r["put"]["arrow"] != "down" or r["put"]["label"] == "Short Cov" for r in table)
    atm = row[25400]["call"]
    assert atm["week"] == pytest.approx(atm["oi"] - 900) and row[25400]["put"]["week"] is None
    assert atm["dex"] == pytest.approx(atm["delta"] * atm["oi"])
    assert atm["gex"] > 0 and row[25400]["put"]["dex"] < 0
    labels = {r[s]["label"] for r in table for s in ("call", "put")}
    assert labels <= {"Call Buying", "Call Writing", "Put Buying", "Put Writing", "Short Cov", "Long Unwind", "·"}


def test_two_short_cov_strikes_get_no_arrow():
    before = snap(0)
    oi = {(k, "CE"): 1000 + abs(k - 25400) - (300 if k in (25500, 25550) else 0) for k in range(24850, 25951, 50)}
    table = chain_table(snap(15, fwd=25430, oi=oi), before, 8)
    assert not any(r["call"]["arrow"] for r in table)
