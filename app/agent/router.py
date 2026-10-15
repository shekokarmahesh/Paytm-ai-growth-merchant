"""Inbound WhatsApp message -> reply. Commands first (instant, exact), then the sarvam-105b tool loop.

Every tool returns a finished message built by code, which is sent as-is: the LLM picks *what to do*,
never the numbers. Free text the LLM writes itself must pass the numbers guardrail.
"""
import json
import logging
import re

from app import db, sarvam
from app.agent import guard, lang
from app.analytics import summary
from app.agent.guard import inr
from app.config import now
from app.flows import briefing, choices, common, restock, slump

log = logging.getLogger("router")

MENU = {
    "kirana": ("Namaste {owner} 🙏 Main aapka *Vyapar Copilot* hoon — aapke Paytm payments se dukaan badhane mein "
               "madad karta hoon.\n\nNeeche se chuniye 👇 — ya seedha likhiye / 🎙️ voice note bhejiye, "
               "jaise \"kal kitni bikri hui?\""),
    "electronics": ("Hello {owner} 🙏 I'm your *Vyapar Copilot* — I watch your POS sales and stock so you never run out."
                    "\n\nTap an option 👇 — or just type / 🎙️ send a voice note, e.g. \"what's running low?\""),
}
MENU_HINT = {"kirana": "\n\n_*menu* — sab options_", "electronics": "\n\n_*menu* — all options_"}


def menu(m: dict) -> str:
    common.set_prompt(m["id"], "menu")  # sent with the menu's list picker / buttons
    return MENU[m["kind"]].format(owner=m["owner"])


def _resolve_choice(m: dict, text: str) -> str:
    """A tapped button, or a typed number, answers the bot's most recent message."""
    if cmd := choices.tapped(text):
        return cmd
    t = text.strip().rstrip(".")
    if not t.isdigit():
        return text
    asked = common.last_prompt(m["id"])
    if asked not in ("cashback", "restock") or not slump.pending(m["id"], asked):
        asked = "menu"
    commands = choices.numbered_commands(choices.for_prompt(asked, m["kind"], common.language(m)))
    return commands[int(t) - 1] if 1 <= int(t) <= len(commands) else text


TOOLS = [
    {"type": "function", "function": {
        "name": "respond_to_proposal",
        "description": "The merchant is answering the pending proposal shown in the system message (yes / no / change).",
        "parameters": {"type": "object", "properties": {
            "decision": {"type": "string", "enum": ["approve", "reject", "modify"]},
            "discount_pct": {"type": "number", "description": "New cashback % if the merchant asked to change it"},
            "duration_hours": {"type": "number", "description": "New duration in hours if the merchant asked to change it"},
        }, "required": ["decision"]}}},
    {"type": "function", "function": {
        "name": "morning_briefing", "description": "Summary of yesterday's sales and today's outlook.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "slump_offer", "description": "Check for slow hours today and prepare a margin-safe cashback offer.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "restock_check", "description": "Check which items will run out and draft purchase orders.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "campaign_result", "description": "Outcome of the latest cashback campaign.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "sales_summary", "description": "Sales numbers for a day.",
        "parameters": {"type": "object", "properties": {
            "day": {"type": "string", "enum": ["today", "yesterday"]}}, "required": ["day"]}}},
]


def _pending_note(m: dict) -> str:
    c = slump.pending(m["id"], "cashback")
    if c:
        pl = c["payload"]["plan"]
        return (f"PENDING PROPOSAL: {pl['discount_pct']:g}% cashback for {pl['duration_hours']:g} hours to "
                f"{pl['targets']} regulars. If the merchant says yes/no/change, call respond_to_proposal.")
    r = slump.pending(m["id"], "restock")
    if r:
        return ("PENDING PROPOSAL: purchase orders for low-stock items. If the merchant approves or rejects, "
                "call respond_to_proposal.")
    if live := slump.live_campaign(m["id"]):
        return (f"LIVE CAMPAIGN: {live['discount_pct']:g}% cashback is running. If the merchant asks for a different "
                "cashback or duration, call respond_to_proposal with decision=modify.")
    return "No pending proposal."


def _sales_text(m: dict, day: str, language: str) -> str:
    d = now().date()
    if m["kind"] == "electronics":
        return "Ask me *stock* for the restock check — sales summaries for the POS store are coming soon."
    if day == "yesterday":
        y = summary.yesterday_vs_last_week(m["id"], d)
        up = y["change_pct"] >= 0
        if language == "en":
            return (f"Yesterday: {inr(y['sales'])} from {y['payments']} payments ({y['customers']} customers), "
                    f"{abs(y['change_pct'])}% {'up' if up else 'down'} vs last {y['weekday']}.")
        return (f"Kal: {inr(y['sales'])} ki bikri, {y['payments']} payments ({y['customers']} grahak) — "
                f"pichhle {y['weekday']} se {abs(y['change_pct'])}% {'zyada' if up else 'kam'}.")
    t = summary.day_totals(m["id"], d)
    when = now().strftime("%-I:%M %p")
    if language == "en":
        return f"Today so far (till {when}): {inr(t['sales'])} from {t['payments']} payments."
    return f"Aaj ab tak ({when} tak): {inr(t['sales'])} ki bikri, {t['payments']} payments."


def _respond(m: dict, decision: str, args: dict) -> str:
    if slump.pending(m["id"], "cashback"):
        return slump.respond(m, decision, args.get("discount_pct"), args.get("duration_hours"))
    if slump.pending(m["id"], "restock"):
        return restock.respond(m, decision)
    if (live := slump.live_campaign(m["id"])) and decision == "modify":
        return slump.change_live(m, live, args.get("discount_pct"))
    return "No open proposal right now." if common.language(m) == "en" else "Abhi koi proposal pending nahi hai."


