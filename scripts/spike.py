"""De-risk spike: Sarvam tool-calling on Hinglish, TTS, STT round-trip, Twilio send + poll.

Run: .venv/bin/python -m scripts.spike [chat|tts|stt|twilio|all]
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app import sarvam
from app.channels import twilio
from app.config import ROOT, settings

OUT = ROOT / "var"

TOOLS = [{
    "type": "function",
    "function": {
        "name": "respond_to_proposal",
        "description": "Record the merchant's decision on the pending cashback proposal.",
        "parameters": {
            "type": "object",
            "properties": {
                "decision": {"type": "string", "enum": ["approve", "reject", "modify"]},
                "discount_pct": {"type": "number", "description": "Only if merchant asked for a different %"},
                "duration_hours": {"type": "number", "description": "Only if merchant asked for a different duration"},
            },
            "required": ["decision"],
        },
    },
}]


def spike_chat():
    sys_msg = {"role": "system", "content": "You are Vyapar Copilot. A proposal is pending: 10% cashback for 3 hours. "
               "Call respond_to_proposal with the merchant's decision."}
    for text in ["haan bilkul shuru kar do", "nahi abhi mat karo", "8% kar do aur sirf 2 ghante"]:
        msg = sarvam.chat([sys_msg, {"role": "user", "content": text}], tools=TOOLS)
        calls = [(c["function"]["name"], json.loads(c["function"]["arguments"])) for c in msg.get("tool_calls") or []]
        print(f"  {text!r:40} -> {calls or ('TEXT: ' + (msg.get('content') or '')[:80])}")


def spike_tts() -> Path:
    wav = sarvam.speak("Ramesh ji, kal aapki kul bikri chaudah hazaar do sau rupaye rahi. Offer live ho chuka hai.", "hi-IN")
    p = OUT / "spike.wav"
    p.write_bytes(wav)
    print(f"  wrote {p} ({len(wav)} bytes)")
    return p


def spike_stt():
    p = OUT / "spike.wav"
    if not p.exists():
        p = spike_tts()
    print(f"  transcript: {sarvam.transcribe(p.read_bytes(), 'spike.wav', 'audio/wav')!r}")


def spike_twilio():
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    inbound = twilio.inbound_since(since)
    print(f"  inbound in last 24h: {len(inbound)}; latest: "
          f"{[(m['from'], m['body'][:30], m['_sent'].isoformat()) for m in inbound[-3:]]}")
    sid = twilio.send(settings.demo_merchant_whatsapp, "✅ Vyapar Copilot spike: Twilio send works.")
    print(f"  sent {sid}")


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    for name, fn in [("chat", spike_chat), ("tts", spike_tts), ("stt", spike_stt), ("twilio", spike_twilio)]:
        if which in (name, "all"):
            print(f"[{name}]")
            try:
                fn()
            except Exception as e:  # spike: report and continue
                print(f"  FAILED: {type(e).__name__}: {str(e)[:300]}")
                if hasattr(e, "response"):
                    print(f"  body: {e.response.text[:500]}")


if __name__ == "__main__":
    main()
