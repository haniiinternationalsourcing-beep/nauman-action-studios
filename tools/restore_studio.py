#!/usr/bin/env python3
"""REAL restore for Nauman Action Studios export ZIPs.

Usage:
  python3 restore_studio.py <export.zip> <target-folder>
      Verify the ZIP, then extract it completely and safely into
      <target-folder> and re-verify every restored file on disk.
  python3 restore_studio.py <export.zip> --verify-only
      Verify only, extract nothing (the old behaviour, kept for audits).

Safety:
  - Entries with absolute paths, '..' components or symlink types are
    REJECTED (zip-slip / link attacks) and abort the restore.
  - If the ZIP carries MANIFEST.json (exports from 2026-11-13 onward),
    every file's SHA-256 must match the manifest before extraction, and
    every extracted file is hashed again on disk and compared.
  - Older ZIPs without a manifest still restore: structure + data.json
    schema are verified and each file's ZIP CRC is checked by zipfile,
    but the report says plainly that no manifest verification was possible.
  - If the target already holds a NAS-STUDIO tree, that tree is FIRST
    backed up to a timestamped ZIP (with SHA-256 manifest) beside the
    target folder, and only then replaced. A failed backup aborts the
    restore with the existing tree untouched. Data is never silently lost.
"""
import sys, os, io, json, zipfile, hashlib, stat, datetime, shutil

REQUIRED = ["NAS-STUDIO/README.md", "NAS-STUDIO/OPERATOR-MANUAL.md",
            "NAS-STUDIO/data.json",
            "NAS-STUDIO/00-master-control/approvals-log.csv",
            "NAS-STUDIO/03-video-center/GENERATION-LOG.md"]

def backup_existing_tree(target):
    """Zip the existing <target>/NAS-STUDIO tree (with a SHA-256 manifest)
    to a timestamped backup BESIDE the target folder. Returns the path."""
    tree_root = os.path.join(target, "NAS-STUDIO")
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    parent = os.path.dirname(os.path.abspath(target))
    out = os.path.join(parent, f"NAS-STUDIO-pre-restore-backup-{stamp}.zip")
    manifest = {}
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(tree_root):
            for fn in sorted(files):
                full = os.path.join(root, fn)
                arc = os.path.relpath(full, os.path.abspath(target))
                h = hashlib.sha256()
                with open(full, "rb") as f:
                    for chunk in iter(lambda: f.read(1024 * 1024), b""):
                        h.update(chunk)
                manifest[arc] = h.hexdigest()
                z.write(full, arc)
        z.writestr("MANIFEST.json", json.dumps(
            {"format": "nas-studio-export-manifest/1",
             "created": datetime.datetime.now().isoformat(timespec="seconds"),
             "files": manifest}, indent=2))
    return out

def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()

def check_entry_safety(info):
    name = info.filename
    if name.startswith("/") or name.startswith("\\"):
        return f"absolute path entry: {name}"
    parts = name.replace("\\", "/").split("/")
    if ".." in parts:
        return f"path traversal entry: {name}"
    mode = (info.external_attr >> 16) & 0xFFFF
    if stat.S_ISLNK(mode):
        return f"symlink entry refused: {name}"
    return None

# Decompression-bomb + abuse limits, checked from the ZIP directory BEFORE
# anything is extracted (added 2026-11-13 after a bomb test filled the disk:
# the previous version had no size limits at all). Legit studio exports are
# ~61 MB total with a 25 MB largest file, so these caps are generous.
MAX_ENTRIES = 10000
MAX_FILE_BYTES = 500 * 1024 * 1024
MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024
MAX_RATIO = 100          # uncompressed:compressed, for files over 10 MB
RATIO_FLOOR_BYTES = 10 * 1024 * 1024

def check_archive_limits(infos):
    if len(infos) > MAX_ENTRIES:
        return f"too many entries: {len(infos)} > {MAX_ENTRIES}"
    seen, dupes = set(), set()
    for i in infos:
        if i.filename in seen:
            dupes.add(i.filename)
        seen.add(i.filename)
    if dupes:
        return f"duplicate path entries refused: {sorted(dupes)}"
    total = 0
    for i in infos:
        if i.file_size > MAX_FILE_BYTES:
            return f"entry too large: {i.filename} ({i.file_size} bytes)"
        if (i.file_size > RATIO_FLOOR_BYTES and i.compress_size > 0
                and i.file_size / i.compress_size > MAX_RATIO):
            return (f"suspicious compression ratio: {i.filename} "
                    f"({i.file_size / i.compress_size:.0f}:1) — possible ZIP bomb")
        total += i.file_size
    if total > MAX_TOTAL_BYTES:
        return f"total uncompressed size too large: {total} bytes"
    return None

def total_uncompressed(infos):
    return sum(i.file_size for i in infos if i.filename != "MANIFEST.json")

