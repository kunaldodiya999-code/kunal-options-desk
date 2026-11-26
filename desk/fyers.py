"""Everything that talks to FYERS (API v3): login, token, quotes, history, option chain, funds, contract list.
(Copied from kunal-fyers-terminal/terminal/fyers.py, plus history() and option_chain().)

Secrets stay on the PC: ``.env`` (FYERS_CLIENT_ID, FYERS_SECRET_KEY, FYERS_REDIRECT_URI) and ``data/token.json``
(today's access token), both ignored by git. Read-only towards the market: orders live in terminal/broker.py.
"""

from __future__ import annotations

import json
import threading
import time as _time
import os
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional, Sequence
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

from desk.candles import Candle, parse_history

try:
    IST = ZoneInfo("Asia/Kolkata")
except Exception:                          # Windows without the tzdata package: India has no daylight saving
    from datetime import timedelta, timezone
    IST = timezone(timedelta(hours=5, minutes=30), "IST")
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def data_dir() -> Path:
    """data/ of this folder (tests point KOD_DATA at a temporary folder)."""
    return Path(os.environ.get("KOD_DATA") or DATA)
MASTER_URL = "https://public.fyers.in/sym_details/{name}_sym_master.json"
STATE = "kunal_options_desk"


@dataclass(frozen=True)
class IndexInfo:
    key: str
    label: str
    spot: str               # FYERS symbol of the index
    underlying: str         # underSym in the FYERS contract list
    master: str             # NSE_FO / BSE_FO
    chain_width: int        # strikes each side of ATM (owner: NIFTY / BANK NIFTY 5, SENSEX 8)


INDEXES = {
    "NIFTY": IndexInfo("NIFTY", "NIFTY 50", "NSE:NIFTY50-INDEX", "NIFTY", "NSE_FO", 5),
    "BANKNIFTY": IndexInfo("BANKNIFTY", "BANK NIFTY", "NSE:NIFTYBANK-INDEX", "BANKNIFTY", "NSE_FO", 5),
    "SENSEX": IndexInfo("SENSEX", "SENSEX", "BSE:SENSEX-INDEX", "SENSEX", "BSE_FO", 8),
}


# ------------------------------------------------------------------ credentials and login
def read_env(path: Path = ROOT / ".env") -> dict:
    out = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def write_env(values: dict, path: Path = ROOT / ".env") -> None:
    current = read_env(path)
    current.update({k: v for k, v in values.items() if v})
    path.write_text("".join(f"{k}={v}\n" for k, v in current.items()), encoding="utf-8")


# The owner's other programs (same FYERS app): their .env and today's token are reused, so one login a day is enough.
SIBLINGS = ("kunal-fyers-terminal", "KunalQuant", "kunal-quant-claude-version")


def other_folders() -> list[Path]:
    """Sibling project folders next to this one (or one level higher), e.g. Desktop\\Kunal\\kunal-fyers-terminal."""
    if os.environ.get("KOD_NO_SHARE"):
        return []
    out = []
    for up in (ROOT.parent, ROOT.parent.parent):
        for name in SIBLINGS:
            p = up / name
            if p.is_dir() and p.resolve() != ROOT and p not in out:
                out.append(p)
    return out


def _shared_env() -> dict:
    for folder in other_folders():
        env = read_env(folder / ".env")
        if env.get("FYERS_CLIENT_ID") and env.get("FYERS_SECRET_KEY"):
            return env
    return {}


def credentials() -> dict:
    own = read_env()
    base = own if own.get("FYERS_CLIENT_ID") else {**_shared_env(), **own}
    env = {**base, **{k: os.environ[k] for k in ("FYERS_CLIENT_ID", "FYERS_SECRET_KEY", "FYERS_REDIRECT_URI")
                      if os.environ.get(k)}}
    return {"client_id": env.get("FYERS_CLIENT_ID", ""), "secret_key": env.get("FYERS_SECRET_KEY", ""),
            "redirect_uri": env.get("FYERS_REDIRECT_URI", "http://127.0.0.1:8000")}


def _session(creds: dict):
    from fyers_apiv3 import fyersModel
    return fyersModel.SessionModel(client_id=creds["client_id"], secret_key=creds["secret_key"],
                                   redirect_uri=creds["redirect_uri"], response_type="code",
                                   grant_type="authorization_code", state=STATE)


def login_url(creds: dict) -> str:
    return _session(creds).generate_authcode()


def auth_code_from(text: str) -> str:
    """The auth_code from the address FYERS opened after login (or the bare code itself)."""
    text = (text or "").strip()
    if "auth_code=" in text:
        code = parse_qs(urlparse(text).query).get("auth_code", [""])[0]
        if code:
            return code
    if text and "=" not in text and " " not in text and len(text) > 20:
        return text
    raise ValueError("No auth_code found. Paste the WHOLE address from the browser after the FYERS login.")


