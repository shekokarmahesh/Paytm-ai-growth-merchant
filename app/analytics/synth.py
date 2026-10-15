"""Synthetic data for the two demo merchants.

Kirana: 180 days of QR payments carrying only (ts, amount, payer_hash) — what a real UPI QR gives.
Electronics: a POS SKU catalogue with 90 days of daily unit sales, accelerating into Diwali.
"""
import hashlib
from datetime import date, datetime, time, timedelta

import numpy as np

from app import db
from app.config import now, settings

KIRANA = "gupta-kirana"
ELECTRONICS = "sharma-electronics"

# 2026 calendar (dates as published for 2026; used as demand multipliers).
FESTIVALS = {
    date(2026, 8, 15): 1.15,  # Independence Day
    date(2026, 8, 28): 1.35,  # Raksha Bandhan
    date(2026, 9, 14): 1.30,  # Ganesh Chaturthi
}
DIWALI = date(2026, 11, 8)

# Typical QR payments per hour for the kirana (07:00–22:59). The 14–17 trough is the real-world
# afternoon lull the Slump Buster targets.
HOURLY = {7: 5, 8: 11, 9: 13, 10: 12, 11: 9, 12: 8, 13: 6, 14: 3.0, 15: 2.4, 16: 3.0,
          17: 7, 18: 12, 19: 14, 20: 13, 21: 8, 22: 4}
DOW = [0.93, 1.0, 1.0, 1.0, 1.04, 1.10, 1.16]  # Mon..Sun

MERCHANTS = [
    dict(id=KIRANA, name="Gupta Kirana Store", owner="Ramesh ji", kind="kirana",
         voice_lang="hi-IN", text_lang="hinglish", margin_pct=0.20, upi_vpa="guptakirana@paytm"),
    dict(id=ELECTRONICS, name="Sharma Electronics, Phoenix Mall", owner="Mr. Sharma", kind="electronics",
         voice_lang="en-IN", text_lang="en", margin_pct=0.12, upi_vpa="sharmaelectronics@paytm"),
]

# (name, category, price, unit_cost, base units/day, lead days, distributor)
CATALOGUE = [
    ("iPhone 17 128GB", "Mobiles", 79900, 72500, 1.6, 6, "Ingram Micro"),
    ("iPhone 17 Pro 256GB", "Mobiles", 134900, 123000, 0.7, 6, "Ingram Micro"),
    ("Galaxy S26 256GB", "Mobiles", 84999, 76000, 1.1, 4, "Samsung India Distribution"),
    ("Galaxy A57 5G", "Mobiles", 32999, 28800, 2.6, 4, "Samsung India Distribution"),
    ("Redmi Note 15 Pro", "Mobiles", 24999, 21900, 3.2, 5, "Xiaomi Partner Hub"),
    ("OnePlus 15R", "Mobiles", 44999, 39800, 1.4, 5, "OnePlus Distribution"),
    ("Vivo V60", "Mobiles", 36999, 32500, 1.5, 5, "Vivo Trade Partners"),
    ("MacBook Air M5 13\"", "Laptops", 114900, 104000, 0.5, 8, "Ingram Micro"),
    ("HP Pavilion 15 i5", "Laptops", 64990, 57500, 0.7, 7, "Redington"),
    ("Dell Inspiron 14 Ryzen 7", "Laptops", 69990, 61800, 0.6, 7, "Redington"),
    ("Lenovo IdeaPad Slim 5", "Laptops", 59990, 53000, 0.8, 7, "Redington"),
    ("ASUS TUF Gaming F15", "Laptops", 82990, 73500, 0.4, 9, "Redington"),
    ("Samsung 55\" Crystal 4K", "Televisions", 46990, 41000, 0.9, 10, "Samsung India Distribution"),
    ("LG 65\" OLED evo", "Televisions", 189990, 168000, 0.2, 10, "LG Electronics Trade"),
    ("Sony Bravia 55\" X80L", "Televisions", 79990, 70500, 0.5, 10, "Sony Trade Partners"),
    ("TCL 43\" QLED", "Televisions", 24990, 21500, 1.1, 8, "TCL Distributors"),
    ("Xiaomi 50\" X Pro", "Televisions", 32999, 28900, 0.8, 8, "Xiaomi Partner Hub"),
    ("AirPods Pro 3", "Audio", 24900, 21200, 2.1, 6, "Ingram Micro"),
    ("Galaxy Buds 4", "Audio", 12999, 10800, 1.5, 4, "Samsung India Distribution"),
    ("Sony WH-1000XM6", "Audio", 32990, 28400, 0.7, 6, "Sony Trade Partners"),
    ("boAt Airdopes 800", "Audio", 2499, 1650, 6.5, 3, "Imagine Marketing"),
    ("JBL Flip 7", "Audio", 11999, 9900, 1.2, 5, "Harman India"),
    ("Apple Watch Series 11", "Wearables", 46900, 41500, 0.8, 6, "Ingram Micro"),
    ("Galaxy Watch 8", "Wearables", 29999, 26000, 0.7, 4, "Samsung India Distribution"),
    ("Noise ColorFit Pro 6", "Wearables", 3999, 2700, 4.1, 3, "Noise Distribution"),
    ("iPad 11th Gen", "Tablets", 34900, 31200, 0.9, 6, "Ingram Micro"),
    ("Galaxy Tab S10 FE", "Tablets", 39999, 35200, 0.5, 4, "Samsung India Distribution"),
    ("Anker 20W Charger", "Accessories", 1499, 900, 7.5, 3, "Anker Innovations"),
    ("Samsung 25W Charger", "Accessories", 1699, 1050, 5.2, 4, "Samsung India Distribution"),
    ("Apple USB-C 1m Cable", "Accessories", 1900, 1300, 4.4, 6, "Ingram Micro"),
    ("Mi Power Bank 20000", "Accessories", 2199, 1500, 4.8, 5, "Xiaomi Partner Hub"),
    ("SanDisk 128GB microSD", "Accessories", 1199, 750, 3.9, 3, "Redington"),
    ("Philips Air Fryer 4.1L", "Home Appliances", 9999, 8100, 1.3, 7, "Philips Domestic"),
    ("Dyson V12 Detect", "Home Appliances", 55900, 49800, 0.3, 9, "Dyson Trade"),
    ("LG 8kg Front Load", "Home Appliances", 41990, 36800, 0.5, 10, "LG Electronics Trade"),
    ("Samsung 253L Fridge", "Home Appliances", 27990, 24300, 0.6, 10, "Samsung India Distribution"),
    ("Bajaj Mixer 750W", "Home Appliances", 3999, 2900, 1.8, 5, "Bajaj Electricals"),
    ("Canon EOS R100 Kit", "Cameras", 54990, 48900, 0.3, 9, "Canon Trade"),
    ("GoPro HERO 14", "Cameras", 44990, 39900, 0.3, 8, "Ingram Micro"),
    ("PlayStation 5 Slim", "Gaming", 49990, 45200, 0.8, 7, "Sony Trade Partners"),
]

