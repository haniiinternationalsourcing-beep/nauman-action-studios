# Integrations — real connection architecture (honest statuses)

Rule: a route is marked **Working** only when it has actually been used end
to end. Anything else is **Manual** (a human/operator does it in the real
service) or **Planned** (architecture ready, account/key still needed).
No fake API responses and no simulated success anywhere in this studio.

| Route | Status | What it really is | Needed to connect |
|---|---|---|---|
| Google Flow (Veo 3.1) | **Manual** | Flow has NO public API. The operator (owner or Naumii) works in the Flow web app in a browser. Flow subscription credits can NEVER be spent through any API — anyone claiming otherwise is selling account access, not an API. | Already working: owner's Google AI Pro account. |
| Veo via Gemini API | **Planned** | A separate, real API from Google AI. Billed per second of video, far more expensive than Flow subscription credits, and billed to a different account. Would let the studio queue generations programmatically. | Google AI API key + paid API billing, owner's decision. Not needed while the Flow Manual route works. |
| ElevenLabs (voices) | **Planned** | Real API exists (text-to-speech, voice library). The studio's film voices are planned here because the built-in TTS voices were verified inadequate (2026-11-12). | Owner creates the ElevenLabs account (free tier first) and adds credits; API key stored by the owner, never in this folder or the app. |
| Kling | **Planned** | Real API exists for image/video generation. Routed for action/motion work in the studio's tool plan. | Kling account + API access, owner's decision. |
| Seedance (via Dreamina) | **Manual** | No direct public API; work happens in the Dreamina web app. Routed for dialogue/multi-shot consistency + cartoon in the tool plan. | Owner's Dreamina account when purchased. |
| GitHub | **Working** | This studio's audit package is published and updated through the GitHub API (repo: haniiinternationalsourcing-beep/nauman-action-studios). Used 2026-11-13 for the independent audit. | Already connected. |
| ffmpeg editor pipeline | **Working** | Local scripted editing (05-post/EDITOR-PIPELINE.md) — assembled the first film and the micro-pilot handling. Runs on the operator's machine, no account needed. | Nothing. |
| YouTube upload | **Manual** | Uploads happen in the owner's signed-in browser/Studio (standing owner-approved route for his channels). No YouTube API integration is claimed. | Owner's channel, already in use. |

## Connection procedure (any Planned route, when the owner decides)
1. Owner creates the account on his own device and completes verification.
2. Owner generates the API key and stores it in the Secure Vault — never in
   chat, never in this folder, never in the public app or repo.
3. The operator writes a small connector script under
   `nauman-action-studios/tools/` that reads the key from the vault at run
   time, makes ONE test call, and logs the real result.
4. Only after that test passes does the route's status here become Working,
   and the Control Room Integrations panel is updated to match.

## Demo vs real in the Control Room app
- The public app ships with a clearly badged DEMO dataset.
- Loading a local `data.json` (from `tools/generate_data.py`) switches the
  app to STUDIO DATA via the `studioToAppData()` adapter; the header badge
  changes and exports say so.
- Feature status chips (Working / Partially Working / Manual / Planned)
  describe the feature, not the data, and are kept honest per feature.
