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
