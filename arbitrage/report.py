"""The report of a history run: summary.txt (to paste to Claude), events.csv (Excel) and report.html (offline)."""

from __future__ import annotations

import csv
import html
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from arbitrage.core import BUCKETS, bucket_name
from desk.candles import IST

ORDER = [bucket_name((lo + hi) / 2 if hi < 1 else lo) for lo, hi in BUCKETS]


def hhmm(ts: int) -> str:
    return datetime.fromtimestamp(int(ts), IST).strftime("%d %b %Y %H:%M")


def build(results: list[dict], folder: Path, days: int, calls: int = 0) -> str:
    folder.mkdir(parents=True, exist_ok=True)
    events = [e for r in results for e in r["events"]]
    events.sort(key=lambda e: -e["net_per_lot"])
    done = [r for r in results if r["status"].startswith("ok")]
    no_data = [r for r in results if not r["status"].startswith("ok")]
    unds = {r["underlying"] for r in results}
    months = sorted({r["expiry"][:7] for r in results})
    by_bucket = Counter(e["bucket"] for e in events)
    sure_bucket = Counter(e["bucket"] for e in events if e["sure"])
    by_month = Counter(datetime.fromtimestamp(e["start"], IST).strftime("%Y-%m") for e in events)
    by_und = defaultdict(lambda: [0, 0.0])
    for e in events:
        by_und[e["underlying"]][0] += 1
        by_und[e["underlying"]][1] += e["net_per_lot"]

    lines = [f"OPTION ARBITRAGE - HISTORY CHECK ({datetime.now(IST):%d %b %Y %H:%M})",
             f"Asked: last {days} days, options trading 5% or more below their value (future - strike), after charges.",
             f"Scanned: {len(unds)} underlyings, {len(results)} underlying x expiry pieces ({months[0] if months else '-'}"
             f" to {months[-1] if months else '-'}); with data: {len(done)}; without data: {len(no_data)}."
             + (f" FYERS calls this run: {calls}." if calls else ""),
             f"Options with candles: {sum(r['with_data'] for r in results)} of {sum(r['options'] for r in results)} checked.",
             "", f"EVENTS FOUND: {len(events)} (an event = minutes in a row where the option traded 5%+ below value)",
             f"  of which SURE (even the minute's worst prices give 5%+): {sum(1 for e in events if e['sure'])}", ""]
    lines.append("BY SIZE OF THE DISCOUNT        all   sure")
    for b in ORDER:
        lines.append(f"  {b:<28}{by_bucket.get(b, 0):>5}  {sure_bucket.get(b, 0):>5}")
    lines += ["", "BY MONTH"] + [f"  {m}  {by_month[m]}" for m in sorted(by_month)]
    lines += ["", "TOP 15 UNDERLYINGS (events, total net Rs per lot)"]
    for name, (n, net) in sorted(by_und.items(), key=lambda x: -x[1][1])[:15]:
        lines.append(f"  {name:<14}{n:>5}  Rs {net:,.0f}")
    lines += ["", "TOP 25 EVENTS BY NET PROFIT PER LOT"]
    for e in events[:25]:
        lines.append(f"  {e['underlying']:<12}{e['option']:<14}exp {e['expiry']}  {hhmm(e['start'])}  {e['minutes']} min"
                     f"  disc {e['discount']:.1f}%  paid {e['price']} vs value {e['fair']}  lots traded {e['lots_traded']}"
                     f"  net Rs {e['net_per_lot']:,.0f}/lot  {e['return_pct']:.1f}% {'SURE' if e['sure'] else 'maybe'}")
    if no_data:
        reasons = Counter(r["status"].split(" for ")[0] for r in no_data)
        lines += ["", "PIECES WITHOUT DATA (why)"] + [f"  {k}: {v}" for k, v in reasons.most_common(8)]
    lines += ["", "READ ME: prices are TRADES (1-minute candles), not offers you could have taken. A 'maybe' event",
              "can be one small trade between other quotes. 'Lots traded' shows how much changed hands at a discount."]
    text = "\n".join(lines)
    (folder / "summary.txt").write_text(text, encoding="utf-8")

    cols = ["underlying", "expiry", "option", "start", "minutes", "discount", "bucket", "sure", "price", "fair", "ref",
            "lots_traded", "net_per_lot", "charges_per_lot", "capital_per_lot", "return_pct"]
    with open(folder / "events.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for e in events:
            w.writerow([hhmm(e[c]) if c == "start" else e[c] for c in cols])

    rows = "".join("<tr>" + "".join(f"<td>{html.escape(str(hhmm(e[c]) if c == 'start' else e[c]))}</td>" for c in cols)
                   + "</tr>" for e in events[:2000])
    page = f"""<!doctype html><html><head><meta charset="utf-8"><title>Option arbitrage history</title>
<style>body{{font:13px Segoe UI,sans-serif;margin:20px;background:#131722;color:#d1d4dc}}
table{{border-collapse:collapse}}td,th{{padding:4px 8px;border-bottom:1px solid #2a2e39;text-align:right}}
th{{color:#868993;position:sticky;top:0;background:#131722}}pre{{background:#1e222d;padding:12px;border-radius:6px}}</style>
</head><body><h2>Option arbitrage: history check</h2><pre>{html.escape(text)}</pre>
<h3>Events (best first, up to 2000)</h3><table><tr>{''.join(f'<th>{c}</th>' for c in cols)}</tr>{rows}</table></body></html>"""
    (folder / "report.html").write_text(page, encoding="utf-8")
    return text


__all__ = ["build"]
