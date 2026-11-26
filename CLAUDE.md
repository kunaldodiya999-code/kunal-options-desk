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
- Owner 26 Nov 2026: chart profiles OI / OI chg / Delta / GEX side by side in their own columns (tick-boxes
  oi_total, oi_change, prof_dex, prof_gex), never overlapping. Box "CALLS VS PUTS" (analytics.pricing): dear side =
  options' forward (K + C - P at ATM) vs fair forward from the future (carry scaled to this expiry); bias = 2 of 3
  votes (parity, 25-delta skew change since open, OI lean); expected move = index x avg(ATM IV, last-hour realised)
  x sqrt(minutes / (252 x 375)); ATM CE / PE rupees = |delta| m + 1/2 gamma m^2 - theta x minutes/375, for half to
  one expected move, next 30 / 60 min and rest of day. Maths, not a direction forecast.
- Owner 26 Nov 2026 (2nd round): profiles use at most ~34% of the chart, soft colours (OI red/green, DEX blue/orange,
  GEX purple/cyan), labels in text colour. Toggles vwap1 / vwap2 (TradingView VWAP st-dev bands) and bb (20, 2).
  Call/put charts: OHLC legend, volume, VWAP, volume profile (sky blue 30%, 70% value area, VAH/POC/VAL) + delta
  profile (opt_vp / opt_dp). Hover boxes are see-through (~35%, blur, text shadow); flow pane has one too.
  Chain: Value column (OI x lot x premium). Short Cov arrows only when each of the 3+ strikes moved >= Rs 50 lakh in
  15 min (analytics.BIG_MOVE). Trapped list shows "At stake" (lots x lot x built price) and the loss.
- Owner 26 Nov 2026 (3rd round): VWAP bands stronger (±1 cyan, ±2 orange, dashed); chart type Candles / Heikin-Ashi
  (display only, indicators on real prices); instrument Spot / Near future / Next future. Opening ranges 5 / 15 / 30
  min. Today's volume profile from 09:15 (flow.day_profile, sky blue, 70% VA). Big trades (desk/bigtrades.py): one
  trade >= Rs 50 lakh, side from the bid/ask a moment before (tick rule in between), counted once via the day volume;
  futures' trades drawn at the index price on the spot chart; option charts show their own. SMC (desk/smc.py):
  BOS / CHoCH, order blocks (last 3 each way, last few sessions, <= 0.6% tall), today's open FVGs (last 4),
  premium / discount. Guide for the owner: docs/DESK_GUIDE.pdf (screens from the demo).
- FYERS DAILY LIMIT (26 Nov 2026): Standard plan = 5,000 REST calls/DAY (and 5/s), shared by desk + terminal +
  arbitrage. desk.fyers.Budget counts calls per day in data/api_calls.json; paced() raises DailyLimit when FYERS says
  "requests/day" (is_daily_limit). Desk: candles from the live websocket (_live_candle), REST history only at start
  (saved copy in data/minutes, then today only) and every 15 min; chain every 60 s; backup quotes only when the feed
  is down; at the limit the page keeps working on saved data + live prices (status turns red). Arbitrage history
  stops at 3,500/run and keeps RESERVE 1,000; the live scanner paces itself to ~1,500/day. Never design a loop that
  calls FYERS REST every few seconds.
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
