"""Polls Twilio for inbound WhatsApp messages (no webhook, so no tunnel) and closes finished campaigns."""
import logging
import threading
import time
from datetime import datetime, timedelta, timezone

from app import db
from app.channels import twilio
from app.config import settings

log = logging.getLogger("poller")


class Poller(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True, name="twilio-poller")
        self.stop = threading.Event()
        # Only messages that arrive after startup; old ones are history, not commands.
        self.since = datetime.now(timezone.utc)

    def run(self):
        from app.agent import router
        from app.flows import common, slump
        log.info("polling Twilio every %ss for messages to %s", settings.twilio_poll_seconds, settings.twilio_from)
        while not self.stop.is_set():
            try:
                for m in twilio.inbound_since(self.since - timedelta(seconds=30)):
                    if db.one("SELECT 1 AS x FROM inbound_seen WHERE sid=?", m["sid"]):
                        continue
                    db.run("INSERT INTO inbound_seen (sid) VALUES (?)", m["sid"])
                    self.since = max(self.since, m["_sent"])
                    log.info("← %s: %r (media: %s)", m["from"], m["body"], m.get("num_media"))
                    try:
                        router.handle(m["from"], m["body"], twilio.media(m))
                    except twilio.SessionClosed:
                        log.error("Send 'hi' from your phone to reopen the WhatsApp session.")
                    except Exception:
                        log.exception("failed to handle %s", m["sid"])
                for merchant, report in slump.close_due():
                    common.send(merchant, report)
            except Exception as e:
                log.warning("poll failed: %s", e)
            self.stop.wait(settings.twilio_poll_seconds)
