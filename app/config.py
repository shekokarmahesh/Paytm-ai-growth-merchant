"""Settings loaded from .env. Phone numbers are normalised to Twilio's `whatsapp:+<digits>` form."""
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def whatsapp_address(raw: str) -> str:
    """'+91 00000 00001' / 'whatsapp:+91...' / '9100...' -> 'whatsapp:+9100...'."""
    digits = re.sub(r"\D", "", raw.removeprefix("whatsapp:"))
    return f"whatsapp:+{digits}" if digits else ""


@dataclass(frozen=True)
class Settings:
    sarvam_api_key: str
    sarvam_chat_model: str
    sarvam_stt_model: str
    sarvam_stt_mode: str
    sarvam_tts_model: str
    twilio_sid: str
    twilio_token: str
    twilio_from: str
    twilio_poll_seconds: float
    demo_merchant_whatsapp: str
    database_path: str
    demo_now: str
    tz: ZoneInfo


def _load() -> Settings:
    e = os.environ.get
    return Settings(
        sarvam_api_key=e("SARVAM_API_KEY", ""),
        sarvam_chat_model=e("SARVAM_CHAT_MODEL", "sarvam-105b-conversations"),
        sarvam_stt_model=e("SARVAM_STT_MODEL", "saaras:v3"),
        sarvam_stt_mode=e("SARVAM_STT_MODE", "codemix"),
        sarvam_tts_model=e("SARVAM_TTS_MODEL", "bulbul:v3"),
        twilio_sid=e("TWILIO_ACCOUNT_SID", ""),
        twilio_token=e("TWILIO_AUTH_TOKEN", ""),
        twilio_from=whatsapp_address(e("TWILIO_WHATSAPP_FROM", "")),
        twilio_poll_seconds=float(e("TWILIO_POLL_SECONDS", "3")),
        demo_merchant_whatsapp=whatsapp_address(e("DEMO_MERCHANT_WHATSAPP", "")),
        database_path=e("DATABASE_PATH", "var/vyapar.db"),
        demo_now=e("DEMO_NOW", ""),
        tz=ZoneInfo(e("TIMEZONE", "Asia/Kolkata")),
    )


settings = _load()


def now() -> datetime:
    """The demo clock: DEMO_NOW if set, else the real time in the configured zone."""
    if settings.demo_now:
        return datetime.fromisoformat(settings.demo_now).astimezone(settings.tz)
    return datetime.now(settings.tz)
