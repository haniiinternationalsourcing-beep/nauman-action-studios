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
- Restore: run `tools/restore_studio.py <export.zip> <target-folder>` — crash-safe procedure: the archive is validated (structure, schema, TWO-directional manifest check — unlisted extra files and missing listed files both reject, path safety, size/ratio limits), extracted into a staging folder on the same filesystem and hash-verified there; an existing studio tree is first backed up to a timestamped ZIP; the swap then happens by rename under a recovery journal, the new tree is hash-verified again in place, and only then is the old tree removed. A crash at any point leaves either the old studio intact or a journal from which the next run (or `--recover`) restores/completes it automatically. `--verify-only` checks without extracting and takes no lock.
- Interrupted restore: run `tools/restore_studio.py --recover <target-folder>`. Recovery finishes or rolls back the interrupted swap recorded in the journal and clears a stale lock only when its owner is proven dead (PID + start-time evidence). A live or unprovable lock is never touched; `--force-stale-lock` is the operator's deliberate manual override and is always reported. A corrupt journal stops everything — nothing is deleted on a guess.
- Restore safety notes (fix phase 3): Windows path forms in a ZIP (drive letters, UNC, device paths, reserved names) are rejected outright, and every extracted file is containment-checked inside the staging folder and created exclusively. A journal is only ever acted on for the exact target folder it records — recovering a different folder, or a journal copied elsewhere, is refused without touching anything. If the tool aborts with a durability failure (exit 4), a genuine disk I/O error hit a journal/rename step: the studio is untouched or journal-guarded — run `--recover <target-folder>` to reconcile, and check the disk before retrying.
- Restore safety notes (fix phase 4): if a restore refuses with a journal-safety message (exit 2) about `.nas-restore-journal.json.tmp`, something unexpected is sitting at the journal's temp path — a symlink there is refused untouched on purpose; inspect it yourself before removing anything. A stale temp from a crashed run is preserved automatically as `.nas-restore-journal.json.tmp.stale-<time>` (its hash and path are printed) — it is evidence, not junk. On Windows, directory fsync does not exist through this tool's mechanism; durability there rests on file-level fsyncs + journal checksums (the tool prints this once) — genuine disk errors still abort with exit 4 on Windows too.
- Data file: regenerate the app's view with `tools/generate_data.py` (the canonical version — the app embeds an identical copy). Never hand-edit data.json.
## Control Room app rules
- The header badge always shows DEMO DATA or STUDIO DATA — believe the badge.
- Approve / Reject / Mark Spent need the Owner PIN unlock. The PIN is stored only as a PBKDF2-HMAC-SHA-256 hash (salt + 210,000 iterations; older plain-SHA-256 records upgrade automatically on the first successful unlock). It is a device-level convenience lock, NOT server security — anyone holding the file's source can bypass it; true accounts need a backend.
- The app keeps a backup copy of its saved state and recovers from it if the main copy is corrupted; a notice is shown when that happens.
