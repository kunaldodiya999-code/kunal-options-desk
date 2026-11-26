"""Which underlyings, expiries and option symbols to scan (FYERS contract lists + FYERS expired-contract API)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Iterable, Optional

from desk.candles import IST

INDEX_NAMES = {"NIFTY": ("NSE:NIFTY50-INDEX", "NSE", "NSE_FO"), "BANKNIFTY": ("NSE:NIFTYBANK-INDEX", "NSE", "NSE_FO"),
               "SENSEX": ("BSE:SENSEX-INDEX", "BSE", "BSE_FO")}
SKIP = {"FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50", "BANKEX", "SENSEX50"}      # owner: only these 3 indexes + stocks
MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
WEEK_MONTH = "123456789OND"


@dataclass
class Underlying:
    name: str
    exchange: str               # NSE / BSE
    spot: str                   # FYERS symbol of the stock / index
    lot: int
    index: bool
    step: float = 0.0           # strike gap today (used only when FYERS cannot list an old expiry's strikes)
    current: dict = field(default_factory=dict)     # expiry -> {(strike, CE/PE): symbol} from today's list
    futures: dict = field(default_factory=dict)     # expiry -> future symbol (today's list)


def from_master(masters: dict[str, dict], today: date) -> dict[str, Underlying]:
    """NSE_FO + BSE_FO contract lists -> the F&O stocks and NIFTY / BANKNIFTY / SENSEX."""
    out: dict[str, Underlying] = {}
    for mname, master in masters.items():
        for sym, r in master.items():
            u = r.get("underSym")
            if not u or u in SKIP:
                continue
            is_index = u in INDEX_NAMES
            if mname == "BSE_FO" and u != "SENSEX":
                continue
            if mname == "NSE_FO" and u == "SENSEX":
                continue
            try:
                exp = datetime.fromtimestamp(int(r["expiryDate"]), IST).date()
            except (KeyError, TypeError, ValueError):
                continue
            if exp < today:
                continue
            ticker = str(r.get("symTicker") or sym)
            exch = ticker.split(":")[0]
            spot = INDEX_NAMES[u][0] if is_index else f"{exch}:{u}-EQ"
            und = out.setdefault(u, Underlying(u, exch, spot, int(r.get("minLotSize") or 1), is_index))
            if r.get("optType") in ("CE", "PE"):
                und.current.setdefault(exp, {})[(float(r["strikePrice"]), r["optType"])] = ticker
            elif ticker.endswith("FUT"):
                und.futures[exp] = ticker
    for u in out.values():
        ks = sorted({k for chain in u.current.values() for k, _ in chain})
        gaps = [b - a for a, b in zip(ks, ks[1:]) if b > a]
        u.step = min(gaps) if gaps else 0.0
    return {k: v for k, v in out.items() if v.futures and v.current}


def monthly(expiries: Iterable[date]) -> list[date]:
    """The last expiry of each month = the monthly expiry."""
    last: dict[tuple[int, int], date] = {}
    for e in sorted(set(expiries)):
        last[(e.year, e.month)] = e
    return sorted(last.values())


def future_symbol(u: Underlying, expiry: date) -> str:
    return f"{u.exchange}:{u.name}{expiry:%y}{MONTHS[expiry.month - 1]}FUT"


def option_prefix(u: Underlying, expiry: date, is_monthly: bool) -> str:
    """FYERS name up to the strike: NSE:RELIANCE26JAN (monthly) or NSE:NIFTY26N17 (weekly: YY, month code, day)."""
    if is_monthly:
        return f"{u.exchange}:{u.name}{expiry:%y}{MONTHS[expiry.month - 1]}"
    return f"{u.exchange}:{u.name}{expiry:%y}{WEEK_MONTH[expiry.month - 1]}{expiry:%d}"


def option_symbol(u: Underlying, expiry: date, strike: float, kind: str, is_monthly: bool) -> str:
    return f"{option_prefix(u, expiry, is_monthly)}{strike:g}{kind}"


def strike_of(symbol: str, kind: str, prefix: str = "") -> Optional[float]:
    """The strike inside a FYERS option name. With the known prefix the date digits can never be mistaken for it."""
    if prefix and symbol.startswith(prefix) and symbol.endswith(kind):
        try:
            return float(symbol[len(prefix):-len(kind)])
        except ValueError:
            return None
    m = re.search(r"[A-Z](\d+(?:\.\d+)?)" + kind + "$", symbol)
    return float(m.group(1)) if m else None


def find_dates(value: Any) -> set[date]:
    out: set[date] = set()
    if isinstance(value, dict):
        for v in value.values():
            out |= find_dates(v)
    elif isinstance(value, list):
        for v in value:
            out |= find_dates(v)
    elif isinstance(value, str):
        for pat, fmt in ((r"\d{4}-\d{2}-\d{2}", "%Y-%m-%d"), (r"\d{2}-\d{2}-\d{4}", "%d-%m-%Y")):
            for m in re.findall(pat, value):
                try:
                    out.add(datetime.strptime(m, fmt).date())
                except ValueError:
                    pass
        if value.isdigit() and len(value) == 10:
            out.add(datetime.fromtimestamp(int(value), IST).date())
    elif isinstance(value, int) and 10 ** 9 < value < 3 * 10 ** 9:
        out.add(datetime.fromtimestamp(value, IST).date())
    return out


def find_symbols(value: Any, prefix: str) -> set[str]:
    out: set[str] = set()
    if isinstance(value, dict):
        for v in value.values():
            out |= find_symbols(v, prefix)
    elif isinstance(value, list):
        for v in value:
            out |= find_symbols(v, prefix)
    elif isinstance(value, str) and value.startswith(prefix) and value[-2:] in ("CE", "PE"):
        out.add(value)
    return out


def window(expiry: date, previous: Optional[date], days: int) -> tuple[date, date]:
    """Days scanned for one expiry: the day after the previous expiry of the same kind, up to the expiry."""
    start = previous + timedelta(days=1) if previous else expiry - timedelta(days=days)
    return start, expiry


__all__ = ["INDEX_NAMES", "Underlying", "find_dates", "find_symbols", "from_master", "future_symbol", "monthly",
           "option_prefix", "option_symbol", "strike_of", "window"]
