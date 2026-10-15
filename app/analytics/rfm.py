"""RFM over hashed payer VPAs: who are the regulars, and which of them are drifting away."""
from datetime import datetime

import pandas as pd

from app import db
from app.config import settings

LOOKBACK_DAYS = 90
MIN_VISITS = 6          # a "regular" paid at least this often in the lookback


def payer_stats(merchant_id: str, now: datetime) -> pd.DataFrame:
    since = (now - pd.Timedelta(days=LOOKBACK_DAYS)).isoformat()
    tx = db.rows("SELECT ts, amount, payer_hash FROM transactions WHERE merchant_id=? AND ts>=? AND ts<?",
                 merchant_id, since, now.isoformat())
    df = pd.DataFrame(tx)
    df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.tz_convert(settings.tz)
    g = df.groupby("payer_hash")
    stats = pd.DataFrame({
        "visits": g.size(),
        "monetary": g["amount"].sum(),
        "avg_ticket": g["amount"].mean(),
        "last_visit": g["ts"].max(),
        "first_visit": g["ts"].min(),
    })
    stats["recency_days"] = (now - stats["last_visit"]).dt.total_seconds() / 86400
    active_span = ((stats["last_visit"] - stats["first_visit"]).dt.total_seconds() / 86400).clip(lower=1)
    stats["gap_days"] = active_span / (stats["visits"] - 1).clip(lower=1)  # their usual time between visits
    return stats


def segments(merchant_id: str, now: datetime) -> pd.DataFrame:
    s = payer_stats(merchant_id, now)
    s = s[s["visits"] >= MIN_VISITS].copy()

    def label(r):
        if r.recency_days > max(7, 3 * r.gap_days):
            return "at_risk"
        if r.monetary >= s["monetary"].quantile(0.8):
            return "high_spender"
        return "loyal"

    s["segment"] = s.apply(label, axis=1)
    return s


def at_risk(merchant_id: str, now: datetime) -> pd.DataFrame:
    """Drifting regulars, most valuable first."""
    s = segments(merchant_id, now)
    return s[s["segment"] == "at_risk"].sort_values("monetary", ascending=False)
