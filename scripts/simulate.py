"""Rehearse the demo in the terminal: real Sarvam + analytics, WhatsApp sends printed instead of sent.

Run: .venv/bin/python -m scripts.simulate                 # scripted demo
     .venv/bin/python -m scripts.simulate "8% kar do" ...  # your own messages, in order
"""
import logging
import os
import sys

os.environ["DATABASE_PATH"] = "var/simulate.db"  # never touch the live server's database

from app import soundbox
from app.agent import router
from app.analytics import synth
from app.channels import twilio
from app.config import settings

DEMO = ["briefing", "8% kar do aur sirf 2 ghante", "haan bilkul shuru kar do", "result",
        "kal kitni bikri hui?", "switch electronics", "stock", "approve", "switch kirana"]


def main():
    logging.basicConfig(level=logging.WARNING, format="%(name)s: %(message)s")
    twilio.send = lambda to, body: print(f"\n📲 BOT ➜\n{body}\n") or "SIM"
    twilio.wait_sent = lambda sid: None
    contents = {}

    def create_content(name, types):
        contents[name] = types
        return name

    def send_content(to, sid):
        (kind, t), = contents[sid].items()
        if kind == "twilio/quick-reply":
            buttons = "  ".join(f"[ {a['title']} ]" for a in t["actions"])
        else:
            buttons = f"[ {t['button']} ] → " + " | ".join(i["item"] for i in t["items"])
        print(f"\n📲 BOT ➜\n{t['body']}\n   {buttons}\n")
        return "SIM"

    twilio.create_content, twilio.send_content = create_content, send_content
    soundbox.announce = lambda text, lang: print(f"🔊 SOUNDBOX ({lang}): {text}")
    synth.seed()
    for text in sys.argv[1:] or DEMO:
        print(f"\n{'=' * 60}\n🧑 MERCHANT: {text}")
        router.handle(settings.demo_merchant_whatsapp, text, [])


if __name__ == "__main__":
    main()
