# TEST REPORT — Audit Fixes (2026-11-13)
Scope: the 7 issues from the independent GitHub audit + the owner's 8 additional
requirements. Every result below is from a test actually run; failures and
limits are stated, not hidden. Originals preserved in
`nauman-action-studios/backups/pre-fix-20261113-0305/`.

## Phase 1 — Python tools (operator-run tests)
Files changed: tools/generate_data.py, tools/export_studio.py,
tools/restore_studio.py; added tools/sync_embedded.py,
tools/connectors/README.md.

1. **Version divergence (audit #1) — CONFIRMED by inspection, then fixed.**
   Three variants of generate_data.py existed: the disk tool (works on the
   real folder), a pathlib variant embedded in the app expecting
   `project.json` + `budget-ledger.md` files that do not exist in the studio,
   and the app's display text. The DISK tool was selected as authoritative
   (it is the only one that runs against the real folder). It now also emits
   `code`, `title`, `status_note` per project for the app adapter. Embedded
   app copies were replaced with the canonical texts at packaging and
   verified byte-identical (builder diff + Node strict-equality re-read).
   During that sync ONE residual difference was found and fixed: three
   comment lines present only in the disk restore_studio.py were removed so
   disk and embedded copies match exactly.
2. **Real restore (audit #3) — PASS.** restore_studio.py now extracts.
   Test: export → restore to a fresh folder → independent SHA-256 comparison
   of every file: **21/21 byte-identical, 0 mismatches, 0 extra files.**
3. **Backup verification (audit #4) — PASS.** export_studio.py now embeds
   MANIFEST.json (SHA-256 per file). Restore verifies the manifest before
   extraction and re-hashes every restored file on disk: all match.
   Backward compatibility: the pre-manifest export
   (NAS-STUDIO-export-20261113-0201.zip) passes verify-only with the report
   plainly stating no manifest was present.
4. **Restore safety (owner req. #4) — PASS.** A ZIP poisoned with a
   `../evil.txt` entry is refused (exit 1, nothing extracted). Restoring
   over an existing studio tree first creates a timestamped
   pre-restore backup ZIP (with manifest), which itself passes
   verification, and only then replaces the tree.
   Full log: nauman-action-studios/integration-test-20261113.log.

## Phase 2 — Control Room app (builder-run Node harness, 34 checks)
Files changed: the app artifact (red/white/yellow design unchanged).
- **Owner PIN gate (audit #2):** PIN stored only as a SHA-256 hash
  (WebCrypto; the digest of the test PIN matched the known SHA-256 value).
  While locked, Approve / Reject / Mark Spent / Reset-to-demo change
  nothing, show a notice, and are written to the audit log. While unlocked
  they work; locking again re-blocks. Reset PIN has a confirmation step and
  is audit-logged. 5 failed attempts → 60-second entry lockout, failures
  logged. HONEST LIMIT: this is a client-side, device-level lock, stated as
  such inside the app — not server-grade security.
- **Storage hardening + migration (audit #5, owner req. #2):** saves are
  shape-validated and mirrored to a backup key. Harness results: corrupt
  main + valid backup → backup recovered with a visible notice; both
  corrupt → demo fallback with a visible notice; the main storage key is
  UNCHANGED from the previous build (nas-control-room-state-v2), so
  existing user data loaded in place; an older legacy key migrates with a
  pre-migration backup copy kept.
- **Import adapter (audit #1):** studioToAppData() verified field-by-field
  against a real generate_data.py output: projects, characters (all
  fields), approvals (APR-S1… IDs, status mapping), both markdown
  registers; its output passes the app's own state validation; an export
  made after a studio import carries schema_version 2 and a NAS-STUDIO
  generated_from. Header badge DEMO DATA / STUDIO DATA present.
- **Integrations (audit #7):** panel lists Flow = Manual, Veo/Gemini API,
  ElevenLabs, Kling = Planned (with real requirements), GitHub = Working.
  No fake connect/success behaviour. Architecture:
  NAS-STUDIO/INTEGRATIONS.md + tools/connectors/README.md. No API keys
  exist in the app, the repo, or this folder.
- **Buttons (audit #6):** the harness exercised the approval, spend-gate,
  export, restore, ZIP and script-download paths, and a source grep
  confirmed every pre-existing handler still present. LIMIT: tests ran in a
  Node harness with a stubbed DOM, not as live clicks in a real browser —
  the owner's/ChatGPT's browser run remains the live click test.

## Known limitations (not hidden)
1. PIN gate is client-side only (see above). True authentication needs a
   backend, which a static file cannot provide.
2. No live API integration is connected yet (ElevenLabs/Gemini/Kling are
   Planned — they need owner accounts/keys by design).
3. GitHub's API rejects ~60 MB single blobs, so the repo stores the two
   large backup ZIPs as 15 MB parts + SHA-256 files (byte-exact when
   reassembled; checksums published in the repo).
4. App tests are harness-level, not real-browser clicks (see Phase 2).
5. APR-001 (micro-pilot, 300 cr) remains "Pending owner confirmation" —
   approvals recorded through relays are proposals until the owner confirms
   directly, per the owner's own rule.

## Final testing phase (2026-11-13, later session) — actual results
- **ZIP attack suite (operator-run, log: security-test-20261113.log):**
  symlink entry REFUSED; duplicate path REFUSED (with and without a
  manifest); path traversal REFUSED; pre-restore auto-backup PASS;
  disk-space guard PASS (simulated 1 MB free → refused before writing);
  nested poisoned archive restored as inert data, never extracted (0 evil
  files); regression restores PASS after every change.
  ONE REAL FAILURE was found and fixed in this phase: the first ZIP-bomb
  test (300 MB of zeros) was NOT stopped — it filled the test disk,
  because restore had no size limits. Limits were added (entries ≤10,000;
  file ≤500 MB; total ≤2 GB; ratio ≤100:1 above 10 MB) and the bomb is
  now refused before extraction with 0 bytes written.
- **PBKDF2 upgrade (builder Node harness, 43/43 checks PASS, run twice):**
  derivation matches the published PBKDF2-HMAC-SHA256 test vector AND
  Node's crypto.pbkdf2Sync at 1 and 4096 iterations; set/lock/wrong-PIN
  (blocked, failure logged)/correct-PIN/reload persistence all verified;
  PIN reset verified; 5-failure 60-second lockout verified; a seeded
  legacy plain-SHA-256 record migrated to PBKDF2 on successful unlock and
  the upgrade was written to the audit log. Argon2 was NOT adopted: it is
  not native to WebCrypto and would need a third-party WASM library.
- **Larger dataset (adapter):** synthetic schema-v2 data with 3 projects /
  4 characters / 5 approvals imported through studioToAppData — all cards,
  APR-S1…S5 IDs and status mappings correct; export of the imported state
  validates as schema v2. Generator side separately verified at
  5 projects / 6 characters / 5 approvals.
- **Live browser testing: PENDING.** Real Android Chrome (owner's phone)
  and desktop Chrome click-testing cannot be executed by the operator
  from the server side; harness results are not presented as a
  substitute. Manual checklists are in PRODUCTION-READINESS.md.
- **Embedded sync:** RESTORE_DOC re-synced to the final canonical
  restore_studio.py (free-space guard + streaming extraction included);
  all three embedded scripts byte-identical to tools/ at the final commit.

## Fix phase 2 — independent-review findings (2026-11-13, owner-approved)
Baseline recorded before any change (owner condition): original commit
d78f931b86a5c6958bb8da3c1542f6695b2453a4; original restore_studio.py
SHA-256 e61cca15422657a054010410903cc97444222466e8d99926e1b58c8b3df68068;
real NAS-STUDIO tree aggregate SHA-256
8c51d6594cf79d343056b795fd4901aaa9b550b2a443466754f6468701ea35cf (30
files). Full raw log: fix2-verification-20261113.log (workspace root of
the studio package).
- **Finding 1 (extra unlisted file restored silently) — FIXED + TESTED:**
  manifest verification is now two-directional. T1: an unlisted file now
  REJECTS in verify-only and in full restore (nothing restored). T2b: a
  manifest-listed non-required file removed from the ZIP is rejected by
  the manifest check itself (the first T2 attempt was caught earlier by
  the required-files check; T2b isolates the manifest path).
- **Finding 2 (no automatic rollback; crash left a partial studio) —
  FIXED + TESTED:** staged extraction on the same filesystem, journal
  (atomic write + checksum + fsync of file and parent directory),
  rename swap, post-swap hash re-verification, old tree deleted only
  after it passes, single-restore lock with PID + /proc start-time
  two-evidence stale-lock protocol and a --recover mode.
  T3 legit restore: staged + post-swap verification PASS, 24/24 files
  byte-identical to the real tree, no leftovers. T4/T4b collisions
  (unlisted and self-consistent manifested): rejected/aborted in
  staging, existing studio byte-identical. T5 kill during staging:
  journal+lock+staging remained; --recover claimed the stale lock
  (owner PID dead), cleaned up, studio intact. T6 kill mid-swap (old
  aside, new not in): --recover automatically restored the original,
  byte-identical. T7 kill after swap: --recover verified the new studio
  (24/24) and completed the restore. T8 byte corrupted after swap:
  post-swap verification failed and the SAME run rolled back
  automatically; studio byte-identical, failed tree preserved.
  T9 corrupt journals (truncated / bad checksum / unknown state /
  path outside the target parent): restore and --recover both REFUSE
  (exit 2), journal preserved, studio intact. T10 corrupt lock: restore
  refuses (3), --recover refuses (2); only the operator's deliberate
  --force-stale-lock proceeds, is reported, and preserves the old lock
  as a .recovered-* record; studio intact. T11 live lock with a REAL
  running restore process: second restore refused (3), --recover
  refused (3, owner alive with matching start-time), lock file hash
  unchanged by both refusals; the first restore then completed normally
  and removed its own lock. T12 PID/start-time against a real `sleep`
  process: live PID with wrong start-time correctly judged a reused
  PID (owner gone); live PID with correct start-time refused as alive,
  lock untouched. T13 ZIP security suite re-run: symlink, traversal,
  duplicates (with and without manifest), 300 MB bomb (refused
  pre-extraction, 0 bytes), disk-space guard (logic test; the guard
  also fired for real once during this phase on a genuinely full /tmp).
  Nested archives: an unlisted inner archive now REJECTS (Finding 1);
  real exports contain no nested archives, so inertness of listed
  archives rests on construction (restore only ever reads the outer
  ZIP's entries) plus the T3 byte-compare — recorded honestly as such.
  T14 two simultaneous recoveries: exactly one performed the recovery;
  the second found nothing left to do and exited as a harmless no-op
  (NOT a refusal — recorded as observed).
  One full batch (first crash-suite attempt) was INVALID and is kept in
  the log labelled as such: /tmp (512 MB tmpfs) filled up, the
  free-space guard refused the setups, and the crash points were never
  reached; the batch was re-run after cleanup and passed as above.
- **Condition 9 proof:** after ALL tests, the real NAS-STUDIO tree
  aggregate SHA-256 was re-measured: identical to the baseline
  (8c51d659…). The production studio and its backups were never used
  as a test target; every test ran in /tmp.
- Final restore_studio.py SHA-256:
  3e78237167fc191036502dbe083a4356246526aa105eba3c245a8a99540b1bb0.
  (One cosmetic fix during the phase removed a duplicated override
  warning line in --recover; T10 was re-run after it.)
- **App regression after the embedded sync (builder Node harness, run
  twice, identical):** PBKDF2/PIN suite 49/49 PASS (test vectors +
  Node pbkdf2Sync cross-check; set/lock/wrong/correct; persistence
  across simulated reload; PIN reset; 5-failure lockout incl. correct
  PIN refused during lockout and accepted after expiry; legacy
  migration on successful unlock only). Adapter suite 29/29 PASS
  (3 projects / 4 characters / 5 approvals, APR-S1..S5, export
  re-validates as schema v2). Embedded RESTORE_DOC decoded from the
  built page = 32,407 bytes, SHA-256 3e782371… — byte-identical to
  tools/restore_studio.py; SCRIPT_GEN/SCRIPT_EXP unchanged.