def check_free_space(infos, target):
    """Refuse BEFORE writing anything when the target volume cannot hold
    the restored tree plus a 10% margin. (A 2026-11-13 bomb test filled
    the disk mid-extraction; failing late also leaves a half-written
    tree, so this check runs before the first byte is written.)"""
    need = int(total_uncompressed(infos) * 1.1)
    anchor = target
    while not os.path.exists(anchor):
        anchor = os.path.dirname(os.path.abspath(anchor))
    free = shutil.disk_usage(anchor).free
    if free < need:
        return (f"not enough free space at {anchor}: need ~{need} bytes, "
                f"only {free} free — restore refused before writing anything")
    return None

def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    zip_path = sys.argv[1]
    verify_only = sys.argv[2] == "--verify-only"
    target = None if verify_only else sys.argv[2]

    z = zipfile.ZipFile(zip_path)
    infos = [i for i in z.infolist() if not i.is_dir()]
    names = {i.filename for i in infos}

    for info in infos:
        problem = check_entry_safety(info)
        if problem:
            print(f"RESTORE ABORTED — unsafe entry: {problem}")
            return 1

    limit_problem = check_archive_limits(infos)
    if limit_problem:
        print(f"RESTORE ABORTED — archive limit: {limit_problem}")
        return 1

    bad_crc = z.testzip()
    if bad_crc:
        print(f"RESTORE ABORTED — corrupt entry (CRC): {bad_crc}")
        return 1

    missing = [r for r in REQUIRED if r not in names]
    if missing:
        print(f"RESTORE ABORTED — required files missing: {missing}")
        return 1

    d = json.loads(z.read("NAS-STUDIO/data.json").decode("utf-8"))
    if not (d.get("schema_version") == 2 and "projects" in d and "characters" in d):
        print("RESTORE ABORTED — data.json schema mismatch (need schema_version 2 "
              "with projects[] and characters[])")
        return 1

    manifest = None
    if "MANIFEST.json" in names:
        manifest = json.loads(z.read("MANIFEST.json").decode("utf-8"))["files"]
        mismatched = []
        for arc, want in manifest.items():
            if arc not in names:
                mismatched.append(f"{arc} (missing from ZIP)")
            elif sha256_bytes(z.read(arc)) != want:
                mismatched.append(f"{arc} (SHA-256 mismatch)")
        if mismatched:
            print(f"RESTORE ABORTED — manifest verification failed: {mismatched}")
            return 1
        print(f"Manifest verified: {len(manifest)} files, SHA-256 all match.")

    if verify_only:
        print(f"VERIFY-ONLY PASSED — {len(names)} files; required: all present; "
              f"projects: {len(d['projects'])}, characters: {len(d['characters'])}; "
              f"manifest: {'verified' if manifest else 'absent (older export)'}")
        return 0

    space_problem = check_free_space(infos, target)
    if space_problem:
        print(f"RESTORE ABORTED — {space_problem}")
        return 1

    existing = os.path.join(target, "NAS-STUDIO")
    if os.path.exists(existing):
        backup_path = backup_existing_tree(target)
        check = zipfile.ZipFile(backup_path)
        if check.testzip() is not None:
            print(f"RESTORE ABORTED — pre-restore backup {backup_path} failed "
                  "its CRC check; existing tree left untouched.")
            return 1
        print(f"Existing studio tree backed up before restore: {backup_path}")
        shutil.rmtree(existing)
    os.makedirs(target, exist_ok=True)

    restored = 0
    total_bytes = 0
    for info in infos:
        if info.filename == "MANIFEST.json":
            continue
        dest = os.path.join(target, info.filename)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        # Stream in 1 MB chunks: a large entry never sits fully in memory.
        # Nested archives are copied as inert data files — a restore never
        # opens, extracts or executes an archive stored inside the backup.
        with z.open(info) as src, open(dest, "wb") as out_f:
            shutil.copyfileobj(src, out_f, 1024 * 1024)
        restored += 1
        total_bytes += info.file_size

    if manifest:
        bad = []
        for arc, want in manifest.items():
            p = os.path.join(target, arc)
            h = hashlib.sha256()
            with open(p, "rb") as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    h.update(chunk)
            if h.hexdigest() != want:
                bad.append(arc)
        if bad:
            print(f"RESTORE FAILED — on-disk verification mismatch: {bad}")
            return 1
        print(f"On-disk verification: {len(manifest)} files re-hashed, all match.")

    print(f"RESTORE COMPLETE — {restored} files, {total_bytes/1e6:.1f} MB restored to "
          f"{target}/NAS-STUDIO; projects: {len(d['projects'])}, "
          f"characters: {len(d['characters'])}; "
          f"manifest: {'verified' if manifest else 'absent (older export — CRC + schema verified only)'}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
