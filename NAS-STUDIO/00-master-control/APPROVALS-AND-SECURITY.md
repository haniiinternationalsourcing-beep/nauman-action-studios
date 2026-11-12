# Approvals & Security Controls
## Paid-action rule (absolute)
No paid action executes without an approval entry from Nauman:
- Subscriptions (Ultra, ElevenLabs, any tool) — approval per purchase
- Credit top-ups — approval per pack
- Paid generation batches — estimate shown first, approval, then generation
Approvals are recorded in approvals-log.csv (date, item, cost, approved-by, status).
## Security
- API keys: NEVER stored in this folder, the app, or chat. Keys live only in secure vault/connection flows.
- All tool accounts belong to Nauman (his identity, his devices for verification).
- Project data is private by default; exports are made only for Nauman.
- The Control Room app is static and holds no secrets — it can be shared as a link without exposing keys.
