"""Option arbitrage scanner (owner 26 Nov 2026): options trading 5% or more BELOW their value locked by the future.

CALL: buy the call at C, sell the same-expiry future at F  -> at expiry both settle, locked = (F - K) - C.
PUT : buy the put  at P, buy  the same-expiry future at F  -> locked = (K - F) - P.
Discount = locked / intrinsic (F - K or K - F). Owner: only 5% and above matters. Information only: no orders.
"""
