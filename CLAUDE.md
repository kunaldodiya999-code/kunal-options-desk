# Notes for Claude (read first)

- Owner: Kunal, about 10% coding knowledge, Windows + VS Code + PowerShell. Plain words, one step at a time, always
  give the folder: `C:\Users\USER\Desktop\Kunal\kunal-options-desk` (own `.venv`; Activate.ps1 is blocked on the
  owner's PC, so use `.venv\Scripts\python.exe` / start_desk.bat). Setup: `python setup_pc.py`
  (fyers-apiv3==3.2.0 installed --no-deps: its aiohttp pin cannot build on Python 3.13 Windows).
- Tests: `python -m pytest tests -q` (tests/conftest.py points KOD_DATA at a temp folder). Demo: `run.py --demo`.
- Owner request 20 Nov 2026: single page like the "options desk" video (17 Nov) + ODX-style studies. FYERS primary,
  Dhan later. Light/dark TradingView-style chart. OI profile with two tick-boxes: Total (live) OI, OI change today.
  Delivery in 3 phases: 1 chart + OI profile + chain readings + option maths/Greeks + trapped + hedging (done);
  2 ODX order-flow studies from recorded ticks (data/ticks); 3 paper trade panel, discipline rules, journal
  (paper first, real later: NEVER market orders, limit + buffer, real orders need a setting AND a daily arm).
- We build our own from public descriptions; never copy proprietary software. Never publish KTMI code.
- Index has no volume: always use the nearest FUTURES volume (owner rule). FYERS data only.
- Never commit `.env`, `data/`, tokens. Bearish = BUY PUT, never sell options. Tools only, never trade calls (SEBI).
- Code map: desk/black76.py (IV, Greeks), chain.py (FYERS chain -> Snapshot, minute store), analytics.py
  (summary, saying, maths, TrapBook, hedging, marks), flow.py (buy-sell estimate, KAMA, divergence, VWAP, levels),
  ticks.py, service.py (server 127.0.0.1 + key + origin check, websocket), demo.py, web/ (index.html, app.js, style.css).
