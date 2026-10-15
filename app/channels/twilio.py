"""Twilio WhatsApp over plain REST. Outbound is text or tap-button messages (no media); inbound is
polled (no webhook, no tunnel)."""
import time
from datetime import datetime, timedelta, timezone

import httpx

from app.config import settings

API = "https://api.twilio.com/2010-04-01/Accounts"


def _auth() -> tuple[str, str]:
    return (settings.twilio_sid, settings.twilio_token)


class SessionClosed(Exception):
    """Twilio 63016: recipient hasn't messaged the business number in the last 24h."""


def send(to: str, body: str) -> str:
    r = httpx.post(f"{API}/{settings.twilio_sid}/Messages.json", auth=_auth(), timeout=30,
                   data={"From": settings.twilio_from, "To": to, "Body": body[:1600]})
    if r.status_code >= 400:
        if '"code": 63016' in r.text or "63016" in r.text:
            raise SessionClosed("Send 'hi' from your phone to the business number to open a session.")
        r.raise_for_status()
    return r.json()["sid"]


def delivery_error(sid: str) -> int | None:
    """63016 is often reported asynchronously on the message, not on the POST."""
    r = httpx.get(f"{API}/{settings.twilio_sid}/Messages/{sid}.json", auth=_auth(), timeout=30)
    r.raise_for_status()
    return r.json().get("error_code")


def inbound_since(since: datetime) -> list[dict]:
    """Inbound messages to our business number sent after `since` (oldest first).

    Twilio's DateSent filter is day-granular, so we filter precisely client-side.
    """
    day = (since.astimezone(timezone.utc) - timedelta(days=1)).date().isoformat()
    r = httpx.get(f"{API}/{settings.twilio_sid}/Messages.json", auth=_auth(), timeout=30,
                  params={"To": settings.twilio_from, "DateSent>": day, "PageSize": 50})
    r.raise_for_status()
    out = []
    for m in r.json().get("messages", []):
        if m.get("direction") != "inbound":
            continue
        sent = datetime.strptime(m["date_sent"] or m["date_created"], "%a, %d %b %Y %H:%M:%S %z")
        if sent > since:
            m["_sent"] = sent
            out.append(m)
    return sorted(out, key=lambda m: m["_sent"])


def media(message: dict) -> list[tuple[bytes, str]]:
    """Downloads attachments of an inbound message -> [(bytes, content_type)]."""
    if int(message.get("num_media") or 0) == 0:
        return []
    r = httpx.get(f"https://api.twilio.com{message['subresource_uris']['media']}", auth=_auth(), timeout=30)
    r.raise_for_status()
    out = []
    for item in r.json().get("media_list", []):
        url = f"https://api.twilio.com{item['uri'].removesuffix('.json')}"
        f = httpx.get(url, auth=_auth(), timeout=60, follow_redirects=True)
        f.raise_for_status()
        out.append((f.content, item.get("content_type", "audio/ogg")))
    return out


# --- Interactive messages (Content API) -----------------------------------------------------------
# Quick-reply (≤3 buttons) and list-picker (≤10 items) need no WhatsApp approval inside the 24h
# session. A tapped button / picked item comes back as an ordinary inbound message whose Body is its title.

CONTENT_API = "https://content.twilio.com/v1/Content"


def create_content(friendly_name: str, types: dict) -> str:
    r = httpx.post(CONTENT_API, auth=_auth(), timeout=30,
                   json={"friendly_name": friendly_name, "language": "en", "types": types})
    r.raise_for_status()
    return r.json()["sid"]


def send_content(to: str, content_sid: str) -> str:
    r = httpx.post(f"{API}/{settings.twilio_sid}/Messages.json", auth=_auth(), timeout=30,
                   data={"From": settings.twilio_from, "To": to, "ContentSid": content_sid})
    if r.status_code >= 400:
        if "63016" in r.text:
            raise SessionClosed("Send 'hi' from your phone to the business number to open a session.")
        r.raise_for_status()
    return r.json()["sid"]


def wait_sent(sid: str, timeout: float = 5.0) -> None:
    """Twilio doesn't guarantee ordering between messages; wait until this one has left before the next."""

    end = time.time() + timeout
    while time.time() < end:
        r = httpx.get(f"{API}/{settings.twilio_sid}/Messages/{sid}.json", auth=_auth(), timeout=30)
        if r.json().get("status") in {"sent", "delivered", "read", "failed", "undelivered"}:
            return
        time.sleep(0.4)
