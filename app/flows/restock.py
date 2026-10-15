"""F3 Smart Restock (POS merchants): flag SKUs that run out before a reorder could land, draft POs."""
from collections import defaultdict
from datetime import timedelta

from app import db, soundbox
from app.agent.guard import inr
from app.analytics import restock
from app.config import now
from app.flows import common
from app.flows.common import language, send
from app.flows.slump import pending


def propose(m: dict) -> str:
    if m["kind"] != "electronics":
        return ("Smart Restock needs item-level stock from a billing/POS system. "
                "Send *switch electronics* to see it for the POS store.")
    t = now()
    p = restock.plan(m["id"], t.date())
    if not p["lines"]:
        return "✅ Stock looks healthy — nothing will run out before a reorder could arrive."
    db.run("UPDATE proposals SET status='superseded' WHERE merchant_id=? AND kind='restock' AND status='pending'", m["id"])
    common.set_prompt(m["id"], "restock")
    db.run("INSERT INTO proposals (merchant_id, kind, payload, created_at, expires_at) VALUES (?, 'restock', ?, ?, ?)",
           m["id"], db.dumps(p), db.ts(t), db.ts(t + timedelta(days=1)))
    lines = []
    for l in p["lines"]:
        risk = " ⚠️ runs out *before* delivery" if l["days_left"] < l["lead_days"] else ""
        lines.append(f"• *{l['name']}* — {l['stock']} left, ~{l['days_left']:g} days at current pace "
                     f"(lead time {l['lead_days']}d){risk}\n   → order {l['reorder_qty']} ({inr(l['line_value'])})")
    n_dist = len({l["distributor"] for l in p["lines"]})
    gap = (f"\n💸 Cash-flow check: this PO ({inr(p['po_value'])}) is more than last week's sales "
           f"({inr(p['week_sales'])}) — consider a Paytm merchant loan." if p["cash_gap"] else
           f"\n💰 Cash-flow check: PO total {inr(p['po_value'])} vs last week's sales {inr(p['week_sales'])} — covered.")
    return (f"📦 *Smart Restock* — Diwali is {p['days_to_diwali']} days away and demand is accelerating.\n"
            f"{len(p['lines'])} items will run low before a reorder lands:\n\n" + "\n".join(lines) + "\n" + gap +
            f"\n\nSend purchase orders to {n_dist} distributors?")


def respond(m: dict, decision: str) -> str:
    p = pending(m["id"], "restock")
    if not p:
        return "There's no open restock draft. Send *stock* to check."
    if decision == "reject":
        db.run("UPDATE proposals SET status='rejected' WHERE id=?", p["id"])
        return "Okay, no purchase orders sent."
    if decision == "modify":
        return "For now I can only send this draft as-is — approve or reject it."
    by_dist = defaultdict(list)
    for l in p["payload"]["lines"]:
        by_dist[l["distributor"]].append(l)
    pos = []
    for i, (dist, lines) in enumerate(sorted(by_dist.items()), start=1):
        po_no = f"PO-{p['id']:04d}-{i}"
        items = "\n".join(f"  {l['sku']} {l['name']} × {l['reorder_qty']} @ {inr(l['unit_cost'])}" for l in lines)
        total = sum(l["line_value"] for l in lines)
        body = (f"🧾 Purchase Order {po_no}\nFrom: {m['name']}\nTo: {dist}\n{items}\nTotal: {inr(total)}\n"
                f"Please confirm dispatch date. Payment via Paytm.")
        pos.append((m["id"], p["id"], dist, body, db.ts(now())))
    db.many("INSERT INTO outbox (merchant_id, kind, ref_id, recipient, body, created_at) VALUES (?, 'purchase_order', ?, ?, ?, ?)",
            pos)
    db.run("UPDATE proposals SET status='executed' WHERE id=?", p["id"])
    send(m, f"✅ {len(pos)} purchase orders sent ({inr(p['payload']['po_value'])} total) to: "
            + ", ".join(sorted(by_dist)) + ".")
    send(m, "👁 *Distributor view* (sample of what the distributor received):\n\n" + pos[0][3]
         + "\n\n_*menu* — all options_")
    soundbox.announce(f"Purchase orders sent to {len(pos)} distributors.", m["voice_lang"])
    return ""
