"""F2 Slump Buster: predict the slow window, propose margin-safe cashback, execute on approval, report."""
from datetime import datetime, timedelta

import numpy as np

from app import db, mock_paytm, soundbox
from app.agent import writer
from app.agent.guard import inr
from app.analytics import discount, footfall, rfm
from app.config import now
from app.flows import common
from app.flows.common import language, send


def _hhmm(h: int) -> str:
    return datetime(2000, 1, 1, h % 24).strftime("%-I %p")


def pending(merchant_id: str, kind: str) -> dict | None:
    p = db.one("SELECT * FROM proposals WHERE merchant_id=? AND kind=? AND status='pending' ORDER BY id DESC LIMIT 1",
               merchant_id, kind)
    if p and p["expires_at"] <= db.ts(now()):
        db.run("UPDATE proposals SET status='expired' WHERE id=?", p["id"])
        return None
    if p:
        p["payload"] = db.loads(p["payload"])
    return p


def live_campaign(merchant_id: str) -> dict | None:
    return db.one("SELECT * FROM campaigns WHERE merchant_id=? AND status='live' AND ends_at>? ORDER BY id DESC LIMIT 1",
                  merchant_id, db.ts(now()))


def live_text(m: dict, live: dict, lang: str) -> str:
    ends = datetime.fromisoformat(live["ends_at"]).strftime("%-I:%M %p")
    return (f"✅ Your {live['discount_pct']:g}% Happy Hours offer is live until {ends}. Send *result* for the outcome."
            if lang == "en" else
            f"✅ Aapka {live['discount_pct']:g}% Happy Hours offer {ends} tak live hai. Nateeja: *result* bhejein.")


def change_live(m: dict, live: dict, pct: float | None) -> str:
    """A running campaign is never edited (customers already hold its vouchers); explain and re-check the ask."""
    en = language(m) == "en"
    cap = discount.max_safe_discount(m["margin_pct"]) * 100
    ends = datetime.fromisoformat(live["ends_at"]).strftime("%-I:%M %p")
    if pct is not None and pct > cap:
        return (f"⚠️ {pct:g}% is above your margin-safe limit of {cap:g}% — it would lose money on every sale. "
                f"Your {live['discount_pct']:g}% offer keeps running until {ends}." if en else
                f"⚠️ {pct:g}% aapki margin-safe seema {cap:g}% se bahut zyada hai — har bikri pe nuksan hoga. "
                f"Aapka {live['discount_pct']:g}% offer {ends} tak chalta rahega.")
    return (f"Your {live['discount_pct']:g}% offer is already live until {ends} — customers hold those vouchers, "
            "so it can't change mid-way. Send *slump* after it ends for a new offer." if en else
            f"Aapka {live['discount_pct']:g}% offer {ends} tak live hai — grahakon ke paas voucher pahunch chuke hain, "
            "isliye beech mein badal nahi sakte. Khatam hone ke baad *slump* bhejiye.")


def build(m: dict) -> dict | None:
    """Analytics only: the slump window and the best safe offer, or None if there is nothing worth doing."""
    t = now()
    fc = footfall.forecast_day(m["id"], t.date())
    slump = footfall.find_slump(fc, after=t)
    if not slump:
        return {"slump": None, "forecast": fc}
    start = max(t, t.replace(hour=slump.start_hour, minute=0, second=0, microsecond=0))
    end = t.replace(hour=slump.end_hour, minute=0, second=0, microsecond=0)
    hours = round((end - start).total_seconds() / 3600, 1)
    targets = rfm.at_risk(m["id"], t)
    # p0: chance a drifting regular shows up in this window anyway (their recent daily rate × window share).
    window_share = sum(fc.hourly[h] for h in range(slump.start_hour, slump.end_hour)) / sum(fc.hourly.values())
    recent = db.one("""SELECT COUNT(*) AS n FROM transactions WHERE merchant_id=? AND ts>=? AND payer_hash IN
                       (SELECT value FROM json_each(?))""", m["id"], db.ts(t - timedelta(days=14)),
                    db.dumps(list(targets.index)))["n"]
    p0 = max(0.005, recent / max(len(targets), 1) / 14 * window_share)
    avg_ticket = float(targets["avg_ticket"].mean()) if len(targets) else 0.0
    plan = discount.optimise(len(targets), avg_ticket, m["margin_pct"], hours, p0)
    return {"slump": slump, "forecast": fc, "start": start, "end": end, "hours": hours, "plan": plan,
            "targets": list(targets.index), "avg_ticket": avg_ticket, "p0": p0}


