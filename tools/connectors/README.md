# Connectors — modular API architecture (Nauman Action Studios)

One module per provider. A connector is a small Python file in this folder
that knows how to talk to ONE service. Nothing here calls any API until the
owner has created that account and stored its key in the Secure Vault.

## Module contract (every connector must follow it)
1. **Key handling:** the connector reads its key at run time from the
   environment variable named in its own header (set from the Secure Vault
   by the operator for that run only). Keys are NEVER written into this
   folder, the Control Room HTML, the GitHub repo, or any log.
2. **One test call first:** every connector ships a `--test` mode that makes
   a single harmless read call and prints the real result. A route is only
   marked Working (in NAS-STUDIO/INTEGRATIONS.md and in the app) after its
   `--test` passes against the owner's real account.
3. **Real results only:** connectors return the provider's actual response
   or the actual error. No canned success, no simulated data.
4. **Logging:** every production call appends one line to the relevant
   studio register (generation log / budget ledger) with provider, action,
   cost and result — the same discipline as the manual Flow route.

## Planned modules (architecture ready, accounts pending owner decision)
- `gemini_veo.py` — Veo via the Gemini API. Separate pay-per-second API
  billing; NOT the Flow subscription (Flow credits can never be spent via
  API). Needs: Google AI API key.
- `elevenlabs_voice.py` — dialogue/TTS for film voices (the built-in TTS
  set was verified inadequate on 2026-11-12). Needs: ElevenLabs account +
  API key.
- `kling_video.py` — action/motion generations. Needs: Kling API access.

## Working today (not in this folder, by design)
- Google Flow — Manual route in the browser (no API exists).
- GitHub — used to publish the audit repo (see the studio operator manual).
- ffmpeg — local post-production pipeline (NAS-STUDIO/05-post/).
