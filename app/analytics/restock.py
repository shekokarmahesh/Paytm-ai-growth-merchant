"""Time-to-stockout and reorder quantities for POS merchants (SKU-level data)."""
import math
from dataclasses import dataclass, asdict
from datetime import date, timedelta

from app import db
from app.analytics.synth import DIWALI

BUFFER_DAYS = 2
COVER_DAYS = 14
FESTIVE_SEASON_DAYS = 45  # demand builds over the weeks before Diwali


@dataclass
class Line:
    sku: str
    name: str
    category: str
    stock: int
    daily_rate: float
    days_left: float
    lead_days: int
    reorder_qty: int
    unit_cost: float
    line_value: float
    distributor: str


def run_rate(units_7: float, units_28: float, today: date) -> float:
    """Blend recent and monthly pace; in the pre-Diwali season, extrapolate the acceleration (capped at 1.5x)."""
    rate = 0.6 * units_7 / 7 + 0.4 * units_28 / 28
    accel = (units_7 / 7) / max(units_28 / 28, 1e-6)
    if 0 <= (DIWALI - today).days <= FESTIVE_SEASON_DAYS and accel > 1:
        rate *= min(accel, 1.5)
    return rate


def reorder_qty(rate: float, lead: int, stock: int) -> int:
    return max(0, math.ceil(rate * (lead + COVER_DAYS) - stock))


def plan(merchant_id: str, today: date) -> dict:
    d7, d28 = (today - timedelta(days=7)).isoformat(), (today - timedelta(days=28)).isoformat()
    rows = db.rows("""
        SELECT s.*, COALESCE(SUM(CASE WHEN x.day >= ? THEN x.units END), 0) AS u7,
                    COALESCE(SUM(x.units), 0) AS u28
        FROM skus s LEFT JOIN sku_sales x
          ON x.merchant_id = s.merchant_id AND x.sku = s.sku AND x.day >= ? AND x.day < ?
        WHERE s.merchant_id = ? GROUP BY s.sku""", d7, d28, today.isoformat(), merchant_id)
    lines = []
    for r in rows:
        rate = run_rate(r["u7"], r["u28"], today)
        days_left = r["stock"] / rate if rate > 0 else math.inf
        if days_left > r["lead_days"] + BUFFER_DAYS:
            continue
        qty = reorder_qty(rate, r["lead_days"], r["stock"])
        if qty == 0:
            continue
        lines.append(Line(r["sku"], r["name"], r["category"], r["stock"], round(rate, 2), round(days_left, 1),
                          r["lead_days"], qty, r["unit_cost"], round(qty * r["unit_cost"]), r["distributor"]))
    lines.sort(key=lambda l: l.days_left)

    week_sales = db.one("""SELECT COALESCE(SUM(x.units * s.price), 0) AS v FROM sku_sales x
        JOIN skus s ON s.merchant_id = x.merchant_id AND s.sku = x.sku
        WHERE x.merchant_id = ? AND x.day >= ? AND x.day < ?""", merchant_id, d7, today.isoformat())["v"]
    total = sum(l.line_value for l in lines)
    return {
        "lines": [asdict(l) for l in lines],
        "po_value": round(total),
        "week_sales": round(week_sales),
        "cash_gap": total > week_sales,   # PO costs more than a week of takings
        "days_to_diwali": (DIWALI - today).days,
    }
