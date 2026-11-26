# Option arbitrage scanner (owner 26 Nov 2026)

**Goal:** find options that trade **5% or more below their value**, after every charge. Below 5% is not useful (owner).

## The trade
- **CALL:** buy the call at C and sell the same-expiry future at F. At expiry both settle, so the locked profit is (F − K) − C.
- **PUT:** buy the put at P and buy the future at F. The locked profit is (K − F) − P.
- **Discount** = locked profit ÷ value, where value is F − K for a call or K − F for a put. The check is made against the **future**, not the spot price: NSE options settle only at expiry, so the future decides what can be locked.
- **Index weekly options** have no future expiring the same day. For these the value uses index + (future − index) × (time to the option's expiry ÷ time to the future's expiry).
- **Which options are checked:** only those at least 2% in the money. That means 2% to 15% in the money for stocks and 2% to 6% for indexes.

## Exchange price rules (checked 26 Nov 2026)
- **NSE Limit Price Protection (LPP):** a limit order priced too far from the recent traded price is rejected. The reference is the average traded price of the last 30 seconds; if there are no trades, a theoretical price is used. Circular FAOP/54242 (Oct 2022) started it, and FAOP/64995 (Nov 2024) added a cap during stock cooling-off periods.
  - Broker summaries give the band for options as about ±40% of the reference, or ±₹20 when the reference is ₹50 or less.
  - BSE uses about 40% for SENSEX options.
  - Effect on this scanner: a discount that is actually trading is inside the band by definition, so buying at it is allowed. LPP only stops orders placed far away from where the option trades.
- **Market Price Protection (MPP):** market orders are turned into limit orders within a few % of the last price. We never use market orders anyway (owner rule).
- **Not confirmed:** a document the owner shared says the outer operating range puts a floor near intrinsic value for deep in-the-money options. I could not find an NSE source for this.

## Charges
`arbitrage/costs.py` holds every charge, and `data/arbitrage/costs.json` on the PC can override them:
- brokerage ₹20 × 4 orders;
- STT 0.1% on the option sale and 0.02% on the future sale;
- exchange charges, stamp duty, SEBI fee, and GST on top;
- margin for the future leg: 20% for stocks, 12% for indexes.

Both legs are assumed closed at the value, because brokers close in-the-money stock options before expiry (physical delivery).

## History check (`arbitrage_history.bat` / `arb_history.py`)
- **What it uses:** FYERS 1-minute candles. Expired contracts come from `fno_historical_data`, past expiries from `expiry_dates`, and expired symbols from `history_underlying_symbols`. If FYERS cannot list an old expiry's symbols, the names are built using today's strike gap.
- **What counts:** only minutes where the option actually **traded**.
  - **SURE:** even the minute's high option price against its least favourable future price gives 5% or more.
- **Pace and limits:** about 3 FYERS calls a second. A run stops itself at 90,000 calls (the daily limit).
- **Resuming:** everything FYERS sends is cached in `data/arbitrage/cache.sqlite`, so a run carries on where it stopped. It works newest month first.
- **Output:** `data/arbitrage/report/summary.txt` (paste it to Claude), `report.html` and `events.csv`.
- **Limits of the check:**
  - Candles are trades, not offers.
  - Only today's F&O stock list is scanned.
  - Today's lot sizes are used.
  - Only the near-month series of each expiry is checked.

## Live scanner (`arbitrage_live.bat` / `arb_live.py`)
- **When:** 09:15 to 15:30 on weekdays.
- **What it reads:** every near-month future and index, plus every option in the in-the-money range above, about once a minute.
- **Prices used:**
  - you **pay the option's ASK**;
  - for a call, you sell the future at its BID;
  - for a put, you buy the future at its ASK.
- **When it finds 5% or more after charges:** it beeps, prints the opportunity, adds it to `data/arbitrage/live_hits.csv` and shows it on `live.html` (refreshes every 15 s).
- **It never places an order.**