def exchange_code(creds: dict, code: str) -> str:
    session = _session(creds)
    session.set_token(code)
    response = session.generate_token()
    token = response.get("access_token") if isinstance(response, dict) else None
    if not token:
        raise ValueError(f"FYERS did not give a token: {response!r}"[:300])
    return token


def save_token(token: str, folder: Optional[Path] = None) -> None:
    folder = Path(folder or data_dir())
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "token.json").write_text(json.dumps({"date": datetime.now(IST).date().isoformat(), "token": token}),
                                       encoding="utf-8")


def _token_in(path: Path) -> Optional[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data.get("token") if data.get("date") == datetime.now(IST).date().isoformat() else None


def saved_token(folder: Optional[Path] = None, client_id: str = "") -> Optional[str]:
    """Today's token (FYERS tokens last one trading day). If this desk has none, today's token of the FYERS terminal
    is used when it belongs to the same FYERS app (one login a day for both programs)."""
    own = _token_in(Path(folder or data_dir()) / "token.json")
    if own or not client_id:
        return own
    for other in other_folders():
        if read_env(other / ".env").get("FYERS_CLIENT_ID") == client_id:
            token = _token_in(other / "data" / "token.json")
            if token:
                return token
    return None


def clear_token(folder: Optional[Path] = None) -> None:
    try:
        (Path(folder or data_dir()) / "token.json").unlink()
    except OSError:
        pass


# ------------------------------------------------------------------ the client
class _Pace:
    """FYERS Standard plan: at most 5 requests a second (error -360 above that). Every REST call of this program
    waits its turn here, so the desk stays at about 4 a second whatever else is running."""
    gap = 0.26
    lock = threading.Lock()
    last = 0.0

    @classmethod
    def wait(cls) -> None:
        with cls.lock:
            now = _time.monotonic()
            if now - cls.last < cls.gap:
                _time.sleep(cls.gap - (now - cls.last))
            cls.last = _time.monotonic()


def paced(fn, *args, **kwargs):
    _Pace.wait()
    return fn(*args, **kwargs)


class Fyers:
    def __init__(self, client_id: str, token: str, model: Any = None) -> None:
        if model is None:
            from fyers_apiv3 import fyersModel
            logs = data_dir() / "logs"
            logs.mkdir(parents=True, exist_ok=True)
            model = fyersModel.FyersModel(client_id=client_id, token=token, is_async=False, log_path=str(logs))
        self.model = model

    @staticmethod
    def _ok(response: Any, what: str) -> dict:
        if not isinstance(response, dict) or response.get("s") != "ok":
            raise ValueError(f"FYERS {what} failed: {response!r}"[:300])
        return response

    def profile(self) -> dict:
        return self._ok(paced(self.model.get_profile), "profile").get("data", {})

    fund_rows: list = []

    def available_funds(self) -> float:
        rows = self._ok(paced(self.model.funds), "funds").get("fund_limit") or []
        self.fund_rows = [{"title": r.get("title"), "equity": r.get("equityAmount"),
                           "commodity": r.get("commodityAmount")} for r in rows]
        for row in rows:
            if row.get("id") == 10 or str(row.get("title", "")).strip().lower() == "available balance":
                return float(row.get("equityAmount") or 0.0)
        raise ValueError("FYERS funds: no 'Available Balance' row")

    def quotes(self, symbols: Sequence[str]) -> dict[str, dict]:
        """symbol -> {"ltp", "bid", "ask"}; up to 50 symbols per FYERS call."""
        out: dict[str, dict] = {}
        symbols = [s for s in dict.fromkeys(symbols) if s]
        for i in range(0, len(symbols), 50):
            response = self._ok(paced(self.model.quotes, data={"symbols": ",".join(symbols[i:i + 50])}), "quotes")
            for row in response.get("d") or []:
                v = row.get("v") or {}
                if isinstance(v, dict) and v.get("lp") is not None:
                    out[row.get("n")] = {"ltp": float(v["lp"]), "bid": float(v.get("bid") or 0),
                                         "ask": float(v.get("ask") or 0)}
        return out

    def minutes(self, symbol: str, start: date, end: date) -> list[Candle]:
        """1-minute candles from ``start`` to ``end`` (FYERS: up to 100 days a request)."""
        response = paced(self.model.history, data={"symbol": symbol, "resolution": "1", "date_format": "1",
                                            "range_from": start.isoformat(), "range_to": end.isoformat(),
                                            "cont_flag": "1"})
        return parse_history(response)

    def history(self, symbol: str, resolution: str, start: date, end: date) -> list[Candle]:
        """Candles of any FYERS resolution ("1", "5", "D" ...)."""
        return parse_history(paced(self.model.history, data={
            "symbol": symbol, "resolution": resolution, "date_format": "1", "range_from": start.isoformat(),
            "range_to": end.isoformat(), "cont_flag": "1"}))

    def option_chain(self, symbol: str, strikes: int = 15) -> dict:
        """Raw FYERS option chain (nearest expiry): strikes each side of ATM, with OI and OI change."""
        return self._ok(paced(self.model.optionchain,
                              data={"symbol": symbol, "strikecount": int(strikes), "timestamp": ""}), "option chain")

    def daily_oi(self, symbol: str, start: date, end: date) -> list[tuple[date, float]]:
        """(day, open interest at that day's close) from FYERS daily candles with oi_flag (quantity, not lots)."""
        response = paced(self.model.history, data={"symbol": symbol, "resolution": "D", "date_format": "1",
                                                  "range_from": start.isoformat(), "range_to": end.isoformat(),
                                                  "cont_flag": "1", "oi_flag": "1"})
        if not isinstance(response, dict) or response.get("s") not in ("ok", "no_data"):
            raise ValueError(f"FYERS daily OI failed: {response!r}"[:300])
        out = []
        for row in response.get("candles") or []:
            if len(row) > 6 and row[6] is not None:
                out.append((datetime.fromtimestamp(int(row[0]), IST).date(), float(row[6])))
        return sorted(out)


# ------------------------------------------------------------------ contract list (public, once a day)
def load_master(name: str, today: date, folder: Optional[Path] = None, fetch=None) -> dict:
    folder = Path(folder or data_dir() / "master")
    path = folder / f"{name}_{today.isoformat()}.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            path.unlink()
    if fetch is None:
        def fetch(url):
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "KunalTerminal"}),
                                        timeout=180) as r:
                return json.loads(r.read().decode("utf-8"))
    data = fetch(MASTER_URL.format(name=name))
    if not isinstance(data, dict) or not data:
        raise RuntimeError(f"FYERS {name} contract list looks wrong")
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob(f"{name}_*.json"):
        old.unlink()
    path.write_text(json.dumps(data), encoding="utf-8")
    return data


