"""Every tappable choice the bot offers, in one place.

A choice is (command, title, description). The command is what the router acts on; the title is what
the merchant sees on the button and what WhatsApp sends back when it's tapped. Titles: ≤20 chars for
buttons, ≤24 for list items (Twilio limits).
"""
import re

QUICK = {  # kind -> lang -> [(command, title)]  (≤3, rendered as quick-reply buttons)
    "cashback": {
        "hinglish": [("haan", "✅ Haan, shuru karo"), ("nahi", "❌ Nahi"), ("badlav", "✏️ Badlav karna hai")],
        "en": [("haan", "✅ Yes, start it"), ("nahi", "❌ No"), ("badlav", "✏️ Change it")],
    },
    "restock": {
        "en": [("approve", "✅ Approve POs"), ("reject", "❌ Reject")],
    },
    "menu_electronics": {
        "en": [("briefing", "☀️ Morning briefing"), ("stock", "📦 Restock check"), ("switch kirana", "🏪 Kirana store")],
    },
}

LIST = {  # kind -> (button, [(command, item, description)])  (rendered as a list picker)
    "menu_kirana": ("📋 Options dekhein", [
        ("briefing", "☀️ Aaj ki briefing", "Kal ki bikri vs pichhla hafta, aaj ke slow ghante"),
        ("slump", "📉 Slow ghanton ka offer", "Margin-safe cashback se purane grahak wapas"),
        ("result", "📊 Offer ka nateeja", "Kitne grahak aaye, kitna munafa hua"),
        ("sales", "💰 Kal ki bikri", "Kal ki kul bikri aur grahak"),
        ("switch electronics", "📱 Electronics store", "Demo: POS wale store pe jaayein"),
    ]),
}


def for_prompt(kind: str, merchant_kind: str, lang: str):
    """-> ('quick', [(cmd, title)]) | ('list', (button, items)) | None for a prompt kind."""
    if kind == "menu":
        kind = f"menu_{merchant_kind}"
    if kind in LIST:
        return "list", LIST[kind]
    if kind in QUICK:
        options = QUICK[kind]
        return "quick", options.get(lang) or options.get("hinglish") or options["en"]
    return None


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


TAPS = {_norm(t): cmd for v in QUICK.values() for opts in v.values() for cmd, t in opts}
TAPS |= {_norm(item): cmd for _, items in LIST.values() for cmd, item, _ in items}


def tapped(text: str) -> str | None:
    """The command behind a tapped button / picked list item, if `text` is one."""
    return TAPS.get(_norm(text)) if text else None


def numbered(spec) -> str:
    """Plain-text fallback when interactive messages can't be sent."""
    style, data = spec
    titles = [t for _, t in data] if style == "quick" else [item for _, item, _ in data[1]]
    return "\n\n" + "\n".join(f"*{i}* {t}" for i, t in enumerate(titles, 1))


def numbered_commands(spec) -> list[str]:
    style, data = spec
    return [c for c, _ in data] if style == "quick" else [c for c, _, _ in data[1]]
