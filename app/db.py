"""SQLite access: schema plus small helpers. Dict rows; JSON columns stored as TEXT.

Timestamps are ISO-8601 strings in the app timezone (always written via `ts()`), so they compare
correctly as text.
"""
import json as _json
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from app.config import ROOT, settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS merchants (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  owner TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('kirana', 'electronics')),
  whatsapp TEXT NOT NULL,            -- production routing key; demo maps both merchants to one phone
  voice_lang TEXT NOT NULL,          -- bulbul language code for the Soundbox
  text_lang TEXT NOT NULL,           -- default reply style: hinglish | en | hi
  margin_pct REAL NOT NULL,          -- merchant-declared shop-level margin (QR data has no item margin)
  upi_vpa TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS transactions (
  id INTEGER PRIMARY KEY,
  merchant_id TEXT NOT NULL REFERENCES merchants(id),
  ts TEXT NOT NULL,
  amount REAL NOT NULL,
  payer_hash TEXT NOT NULL           -- all a QR payment tells us: when, how much, who (hashed VPA)
);
CREATE INDEX IF NOT EXISTS transactions_merchant_ts ON transactions (merchant_id, ts);
CREATE TABLE IF NOT EXISTS skus (
  merchant_id TEXT NOT NULL REFERENCES merchants(id),
  sku TEXT NOT NULL,
  name TEXT NOT NULL,
  category TEXT NOT NULL,
  unit_cost REAL NOT NULL,
  price REAL NOT NULL,
  stock INTEGER NOT NULL,
  lead_days INTEGER NOT NULL,
  distributor TEXT NOT NULL,
  PRIMARY KEY (merchant_id, sku)
);
CREATE TABLE IF NOT EXISTS sku_sales (
  merchant_id TEXT NOT NULL,
  sku TEXT NOT NULL,
  day TEXT NOT NULL,
  units INTEGER NOT NULL,
  PRIMARY KEY (merchant_id, sku, day)
);
CREATE TABLE IF NOT EXISTS proposals (
  id INTEGER PRIMARY KEY,
  merchant_id TEXT NOT NULL REFERENCES merchants(id),
  kind TEXT NOT NULL CHECK (kind IN ('cashback', 'restock')),
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'rejected', 'executed', 'expired', 'superseded')),
  payload TEXT NOT NULL,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS campaigns (
  id INTEGER PRIMARY KEY,
  proposal_id INTEGER NOT NULL REFERENCES proposals(id),
  merchant_id TEXT NOT NULL REFERENCES merchants(id),
  paytm_campaign_id TEXT NOT NULL,
  discount_pct REAL NOT NULL,
  starts_at TEXT NOT NULL,
  ends_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'live' CHECK (status IN ('live', 'ended')),
  plan TEXT NOT NULL,
  result TEXT
);
-- Every message meant for someone other than the merchant (customers, distributor) is logged here.
CREATE TABLE IF NOT EXISTS outbox (
  id INTEGER PRIMARY KEY,
  merchant_id TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('voucher', 'purchase_order')),
  ref_id INTEGER NOT NULL,
  recipient TEXT NOT NULL,
  body TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS inbound_seen (sid TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS sessions (
  whatsapp TEXT PRIMARY KEY,
  active_merchant_id TEXT REFERENCES merchants(id),
  last_lang TEXT
);
-- What the bot's most recent message asked ('menu' | 'cashback' | 'restock' | 'none'): decides what a
-- bare "1"/"2" means. `armed` = set for the message about to be sent; any other message resets to 'none'.
CREATE TABLE IF NOT EXISTS last_prompt (merchant_id TEXT PRIMARY KEY, kind TEXT NOT NULL, armed INTEGER NOT NULL DEFAULT 0);
-- Twilio Content resources already created for an exact (body, buttons) combination.
CREATE TABLE IF NOT EXISTS content_cache (key TEXT PRIMARY KEY, sid TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS chat_log (
  id INTEGER PRIMARY KEY,
  merchant_id TEXT NOT NULL,
  role TEXT NOT NULL,
  content TEXT NOT NULL
);
"""


def path() -> str:
    p = settings.database_path
    return p if p.startswith("/") or p == ":memory:" else str(ROOT / p)


@contextmanager
def conn():
    c = sqlite3.connect(path(), timeout=30, check_same_thread=False)
    c.row_factory = lambda cur, row: {d[0]: v for d, v in zip(cur.description, row)}
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init():
    (ROOT / "var").mkdir(exist_ok=True)
    with conn() as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(SCHEMA)


def rows(sql: str, *params) -> list[dict]:
    with conn() as c:
        return c.execute(sql, params).fetchall()


def one(sql: str, *params) -> dict | None:
    with conn() as c:
        return c.execute(sql, params).fetchone()


def run(sql: str, *params) -> int:
    """Executes and returns lastrowid."""
    with conn() as c:
        return c.execute(sql, params).lastrowid


def many(sql: str, seq) -> None:
    with conn() as c:
        c.executemany(sql, seq)


def ts(dt: datetime) -> str:
    return dt.astimezone(settings.tz).isoformat(timespec="seconds")


def dumps(value) -> str:
    return _json.dumps(value, ensure_ascii=False, default=str)


def loads(value: str | None):
    return _json.loads(value) if value else None
