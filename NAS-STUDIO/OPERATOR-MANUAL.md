# OPERATOR MANUAL — NAUMAN ACTION STUDIOS (plain language, for any operator)
## What this studio is
A folder of open files (NAS-STUDIO) + a viewer app (Control Room) + production tools (Flow, Kling, Seedance, ElevenLabs) that belong to the owner, Nauman Magray. The operator runs production; the owner approves every paid step.
## Where things live
- Projects: 01-projects/PROJECT-001/ (screenplay, characters, scenes, clips, dialogue, audio, edit, expenses, exports)
- Characters: 02-characters/ (one .json + locked portrait per character)
- Generation records: 03-video-center/GENERATION-LOG.md
- Budget: 06-budget/BUDGET-LEDGER.md · Approvals: 00-master-control/approvals-log.csv
## How a character is locked
1. Generate ONE approved portrait (free image generation in Flow). 2. Save it in 02-characters with a .json profile (name, age, build, hair, clothes, voice). 3. Every video generation attaches that portrait as reference (Veo Fast/Lite only — Quality cannot take references). 4. Check every clip: eyes/face shape, hairstyle, clothes, body proportions.
## How credits are logged
Every generation: note credits before/after, model, blocked/refunded, usable seconds. No log = it did not happen.
## How money moves
Nothing paid without the owner's approval entry. Estimates are always shown first, in PKR.
## If you are a new operator
Read this manual + AGENTS-AND-WORKFLOW.md (07-agents/) + the project folder. You now know everything the previous operator knew.
## Backup and restore (post-audit procedure, 2026-11-13)
- Backup: run `tools/export_studio.py` — it writes a timestamped ZIP into 09-backups/ with a SHA-256 manifest inside. A ZIP without a verified restore is NOT a proven backup.
- Restore: run `tools/restore_studio.py <export.zip> <target-folder>` — it validates the archive (structure, schema, hashes, path safety), backs up any existing studio tree at the target to a timestamped ZIP first, then restores and re-verifies every file on disk. `--verify-only` checks without extracting.
- Data file: regenerate the app's view with `tools/generate_data.py` (the canonical version — the app embeds an identical copy). Never hand-edit data.json.
## Control Room app rules
- The header badge always shows DEMO DATA or STUDIO DATA — believe the badge.
- Approve / Reject / Mark Spent need the Owner PIN unlock. The PIN is stored only as a SHA-256 hash. It is a device-level convenience lock, NOT server security — anyone holding the file's source can bypass it; true accounts need a backend.
- The app keeps a backup copy of its saved state and recovers from it if the main copy is corrupted; a notice is shown when that happens.
