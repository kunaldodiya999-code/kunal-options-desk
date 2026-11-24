# Kunal Options Desk

One page for NIFTY / BANK NIFTY / SENSEX options: a TradingView-style chart (light and dark), an OI profile, option
chain readings, option maths and Greeks, trapped positions and hedging pressure. Data from FYERS (Dhan later).
Runs only on your PC (127.0.0.1). It places NO orders (trading comes in phase 3, paper first).

## First time (Windows, PowerShell)
Folder: `C:\Users\USER\Desktop\Kunal\kunal-options-desk`
```
python setup_pc.py
```
It makes `.venv`, installs everything and runs the tests (should end with "passed").

## Every day
Double-click `start_desk.bat` (or `.venv\Scripts\python.exe run.py`). The browser opens. First time it asks for
your FYERS app (App ID, Secret, Redirect URL from myapi.fyers.in, saved in `.env`); then log in each morning.
To see the page without FYERS: `.venv\Scripts\python.exe run.py --demo` (pretend prices, NOT real).

## What is on the page
- Chart: candles of the future (or the index with the future's volume), volume split bull/bear, VWAP, bulls' and
  bears' VWAP, EMA 1/2, day's open, previous day H/L/C, first 30-minute range, bull/bear strip.
- OI profile at each strike, two tick-boxes: **Total (live) OI** and **OI change today**. Both ticked = both shown.
  Calls red above, puts green below; values inside the bars (setting). Setting to align strikes to the future (basis).
- Marks with hover text: lean changes, calls/puts added or exiting, divergence, trapped.
- Buying − selling pane (estimated from where candles close) with an adaptive average (KAMA).
- ATM call and put charts (strike can be chosen).
- What the options are saying (lean + cards), summary strip, OI change chart, chain with readings
  (buying / writing / covering / unwinding over 15 minutes), IV / delta / theta (Black-76, calculated here).
- Option maths (straddle break-even, theta per hour, gamma blast, now / 15 min / open), trapped positions,
  hedging pressure (lots hedged per 50-point move).
- Every reading is a rule of thumb, not a tested signal. OI never says who traded.

## Saved on the PC (never in git)
`data/chain` (one option chain per minute), `data/ticks` (every live tick, for phase 2), `data/master`, token.

## Phases
1. This page (done). 2. Order-flow studies from the recorded ticks. 3. Paper trade panel, discipline rules, journal.

Tests: `.venv\Scripts\python.exe -m pytest tests -q`