def propose(m: dict, intro: bool = True, analysis: dict | None = None, show_window: bool = True) -> str:
    """Creates a cashback proposal and returns the message text (caller sends)."""
    lang = language(m)
    if live := live_campaign(m["id"]):
        return live_text(m, live, lang)
    a = analysis or build(m)
    if not a["slump"]:
        return ("Aaj koi slow window nahi dikh rahi — offer ki zarurat nahi. 👍" if lang != "en"
                else "No slow window ahead today — no offer needed. 👍")
    if not a["plan"]:
        return ("Slow window hai, par koi cashback margin-safe nahi ban raha — isliye offer nahi chalayenge."
                if lang != "en" else "There is a slow window, but no cashback is margin-safe, so I won't run one.")
    plan = a["plan"]
    db.run("UPDATE proposals SET status='superseded' WHERE merchant_id=? AND kind='cashback' AND status='pending'", m["id"])
    payload = {"window": [a["slump"].start_hour, a["slump"].end_hour], "drop_pct": a["slump"].drop_pct,
               "starts_at": db.ts(a["start"]), "ends_at": db.ts(a["end"]), "plan": plan.__dict__,
               "targets": a["targets"], "avg_ticket": a["avg_ticket"], "p0": a["p0"], "margin": m["margin_pct"]}
    db.run("INSERT INTO proposals (merchant_id, kind, payload, created_at, expires_at) VALUES (?, 'cashback', ?, ?, ?)",
           m["id"], db.dumps(payload), db.ts(now()), db.ts(a["end"]))
    return offer_text(m, payload, lang, intro, show_window)


def offer_text(m: dict, payload: dict, lang: str, intro: bool = True, show_window: bool = True) -> str:
    common.set_prompt(m["id"], "cashback")
    plan = payload["plan"]
    facts = {
        "start": _hhmm(payload["window"][0]), "end": _hhmm(payload["window"][1]),
        "drop": f"{payload['drop_pct']}%", "pct": f"{plan['discount_pct']:g}%",
        "hours": f"{plan['duration_hours']:g}", "regulars": str(plan["targets"]),
        "extra_sales": inr(plan["expected_sales"]), "profit": inr(plan["expected_profit"]),
        "cap": f"{discount.max_safe_discount(payload['margin']) * 100:g}%",
    }
    if lang == "en":
        fallback = ("📉 Footfall is predicted to drop {drop} between {start}–{end}.\n" if show_window else "") + (
                    "💡 Offer: {pct} cashback for {hours} hours to {regulars} regulars who haven't visited lately.\n"
                    "Expected: {extra_sales} extra sales, {profit} net profit after cashback (safe limit {cap}).")
        ask = "\n\nLaunch it? _Or type / 🎙️ say a change — e.g. \"make it 8% for 2 hours\"_"
    else:
        fallback = ("📉 Aaj {start}–{end} footfall {drop} kam rehne ka anumaan hai.\n" if show_window else "") + (
                    "💡 Offer: {regulars} purane regular grahakon ko {hours} ghante ke liye {pct} cashback.\n"
                    "Anumaan: {extra_sales} extra bikri, cashback ke baad {profit} munafa (safe seema {cap}).")
        ask = "\n\nChalu karein? _Ya badlav likhiye / 🎙️ boliye — jaise \"8% kar do, sirf 2 ghante\"_"
    if not intro:
        return writer.fill_only(fallback, facts) + ask
    return writer.compose("Heads-up that a slow afternoon is coming and a profitable win-back offer is ready",
                          fallback, facts, lang) + ask


