"""The desk server end to end on the pretend market: key + origin checks, page, assets, websocket view."""

import json

import pytest

from desk.demo import DemoClock, DemoFyers, demo_master
from desk.service import DeskService


@pytest.fixture()
def svc(tmp_path):
    clock = DemoClock(speed=0)
    return DeskService(folder=tmp_path, client=DemoFyers(clock), master_loader=demo_master(clock), start_feed=False,
                       clock=clock, port=8899)


def test_page_needs_the_key_and_assets_are_served(svc):
    from starlette.testclient import TestClient
    c = TestClient(svc.app())
    assert c.get("/").status_code == 403
    page = c.get(f"/?k={svc.key}")
    assert page.status_code == 200 and svc.key in page.text and "__KEY__" not in page.text
    assert c.get("/a/app.js").status_code == 200 and c.get("/a/lwc.js").status_code == 200
    assert c.get("/a/secret.txt").status_code == 404


def test_websocket_rejects_wrong_key_or_origin(svc):
    from starlette.testclient import TestClient
    from starlette.websockets import WebSocketDisconnect
    c = TestClient(svc.app())
    with pytest.raises(WebSocketDisconnect):
        with c.websocket_connect("/ws?k=wrong") as ws:
            ws.receive_text()
    with pytest.raises(WebSocketDisconnect):
        with c.websocket_connect(f"/ws?k={svc.key}", headers={"origin": "http://evil.example"}) as ws:
            ws.receive_text()


def test_view_sends_bars_and_analytics(svc):
    from starlette.testclient import TestClient
    c = TestClient(svc.app())
    with c.websocket_connect(f"/ws?k={svc.key}", headers={"origin": f"http://127.0.0.1:{svc.port}"}) as ws:
        ws.send_text(json.dumps({"op": "view", "index": "NIFTY", "tf": 5, "instrument": "INDEX"}))
        bars, ana = json.loads(ws.receive_text()), json.loads(ws.receive_text())
    assert bars["type"] == "bars" and bars["bars"] and len(bars["vwap"]) == len(bars["bars"])
    assert all(b["v"] > 0 for b in bars["bars"])                 # index chart carries the futures volume
    assert ana["type"] == "analytics" and not ana.get("empty")
    assert ana["profile"] and {"call_oi", "put_oi", "call_ch", "put_ch"} <= set(ana["profile"][0])
    assert ana["chain"] and ana["summary"]["atm"] is not None and ana["live"]["ce"]


def test_week_column_and_future_lines(svc):
    svc.handle({"op": "view", "index": "NIFTY", "tf": 5})
    while svc.fill_week("NIFTY", budget=10):
        pass
    ana, bars = svc.analytics("NIFTY"), svc.bars("NIFTY")
    assert all(r["call"]["week"] is not None and r["put"]["week"] is not None for r in ana["chain"])
    assert (svc.folder / "week").exists() and ana["week_from"]
    assert bars["symbol"] == "NSE:NIFTY50-INDEX"                       # spot is the default chart
    assert bars["near"]["line"] and bars["next"]["symbol"] == "NSE:NIFTY26DECFUT" and bars["next"]["line"]
