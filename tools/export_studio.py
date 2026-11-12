#!/usr/bin/env python3
"""Create a timestamped full-studio ZIP export in NAS-STUDIO/09-backups/ and print a manifest."""
import os, zipfile, datetime
BASE = os.path.join(os.path.dirname(__file__), "..")
STUDIO = os.path.join(BASE, "NAS-STUDIO")
stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
out = os.path.join(STUDIO, "09-backups", f"NAS-STUDIO-export-{stamp}.zip")
count = 0
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for root, dirs, files in os.walk(STUDIO):
        if "09-backups" in root: continue
        for fn in files:
            full = os.path.join(root, fn)
            z.write(full, os.path.relpath(full, BASE)); count += 1
print(f"Export created: {out} — {count} files. Restore: unzip anywhere, open NAS-STUDIO/README.md.")
