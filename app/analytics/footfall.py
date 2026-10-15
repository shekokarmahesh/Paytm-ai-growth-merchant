"""Hourly footfall forecast (gradient-boosted trees) and slump-window detection for QR merchants."""
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from app import db
from app.analytics.synth import FESTIVALS
from app.config import settings

OPEN_HOURS = range(7, 23)
SLUMP_RATIO = 0.55  # an hour is a slump if forecast < 55% of the day's average open hour


def hourly_counts(merchant_id: str, before: date) -> pd.DataFrame:
    """Complete day×hour grid of payment counts (zeros filled) for days before `before`."""
    tx = db.rows("SELECT ts FROM transactions WHERE merchant_id=? AND ts < ?", merchant_id, before.isoformat())
    ts = pd.to_datetime(pd.Series([r["ts"] for r in tx]), utc=True).dt.tz_convert(settings.tz)
    counts = pd.DataFrame({"day": ts.dt.date, "hour": ts.dt.hour}).value_counts().rename("n")
    days = pd.date_range(ts.min().date(), before - timedelta(days=1), freq="D").date
    grid = pd.MultiIndex.from_product([days, list(OPEN_HOURS)], names=["day", "hour"])
    return counts.reindex(grid, fill_value=0).reset_index()


def _features(df: pd.DataFrame) -> pd.DataFrame:
    d = pd.to_datetime(df["day"])
    return pd.DataFrame({
        "hour": df["hour"],
        "dow": d.dt.dayofweek,
        "festival": df["day"].map(lambda x: FESTIVALS.get(x, 1.0)),
        "t": (d - pd.Timestamp("2026-01-01")).dt.days,
    })


@dataclass
class Forecast:
    day: date
    hourly: dict[int, float]          # predicted payments per open hour
    holdout_mape: float               # last-14-days accuracy of the same model


def forecast_day(merchant_id: str, day: date) -> Forecast:
    hist = hourly_counts(merchant_id, day)
    cut = day - timedelta(days=14)
    train, test = hist[hist["day"] < cut], hist[hist["day"] >= cut]
    model = HistGradientBoostingRegressor(loss="poisson", max_iter=300, learning_rate=0.05,
                                          categorical_features=[0, 1], random_state=0)
    model.fit(_features(train), train["n"])
    pred = model.predict(_features(test))
    # MAPE on daily totals: hourly counts of 2–3 make per-hour MAPE meaningless.
    daily = test.assign(p=pred).groupby("day")[["n", "p"]].sum()
    mape = float((abs(daily["p"] - daily["n"]) / daily["n"].clip(lower=1)).mean())

    model.fit(_features(hist), hist["n"])  # refit on everything for the real forecast
    today = pd.DataFrame({"day": [day] * len(OPEN_HOURS), "hour": list(OPEN_HOURS)})
    return Forecast(day, dict(zip(OPEN_HOURS, model.predict(_features(today)).round(1).tolist())), round(mape, 3))


@dataclass
class Slump:
    start_hour: int
    end_hour: int                     # exclusive
    drop_pct: float                   # vs the day's average open hour
    expected_payments: float          # forecast payments inside the window


def find_slump(fc: Forecast, after: datetime | None = None) -> Slump | None:
    """Longest contiguous run of slump hours (optionally only hours starting at/after `after`)."""
    avg = float(np.mean(list(fc.hourly.values())))
    first = after.hour + (1 if after and after.minute > 0 else 0) if after else min(OPEN_HOURS)
    best, run = None, []
    for h in list(OPEN_HOURS) + [None]:
        if h is not None and h >= first and fc.hourly[h] < SLUMP_RATIO * avg:
            run.append(h)
            continue
        if run and (best is None or len(run) > len(best)):
            best = run
        run = []
    if not best:
        return None
    inside = sum(fc.hourly[h] for h in best)
    drop = 1 - (inside / len(best)) / avg
    return Slump(best[0], best[-1] + 1, round(drop * 100), round(inside, 1))
