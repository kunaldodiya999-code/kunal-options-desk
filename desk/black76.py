"""Black-76 option maths on the forward price (index options are priced off the futures/forward; rate taken as 0).

All Greeks are in the units a trader reads on the screen:
  delta  premium points per 1 index point
  gamma  delta gained per 1 index point
  theta  premium points lost per CALENDAR DAY (negative)
  vega   premium points per 1 point of implied volatility (1% = 1 point)
Implied volatility is solved by bisection (robust; no failure on deep in/out-of-the-money options).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

YEAR_DAYS = 365.0
MIN_T = 1.0 / (YEAR_DAYS * 24 * 60)          # one minute: never divide by a zero time


def _n(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


def _cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def price(forward: float, strike: float, years: float, vol: float, call: bool) -> float:
    t = max(years, MIN_T)
    if vol <= 0:
        return max(forward - strike, 0.0) if call else max(strike - forward, 0.0)
    sd = vol * math.sqrt(t)
    d1 = (math.log(forward / strike) + 0.5 * sd * sd) / sd
    d2 = d1 - sd
    if call:
        return forward * _cdf(d1) - strike * _cdf(d2)
    return strike * _cdf(-d2) - forward * _cdf(-d1)


def implied_vol(premium: float, forward: float, strike: float, years: float, call: bool) -> Optional[float]:
    """Volatility (0.25 = 25%) that gives ``premium``; None when the premium is below intrinsic or not usable."""
    intrinsic = max(forward - strike, 0.0) if call else max(strike - forward, 0.0)
    if premium is None or premium <= 0 or forward <= 0 or strike <= 0 or premium < intrinsic - 1e-9:
        return None
    lo, hi = 1e-4, 5.0
    if price(forward, strike, years, hi, call) < premium:
        return None
    for _ in range(80):
        mid = (lo + hi) / 2
        if price(forward, strike, years, mid, call) < premium:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


@dataclass(frozen=True)
class Greeks:
    iv: float              # 0.21 = 21%
    delta: float
    gamma: float
    theta: float           # per calendar day
    vega: float            # per 1 vol point


def greeks(forward: float, strike: float, years: float, vol: float, call: bool) -> Greeks:
    t = max(years, MIN_T)
    sd = vol * math.sqrt(t)
    d1 = (math.log(forward / strike) + 0.5 * sd * sd) / sd
    delta = _cdf(d1) if call else _cdf(d1) - 1.0
    gamma = _n(d1) / (forward * sd)
    theta = -forward * _n(d1) * vol / (2 * math.sqrt(t)) / YEAR_DAYS
    vega = forward * _n(d1) * math.sqrt(t) / 100.0
    return Greeks(vol, delta, gamma, theta, vega)


def implied_forward(strike: float, call_price: float, put_price: float) -> float:
    """Put-call parity at one strike (rate 0): forward = strike + call - put. The video's 'price implied by the
    options'."""
    return strike + call_price - put_price


__all__ = ["Greeks", "greeks", "implied_forward", "implied_vol", "price"]