def respond(m: dict, decision: str, discount_pct: float | None = None, duration_hours: float | None = None) -> str:
    p = pending(m["id"], "cashback")
    lang = language(m)
    en = lang == "en"
    if not p:
        return "There's no open offer right now. Send *slump* to check." if en else \
            "Abhi koi offer pending nahi hai. *slump* bhejiye naya check karne ke liye."
    if decision == "reject":
        db.run("UPDATE proposals SET status='rejected' WHERE id=?", p["id"])
        return "Okay, skipped. 👍" if en else "Theek hai, offer nahi chalayenge. 👍"
    payload = p["payload"]
    plan = payload["plan"]
    if decision == "modify":
        pct = discount_pct if discount_pct is not None else plan["discount_pct"]
        hrs = duration_hours if duration_hours is not None else plan["duration_hours"]
        new, reason = discount.check(pct, hrs, plan["targets"], payload["avg_ticket"], payload["margin"], payload["p0"])
        if not new:
            cap = f"{discount.max_safe_discount(payload['margin']) * 100:g}%"
            msg = {
                "above_cap": (f"⚠️ {pct:g}% is above your margin-safe limit of {cap}.",
                              f"⚠️ {pct:g}% aapki margin-safe seema {cap} se zyada hai — isme nuksan hoga."),
                "below_min": ("⚠️ Below 5% cashback doesn't bring customers back.",
                              "⚠️ 5% se kam cashback pe grahak wapas nahi aate."),
                "bad_duration": ("⚠️ Duration must be between 30 minutes and 8 hours.",
                                 "⚠️ Samay 30 minute se 8 ghante ke beech hona chahiye."),
                "loss_making": (f"⚠️ {pct:g}% for {hrs:g}h would lose money.",
                                f"⚠️ {pct:g}% {hrs:g} ghante ke liye ghaate ka sauda hai."),
            }[reason][0 if en else 1]
            keep = (f" Current offer stays: {plan['discount_pct']:g}% for {plan['duration_hours']:g}h. Reply *yes* to run it."
                    if en else f" Pehle wala offer khula hai: {plan['discount_pct']:g}% {plan['duration_hours']:g} ghante. *haan* bolein to chalu.")
            return msg + keep
        start = datetime.fromisoformat(payload["starts_at"])
        payload["plan"] = new.__dict__
        payload["ends_at"] = db.ts(start + timedelta(hours=hrs))
        payload["window"] = [start.hour, int(np.ceil(start.hour + (start.minute / 60) + hrs))]
        db.run("UPDATE proposals SET payload=? WHERE id=?", db.dumps(payload), p["id"])
        updated = "✏️ Updated offer:\n" if en else "✏️ Naya offer:\n"
        return updated + offer_text(m, payload, lang, intro=False)
    return execute(m, p)


def execute(m: dict, p: dict) -> str:
    payload, plan = p["payload"], p["payload"]["plan"]
    lang = language(m)
    starts_at, ends_at = payload["starts_at"], payload["ends_at"]
    cid = mock_paytm.create_cashback_campaign(m["id"], plan["discount_pct"], starts_at, ends_at, payload["targets"])
    row = db.run("""INSERT INTO campaigns (proposal_id, merchant_id, paytm_campaign_id, discount_pct, starts_at, ends_at, plan)
                    VALUES (?,?,?,?,?,?,?)""", p["id"], m["id"], cid, plan["discount_pct"], starts_at, ends_at,
                 db.dumps(payload))
    db.run("UPDATE proposals SET status='executed' WHERE id=?", p["id"])
    end_txt = datetime.fromisoformat(ends_at).strftime("%-I:%M %p")
    vouchers = []
    for payer in payload["targets"]:
        code = mock_paytm.voucher_code(cid, payer)
        vouchers.append((m["id"], row, payer, (
            f"🎁 {m['name']} misses you! Pay with Paytm UPI before {end_txt} today and get "
            f"{plan['discount_pct']:g}% cashback. Code: {code}"), db.ts(now())))
    db.many("INSERT INTO outbox (merchant_id, kind, ref_id, recipient, body, created_at) VALUES (?, 'voucher', ?, ?, ?, ?)",
            vouchers)
    link = mock_paytm.promo_upi_link(m["upi_vpa"], m["name"], f"Happy Hours {plan['discount_pct']:g}% cashback")
    if lang == "en":
        confirm = (f"✅ Campaign live! ({cid})\n• {plan['discount_pct']:g}% cashback until {end_txt}\n"
                   f"• Vouchers sent to {len(vouchers)} regulars on WhatsApp\n• Promo QR link: {link}\n"
                   "Send *result* anytime for the outcome · *menu* for all options.")
    else:
        confirm = (f"✅ Offer live ho gaya! ({cid})\n• {end_txt} tak {plan['discount_pct']:g}% cashback\n"
                   f"• {len(vouchers)} regular grahakon ko WhatsApp voucher bhej diye\n• Promo QR link: {link}\n"
                   "Nateeja: kabhi bhi *result* bhejein · *menu* — sab options")
    send(m, confirm)
    send(m, "👁 *Customer view* (sample of the voucher your regulars got):\n\n" + vouchers[0][3])
    soundbox.announce("ऑफर लाइव हो चुका है। हैप्पी आवर्स कैशबैक शुरू।" if m["voice_lang"] == "hi-IN"
                      else "Offer is now live. Happy hours cashback has started.", m["voice_lang"])
    return ""


