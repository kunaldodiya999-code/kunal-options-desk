# Notes for Claude (read first)

- Owner: Kunal, about 10% coding knowledge, Windows + VS Code + PowerShell. Plain words, one step at a time, always
  give the folder: `C:\Users\USER\Desktop\Kunal\kunal-options-desk` (own `.venv`; Activate.ps1 is blocked on the
  owner's PC, so use `.venv\Scripts\python.exe`). Owner uses DOUBLE-CLICK files: setup_desk.bat, demo_desk.bat,
  start_desk.bat, update_desk.bat (git fetch + checkout origin/main, then setup; works even in a zip folder).
  VS Code opens PowerShell one folder ABOVE the desk on the owner's PC: always give a full `cd` first.
  Owner's PC runs Python 3.14 on Windows (25 Nov 2026). fyers-apiv3==3.2.0 is installed --no-deps (its aiohttp pin
  cannot build there), so its own parts MUST be in requirements.txt (aws_lambda_powertools<2, websocket-client,
  protobuf, setuptools<81). `tzdata` is needed on Windows (IST also falls back to a fixed +05:30).
  Before pushing: check every package has a cp314 win_amd64 wheel or is pure Python
  (`pip download --platform win_amd64 --python-version 3.14 --only-binary=:all: -r requirements.txt`).
- FYERS login is shared: `.env` and today's `data/token.json` are read from a sibling kunal-fyers-terminal /
  KunalQuant folder when this desk has none (same client id only). A FYERS login error -> service.logout -> login box.
- Owner 25 Nov 2026 (chain + chart): readings say Call Buying / Call Writing / Put Buying / Put Writing / Short Cov /
  Long Unwind; Short Cov on 3+ strikes in a row -> calls green UP arrow, puts red DOWN arrow (analytics.chain_table).
  Chain columns per side: OI, Week (OI vs the close of expiry-7 days, FYERS daily candles with oi_flag, saved in
  data/week), Day, 15 min, Reading, DEX (delta x OI lots), GEX (gamma x OI x lot x price^2 x 1%), bars in every one,
  all bars right-anchored on BOTH sides. Trapped / heaviest hedging = dots on the chart (hover) + side panel
  "Trapped and key levels", never long labels. Main chart default = SPOT (futures volume); tick-boxes add near /
  next future lines. FYERS Standard plan = 5 requests/s (error -360): every REST call goes through fyers.paced (~4/s).
- OPTION ARBITRAGE (owner 26 Nov 2026): docs/OPTION_ARBITRAGE.md, package arbitrage/ (core, costs, universe, history,
  report, live), arb_history.py + arbitrage_history.bat (1 year, resumable cache data/arbitrage/cache.sqlite, newest
  first, stops at 90k FYERS calls), arb_live.py + arbitrage_live.bat (market hours, option ASK vs future bid/ask).
  Value = FUTURE - strike (calls), strike - FUTURE (puts); index weeklies use index + carry. Owner: only >= 5% below
  value counts, after every charge. Information only, never orders. Weekly FYERS names NIFTY26N17<strike>: always use
  option_prefix to read a strike (date digits must never join the strike).
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