def _run_tool(m: dict, name: str, args: dict, language: str) -> str:
    if name == "respond_to_proposal":
        return _respond(m, args.get("decision", ""), args)
    if name == "morning_briefing":
        briefing.run(m)
        return ""
    if name == "slump_offer":
        return slump.propose(m) if m["kind"] == "kirana" else menu(m)
    if name == "restock_check":
        return restock.propose(m)
    if name == "campaign_result":
        return slump.result(m)
    if name == "sales_summary":
        return _sales_text(m, args.get("day", "yesterday"), language)
    return menu(m)


YES = re.compile(r"^(haan|haa|han|ha|yes|y|ok|okay|approve|approved|chalu karo|shuru karo|go|haan ji|ji haan)[.! ]*$")
NO = re.compile(r"^(nahi|nahin|na|no|n|reject|mat karo|cancel)[.! ]*$")


def _command(m: dict, text: str, language: str) -> str | None:
    """Deterministic shortcuts. Returns a reply, "" if the flow already sent its messages, or None."""
    t = text.strip().lower()
    if t in {"hi", "hello", "hey", "hii", "namaste", "help", "menu", "start", "options"}:
        return menu(m)
    if t == "sales":
        return _sales_text(m, "yesterday", language) + MENU_HINT[m["kind"]]
    if t == "badlav":
        return ("Batayein kya badlav chahiye — likh ke ya 🎙️ bol ke. Jaise: \"8% kar do\" ya \"sirf 2 ghante\"."
                if language != "en" else "Tell me the change — type or 🎙️ say it, e.g. \"make it 8%\" or \"only 2 hours\".")
    if t in {"briefing", "brief", "morning"}:
        briefing.run(m)
        return ""
    if t in {"slump", "offer"}:
        return _run_tool(m, "slump_offer", {}, language)
    if t in {"stock", "restock"}:
        return restock.propose(m)
    if t in {"result", "results", "nateeja"}:
        return slump.result(m) + MENU_HINT[m["kind"]]
    if YES.match(t):
        return _respond(m, "approve", {})
    if NO.match(t):
        return _respond(m, "reject", {})
    return None


def _agent(m: dict, text: str, language: str) -> str:
    history = db.rows("SELECT role, content FROM chat_log WHERE merchant_id=? ORDER BY id DESC LIMIT 6", m["id"])[::-1]
    system = (f"You are Vyapar Copilot, a Paytm business assistant for {m['owner']} of {m['name']} ({m['kind']}). "
              f"Use a tool whenever the merchant asks about their business, offers, stock or results. "
              f"{_pending_note(m)} If no tool fits, reply in one or two short sentences in {lang.NAMES[language]} "
              "WITHOUT any numbers. Never invent offers, products, prices, rules or store details; if unsure, "
              "suggest sending *help*.")
    messages = [{"role": "system", "content": system}] + \
               [{"role": r["role"], "content": r["content"][:600]} for r in history] + \
               [{"role": "user", "content": text}]
    msg = sarvam.chat(messages, tools=TOOLS)
    calls = msg.get("tool_calls") or []
    if calls:
        c = calls[0]["function"]
        args = json.loads(c.get("arguments") or "{}")
        log.info("tool %s %s", c["name"], args)
        return _run_tool(m, c["name"], args, language)
    reply = (msg.get("content") or "").strip()
    if not reply or len(reply) > 280 or guard.validate(reply, set()) is not None:
        return menu(m)
    return reply


SWITCH = re.compile(r"^\s*(?:(?:switch|change|go|move)(?:\s+(?:to|on))?\s+)?(?:the\s+)?"
                    r"(kirana|electronics)(?:\s+(?:store|shop|dukaan))?\s*(?:pe|par)?\s*(?:chalo|jao)?\s*$", re.I)


def _switch_target(text: str) -> str | None:
    m = SWITCH.match(text)
    return m.group(1).lower() if m else None


def handle(sender: str, text: str, media: list[tuple[bytes, str]]) -> None:
    candidates = common.merchants_for(sender)
    if not candidates:
        log.warning("message from unregistered number %s ignored", sender)
        return
    sess = common.session(sender)

    active = next((c for c in candidates if c["id"] == sess["active_merchant_id"]), candidates[0])
    text = _resolve_choice(active, text or "")

    # Demo only: one phone stands in for two merchants. Production routes by number alone.
    if kind := _switch_target(text or ""):
        target = next((c for c in candidates if c["kind"] == kind), None)
        if target:
            common.set_session(sender, active_merchant_id=target["id"], last_lang=None)  # new shop, its own default language
            common.send(target, "🔄 Switched\n\n" + menu(target))
        return
    m = next((c for c in candidates if c["id"] == sess["active_merchant_id"]), candidates[0])

    if media:
        audio, ctype = media[0]
        try:
            text = sarvam.transcribe(audio, "voice." + ctype.split("/")[-1].split(";")[0], ctype)
        except Exception as e:
            log.warning("STT failed: %s", e)
            common.send(m, "Voice note samajh nahi aaya — kripya type karke bhejiye. 🙏")
            return
        common.send(m, f"🎙️ _Suna:_ \"{text}\"")

    text = (text or "").strip()
    if not text:
        return
    language = lang.detect(text, common.language(m))
    common.set_session(sender, last_lang=language)
    db.run("INSERT INTO chat_log (merchant_id, role, content) VALUES (?, 'user', ?)", m["id"], text)

    reply = _command(m, text, language)
    if reply is None:
        try:
            reply = _agent(m, text, language)
        except Exception as e:
            log.exception("agent failed: %s", e)
            reply = menu(m)
    if reply:
        common.send(m, reply)
