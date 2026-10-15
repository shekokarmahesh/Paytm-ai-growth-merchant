"""Sales facts for a day, from QR payments only."""
from datetime import date, timedelta

from app import db


def day_totals(merchant_id: str, day: date) -> dict:
    r = db.one("""SELECT COUNT(*) AS payments, COALESCE(SUM(amount), 0) AS sales,
                         COUNT(DISTINCT payer_hash) AS customers
                  FROM transactions WHERE merchant_id=? AND ts>=? AND ts<?""",
               merchant_id, day.isoformat(), (day + timedelta(days=1)).isoformat())
    peak = db.one("""SELECT CAST(substr(ts, 12, 2) AS INTEGER) AS hour, COUNT(*) AS n
                     FROM transactions WHERE merchant_id=? AND ts>=? AND ts<?
                     GROUP BY hour ORDER BY n DESC LIMIT 1""",
                  merchant_id, day.isoformat(), (day + timedelta(days=1)).isoformat())
    return {"sales": round(r["sales"]), "payments": r["payments"], "customers": r["customers"],
            "peak_hour": peak["hour"] if peak else None}


def yesterday_vs_last_week(merchant_id: str, today: date) -> dict:
    y = today - timedelta(days=1)
    a, b = day_totals(merchant_id, y), day_totals(merchant_id, y - timedelta(days=7))
    change = (a["sales"] - b["sales"]) / b["sales"] * 100 if b["sales"] else 0.0
    return {"day": y.isoformat(), "weekday": y.strftime("%A"), **a,
            "last_week_sales": b["sales"], "change_pct": round(change)}
