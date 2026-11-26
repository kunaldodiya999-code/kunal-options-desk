"""Builds the Kunal Options Desk guide (HTML -> PDF with the browser)."""
import sys
sys.path.insert(0, sys.argv[1])
from imgs import IMGS

SECTIONS = [
("How to read this guide", None, """
<p>The desk is one page. It reads FYERS every few seconds and turns the option chain into pictures and plain sentences.
The screens in this guide come from the <b>demo</b> (pretend prices), so the numbers in them mean nothing. Only the
layout and the way to read each part matter.</p>
<p><b>Golden rule:</b> nothing on this page is a buy or sell signal. Each part answers one question: <i>where is the money
sitting, who is under pressure, and how far can price realistically move?</i> You decide the trade.</p>"""),

("1. Top bar", "01_top", """
<ul><li><b>Index</b>: NIFTY, BANK NIFTY or SENSEX. <b>Timeframe</b>: 1, 3, 5 or 15 minutes.</li>
<li><b>Chart</b>: <i>Spot</i> (the index, with the near future's volume, owner rule), <i>Near future</i> or <i>Next future</i>.</li>
<li><b>Candles / Heikin-Ashi</b>: Heikin-Ashi smooths the candles so a trend is easier to see. It is display only:
every line and level still uses the real prices.</li>
<li><b>Options panel</b> shows or hides the lower half. <b>Theme</b> switches light and dark. The status reads
<i>live · FYERS</i> when data is flowing.</li></ul>"""),

("2. Tick-boxes", "02_toggles", """
<p>Every drawing can be switched on or off. The desk remembers your choice. Start with few boxes ticked; a crowded chart
hides the candles.</p>
<ul><li><b>CHART</b>: volume, VWAP and its ±1 / ±2 deviation bands, day's open, previous day high/low/close, first 5 / 15 /
30 minute ranges, today's volume profile, big trades, Bollinger Bands, EMAs, near / next future lines.</li>
<li><b>OPTIONS</b>: the four profiles (OI, OI change, Delta, GEX), the call and put charts and the lower panels.</li>
<li><b>SMC</b>: break of structure / change of character, order blocks, fair value gaps, premium / discount.</li>
<li><b>MARKS</b>: small symbols on candles: lean changes, calls / puts added or exiting, divergence, trapped.</li></ul>"""),

("3. Main chart", "03_main", """
<p><b>Price and VWAP.</b> VWAP (blue) is the day's average traded price. Above it, buyers are in control on average. The
dashed <b>±1 deviation</b> band (cyan) holds most of the day's trading, and the <b>±2</b> band (orange) is stretched.
A move from ±2 back towards VWAP is common; holding outside ±1 for long means a trending day.</p>
<p><b>Levels.</b> Day's open, previous day high / low / close and the opening ranges (5, 15, 30 min). A break of the
opening range with volume often sets the day's direction.</p>
<p><b>Today's volume profile</b> (sky blue, starts at 09:15 and grows through the day). <b>POC</b> = the most traded
price today, which acts like a magnet. <b>VAH / VAL</b> = the 70% value area. Inside it = balance (range). Accepted
outside it = a new trend.</p>
<p><b>Profiles on the right</b> (each strike; calls on the upper bar, puts on the lower bar): <b>OI</b> (open contracts),
<b>OI chg</b> (added today; hollow = reduced), <b>Delta</b> (blue/orange) and <b>GEX</b> (purple/cyan). How to use Delta
and GEX is explained in section 11.</p>
<p><b>Dots and circles.</b> ● = trapped positions, ◆ = heaviest hedging strike; hover them for details. <b>Green / red
circles</b> = big trades of ₹50 lakh or more that hit the offer (buy, green) or the bid (sell, red). The size of the
circle grows with the rupee amount. Several same-colour circles in a row = a large player pushing one way.</p>
<p><b>SMC</b>: <b>BOS</b> = price broke the last swing in the trend's direction (trend continues). <b>CHoCH</b> = the first
break against the trend (possible turn). <b>Order block</b> = the last opposite candle before a strong break; price often
reacts when it comes back to it. <b>FVG</b> = a gap left by a fast move; price often comes back to fill it.
<b>Premium / discount</b> = the upper / lower part of the latest swing range. Buyers prefer discount, sellers premium.</p>"""),

("4. Buying − selling pane", "04_flow", """
<p>Each candle's volume is split by where it closed in its range (closed near the high = mostly buying). Bars = this
candle; blue line = running total for the day; orange = adaptive average. <b>Read it:</b> price making new highs while
the blue line does not = buying is tiring (divergence). Blue line crossing above orange = buying picking up.
Hover the pane for the values at any time. It is an estimate from candles, not real order data.</p>"""),

("5. Call and put charts", "05_cp", """
<p>The ATM call and put (or the strike you choose), with open / high / low / close at the top, volume, the option's
own VWAP, a <b>volume profile</b> (sky blue, with a 70% value area and VAH / POC / VAL) and a <b>delta profile</b>
(green = more buying than selling at that price). <b>Read it:</b> an option holding above its VWAP and its POC is being
bought; one falling through its VAL is being sold.</p>"""),

("6. What the options are saying", "06_saying", """
<p>Rule-of-thumb sentences about the last 15 minutes and the day so far: which side is being written or bought, put / call
ratio, walls getting stronger or weaker, implied volatility, expected range, theta and gamma risk. The <b>Lean</b> badge
sums them up (BULLISH / BEARISH / MIXED).</p>"""),

("7. Summary strip and OI added today", "07_strip", """
<p>Put/call OI ratio, calls and puts added today, the call wall above (most call OI), the put wall below (most put OI),
ATM implied volatility, the ATM straddle (the market's expected move to expiry) and hours left.</p>"""),

("", "08_oiline", """
<p><b>OI added today</b>: red = calls, green = puts. Hover for the values at any minute. Green rising above red = put
writers more active (supportive). Red rising faster = call writers more active (capping).</p>"""),

("8. Option chain", "09_chain", """
<p>Per side: <b>OI</b>, <b>Value</b> (OI × lot × premium, the money in that strike), <b>Week</b> (OI change since the
previous expiry), <b>Day</b>, <b>15 min</b>, <b>Reading</b>, <b>DEX</b>, <b>GEX</b>, IV, delta, theta, price.</p>
<ul><li><b>Call / Put Buying</b> = OI up and premium up. <b>Call / Put Writing</b> = OI up and premium down.</li>
<li><b>Short Cov</b> (yellow) = OI down and premium up: writers buying back. An arrow appears only when 3 or more
strikes in a row do it with ₹50 lakh or more each in 15 minutes. <b>Calls ▲ green</b> = call writers running (upside
fuel). <b>Puts ▼ red</b> = put writers running (downside fuel).</li>
<li><b>Long Unwind</b> = OI down and premium down: buyers giving up.</li></ul>"""),

("9. Trapped positions", "10_trap", """
<p>Each minute's new OI is filed at the premium of that moment. If buyers built at 164 and the option is now 120, they
are under water. A large trapped block near the price is fuel: when trapped call writers buy back (or trapped put
buyers sell out), the move speeds up. The list on the right shows the same blocks with <b>At stake</b> (lots × lot ×
build price) and the loss in rupees.</p>"""),

("10. Option maths and hedging pressure", "11_maths", """
<p>Break-even moves (how far the index must move in a day for a straddle, a call or a put to pay for its time decay),
delta, gamma and vega per point of theta, now vs 15 minutes ago vs the open. <b>Read it:</b> if the index usually moves
less than the straddle break-even, option buyers are paying too much for time.</p>"""),

("", "12_hedge", """
<p><b>Hedging pressure</b>: the lots of futures that writers must trade for a 50-point move, at each strike. The 5 tallest
bars are coloured (red = mostly call writers there, green = mostly put writers). The dashed line is the price.</p>"""),

("11. Right column: live prices, calls vs puts, trapped and key levels", "13_live", """
<p><b>Live prices</b>: chart price, ATM strike, ATM call and put, index, near future, the price implied by the options,
lot and expiry.</p>"""),

("", "14_pricing", """
<p><b>CALLS VS PUTS</b> answers three questions.</p>
<ol><li><b>Which side is expensive?</b> The options imply an index price (strike + call − put at ATM). The futures give
a fair price. If the options' price is <b>higher</b>, calls are dear and puts cheap: people are paying up for the upside.
If it is lower, puts are dear. A gap of a few points is noise. Treat 15–20+ points on NIFTY as meaningful.</li>
<li><b>Bias.</b> Three votes are counted: (a) the dear side, (b) the <b>25-delta skew</b>, i.e. whether calls or puts gained
in implied volatility since the open, and (c) the open-interest lean of the last 15 minutes. At least 2 of the 3 must
agree for CALL SIDE or PUT SIDE; otherwise it says NEUTRAL.</li>
<li><b>How far can it move?</b> The index's expected move = index × volatility × √time. The volatility used is the
average of ATM implied and the last hour's actual. About 2 times in 3 the index stays inside ± that number. The ₹ range is
what the ATM call or put gains if the index moves half to one expected move its way, after time decay.</li></ol>
<p><b>Your screenshot</b>, read the same way: <i>Calls are expensive, +28.2 pts</i> (options imply 25,934.70, futures
say 25,906.51): buyers were paying up for calls, which is one vote for the call side. <i>Skew −0.4 (open −0.5): little
change</i>, so no vote. <i>OI lean MIXED</i>, so no vote. That is 1 vote of 3, so <b>NEUTRAL</b>: no edge yet. <i>Volatility
11.8%</i> = average of 14.7% implied and 8.9% actual, so options were priced for more movement than the index was
delivering (good for writers, hard for buyers). <i>Next 30 min ±54 points</i>: if NIFTY rises 27–54 points quickly, the
25,950 CE should gain about ₹12–27; if it falls that much, the PE gains about ₹13–28. In 60 minutes the move is ±77 and
the gains ₹17–37 / ₹17–39, but you must wait twice as long and pay more time decay. <b>Conclusion from that box:</b>
neutral, with options a bit expensive versus actual movement. A buyer needs a fast, clean break, ideally confirmed by big
trades and Short Cov arrows, and should not sit and wait.</p>"""),

("", "15_levels", """
<p><b>Trapped and key levels</b>: call wall, put wall, heaviest hedging strike and the biggest trapped blocks with lots,
% down, build price, money at stake and the loss. These are the levels to watch on the chart.</p>"""),

("12. How to trade with the Delta and GEX profiles", None, """
<p><b>GEX (gamma exposure)</b> shows where option writers must re-hedge the most when price moves. Big GEX bars are the
strikes the market cares about.</p>
<ul><li><b>Near a big GEX strike price usually slows down and pins</b>, especially on expiry day, because writers
defend it and their hedging pushes against small moves. Do not buy options expecting a big move while price is stuck
between two large GEX strikes: time decay wins.</li>
<li><b>A clean break through the biggest GEX strike speeds the move up</b>, because the writers there are now losing
and have to hedge in the direction of the move (buy futures as it rises, sell as it falls). This is the moment option
buyers want. Look for confirmation: big trades the same colour, Short Cov arrows on that side, price outside VWAP ±1.</li>
<li><b>Targets</b>: after a break, the next big GEX strike is a natural place to take profit.</li></ul>
<p><b>Delta (DEX)</b> shows how much directional exposure the open options carry at each strike (calls +, puts −).</p>
<ul><li><b>The biggest call DEX above the price</b> is where call writers are most exposed. If price breaks it, they
must buy futures (or buy back calls), which adds fuel up. <b>The biggest put DEX below</b> is the mirror for a fall.</li>
<li><b>Watch it change.</b> Call DEX growing above while the price rises means writers are adding: a stronger ceiling.
Call DEX shrinking with Short Cov means writers are leaving: the ceiling is weakening.</li>
<li><b>Balance.</b> If total call DEX and total put DEX are about equal, there is no one-sided pressure. A big imbalance
shows which side has more to lose if price goes against it.</li></ul>
<p><b>A simple routine:</b> (1) Mark the biggest GEX and DEX strikes above and below the price. (2) Inside them, expect
a range and avoid buying options. (3) On a break with volume, big trades and Short Cov on that side, buy the ATM option
of that side. Exit near the next big GEX strike, or if price comes back inside the broken level. (4) Size small. These
are tools, not signals, so test them on paper first.</p>"""),
]


