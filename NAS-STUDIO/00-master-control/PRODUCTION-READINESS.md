# PRODUCTION READINESS — Nauman Action Studios (2026-11-13, final)

Verdict rule (owner's): nothing is "complete" that was not actually tested.
PASS = tested and worked. FAIL = tested and failed (with what was done).
PENDING = not yet tested in the required environment. PLANNED = not built.

## PASS
- Data pipeline: generate_data.py (canonical, schema v2) → app import via
  studioToAppData() → app export validates as schema v2. Tested at
  1/1/1 records and at 5 projects / 6 characters / 5 approvals (generator)
  and 3 / 4 / 5 (adapter, incl. APR-S IDs + status mapping).
- Backup: export_studio.py ZIP + SHA-256 manifest.
- Restore: real extraction; manifest verified before + re-hashed after;
  21/21 files byte-identical to source (independent comparison).
  Fix phase 2 (post-review): manifest verification is TWO-directional
  (unlisted extra files and missing listed files both reject);
  extraction is staged on the same filesystem and the swap is guarded
  by a checksummed journal with fsync — kills during staging, mid-swap
  and after swap all recover automatically (original restored or new
  studio verified and completed); post-swap corruption rolls back in
  the same run; corrupt journal/lock stops everything without touching
  a folder; a single-restore lock with PID + start-time stale-lock
  protocol protects live processes. Full evidence:
  TEST-REPORT-2026-11-13.md (Fix phase 2) and
  fix2-verification-20261113.log.
- Restore safety: path traversal refused; symlink refused; duplicate
  paths refused (with/without manifest); ZIP bomb refused pre-extraction
  (ratio/size/entry limits); low-disk-space refused pre-write; nested
  archives inert; pre-restore auto-backup of an existing tree works and
  itself verifies; old pre-manifest exports still verify/restore.
- Owner PIN: PBKDF2-HMAC-SHA-256 (salt, 210,000 iterations), versioned
  record; wrong PIN blocked + logged; 5 failures → 60 s lockout; PIN
  reset with confirmation; legacy plain-SHA-256 record migrates on first
  successful unlock (audit-logged). All in a 43/43-check Node harness,
  run twice; PBKDF2 output matches the published test vector and Node's
  own pbkdf2Sync.
- Approval gate: Approve / Reject / Mark Spent / Reset-to-demo blocked
  while locked (attempts audit-logged); approval-ID-linked spend gate.
- Storage: save-on-change with backup copy; corrupt-main recovery from
  backup (notice shown); both-corrupt → demo fallback (notice shown);
  storage key unchanged from the previous build (no user data lost);
  legacy-key migration with pre-migration backup.
- Honesty systems: DEMO DATA / STUDIO DATA header badge; per-feature
  status chips; Integrations panel with real statuses; embedded tool
  scripts byte-identical to tools/ (packaging sync, verified).
- GitHub audit repo: public, main branch only, updated by API commits.

## FAIL (found, fixed, re-tested — recorded, not hidden)
- ZIP bomb v1: the first bomb test filled the test disk — restore had NO
  size limits. Fixed with archive limits + free-space guard; re-test
  PASS (refused before extraction, 0 bytes written).
- generate_data.py divergence: three variants existed. Fixed by choosing
  the disk tool as canonical + packaging sync; re-verified byte-equal.
- Restore was verify-only in the audited build. Rebuilt as a real
  restore; proof above.
- Manifest check was one-directional (independent review of commit
  d78f931): an extra unlisted file restored silently. Fixed with
  two-directional verification; reject proven by test.
- Restore had no rollback (same review): a mid-extraction crash left a
  partial studio. Fixed with staged extraction + journal + lock +
  recovery mode; kill/corruption tests prove automatic recovery.

## PENDING (not done — do not treat as passed)
- **Live browser click-testing** in real Android Chrome (owner's Infinix)
  and desktop Chrome. The operator cannot run the owner's phone browser;
  harness tests are NOT a substitute. Use the checklists below.
- **ChatGPT's re-audit verdict** on the final commit.
- APR-001 owner confirmation (micro-pilot approval stays "Pending owner
  confirmation" until the owner confirms directly).

## PLANNED (architecture ready, not connected)
- ElevenLabs voices (needs owner account + key in the Secure Vault).
- Veo via Gemini API (separate per-second billing; needs API key).
- Kling API (needs account/API access).
- Server-grade authentication (needs a backend; the static app cannot
  provide it — the PIN lock is device-level by design and says so).

## Manual testing checklist — Android Chrome (owner's phone)
1. Open the final HTML file in Chrome. Header badge shows DEMO DATA.
2. Master Control → Owner Lock → Set Owner PIN (choose one you remember).
3. Approvals: try Approve while LOCKED → must show "Owner unlock
   required" and change nothing.
4. Unlock with a WRONG PIN → blocked; repeat 5 times → 60-second lockout
   countdown appears.
5. Wait, unlock with the CORRECT PIN → approvals now work.
6. Add a budget line and try Mark Spent without an approved ID → blocked;
   approve it first (unlocked), then Mark Spent → works.
7. Reload the page → your data is still there (persistence).
8. Data Vault → download the three scripts → each file downloads.
9. Data Vault → export data (JSON + ZIP) → files download; restore the
   JSON → data comes back.
10. Reset PIN (with confirmation) → old PIN no longer unlocks; set a new
    one → new PIN works.
## Manual testing checklist — Desktop Chrome (laptop)
Same 10 steps, plus:
11. Resize the window narrow/wide — layout stays clean, bottom tabs on
    narrow, sidebar on wide.
12. Load a local data.json (from tools/generate_data.py) in Data Vault →
    badge flips to STUDIO DATA and the real project/character records
    appear.
