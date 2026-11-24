"""Tick recorder (owner 20 Nov 2026: 'build live + save ticks to disk'). Every FYERS websocket tick of the watched
symbols is appended to data/ticks/<date>/<symbol>.jsonl (one JSON per line), so phase 2's order-flow studies
(footprint, cumulative delta, aggressive buy/sell, imbalance zones) keep their history day after day.
Writes are buffered and flushed about once a second; nothing is ever rewritten."""

from __future__ import annotations

import json
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from desk.candles import IST


class TickRecorder:
    def __init__(self, folder: Path) -> None:
        self.folder = Path(folder)
        self._buf: dict[Path, list[str]] = {}
        self._lock = threading.Lock()
        self.count = 0

    def path(self, symbol: str, when: datetime) -> Path:
        safe = re.sub(r"[^A-Za-z0-9_-]", "_", symbol)
        return self.folder / when.strftime("%Y-%m-%d") / f"{safe}.jsonl"

    def add(self, symbol: str, tick: dict, when: Optional[datetime] = None) -> None:
        when = when or datetime.now(IST)
        line = json.dumps({"rx": round(when.timestamp(), 3), **tick}, separators=(",", ":"), default=str)
        with self._lock:
            self._buf.setdefault(self.path(symbol, when), []).append(line)
            self.count += 1

    def flush(self) -> None:
        with self._lock:
            buf, self._buf = self._buf, {}
        for path, lines in buf.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")


def read_ticks(folder: Path, symbol: str, day: str) -> list[dict]:
    p = TickRecorder(folder).path(symbol, datetime.fromisoformat(day + "T12:00:00+05:30"))
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


__all__ = ["TickRecorder", "read_ticks"]
