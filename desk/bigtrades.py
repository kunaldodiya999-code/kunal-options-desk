"""Big trades (owner 26 Nov 2026): a single trade worth Rs 50 lakh or more that hit the other side's price
(an aggressive market order). Side: at or above the ask a moment before = BUY (green), at or below the bid = SELL
(red); in between, the tick rule (higher than the last trade = buy, lower = sell).

FYERS' price feed sends snapshots: each carries the LAST trade's size (last_traded_qty) and the day's volume, so a
trade counts only once (the day's volume must have grown by at least its size). Only trades seen while the desk runs
are known; they are kept in data/bigtrades/<day>.jsonl.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from desk.candles import IST

THRESHOLD = 50e5


class BigTrades:
    def __init__(self, folder: Path, threshold: float = THRESHOLD) -> None:
        self.folder, self.threshold = Path(folder), threshold
        self.prev: dict[str, dict] = {}
        self.trades: list[dict] = []
        self.day = None
        self._lock = threading.Lock()

    def path(self, day) -> Path:
        return self.folder / f"{day.isoformat()}.jsonl"

    def load(self, day) -> None:
        self.day, self.trades = day, []
        try:
            self.trades = [json.loads(x) for x in self.path(day).read_text(encoding="utf-8").splitlines() if x]
        except OSError:
            pass

    def on_tick(self, symbol: str, q: dict, spot: Optional[float] = None, now: Optional[datetime] = None) -> Optional[dict]:
        now = now or datetime.now(IST)
        if self.day != now.date():
            self.load(now.date())
        ltp, qty, vol = q.get("ltp"), q.get("ltq"), q.get("vol")
        prev = self.prev.get(symbol)
        self.prev[symbol] = {"ltp": ltp, "bid": q.get("bid") or (prev or {}).get("bid"),
                             "ask": q.get("ask") or (prev or {}).get("ask"), "vol": vol,
                             "side": (prev or {}).get("side")}
        if not prev or not ltp or not qty or vol is None or prev.get("vol") is None:
            return None
        if vol - prev["vol"] < qty:                     # no new trade of that size since the last update
            return None
        value = ltp * qty
        if value < self.threshold:
            return None
        if prev.get("ask") and ltp >= prev["ask"]:
            side = "buy"
        elif prev.get("bid") and ltp <= prev["bid"]:
            side = "sell"
        elif prev.get("ltp") and ltp != prev["ltp"]:
            side = "buy" if ltp > prev["ltp"] else "sell"
        else:
            side = prev.get("side") or "buy"
        self.prev[symbol]["side"] = side
        t = {"ts": int(now.timestamp()), "symbol": symbol, "price": ltp, "qty": qty, "value": value, "side": side,
             "spot": spot}
        with self._lock:
            self.trades.append(t)
            self.folder.mkdir(parents=True, exist_ok=True)
            with self.path(now.date()).open("a", encoding="utf-8") as f:
                f.write(json.dumps(t) + "\n")
        return t

    def today(self, symbols: Optional[set] = None) -> list[dict]:
        with self._lock:
            return [t for t in self.trades if symbols is None or t["symbol"] in symbols]


__all__ = ["BigTrades", "THRESHOLD"]
