# Nauman Action Studios - Audit Package (V4, post-audit fixes)

Public repository holding the Nauman Action Studios system files for
independent technical audit. Everything is byte-exact as delivered.
(The earlier V3 package remains in this repo's git history.)

## Contents

- `NAS-ControlRoom-V4-AUDITFIX.html` - the Control Room app, audit-fixed
  build: owner PIN gate for approvals (SHA-256 hash only), hardened
  localStorage with backup recovery + data migration, studioToAppData
  import adapter, DEMO/STUDIO data badge, honest Integrations panel.
  Red/white/yellow VIP design unchanged. Demo data only, by design.
- `tools/` - `generate_data.py` (canonical, schema v2), `export_studio.py`
  (backup ZIP with SHA-256 manifest), `restore_studio.py` (REAL restore
  with archive validation, path-traversal protection and pre-restore
  auto-backup), `sync_embedded.py` (keeps the app's embedded script copies
  byte-identical to these files), `connectors/README.md` (modular API
  architecture - keys never live in code or this repo).
- `NAS-STUDIO/` - the complete studio folder system: master control
  (including 00-master-control/TEST-REPORT-2026-11-13.md with every test
  actually run and its result), Project 001 with all pilot clips,
  characters, generation log, budget ledger, INTEGRATIONS.md, backups.

## The large backup ZIPs (transport note)

GitHub's API rejects single blobs of ~60 MB, so the backup ZIPs in
`NAS-STUDIO/09-backups/` are stored as 15 MB parts in a `<name>.parts/`
folder next to a `<name>.sha256` checksum file. The bytes are complete and
unmodified. To restore an original file:

    cat NAS-STUDIO-export-20261113-0201.zip.parts/part-* > NAS-STUDIO-export-20261113-0201.zip
    sha256sum -c NAS-STUDIO-export-20261113-0201.zip.sha256

Owner: Nauman Magray (Studio Owner & Executive Producer).