# SKUs deliberately stocked short so the demo has something real to flag.
SHORT_STOCKED = {"iPhone 17 128GB", "Redmi Note 15 Pro", "Samsung 55\" Crystal 4K",
                 "boAt Airdopes 800", "Anker 20W Charger"}


def _hash(i: int) -> str:
    return "vpa_" + hashlib.sha1(f"payer-{i}".encode()).hexdigest()[:10]


def kirana_transactions(rng: np.random.Generator, end: datetime, days: int = 180) -> list[tuple]:
    """Returns (ts, amount, payer_hash) rows from `days` days before `end`'s date up to `end`."""
    n_reg = 420
    rate = rng.gamma(2.0, 1.0, n_reg)  # relative visit propensity
    # A quarter of regulars drift to quick-commerce: they stop visiting 10–35 days before `end`.
    drift_day = np.full(n_reg, None, dtype=object)
    for i in rng.choice(n_reg, n_reg // 4, replace=False):
        drift_day[i] = end.date() - timedelta(days=int(rng.integers(10, 36)))
    walkin = 100_000
    out = []
    start = end.date() - timedelta(days=days)
    for k in range(days + 1):
        d = start + timedelta(days=k)
        mult = DOW[d.weekday()] * FESTIVALS.get(d, 1.0) * (1 + 0.0006 * k)  # slow growth trend
        active = np.array([dd is None or d < dd for dd in drift_day])
        p = rate * active
        p = p / p.sum()
        for h, base in HOURLY.items():
            for _ in range(rng.poisson(base * mult)):
                ts = datetime.combine(d, time(h, int(rng.integers(0, 60)), int(rng.integers(0, 60))),
                                      tzinfo=settings.tz)
                if ts > end:
                    continue
                if rng.random() < 0.68:
                    payer = _hash(int(rng.choice(n_reg, p=p)))
                else:
                    walkin += 1
                    payer = _hash(walkin)
                ticket = rng.lognormal(np.log(95 if h < 17 else 125), 0.55)
                out.append((db.ts(ts), round(float(min(ticket, 2500)), 0), payer))
    return out


def electronics(rng: np.random.Generator, today: date, days: int = 90):
    skus, sales = [], []
    for i, (name, cat, price, cost, base, lead, dist) in enumerate(CATALOGUE):
        sku = f"SKU{i + 1:03d}"
        for k in range(days, 0, -1):
            d = today - timedelta(days=k)
            to_diwali = (DIWALI - d).days
            ramp = 1.0 + max(0.0, (45 - to_diwali) / 45) * 0.6  # demand builds over the 45 days before Diwali
            weekend = 1.25 if d.weekday() >= 5 else 1.0
            sales.append((sku, d.isoformat(), int(rng.poisson(base * ramp * weekend))))
        cover = rng.uniform(2.5, 6) if name in SHORT_STOCKED else rng.uniform(18, 45)
        skus.append((sku, name, cat, cost, price, max(1, int(base * 1.3 * cover)), lead, dist))
    return skus, sales


def seed(seed: int = 7) -> dict:
    rng = np.random.default_rng(seed)
    end = now()
    db.init()
    for t in ["last_prompt", "outbox", "campaigns", "proposals", "transactions", "sku_sales", "skus", "sessions",
              "chat_log", "merchants"]:
        db.run(f"DELETE FROM {t}")
    db.many("INSERT INTO merchants VALUES (:id,:name,:owner,:kind,:whatsapp,:voice_lang,:text_lang,:margin_pct,:upi_vpa)",
            [m | {"whatsapp": settings.demo_merchant_whatsapp} for m in MERCHANTS])
    tx = kirana_transactions(rng, end)
    db.many(f"INSERT INTO transactions (merchant_id, ts, amount, payer_hash) VALUES ('{KIRANA}',?,?,?)", tx)
    skus, sales = electronics(rng, end.date())
    db.many(f"INSERT INTO skus VALUES ('{ELECTRONICS}',?,?,?,?,?,?,?,?)", skus)
    db.many(f"INSERT INTO sku_sales VALUES ('{ELECTRONICS}',?,?,?)", sales)
    return {"transactions": len(tx), "skus": len(skus), "sku_sales_rows": len(sales), "now": db.ts(end)}
