r"""Start the options desk:  .venv\Scripts\python.exe run.py   (or double-click start_desk.bat)

  --demo    pretend market (not real prices) to look at the page without FYERS
  --no-open do not open the browser
"""

import argparse
import time
import webbrowser

from desk.service import DeskService


def main() -> None:
    ap = argparse.ArgumentParser(description="Kunal Options Desk")
    ap.add_argument("--demo", action="store_true", help="pretend market, no FYERS")
    ap.add_argument("--no-open", action="store_true", help="do not open the browser")
    ap.add_argument("--port", type=int, default=None)
    a = ap.parse_args()
    if a.demo:
        from desk.demo import DemoClock, DemoFyers, demo_master
        clock = DemoClock()
        svc = DeskService(client=DemoFyers(clock), master_loader=demo_master(clock), start_feed=False, clock=clock,
                          port=a.port)
        svc.note("DEMO: pretend market, NOT real prices")
    else:
        svc = DeskService(port=a.port)
    svc.start()
    print("\nKunal Options Desk is running. Open this address in your browser:\n\n  " + svc.url +
          "\n\nKeep this window open. Press Ctrl+C here to stop.\n", flush=True)
    if not a.no_open:
        webbrowser.open(svc.url)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("stopped")


if __name__ == "__main__":
    main()
