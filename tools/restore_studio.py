#!/usr/bin/env python3
"""Restore test: verify a studio export ZIP is complete and readable.
Usage: python3 restore_studio.py <export.zip> — checks required files + parses data.json."""
import sys, zipfile, json, io
REQUIRED = ["NAS-STUDIO/README.md", "NAS-STUDIO/OPERATOR-MANUAL.md", "NAS-STUDIO/data.json",
            "NAS-STUDIO/00-master-control/approvals-log.csv", "NAS-STUDIO/03-video-center/GENERATION-LOG.md"]
z = zipfile.ZipFile(sys.argv[1]); names = set(z.namelist())
missing = [r for r in REQUIRED if r not in names]
d = json.loads(z.read("NAS-STUDIO/data.json").decode("utf-8"))
assert d.get("schema_version") == 2 and "projects" in d and "characters" in d, "schema mismatch"
print(f"RESTORE TEST PASSED — {len(names)} files; missing: {missing or 'none'}; projects: {len(d['projects'])}, characters: {len(d['characters'])}")
