"""SMC structure / order blocks / FVG, today's volume profile, opening ranges, big trades."""

from datetime import datetime, timedelta

import pytest

from desk.bigtrades import BigTrades
from desk.candles import IST, Candle
from desk.flow import day_levels, day_profile
from desk.smc import smc

DAY = datetime(2026, 11, 26, 9, 15, tzinfo=IST)


def candles(closes, start=DAY, vol=100.0):
    out, prev = [], closes[0]
    for i, c in enumerate(closes):
        o = prev
        out.append(Candle(int((start + timedelta(minutes=i)).timestamp()), o, max(o, c) + 1, min(o, c) - 1, c, vol))
        prev = c
    return out


def test_smc_finds_bos_then_choch_and_an_order_block():
    up = [100 + i for i in range(12)] + [111 - i for i in range(6)] + [106 + 2 * i for i in range(10)]   # higher high
    down = [124 - 3 * i for i in range(14)]                                                             # breaks the low
    s = smc(candles(up + down), length=3)
    kinds = [(e["kind"], e["dir"]) for e in s["structure"]]
    assert ("BOS", "up") in kinds or ("CHoCH", "up") in kinds
    assert kinds[-1] == ("CHoCH", "down")
    assert s["pd"] and s["pd"]["bottom"] < s["pd"]["eq"] < s["pd"]["top"]


def test_fvg_and_its_filling():
    c = candles([100, 100, 100])
    gap = [Candle(c[-1].ts + 60, 100, 101, 99, 100), Candle(c[-1].ts + 120, 101, 110, 101, 109),
           Candle(c[-1].ts + 180, 109, 112, 105, 111)]               # candle 1 high 101 < candle 3 low 105
    s = smc(c + gap, length=1)
    assert any(g["dir"] == "bull" and g["bottom"] == 101 and g["top"] == 105 for g in s["fvgs"])
    filled = gap + [Candle(gap[-1].ts + 60, 111, 111, 100, 100)]
    assert not any(g["dir"] == "bull" and g["bottom"] == 101 for g in smc(c + filled, length=1)["fvgs"])


def test_day_profile_today_only_with_value_area():
    yday = candles([200] * 30, start=DAY - timedelta(days=1), vol=10_000)
    today = candles([100] * 20 + [110] * 5, vol=100)
    p = day_profile(yday + today, DAY.date())
    assert p["from_ts"] == today[0].ts and p["low"] >= 98                 # yesterday is not in it
    assert 98 <= p["poc"] <= 102 and p["val"] <= p["poc"] <= p["vah"]
    va_share = sum(p["vol"][i] for i in p["va"]) / sum(p["vol"])
    assert 0.7 <= va_share < 0.95


def test_opening_ranges_5_15_30():
    c = candles([100 + i for i in range(40)])
    lv = day_levels(c, DAY.date())
    assert lv["or5_high"] == 105 and lv["or15_high"] == 115 and lv["or_high"] == 130
    assert lv["or5_low"] == lv["or15_low"] == lv["or_low"] == 99


def test_big_trades_side_size_and_no_double_count(tmp_path):
    b = BigTrades(tmp_path)
    now = DAY + timedelta(hours=2)
    b.on_tick("NSE:NIFTY26DECFUT", {"ltp": 25900, "bid": 25899, "ask": 25901, "ltq": 65, "vol": 1000}, 25850, now)
    t = b.on_tick("NSE:NIFTY26DECFUT", {"ltp": 25901, "bid": 25900, "ask": 25902, "ltq": 260, "vol": 1260}, 25851, now)
    assert t and t["side"] == "buy" and t["value"] == pytest.approx(25901 * 260) and t["spot"] == 25851
    again = b.on_tick("NSE:NIFTY26DECFUT", {"ltp": 25901, "bid": 25900, "ask": 25902, "ltq": 260, "vol": 1260}, 25851, now)
    assert again is None                                                   # same trade repeated: counted once
    s = b.on_tick("NSE:NIFTY26DECFUT", {"ltp": 25899, "bid": 25898, "ask": 25900, "ltq": 390, "vol": 1650}, 25849, now)
    assert s and s["side"] == "sell"
    small = b.on_tick("NSE:NIFTY26DECFUT", {"ltp": 25899, "bid": 25898, "ask": 25900, "ltq": 65, "vol": 1715}, 25849, now)
    assert small is None                                                   # Rs 16.8 lakh: below Rs 50 lakh
    again2 = BigTrades(tmp_path)
    again2.load(now.date())
    assert len(again2.today()) == 2                                        # kept on disk for the day
