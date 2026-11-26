"""Charges of one arbitrage, per lot, round trip (both legs opened and both closed), as on the FYERS / NSE schedule
of Nov 2026. Every number is a setting (data/arbitrage/costs.json overrides it) because charges change by circular.

Exit is assumed at the option's intrinsic value (where it ends at expiry), so STT on selling the option is charged on
that. Retail brokers close in-the-money STOCK options before expiry (physical delivery), so we close both legs too.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Costs:
    brokerage_per_order: float = 20.0      # FYERS flat, 4 orders
    stt_option_sell: float = 0.001         # 0.1% of premium on the sell side (from 1 Oct 2024)
    stt_future_sell: float = 0.0002        # 0.02% of contract value on the sell side (from 1 Oct 2024)
    txn_option: float = 0.0003503          # NSE options, of premium (both sides)
    txn_future: float = 0.0000173          # NSE futures, of contract value (both sides)
    stamp_option_buy: float = 0.00003      # 0.003% on the buy side
    stamp_future_buy: float = 0.00002      # 0.002% on the buy side
    sebi_per_crore: float = 10.0
    gst: float = 0.18                      # on brokerage + exchange + SEBI charges
    margin_stock_future: float = 0.20      # money blocked for the future leg, share of contract value
    margin_index_future: float = 0.12

    @staticmethod
    def load(path: Path) -> "Costs":
        try:
            return Costs(**{**asdict(Costs()), **json.loads(Path(path).read_text(encoding="utf-8"))})
        except (OSError, ValueError, TypeError):
            return Costs()

    def round_trip(self, option_in: float, option_out: float, future: float, units: int) -> float:
        """Rupees for one lot: buy option at option_in, sell it at option_out, future opened and closed at future."""
        prem_turn = (option_in + option_out) * units
        fut_turn = 2 * future * units
        brokerage = 4 * self.brokerage_per_order
        exchange = prem_turn * self.txn_option + fut_turn * self.txn_future
        sebi = (prem_turn + fut_turn) * self.sebi_per_crore / 1e7
        stt = option_out * units * self.stt_option_sell + future * units * self.stt_future_sell
        stamp = option_in * units * self.stamp_option_buy + future * units * self.stamp_future_buy
        return brokerage + exchange + sebi + stt + stamp + self.gst * (brokerage + exchange + sebi)

    def capital(self, option_in: float, future: float, units: int, index: bool) -> float:
        """Money needed for one lot: the option premium paid plus the future's margin."""
        return option_in * units + future * units * (self.margin_index_future if index else self.margin_stock_future)


__all__ = ["Costs"]
