"""One FYERS login a day for both programs, and a clean way back to the login box when FYERS refuses the token."""

import json
from datetime import datetime

from desk import fyers
from desk.candles import IST
from desk.demo import DemoClock, DemoFyers, demo_master
from desk.service import DeskService, login_problem


def _sibling(tmp_path, monkeypatch, client="ABC-100", token_day=None):
    root = tmp_path / "Kunal" / "kunal-options-desk"
    term = tmp_path / "Kunal" / "kunal-fyers-terminal"
    (root).mkdir(parents=True)
    (term / "data").mkdir(parents=True)
    (term / ".env").write_text(f"FYERS_CLIENT_ID={client}\nFYERS_SECRET_KEY=s3\nFYERS_REDIRECT_URI=http://x\n",
                               encoding="utf-8")
    day = token_day or datetime.now(IST).date().isoformat()
    (term / "data" / "token.json").write_text(json.dumps({"date": day, "token": "TERMTOKEN"}), encoding="utf-8")
    monkeypatch.setattr(fyers, "ROOT", root)
    monkeypatch.delenv("KOD_NO_SHARE")
    monkeypatch.setattr(fyers, "read_env", _reader(root))
    return root, term


def _reader(root):
    real = fyers.read_env.__wrapped__ if hasattr(fyers.read_env, "__wrapped__") else fyers.read_env

    def read_env(path=None):
        return real(path or root / ".env")
    return read_env


def test_uses_the_terminals_app_and_todays_token(tmp_path, monkeypatch):
    _sibling(tmp_path, monkeypatch)
    c = fyers.credentials()
    assert c["client_id"] == "ABC-100" and c["secret_key"] == "s3" and c["redirect_uri"] == "http://x"
    assert fyers.saved_token(tmp_path / "own", "ABC-100") == "TERMTOKEN"
    assert fyers.saved_token(tmp_path / "own", "OTHER-100") is None           # another app: not shared


def test_yesterdays_token_is_not_used(tmp_path, monkeypatch):
    _sibling(tmp_path, monkeypatch, token_day="2020-01-01")
    assert fyers.saved_token(tmp_path / "own", "ABC-100") is None


def test_own_settings_win(tmp_path, monkeypatch):
    root, _ = _sibling(tmp_path, monkeypatch)
    (root / ".env").write_text("FYERS_CLIENT_ID=MINE-100\nFYERS_SECRET_KEY=m\n", encoding="utf-8")
    assert fyers.credentials()["client_id"] == "MINE-100"


def test_login_problem_words():
    assert login_problem(ValueError("FYERS option chain failed: {'s': 'error', 'code': -16, 'message': 'x'}"))
    assert login_problem(ValueError("Could not authenticate the user"))
    assert not login_problem(ValueError("FYERS history failed: {'s': 'error', 'code': -300, 'message': 'bad'}"))


class Refusing(DemoFyers):
    def option_chain(self, symbol, strikes=15):
        raise ValueError("FYERS option chain failed: {'s': 'error', 'code': -16, 'message': 'Could not authenticate'}")


def test_expired_login_shows_the_login_box_again(tmp_path):
    clock = DemoClock(speed=0)
    svc = DeskService(folder=tmp_path, client=Refusing(clock), master_loader=demo_master(clock), start_feed=False,
                      clock=clock, port=8898)
    fyers.save_token("OLD", tmp_path)
    out = svc.handle({"op": "view", "index": "NIFTY"})
    assert out[0]["type"] == "login" and out[0]["logged_in"] is False
    assert svc.client is None and fyers.saved_token(tmp_path) is None


class NoFuture(DemoFyers):
    def minutes(self, symbol, start, end):
        return [] if symbol.endswith("FUT") else super().minutes(symbol, start, end)


def test_chart_falls_back_to_the_index_when_the_future_has_no_candles(tmp_path):
    clock = DemoClock(speed=0)
    svc = DeskService(folder=tmp_path, client=NoFuture(clock), master_loader=demo_master(clock), start_feed=False,
                      clock=clock, port=8897)
    bars, ana = svc.handle({"op": "view", "index": "NIFTY", "instrument": "FUT"})
    assert bars["type"] == "bars" and bars["bars"] and bars["symbol"] == "NSE:NIFTY50-INDEX"
