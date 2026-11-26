"""Option arbitrage: live scanner in market hours. Easiest: double-click arbitrage_live.bat. Never places orders."""

import webbrowser
from datetime import datetime

from arb_history import login
from arbitrage.costs import Costs
from arbitrage.live import run, write_page
from arbitrage.universe import from_master
from desk.candles import IST
from desk.fyers import data_dir, load_master


def main() -> None:
    client = login()
    folder = data_dir() / "arbitrage"
    folder.mkdir(parents=True, exist_ok=True)
    page = folder / "live.html"
    write_page(page, [], "starting...")
    webbrowser.open(page.as_uri())
    load = lambda d: from_master({m: load_master(m, d) for m in ("NSE_FO", "BSE_FO")}, d)
    try:
        run(client, load, folder, Costs.load(folder / "costs.json"))
    except KeyboardInterrupt:
        print("stopped")


if __name__ == "__main__":
    main()
