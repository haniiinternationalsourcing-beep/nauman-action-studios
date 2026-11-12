# Nauman Action Studios - Audit Package (V4 FINAL, post-audit + final testing)

Public repository holding the Nauman Action Studios system files for
independent technical audit. Everything is byte-exact as delivered.
(Earlier V3/V4 packages remain in this repo's git history.)

## Contents

- `NAS-ControlRoom-V4-AUDITFIX.html` - the Control Room app, final build:
  owner PIN gate for approvals (PIN stored only as a PBKDF2-HMAC-SHA-256
  hash, salt + 210,000 iterations; legacy plain-SHA-256 records migrate
  on first successful unlock; 5 failed attempts trigger a 60 s lockout),
  hardened localStorage with backup recovery + data migration,
  studioToAppData import adapter, DEMO/STUDIO data badge, honest
  Integrations panel. Red/white/yellow VIP design unchanged. Demo data
  only, by design. The PIN lock is a client-side device lock, honestly
  labelled as such - it is NOT server-grade security.
- `tools/` - `generate_data.py` (canonical, schema v2), `export_studio.py`
  (backup ZIP with SHA-256 manifest), `restore_studio.py` (REAL restore
  with manifest verification, path-traversal/symlink/duplicate refusal,
  ZIP-bomb + disk-space guards, pre-restore auto-backup; the app's
  embedded copy is byte-identical to this file), `sync_embedded.py`
  (packaging sync), `connectors/README.md` (modular API architecture -
  keys never live in code or this repo).
- `security-test-20261113.log` / `integration-test-20261113.log` - raw
  test evidence: ZIP attack suite (symlink, duplicates, bomb, disk
  space, nested archives) and the export-restore byte-identity proof.
- `NAS-STUDIO/` - the complete studio folder system: master control
  (TEST-REPORT-2026-11-13.md and PRODUCTION-READINESS.md - every feature
  labelled PASS / FAIL / PENDING honestly), Project 001 with all pilot
  clips, characters, generation log, budget ledger, INTEGRATIONS.md,
  backups.

## The large backup ZIPs (transport note)

GitHub's API rejects single blobs of ~60 MB, so the backup ZIPs in
`NAS-STUDIO/09-backups/` are stored as 15 MB parts in a `<name>.parts/`
folder next to a `<name>.sha256` checksum file. The bytes are complete and
unmodified. To restore an original file:

    cat NAS-STUDIO-export-20261113-0201.zip.parts/part-* > NAS-STUDIO-export-20261113-0201.zip
    sha256sum -c NAS-STUDIO-export-20261113-0201.zip.sha256

Owner: Nauman Magray (Studio Owner & Executive Producer).
