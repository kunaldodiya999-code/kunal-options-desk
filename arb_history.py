r"""Option arbitrage: check the past (default one year). Easiest: double-click arbitrage_history.bat.

  .venv\Scripts\python.exe arb_history.py                 everything, last 365 days (several hours; resumes)
  .venv\Scripts\python.exe arb_history.py --only RELIANCE,NIFTY --days 60     a quick try
  .venv\Scripts\python.exe arb_history.py --report-only   rebuild the report from what is already collected
Results: data\arbitrage\report\summary.txt (paste it to Claude), report.html, events.csv
"""

import argparse
import sys
import webbrowser
from datetime import datetime

from arbitrage.costs import Costs
from arbitrage.history import Cache, Fetcher, Runner, Stop
from arbitrage.report import build
from arbitrage.universe import from_master
from desk.candles import IST
from desk.fyers import Fyers, credentials, data_dir, load_master, saved_token


def login():
    c = credentials()
    token = saved_token(None, c["client_id"])
    if not c["client_id"] or not token:
        print("\nNo FYERS login for today. Double-click start_desk.bat, log in to FYERS in the page that opens,\n"
              "close it, then run this again.")
        sys.exit(1)
    return Fyers(c["client_id"], token)


def main() -> None:
    ap = argparse.ArgumentParser(description="Option arbitrage history check")
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--only", default="", help="comma list, e.g. RELIANCE,NIFTY")
    ap.add_argument("--indexes-only", action="store_true")
    ap.add_argument("--stocks-only", action="store_true")
    ap.add_argument("--report-only", action="store_true")
    ap.add_argument("--max-calls", type=int, default=90000, help="stop after this many FYERS calls (daily limit)")
    ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args()
    folder = data_dir() / "arbitrage"
    cache = Cache(folder / "cache.sqlite")
    calls = 0
    if not a.report_only:
        client = login()
        today = datetime.now(IST).date()
        masters = {m: load_master(m, today) for m in ("NSE_FO", "BSE_FO")}
        universe = from_master(masters, today)
        print(f"{len(universe)} underlyings (F&O stocks + NIFTY, BANK NIFTY, SENSEX)")
        fetcher = Fetcher(client.model, cache, today, max_calls=a.max_calls)
        runner = Runner(fetcher, universe, Costs.load(folder / "costs.json"), days=a.days)
        only = {x.strip().upper() for x in a.only.split(",") if x.strip()} or None
        try:
            jobs = runner.jobs(only, indexes=not a.stocks_only, stocks=not a.indexes_only)
            runner.run(jobs, cache)
            print("\nALL DONE.")
        except Stop as stop:
            print(f"\nSTOPPED: {stop}")
        except KeyboardInterrupt:
            print("\nStopped by you. Run it again later: it carries on where it stopped.")
        calls = fetcher.calls
    text = build(cache.results(), folder / "report", a.days, calls)
    print("\n" + text)
    print(f"\nReport: {folder / 'report' / 'report.html'}\nSummary to send Claude: {folder / 'report' / 'summary.txt'}")
    if not a.no_open:
        webbrowser.open((folder / "report" / "report.html").as_uri())


if __name__ == "__main__":
    main()
