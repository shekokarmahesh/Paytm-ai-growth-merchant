"""LLM-written prose behind the numbers guardrail.

The LLM writes only a short, number-free opener; every line that carries a number comes from a fixed
template filled by code. Letting the LLM place number placeholders was tried and rejected: it kept
the values honest but attached them to the wrong meaning (a cashback % reported as "growth").
"""
import logging

from app import sarvam
from app.agent import guard
from app.agent.lang import NAMES

log = logging.getLogger("writer")

OPENER = """You write the first line of a WhatsApp message from "Vyapar Copilot", a Paytm assistant, to an Indian shop owner.
Rules: one short, warm, respectful line (max 15 words) in {language}. Address them with "ji" / "aap" (never "bhai", "tum" or "sir"). No numbers of any kind, no amounts, no times, no curly braces.
Do not state any business facts — the facts follow in the next lines. Output only the line."""


def opener(goal: str, language: str, context: str = "") -> str:
    try:
        msg = sarvam.chat([{"role": "system", "content": OPENER.format(language=NAMES[language])},
                           {"role": "user", "content": f"Message purpose: {goal}\n{context}".strip()}],
                          temperature=0.6, max_tokens=120)
        line = (msg.get("content") or "").strip().strip('"').splitlines()[0].strip()
    except Exception as e:
        log.warning("opener LLM failed: %s", e)
        return ""
    if not line or len(line) > 160 or guard.validate(line, set()) is not None:
        log.info("opener rejected: %r", line)
        return ""
    return line


def compose(goal: str, template: str, facts: dict, language: str, context: str = "") -> str:
    """LLM opener (if it passes the guard) + the code-filled template."""
    head = opener(goal, language, context)
    body = guard.fill(template, facts)
    return f"{head}\n\n{body}" if head else body


def fill_only(template: str, facts: dict) -> str:
    """A fixed template, no LLM (used where a reply must be instant and exact)."""
    return guard.fill(template, facts)
