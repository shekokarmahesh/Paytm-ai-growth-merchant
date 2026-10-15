"""Margin-safe cashback optimiser.

Cashback goes only to vouchered at-risk regulars, so cost is limited to those who redeem. For each
candidate cashback d (5..15%, never above half the shop margin m):

    profit(d) = N · T · [ lift(d) · (m − d)  −  p0 · d ]

N = target regulars, T = their average ticket, p0 = chance a target would have visited in the
window anyway (we pay cashback on that visit without gaining anything), lift(d) = extra visit
probability the cashback buys. Pick the d with the highest profit; no campaign if none is positive.

lift(d) is an assumed diminishing-returns curve — a hypothesis to be calibrated in a merchant pilot.
"""
import math
from dataclasses import dataclass

D_MIN, D_MAX = 0.05, 0.15
LIFT_MAX = 0.30   # at most 30% of drifting regulars come back, however big the cashback
LIFT_K = 12.0     # how fast lift saturates with d


def lift(d: float, hours: float = 3) -> float:
    """Extra visit probability; a shorter window converts fewer people."""
    window = min(1.0, hours / 3) ** 0.5
    return LIFT_MAX * (1 - math.exp(-LIFT_K * d)) * window


def max_safe_discount(margin: float) -> float:
    return min(D_MAX, margin / 2)


@dataclass
class Plan:
    discount_pct: float      # whole percent
    duration_hours: float
    targets: int
    avg_ticket: float
    expected_visits: float   # extra visits the cashback buys
    expected_sales: float    # extra sales from those visits
    cashback_cost: float     # cashback paid, incl. on visits that would have happened anyway
    expected_profit: float   # net of goods margin and cashback


def evaluate(d: float, hours: float, targets: int, avg_ticket: float, margin: float, p0: float) -> Plan:
    inc = lift(d, hours)
    extra_visits = targets * inc
    cost = targets * (inc + p0) * avg_ticket * d
    profit = targets * avg_ticket * (inc * (margin - d) - p0 * d)
    return Plan(round(d * 100), hours, targets, round(avg_ticket), round(extra_visits, 1),
                round(extra_visits * avg_ticket), round(cost), round(profit))


def optimise(targets: int, avg_ticket: float, margin: float, hours: float = 3, p0: float = 0.02) -> Plan | None:
    if targets <= 0:
        return None
    cap = max_safe_discount(margin)
    best = None
    for pct in range(round(D_MIN * 100), round(D_MAX * 100) + 1):
        d = pct / 100
        if d > cap + 1e-9:
            break
        p = evaluate(d, hours, targets, avg_ticket, margin, p0)
        if p.expected_profit > 0 and (best is None or p.expected_profit > best.expected_profit):
            best = p
    return best


def check(pct: float, hours: float, targets: int, avg_ticket: float, margin: float, p0: float = 0.02):
    """Validate a merchant-modified offer. Returns (plan, None) if safe, else (None, reason)."""
    d = pct / 100
    cap = max_safe_discount(margin)
    if d < D_MIN:
        return None, "below_min"
    if d > cap + 1e-9:
        return None, "above_cap"
    if not 0.5 <= hours <= 8:
        return None, "bad_duration"
    p = evaluate(d, hours, targets, avg_ticket, margin, p0)
    if p.expected_profit <= 0:
        return None, "loss_making"
    return p, None
