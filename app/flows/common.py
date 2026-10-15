"""Merchant lookup, sessions and sending to the merchant."""
import hashlib
import json
import logging

from app import db
from app.channels import twilio
from app.flows import choices

log = logging.getLogger("flows")


def merchant(merchant_id: str) -> dict:
    return db.one("SELECT * FROM merchants WHERE id=?", merchant_id)


def merchants_for(whatsapp: str) -> list[dict]:
    """Production routing: a number belongs to one merchant. The demo maps two merchants to one number."""
    return db.rows("SELECT * FROM merchants WHERE whatsapp=? ORDER BY kind DESC", whatsapp)


def session(whatsapp: str) -> dict:
    s = db.one("SELECT * FROM sessions WHERE whatsapp=?", whatsapp)
    if not s:
        db.run("INSERT INTO sessions (whatsapp) VALUES (?)", whatsapp)
        s = {"whatsapp": whatsapp, "active_merchant_id": None, "last_lang": None}
    return s


def set_session(whatsapp: str, **fields) -> None:
    session(whatsapp)
    for k, v in fields.items():
        db.run(f"UPDATE sessions SET {k}=? WHERE whatsapp=?", v, whatsapp)


def language(m: dict) -> str:
    """Mirror the merchant's last language; fall back to their default."""
    s = db.one("SELECT last_lang FROM sessions WHERE whatsapp=?", m["whatsapp"])
    return (s and s["last_lang"]) or m["text_lang"]


def header(m: dict) -> str:
    """Shows which shop a message is for — needed because the demo puts two shops on one phone."""
    icon = "🏪" if m["kind"] == "kirana" else "📱"
    return f"{icon} *{m['name']}*\n"


BODY_LIMIT = 1024  # Twilio interactive body limit


def send(m: dict, text: str) -> None:
    """Sends to the merchant. If this message asks a question (set_prompt), it goes with tap buttons /
    a list picker; if those can't be sent, with numbered options instead."""
    body = header(m) + text
    db.run("INSERT INTO chat_log (merchant_id, role, content) VALUES (?, 'assistant', ?)", m["id"], text)
    armed = db.one("SELECT kind FROM last_prompt WHERE merchant_id=? AND armed=1", m["id"])
    spec = choices.for_prompt(armed["kind"], m["kind"], language(m)) if armed else None
    try:
        if spec:
            _send_interactive(m, body, spec)
        else:
            twilio.send(m["whatsapp"], body)
    except twilio.SessionClosed as e:
        log.error("WhatsApp session closed: %s", e)
        raise
    _after_send(m["id"])
    log.info("→ %s\n%s", m["whatsapp"], body)


def _send_interactive(m: dict, body: str, spec) -> None:
    question = None
    if len(body) > BODY_LIMIT:  # long body: send it as text, buttons on a short follow-up
        twilio.wait_sent(twilio.send(m["whatsapp"], body))
        body, question = ("👇 Choose:" if language(m) == "en" else "👇 Chuniye:"), body
    try:
        twilio.send_content(m["whatsapp"], _content_sid(body, spec))
    except twilio.SessionClosed:
        raise
    except Exception as e:
        log.warning("interactive send failed (%s) — falling back to numbered options", e)
        twilio.send(m["whatsapp"], (body if question is None else "") + choices.numbered(spec))


def _content_sid(body: str, spec) -> str:
    """Creates (once) the Twilio Content resource for this exact body + choices."""
    style, data = spec
    if style == "quick":
        types = {"twilio/quick-reply": {"body": body, "actions": [{"title": t, "id": c} for c, t in data]}}
    else:
        button, items = data
        types = {"twilio/list-picker": {"body": body, "button": button,
                                        "items": [{"id": c, "item": i, "description": d} for c, i, d in items]}}
    key = hashlib.sha1(json.dumps(types, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    if hit := db.one("SELECT sid FROM content_cache WHERE key=?", key):
        return hit["sid"]
    sid = twilio.create_content(f"vyapar-{key[:16]}", types)
    db.run("INSERT OR REPLACE INTO content_cache VALUES (?, ?)", key, sid)
    return sid


def set_prompt(merchant_id: str, kind: str) -> None:
    """Called while building a message that asks a question; the next send() carries it."""
    db.run("""INSERT INTO last_prompt VALUES (?, ?, 1)
              ON CONFLICT(merchant_id) DO UPDATE SET kind=excluded.kind, armed=1""", merchant_id, kind)


def _after_send(merchant_id: str) -> None:
    """A reply answers the bot's most recent message: a message that asked nothing resets the choices."""
    r = db.one("SELECT armed FROM last_prompt WHERE merchant_id=?", merchant_id)
    if r and r["armed"]:
        db.run("UPDATE last_prompt SET armed=0 WHERE merchant_id=?", merchant_id)
    else:
        db.run("""INSERT INTO last_prompt VALUES (?, 'none', 0)
                  ON CONFLICT(merchant_id) DO UPDATE SET kind='none', armed=0""", merchant_id)


def last_prompt(merchant_id: str) -> str | None:
    r = db.one("SELECT kind FROM last_prompt WHERE merchant_id=?", merchant_id)
    return r["kind"] if r else None
