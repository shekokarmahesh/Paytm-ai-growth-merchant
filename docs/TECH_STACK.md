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
| Backend | **Single** Python FastAPI app — DS as a module (`analytics/`), agent + Twilio poller alongside |
| DS | pandas + scikit-learn HistGradientBoosting (LightGBM-style GBDT, no native libomp dependency); synthetic data generator |
| Agent | Plain tool-calling loop; approvals as `proposals` rows (`pending → approved → executed`) |
| Automation | n8n via `npx n8n` (no Docker): **schedule only** — 08:30 cron calls FastAPI. All sends happen in FastAPI. |
| Messaging | Twilio WhatsApp, **text only outbound**. Inbound via **polling** the Twilio Messages API every ~3s (no webhook). Inbound voice notes downloaded from Twilio media URLs with account auth. |
| DB | SQLite file `var/vyapar.db` (Docker Hub is unreachable on the build network, so no containers) |
| UI | **None.** The merchant's WhatsApp is the UI (text). "Soundbox" = bulbul:v3 audio played on the laptop speaker. |
| Run | Local only: `uvicorn` + `npx n8n`. **No tunnel** — nothing on the laptop is publicly reachable, by design. |

## Twilio constraints
- Single test recipient (owner's phone, in `.env`).
- Session is opened by sending "hi" to the business number; free-form messages work for 24h after the last inbound message. **Re-send "hi" before every demo/test session.**
- Credentials live only in gitignored `.env`.
