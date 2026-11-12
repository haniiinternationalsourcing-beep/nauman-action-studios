# NAS-STUDIO — Master Folder (Owner: Nauman Magray)
This folder IS the studio. The Control Room app is only a viewer over these files.
All formats are open standards: .md/.txt (documents), .csv (tables), .json (structured data), .mp4/.png/.mp3 (media).
Start here: OPERATOR-MANUAL.md explains how everything works, for any operator.

## After the 2026-11-13 technical audit (V4)
- **One canonical data tool:** `tools/generate_data.py` is the ONLY authoritative version; the copies inside the Control Room app are byte-identical to it (packaging sync, verified). data.json stays schema v2; the app imports it through its `studioToAppData()` adapter.
- **Real backup/restore:** `tools/export_studio.py` writes a ZIP with a SHA-256 MANIFEST.json; `tools/restore_studio.py` verifies and actually restores, and backs up any existing tree before replacing it. Proof: `00-master-control/TEST-REPORT-2026-11-13.md`.
- **Approvals have an owner PIN lock** in the app (client-side convenience lock — read the honest note inside the app; it is not server security).
- **Integrations:** see INTEGRATIONS.md — real statuses only (Working / Manual / Planned), no fake connections.
- **Public audit repo:** github.com/haniiinternationalsourcing-beep/nauman-action-studios (demo data only, by design).
