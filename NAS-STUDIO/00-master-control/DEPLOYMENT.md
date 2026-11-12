# Control Room — build & deployment (SECURE DATA MODEL, fixed 2026-11-13)
## The flaw that was fixed
Old plan generated a data.json snapshot of REAL studio data and uploaded it with the public app — that would expose private scripts, budgets and project data to anyone with the link. REMOVED.
## The secure model (binding)
1. The hosted app ships with DEMO DATA ONLY. No real script, budget or project data is ever uploaded to public hosting.
2. Real data never leaves the studio folder by default. To view real data, the app has a "Load studio data" action: the owner picks the local data.json (produced locally by tools/generate_data.py) — the file is read in the browser on HIS device and is NOT uploaded anywhere.
3. Netlify (his account) hosts only the empty shell + demo data. Losing the link exposes nothing private.
4. Source code lives in studio-app/ beside this file; rebuild/redeploy ~1 minute.
## Build notes
Static HTML/CSS/JS, no backend, no keys, no secrets in code. Works from any static host or a local file.

## Complete deployment & operations (V4, 2026-11-13)
### Run the app
- **On the owner's phone/laptop (recommended):** open the single-file build
  `NAS-ControlRoom-V4-AUDITFIX.html` in Chrome (Android or desktop). No
  install, no server. Data saves on that device only (localStorage, with an
  automatic backup copy + recovery).
- **Public audit copy:** github.com/haniiinternationalsourcing-beep/
  nauman-action-studios (demo data only). The large backup ZIPs inside
  `NAS-STUDIO/09-backups/` are stored as `.parts/` + `.sha256` (GitHub API
  blob limit) — reassemble with `cat <name>.parts/part-* > <name>` and
  verify with `sha256sum -c <name>.sha256`.
### First-run setup
1. Open the app → Master Control → Owner Lock → **Set Owner PIN**
   (stored only as a PBKDF2-HMAC-SHA-256 hash + salt; the PIN never is).
2. Approve / Reject / Mark Spent work only while unlocked; 5 wrong PIN
   attempts lock entry for 60 seconds. This lock is device-level
   convenience security, NOT server-grade — the app says so itself.
### Load real studio data (never uploaded anywhere)
1. On the studio machine: `python3 tools/generate_data.py`
   (writes NAS-STUDIO/data.json, schema v2).
2. In the app: Data Vault → load that local data.json. The
   `studioToAppData()` adapter maps it; the header badge flips to
   STUDIO DATA. The file is read in the browser only.
### Backup & restore (proven, see TEST-REPORT-2026-11-13.md)
- Backup: `python3 tools/export_studio.py` → timestamped ZIP +
  SHA-256 MANIFEST.json in NAS-STUDIO/09-backups/.
- Restore: `python3 tools/restore_studio.py <zip> <target-folder>`
  (validates structure/schema/hashes, refuses traversal/symlink/duplicate/
  bomb archives, backs up any existing tree first, re-verifies on disk).
  `--verify-only` checks without extracting.
### Updating the app
Changes go through the artifact builder; the three embedded tool scripts
must be re-synced to the canonical `tools/` files at packaging
(`tools/sync_embedded.py` documents the method) so the app can never drift
from the studio again.
