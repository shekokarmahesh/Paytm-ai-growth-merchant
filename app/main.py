"""FastAPI app: analytics endpoints, the n8n schedule hook, and the background Twilio poller.

Run: .venv/bin/uvicorn app.main:app --port 8000
"""
import logging
from contextlib import asynccontextmanager
from dataclasses import asdict

from fastapi import FastAPI, HTTPException

from app import db
from app.analytics import discount, footfall, restock, rfm, synth
from app.channels.poller import Poller
from app.config import now
from app.flows import briefing, common, slump

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s", datefmt="%H:%M:%S")
logging.getLogger("httpx").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init()
    if not db.one("SELECT 1 AS x FROM merchants"):
        logging.info("empty database — seeding demo data %s", synth.seed())
    poller = Poller()
    poller.start()
    yield
    poller.stop.set()


app = FastAPI(title="Vyapar Copilot", lifespan=lifespan)


def _merchant(merchant_id: str) -> dict:
    m = common.merchant(merchant_id)
    if not m:
        raise HTTPException(404, f"unknown merchant {merchant_id}")
    return m


@app.get("/health")
def health():
    return {"ok": True, "now": db.ts(now())}


@app.get("/analytics/forecast")
def forecast(merchant_id: str = synth.KIRANA):
    fc = footfall.forecast_day(_merchant(merchant_id)["id"], now().date())
    return {"day": fc.day.isoformat(), "hourly": fc.hourly, "holdout_mape": fc.holdout_mape}


@app.get("/analytics/predict-slump")
def predict_slump(merchant_id: str = synth.KIRANA):
    m = _merchant(merchant_id)
    a = slump.build(m)  # same analysis the WhatsApp flow uses
    return {"slump": asdict(a["slump"]) if a["slump"] else None,
            "plan": asdict(a["plan"]) if a.get("plan") else None,
            "baseline_visit_prob": a.get("p0"),
            "safe_cap_pct": discount.max_safe_discount(m["margin_pct"]) * 100}


@app.get("/analytics/customer-segments")
def customer_segments(merchant_id: str = synth.KIRANA):
    s = rfm.segments(_merchant(merchant_id)["id"], now())
    return {"counts": s["segment"].value_counts().to_dict(),
            "avg_ticket": s.groupby("segment")["avg_ticket"].mean().round().to_dict()}


@app.get("/analytics/restock")
def restock_plan(merchant_id: str = synth.ELECTRONICS):
    return restock.plan(_merchant(merchant_id)["id"], now().date())


@app.post("/flows/briefing")
def run_briefing(merchant_id: str | None = None):
    """Called by the n8n 08:30 schedule. Without merchant_id, briefs every merchant."""
    ms = [_merchant(merchant_id)] if merchant_id else db.rows("SELECT * FROM merchants ORDER BY kind DESC")
    for m in ms:
        briefing.run(m)
    return {"briefed": [m["id"] for m in ms]}
