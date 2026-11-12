# Nauman Action Studios - Audit Package

Public repository holding the Nauman Action Studios system files for
independent technical audit. Everything is byte-exact as delivered.

## Contents

- `NAS-ControlRoom-V3-FIXED.html` - the Control Room app (single-file build:
  the 7 fixes + red/white/yellow VIP design). Demo data only, by design.
- `tools/` - `generate_data.py` (schema v2 data builder), `export_studio.py`
  (full studio backup ZIP), `restore_studio.py` (backup restore checker).
- `NAS-STUDIO/` - the complete studio folder system: master control,
  Project 001 with all pilot clips, characters, generation log, budget
  ledger, agents workflow, backups.

## The two large backup ZIPs (transport note)

GitHub's API rejects single blobs of ~60 MB, so the two backup ZIPs in
`NAS-STUDIO/09-backups/` are stored as 15 MB parts in a `<name>.parts/`
folder next to a `<name>.sha256` checksum file. The bytes are complete and
unmodified. To restore the original file:

    cat NAS-STUDIO-export-20261113-0201.zip.parts/part-* > NAS-STUDIO-export-20261113-0201.zip
    sha256sum -c NAS-STUDIO-export-20261113-0201.zip.sha256

Owner: Nauman Magray (Studio Owner & Executive Producer).