@dataclass(frozen=True)
class Contracts:
    expiry: date
    lot_size: int
    step: float
    calls: dict             # strike -> symbol
    puts: dict
    future: Optional[str]   # nearest futures contract (its volume feeds VWAP: the index has none)
    next_future: Optional[str] = None   # the month after (owner: near and / or next future on the spot chart)
    future_expiry: Optional[date] = None


def nearest_contracts(master: dict, underlying: str, today: date) -> Contracts:
    options: dict[date, list] = {}
    futures = []
    for symbol, row in master.items():
        if row.get("underSym") != underlying:
            continue
        try:
            expiry = datetime.fromtimestamp(int(row["expiryDate"]), IST).date()
        except (KeyError, TypeError, ValueError):
            continue
        if expiry < today:
            continue
        ticker = str(row.get("symTicker") or symbol)
        if row.get("optType") in ("CE", "PE"):
            options.setdefault(expiry, []).append((float(row["strikePrice"]), row["optType"], ticker,
                                                   int(row.get("minLotSize") or 0)))
        elif ticker.endswith("FUT"):
            futures.append((expiry, ticker))
    if not options:
        raise RuntimeError(f"No current {underlying} options in the FYERS contract list")
    expiry = min(options)
    rows = options[expiry]
    strikes = sorted({r[0] for r in rows})
    step = min(b - a for a, b in zip(strikes, strikes[1:])) if len(strikes) > 1 else 50.0
    lots = sorted({r[3] for r in rows if r[3]})
    return Contracts(expiry, lots[0] if lots else 1, step,
                     {r[0]: r[2] for r in rows if r[1] == "CE"}, {r[0]: r[2] for r in rows if r[1] == "PE"},
                     min(futures)[1] if futures else None,
                     sorted(futures)[1][1] if len(futures) > 1 else None,
                     min(futures)[0] if futures else None)


def chain_strikes(c: Contracts, spot: float, width: int) -> list[float]:
    """ATM (strike nearest to the index) and ``width`` strikes either side that exist for both CE and PE."""
    both = sorted(set(c.calls) & set(c.puts))
    if not both:
        return []
    atm = min(both, key=lambda k: (abs(k - spot), k))
    i = both.index(atm)
    return both[max(0, i - width): i + width + 1]


__all__ = ["Contracts", "DATA", "data_dir", "Fyers", "INDEXES", "IndexInfo", "auth_code_from", "chain_strikes", "credentials",
           "exchange_code", "load_master", "login_url", "nearest_contracts", "read_env", "save_token",
           "saved_token", "write_env"]