def build(out_html: str) -> None:
    parts = []
    for title, img, text in SECTIONS:
        head = (f'<h2>{title}</h2>' if title else '') + (f'<img src="{IMGS[img]}">' if img else '')
        parts.append('<section><div class="keep">' + head + '</div>' + text + '</section>')
    page = f"""<!doctype html><html><head><meta charset="utf-8"><title>Kunal Options Desk guide</title>
<style>
@page {{ size: A4; margin: 14mm 12mm; }}
body {{ font: 10.5pt/1.5 'Segoe UI', Roboto, Arial, sans-serif; color:#1b1f2a; }}
h1 {{ font-size: 22pt; margin: 0 0 4px; }} h2 {{ font-size: 13.5pt; margin: 14px 0 6px; color:#1d4ed8; }}
.sub {{ color:#5b6170; margin-bottom: 14px; }}
section {{ break-inside: auto; margin-bottom: 10px; }}
img {{ width: 100%; border-radius: 6px; border: 1px solid #d0d5de; margin: 4px 0 6px; break-inside: avoid; }}
ul, ol {{ margin: 4px 0 6px 18px; padding: 0; }} li {{ margin: 2px 0; }}
.keep {{ break-inside: avoid; page-break-inside: avoid; }} h2 {{ break-after: avoid; }}
.note {{ background:#fff7e6; border-left: 4px solid #f59e0b; padding: 8px 10px; margin: 10px 0; }}
</style></head><body>
<h1>Kunal Options Desk: page guide</h1>
<div class="sub">What each part shows, how to read it, and what to conclude. Screens from the demo (pretend prices).
Version of 26 Nov 2026.</div>
<div class="note">Tools, not trade calls. Every reading here is a rule of thumb from public option data. Open interest
never says who traded. Test on paper first.</div>
{''.join(parts)}
</body></html>"""
    open(out_html, 'w', encoding='utf-8').write(page)


if __name__ == '__main__':
    build(sys.argv[2])