def result(m: dict, campaign_id: int | None = None) -> str:
    """Closes a live campaign (simulated redemptions from the lift model) and reports the outcome."""
    lang = language(m)
    c = db.one("SELECT * FROM campaigns WHERE merchant_id=? AND (? IS NULL OR id=?) ORDER BY id DESC LIMIT 1",
               m["id"], campaign_id, campaign_id)
    if not c:
        return "No campaign has run yet." if lang == "en" else "Abhi tak koi campaign nahi chala."
    if c["status"] == "live":
        payload = db.loads(c["plan"])
        plan = payload["plan"]
        rng = np.random.default_rng(c["id"])
        d = plan["discount_pct"] / 100
        prob = discount.lift(d, plan["duration_hours"]) + payload["p0"]
        visits = int(rng.binomial(plan["targets"], min(prob, 1)))
        sales = float(rng.lognormal(np.log(payload["avg_ticket"]), 0.35, visits).sum()) if visits else 0.0
        cashback = sales * d
        baseline = plan["targets"] * payload["p0"] * payload["avg_ticket"] * payload["margin"]
        profit = sales * payload["margin"] - cashback - baseline
        res = {"vouchers": plan["targets"], "visits": visits, "sales": round(sales), "cashback": round(cashback),
               "net_profit": round(profit), "discount_pct": plan["discount_pct"]}
        db.run("UPDATE campaigns SET status='ended', result=? WHERE id=?", db.dumps(res), c["id"])
    else:
        res = db.loads(c["result"])
    facts = {"vouchers": str(res["vouchers"]), "visits": str(res["visits"]), "sales": inr(res["sales"]),
             "cashback": inr(res["cashback"]), "profit": inr(res["net_profit"]), "pct": f"{res['discount_pct']:g}%"}
    if lang == "en":
        fallback = ("📊 Happy Hours result ({pct} cashback)\n• {vouchers} vouchers → {visits} regulars came back\n"
                    "• {sales} sales from them\n• {cashback} cashback paid\n• Net profit after cashback: {profit}")
    else:
        fallback = ("📊 Happy Hours ka nateeja ({pct} cashback)\n• {vouchers} voucher → {visits} regular grahak wapas aaye\n"
                    "• Unse {sales} ki bikri\n• {cashback} cashback diya\n• Cashback ke baad shuddh munafa: {profit}")
    return writer.compose("Celebrate that the cashback campaign brought regular customers back", fallback, facts, lang)


def close_due() -> list[tuple[dict, str]]:
    """Campaigns whose window has passed -> [(merchant, report)]."""
    out = []
    for c in db.rows("SELECT * FROM campaigns WHERE status='live' AND ends_at<=?", db.ts(now())):
        m = db.one("SELECT * FROM merchants WHERE id=?", c["merchant_id"])
        out.append((m, result(m, c["id"])))
    return out
