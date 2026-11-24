"""A pretend NIFTY option chain in FYERS' answer format (prices from Black-76, so the maths can be checked)."""

from datetime import datetime, timedelta

from desk.black76 import price
from desk.candles import IST

LOT = 65


def chain_answer(fwd=25400.0, vol=0.21, now=None, expiry=None, strikes=range(24850, 25951, 50), oi=None,
                 oich=None, quantity=True, ltpch=None):
    now = now or datetime(2026, 11, 17, 10, 0, tzinfo=IST)
    expiry = expiry or now.replace(hour=15, minute=30)
    years = (expiry - now).total_seconds() / (365 * 86400)
    rows = [{"option_type": "", "strike_price": -1, "ltp": fwd - 20, "symbol": "NSE:NIFTY50-INDEX"}]
    for k in strikes:
        for t in ("CE", "PE"):
            lots = (oi or {}).get((k, t), 1000 + abs(k - fwd))
            ch = (oich or {}).get((k, t), 100)
            mult = LOT if quantity else 1
            rows.append({"option_type": t, "strike_price": k, "symbol": f"NSE:NIFTY26N17{k}{t}",
                         "ltp": round(price(fwd, k, years, vol, t == "CE"), 2), "oi": lots * mult,
                         "oich": ch * mult, "volume": 500 * mult, "bid": 0, "ask": 0,
                         "ltpch": (ltpch or {}).get((k, t))})
    return {"s": "ok", "data": {"optionsChain": rows,
                                "expiryData": [{"date": expiry.strftime("%d-%m-%Y"),
                                                "expiry": str(int(expiry.replace(hour=0, minute=0).timestamp()))}]}}
