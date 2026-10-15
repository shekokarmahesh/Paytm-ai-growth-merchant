"""Thin client for the three Sarvam APIs we use: chat (sarvam-105b), STT (saaras), TTS (bulbul)."""
import base64

import httpx

from app.config import settings

BASE = "https://api.sarvam.ai"


def _headers() -> dict:
    return {"api-subscription-key": settings.sarvam_api_key}


def chat(messages: list[dict], tools: list[dict] | None = None, temperature: float = 0.2,
         max_tokens: int = 1024) -> dict:
    """Returns the assistant message dict (content, tool_calls, ...)."""
    body = {
        "model": settings.sarvam_chat_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    r = httpx.post(f"{BASE}/v1/chat/completions", headers=_headers(), json=body, timeout=90)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]


def transcribe(audio: bytes, filename: str = "voice.ogg", content_type: str = "audio/ogg") -> str:
    data = {"model": settings.sarvam_stt_model, "language_code": "unknown"}
    if settings.sarvam_stt_model.startswith("saaras:v3"):
        data["mode"] = settings.sarvam_stt_mode
    r = httpx.post(f"{BASE}/speech-to-text", headers=_headers(), data=data,
                   files={"file": (filename, audio, content_type)}, timeout=90)
    r.raise_for_status()
    return r.json().get("transcript", "").strip()


def speak(text: str, language_code: str = "hi-IN", speaker: str = "shubh") -> bytes:
    """Returns WAV bytes."""
    body = {
        "text": text[:2500],
        "language_code": language_code,
        "target_language_code": language_code,  # older field name, harmless if ignored
        "speaker": speaker,
        "model": settings.sarvam_tts_model,
    }
    r = httpx.post(f"{BASE}/text-to-speech", headers=_headers(), json=body, timeout=90)
    r.raise_for_status()
    return base64.b64decode(r.json()["audios"][0])
