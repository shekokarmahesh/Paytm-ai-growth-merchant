# Vyapar Copilot — Tech Stack (v1, agreed 2026-10-03)

## AI — Sarvam only
| Need | Model |
|---|---|
| Agent LLM (tool calling) | `sarvam-105b` |
| Voice-note STT (Hinglish) | `saaras:v3`, `mode=codemix` |
| Briefing / confirmation TTS | `bulbul:v3` |

## Platform
| Layer | Choice |
|---|---|
| Backend | **Single** Python FastAPI app — DS as a module (`analytics/`), agent + webhooks alongside |
| DS | pandas + LightGBM; synthetic data generator |
| Agent | Plain tool-calling loop; approvals as `proposals` rows (`pending → approved → executed`) |
| Automation | n8n (Docker): 08:30 cron, voucher fan-out, distributor PO, confirmations |
| Messaging | Twilio WhatsApp. Inbound webhook → FastAPI. |
| DB | Postgres (docker-compose) |
| UI | **None.** The merchant's WhatsApp is the UI. "Soundbox" = audio voice note. |
| Run | Local only (docker-compose). A tunnel (cloudflared/ngrok) is still required so Twilio can reach the webhook and fetch TTS audio. |

## Twilio constraints
- Single test recipient (owner's phone, in `.env`).
- Session is opened by sending "hi" to the business number; free-form messages work for 24h after the last inbound message. **Re-send "hi" before every demo/test session.**
- Credentials live only in gitignored `.env`.
