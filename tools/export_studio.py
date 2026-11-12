#!/usr/bin/env python3
"""Create a timestamped full-studio ZIP export in NAS-STUDIO/09-backups/.

The ZIP contains the complete NAS-STUDIO tree (the 09-backups folder itself
is excluded, as before) PLUS a MANIFEST.json at the ZIP root holding the
SHA-256 of every file, so restore_studio.py can prove byte-for-byte that
what was exported is what gets restored. Adding the manifest is additive:
older restore tools and plain unzippers read the ZIP exactly as before.
"""
import os, zipfile, datetime, hashlib, json

BASE = os.path.join(os.path.dirname(__file__), "..")
STUDIO = os.path.join(BASE, "NAS-STUDIO")
stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
out = os.path.join(STUDIO, "09-backups", f"NAS-STUDIO-export-{stamp}.zip")

entries = []  # (full_path, arcname)
for root, dirs, files in os.walk(STUDIO):
    if "09-backups" in root:
        continue
    for fn in sorted(files):
        full = os.path.join(root, fn)
        entries.append((full, os.path.relpath(full, BASE)))

manifest = {"format": "nas-studio-export-manifest/1",
            "created": datetime.datetime.now().isoformat(timespec="seconds"),
            "files": {}}
for full, arc in entries:
    h = hashlib.sha256()
    with open(full, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    manifest["files"][arc] = h.hexdigest()

with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for full, arc in entries:
        z.write(full, arc)
    z.writestr("MANIFEST.json", json.dumps(manifest, indent=2))

print(f"Export created: {out} — {len(entries)} files + MANIFEST.json "
      f"({len(manifest['files'])} SHA-256 hashes).")
print("Restore: python3 restore_studio.py <this.zip> <target-folder>")
