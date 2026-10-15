"""F1 Morning Briefing: yesterday vs same day last week, today's slow window, and the offer, by WhatsApp + Soundbox."""
from app import db, soundbox
from app.agent import writer
from app.agent.guard import inr
from app.analytics import summary
from app.config import now
from app.flows import restock, slump
from app.flows.common import language, send


def _last_result(m: dict) -> dict | None:
    c = db.one("SELECT result FROM campaigns WHERE merchant_id=? AND status='ended' ORDER BY id DESC LIMIT 1", m["id"])
    return db.loads(c["result"]) if c else None


def run(m: dict) -> None:
    if m["kind"] == "electronics":
        send(m, "☀️ Good morning, " + m["owner"] + "!\n\n" + restock.propose(m))
        soundbox.announce("Good morning. A few items will run out before Diwali. I have drafted purchase orders.",
                          m["voice_lang"])
        return

    lang = language(m)
    en = lang == "en"
    y = summary.yesterday_vs_last_week(m["id"], now().date())
    last = _last_result(m)
    a = slump.build(m)
    up = y["change_pct"] >= 0
    facts = {"sales": inr(y["sales"]), "change": f"{abs(y['change_pct'])}%", "customers": str(y["customers"]),
             "weekday": y["weekday"], "trend": ("up" if up else "down") if en else ("zyada" if up else "kam")}
    if en:
        template = "📊 Yesterday ({weekday}): {sales} in sales — {change} {trend} vs last {weekday}. {customers} customers."
    else:
        template = "📊 Kal ({weekday}) ki bikri {sales} — pichhle {weekday} se {change} {trend}. {customers} grahak aaye."
    if a["slump"]:
        facts |= {"slow_start": slump._hhmm(a["slump"].start_hour), "slow_end": slump._hhmm(a["slump"].end_hour),
                  "drop": f"{a['slump'].drop_pct}%"}
        template += ("\n📉 Today {slow_start}–{slow_end}: footfall predicted {drop} below normal." if en else
                     "\n📉 Aaj {slow_start}–{slow_end} footfall {drop} kam rehne ka anumaan hai.")
    if last:
        facts |= {"won_back": str(last["visits"]), "camp_profit": inr(last["net_profit"])}
        template += ("\n🎉 Last offer won back {won_back} regulars, {camp_profit} net profit." if en else
                     "\n🎉 Pichhle offer se {won_back} regular wapas aaye, {camp_profit} munafa.")
    text = writer.compose(f"Good-morning greeting to {m['owner']} before their daily sales briefing",
                          template, facts, lang)
    if live := slump.live_campaign(m["id"]):
        text += "\n\n" + slump.live_text(m, live, lang)
    elif a["slump"] and a["plan"]:
        text += "\n\n" + slump.propose(m, intro=False, analysis=a, show_window=False)
    send(m, text)

    if m["voice_lang"] == "hi-IN":
        voice = (f"नमस्ते {m['owner']}! कल की बिक्री {facts['sales']} रही, पिछले हफ्ते से {facts['change']} "
                 + ("ज़्यादा।" if up else "कम।")
                 + (f" आज {facts['slow_start']} से {facts['slow_end']} तक दुकान धीमी रहने का अनुमान है, ऑफर तैयार है।"
                    if a["slump"] else ""))
    else:
        voice = f"Good morning. Yesterday's sales were {facts['sales']}."
    soundbox.announce(voice, m["voice_lang"])
