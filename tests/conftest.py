"""Every test works in a temporary data folder: the real data/ (token, snapshots, ticks) is never touched."""

import pytest


@pytest.fixture(autouse=True)
def _temporary_data_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("KOD_DATA", str(tmp_path / "kod_data"))
    monkeypatch.setenv("KOD_NO_SHARE", "1")          # never read the owner's other folders in tests
    for k in ("FYERS_CLIENT_ID", "FYERS_SECRET_KEY", "FYERS_REDIRECT_URI"):
        monkeypatch.delenv(k, raising=False)
