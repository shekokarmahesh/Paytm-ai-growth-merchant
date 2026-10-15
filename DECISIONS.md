# Decisions

## A UPI QR / Soundbox payment carries no item or margin data
2026-10-03 · (no ticket) · category 2

Only timestamp, amount and payer VPA arrive. Kirana features (briefing, slump buster) run on those
three fields plus one merchant-declared shop-level margin. SKU-level logic exists only for merchants
on a billing/POS feed.

## Twilio WhatsApp free-form messages need an open 24h session
2026-10-03 · (no ticket) · category 2

Business-initiated sends (including the 08:30 briefing) fail with 63016 unless the recipient
messaged the number within the last 24h. The demo depends on the owner's phone sending "hi" first;
production needs approved Content Templates.

## sarvam-105b reasons before answering; the conversations variant does not
2026-10-03 · (no ticket) · category 2

sarvam-30b was deprecated in July 2026, leaving sarvam-105b and sarvam-105b-conversations. Plain
sarvam-105b spends its whole token budget on reasoning even at reasoning_effort=low (20–50 s, empty
content), so the app uses sarvam-105b-conversations (~0.3 s, tool calling works). STT is saaras:v3 in
codemix mode (accepts WhatsApp OGG/Opus directly); TTS is bulbul:v3.

## LangGraph was rejected for the agent
2026-10-03 · (no ticket) · category 3

Merchant approval arrives asynchronously over WhatsApp, minutes or hours later, so a proposal is a
persisted row (pending → approved → executed) and the agent is a plain sarvam-105b tool-calling loop.
Graph checkpointing would duplicate that state.
