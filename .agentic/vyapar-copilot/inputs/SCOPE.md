# Vyapar Copilot — Build Scope (v1, locked 2026-10-03)

Track 1: Merchant Growth AI · Team Xyz (Mahesh Shekokar — Full-stack AI, T N Sreevarsan — Data Science)

Build order: F1 → F2 → F3. If time runs out, wrap up with what is done.

## Data reality (drives everything)
- A UPI QR / Soundbox payment carries only **timestamp, amount, payer VPA (hashed)**. No item, no margin.
- So F1 and F2 run on QR-only data. Margin = one shop-level average the merchant declares once.
- SKU-level data exists only on a billing/POS system — so F3 gets its own persona.

## Personas
| Persona | Device | Features |
|---|---|---|
| Ramesh Gupta, kirana, Tier-2 | Soundbox + static UPI QR | F1, F2 |
| Mall electronics store | Paytm Android POS / EDC (any POS incl. Pine Labs via billing API — one line in pitch) | F3 |

## Features
| | F1 Morning Briefing | F2 Slump Buster | F3 Smart Restock |
|---|---|---|---|
| DS | Yesterday vs same-day-last-week; today's predicted slow window | Hourly footfall forecast → slump flag; discount d ∈ [5,15]% bounded by margin rule; RFM at-risk regulars | Per-SKU run-rate + festival uplift → days-to-stockout, reorder qty |
| Agent | LLM writes Hinglish script **from DS numbers only** → TTS | Proposes campaign → merchant approves by voice note (STT) → tool call | Drafts PO → one-tap approve |
| Automation | 08:30 cron → generate → WhatsApp + Soundbox | Vouchers to regulars, promo QR, Soundbox confirmation | PO to distributor on WhatsApp |

## Mocked (but done well)
Paytm cashback/promo API · live transaction stream (replay script) · Soundbox (audio voice note on WhatsApp) · POS SKU feed (CSV/JSON).

## Real
WhatsApp via Twilio to the owner's phone — WhatsApp is the only UI (no PWA).

## Skipped (pitch slide only)
Khata/credit · loan / working-capital signals · geo `radius_km` targeting (no customer location → target regulars list) · 3rd vertical (café/garments) · running both Prophet and LightGBM (pick one) · auth / multi-merchant · customer-side app.

## Guardrails
Every number comes from a DS endpoint, never the LLM. Every action waits for merchant approval.
