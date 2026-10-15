"""The numbers guardrail: the LLM writes prose with {placeholders}; only code puts numbers in.

Any digit the LLM typed itself (ASCII or Devanagari) rejects its draft, as does an unknown placeholder.
"""
import re
import string

DIGIT = re.compile(r"[0-9०-९]")


def inr(x: float) -> str:
    """Indian digit grouping: 1234567 -> ₹12,34,567."""
    n = int(round(x))
    s = str(abs(n))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        head = ",".join(re.findall(r"\d{1,2}", head[::-1]))[::-1]
        s = f"{head},{tail}"
    return ("-" if n < 0 else "") + "₹" + s


def placeholders(template: str) -> set[str]:
    return {f for _, f, _, _ in string.Formatter().parse(template) if f}


def validate(draft: str, allowed: set[str]) -> str | None:
    """Returns a reason the draft is unsafe, or None if it may be filled."""
    try:
        used = placeholders(draft)
    except ValueError:
        return "malformed braces"
    if unknown := used - allowed:
        return f"unknown placeholders {sorted(unknown)}"
    if DIGIT.search(re.sub(r"\{[^{}]*\}", "", draft)):
        return "contains a number the model wrote itself"
    return None


def fill(template: str, facts: dict) -> str:
    return template.format_map({k: v for k, v in facts.items()})


def render(draft: str | None, fallback: str, facts: dict) -> tuple[str, bool]:
    """Fill the LLM draft if it is safe, else the fixed template. Returns (text, used_llm)."""
    if draft and validate(draft, set(facts)) is None:
        return fill(draft, facts), True
    return fill(fallback, facts), False
