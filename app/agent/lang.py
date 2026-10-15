"""Which language did the merchant write in? hi (Devanagari) | hinglish (Roman Hindi) | en."""
import re

DEVANAGARI = re.compile(r"[ऀ-ॿ]")
HINGLISH = {
    "haan", "han", "ha", "nahi", "nahin", "na", "mat", "karo", "kar", "do", "dijiye", "kijiye", "kya",
    "hai", "hain", "ji", "bhai", "aaj", "kal", "kitna", "kitni", "kitne", "bikri", "dukaan", "sirf",
    "ghante", "ghanta", "bhejo", "bata", "batao", "shuru", "bilkul", "theek", "thik", "accha", "acha",
    "aur", "mera", "meri", "mujhe", "abhi", "wala", "wali", "kaise", "kyun", "hua", "hui", "chalao",
}


def detect(text: str, default: str) -> str:
    if DEVANAGARI.search(text):
        return "hi"
    words = re.findall(r"[a-z]+", text.lower())
    if not words:
        return default
    hits = sum(w in HINGLISH for w in words)
    if hits >= max(1, len(words) // 4):
        return "hinglish"
    return "en" if len(words) >= 2 else default


NAMES = {"hi": "Hindi in Devanagari script", "hinglish": "Hinglish (Hindi in Roman script, casual WhatsApp style)",
         "en": "simple Indian English"}
