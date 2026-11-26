# Kunal Options Desk

One page for NIFTY / BANK NIFTY / SENSEX options: a TradingView-style chart (light and dark), an OI profile, option
chain readings, option maths and Greeks, trapped positions and hedging pressure. Data from FYERS (Dhan later).
Runs only on your PC (127.0.0.1). It places NO orders (trading comes in phase 3, paper first).

## The four files you double-click (in File Explorer, inside the kunal-options-desk folder)
| File | What it does |
|---|---|
| `setup_desk.bat` | Installs everything. Run once after downloading (safe to run again). Ends with "ALL DONE". |
| `demo_desk.bat` | Opens the desk with PRETEND prices, to look around. Not real. |
| `start_desk.bat` | Opens the desk with REAL FYERS prices. Keep its black window open while you use the desk. |
| `update_desk.bat` | Downloads Claude's latest changes from GitHub and sets up again. |

To stop the desk: click its black window and press Ctrl+C (or just close the window).

## Option arbitrage scanner (separate tool, see docs/OPTION_ARBITRAGE.md)
| File | What it does |
|---|---|
| `arbitrage_history.bat` | Checks the last year for options that traded 5%+ below their value. Several hours; resumes. |
| `arbitrage_live.bat` | During market hours, looks for them live (option ask vs future). Never places orders. |

## FYERS login
The desk reads your FYERS app details (App ID, Secret, Redirect URL) from the `kunal-fyers-terminal` folder when it
sits next to this one, and uses the terminal's login of today. Otherwise the page asks for them once and you log in
once a day (Open FYERS login -> copy the whole address the browser lands on -> paste -> Authorize).

## What is on the page
- Chart: candles of the future (or the index with the future's volume), volume split bull/bear, VWAP, bulls' and
  bears' VWAP, EMA 1/2, day's open, previous day H/L/C, first 30-minute range, bull/bear strip.
- OI profile at each strike, two tick-boxes: **Total (live) OI** and **OI change today**. Both ticked = both shown.
  Calls red above, puts green below; values inside the bars (setting). Setting to align strikes to the future (basis).
- Marks with hover text: lean changes, calls/puts added or exiting, divergence, trapped.
- Buying - selling pane (estimated from where candles close) with an adaptive average (KAMA).
- ATM call and put charts (strike can be chosen).
- What the options are saying (lean + cards), summary strip, OI change chart, chain with readings
  (buying / writing / covering / unwinding over 15 minutes), IV / delta / theta (Black-76, calculated here).
- Option maths (straddle break-even, theta per hour, gamma blast, now / 15 min / open), trapped positions,
  hedging pressure (lots hedged per 50-point move).
- Every reading is a rule of thumb, not a tested signal. OI never says who traded.

## Saved on the PC (never in git)
`data/chain` (one option chain per minute), `data/ticks` (every live tick, for phase 2), `data/master`, token, `.env`.

## Phases
1. This page (done). 2. Order-flow studies from the recorded ticks. 3. Paper trade panel, discipline rules, journal.

Tests (inside the folder): `.venv\Scripts\python.exe -m pytest tests -q`
