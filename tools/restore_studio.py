#!/usr/bin/env python3
"""REAL restore for Nauman Action Studios export ZIPs — crash-safe edition.

Usage:
  python3 restore_studio.py <export.zip> <target-folder>
      Verify the ZIP, stage-extract it, verify the staged tree, and only
      then replace <target-folder>/NAS-STUDIO. Crash-safe: see below.
  python3 restore_studio.py <export.zip> --verify-only
      Verify only, extract nothing. Takes no lock, writes nothing.
  python3 restore_studio.py --recover <target-folder> [--force-stale-lock]
      Finish or roll back an interrupted restore using its journal, and
      clear a stale lock whose owner is proven dead. --force-stale-lock
      is the operator's deliberate manual confirmation for the cases
      where the owner's life/death cannot be proven automatically; it is
      always reported when used.

Safety:
  - Entries with absolute paths, '..' components or symlink types are
    REJECTED (zip-slip / link attacks) and abort the restore.
  - If the ZIP carries MANIFEST.json (exports from 2026-11-13 onward),
    verification is TWO-DIRECTIONAL: every manifest entry must be in the
    ZIP with a matching SHA-256, AND every file in the ZIP (except
    MANIFEST.json itself, which is handled separately) must be listed in
    the manifest. Extra unlisted files and missing listed files abort
    the restore. (Review finding #1, fixed 2026-11-13.)
  - Older ZIPs without a manifest still restore: structure + data.json
    schema are verified and each file's ZIP CRC is checked by zipfile,
    but the report says plainly that no manifest verification was possible.
  - Extraction is STAGED in a folder on the SAME filesystem as the
    target; the staged tree is hash-verified before anything is
    replaced. The swap renames the old tree aside and the staged tree
    in; after the swap the new tree is hash-verified AGAIN in place,
    and the old tree is deleted only after that passes — on failure the
    swap is rolled back automatically. (Review finding #2, fixed
    2026-11-13.)
  - A JOURNAL (.nas-restore-journal.json beside the target) records the
    swap state. It is written atomically (temp file + fsync + rename),
    carries a SHA-256 checksum, and the parent directory is fsync'd
    after every journal write and every rename. A corrupt, incomplete
    or unknown-state journal stops everything: no folder is deleted or
    overwritten on a guess. A leftover journal is processed at the start
    of the next restore, or immediately with --recover. The tool is not
    a background service, so recovery happens at the next tool run, not
    at OS boot.
  - A LOCK (.nas-restore.lock beside the target) allows only ONE
    restore at a time; a second process refuses and reports the lock's
    owner. A process only ever deletes its OWN lock (matched by run
    id). Recovery may set a foreign lock aside only when its owner is
    proven dead by TWO evidences (PID gone, or PID present with a
    different /proc start-time = the PID was reused); dead owners' locks
    are renamed aside, never silently deleted. Alive or unprovable
    owners keep their lock: recovery refuses, or proceeds only with the
    operator's explicit --force-stale-lock.
  - If the target already holds a NAS-STUDIO tree, that tree is also
    backed up to a timestamped ZIP (with SHA-256 manifest) beside the
    target folder before the swap. The tool never deletes that backup.
  - Test-only fault injection (inert unless the environment variable is
    set): NAS_RESTORE_CRASH_AT=during-staging|after-old-aside|after-swap
    hard-kills the process at that point; NAS_RESTORE_CORRUPT_AFTER_SWAP=1
    flips one byte in the swapped tree before its verification;
    NAS_RESTORE_PAUSE=<seconds> sleeps while holding the lock.
"""
import sys, os, io, json, zipfile, hashlib, stat, datetime, shutil, tempfile
import socket, time

REQUIRED = ["NAS-STUDIO/README.md", "NAS-STUDIO/OPERATOR-MANUAL.md",
            "NAS-STUDIO/data.json",
            "NAS-STUDIO/00-master-control/approvals-log.csv",
            "NAS-STUDIO/03-video-center/GENERATION-LOG.md"]

JOURNAL_NAME = ".nas-restore-journal.json"
LOCK_NAME = ".nas-restore.lock"
JOURNAL_STATES = ("staging", "old-aside", "swapped")

# ---------------------------------------------------------------- durability
def fsync_dir(path):
    """Best-effort directory fsync (POSIX). Unsupported platforms (e.g.
    Windows) degrade to file-level fsyncs only; the journal and lock
    logic does not depend on this succeeding."""
    try:
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        pass

def fsync_file(f):
    f.flush()
    os.fsync(f.fileno())

# ---------------------------------------------------------------- processes
def proc_start_time(pid):
    """Linux /proc/<pid>/stat starttime (field 22). None when unknown."""
    try:
        with open(f"/proc/{pid}/stat", "rb") as f:
            data = f.read().decode()
        rest = data[data.rfind(")") + 2:].split()
        return int(rest[19])  # rest[0] is field 3; field 22 -> index 19
    except Exception:
        return None

def pid_alive(pid):
    """True/False when determinable, None when it cannot be told."""
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return None

def assess_lock_owner(lock):
    """Two-evidence death check. Returns (verdict, evidence) with verdict
    in {'dead', 'alive', 'unknown'}."""
    pid = lock.get("pid")
    if not isinstance(pid, int) or pid <= 0:
        return "unknown", "lock carries no valid pid"
    host = lock.get("host")
    if host and host != socket.gethostname():
        return "unknown", f"lock was created on another host ({host})"
    alive = pid_alive(pid)
    if alive is False:
        return "dead", f"pid {pid} no longer exists"
    if alive is None:
        return "unknown", f"liveness of pid {pid} could not be determined"
    recorded = lock.get("start_time")
    current = proc_start_time(pid)
    if recorded is None or current is None:
        return "unknown", f"pid {pid} exists but start-time evidence is unavailable"
    if current != recorded:
        return "dead", (f"pid {pid} exists but its start-time differs from the "
                        f"lock's — the pid was reused; the lock's owner is gone")
    return "alive", f"pid {pid} is alive and its start-time matches the lock"

# ---------------------------------------------------------------- lock
class LockHeld(Exception):
    def __init__(self, existing):
        self.existing = existing

class RestoreLock:
    def __init__(self, parent):
        self.parent = parent
        self.path = os.path.join(parent, LOCK_NAME)
        self.run_id = None

    def payload(self):
        self.run_id = f"{os.getpid()}-{int(time.time())}-{os.urandom(4).hex()}"
        return {"pid": os.getpid(), "start_time": proc_start_time(os.getpid()),
                "host": socket.gethostname(), "run_id": self.run_id,
                "created": datetime.datetime.now().isoformat(timespec="seconds")}

    def acquire(self):
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            existing = None
            try:
                existing = json.loads(open(self.path, encoding="utf-8").read())
            except Exception:
                existing = None
            raise LockHeld(existing)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(self.payload(), indent=2))
            fsync_file(f)
        fsync_dir(self.parent)

    def release(self):
        """Delete ONLY our own lock: re-read and match the run id first."""
        try:
            current = json.loads(open(self.path, encoding="utf-8").read())
            if current.get("run_id") == self.run_id:
                os.unlink(self.path)
                fsync_dir(self.parent)
        except Exception:
            pass

# ---------------------------------------------------------------- journal
def journal_file(parent):
    return os.path.join(parent, JOURNAL_NAME)

def write_journal(parent, payload):
    body = dict(payload)
    body["checksum"] = hashlib.sha256(
        json.dumps(body, sort_keys=True).encode()).hexdigest()
    tmp = journal_file(parent) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(json.dumps(body, indent=2))
        fsync_file(f)
    os.rename(tmp, journal_file(parent))
    fsync_dir(parent)

def read_journal(parent):
    """(payload, None) or (None, error). A journal that cannot be fully
    validated is an error, never a guess."""
    p = journal_file(parent)
    if not os.path.exists(p):
        return None, None
    try:
        d = json.loads(open(p, encoding="utf-8").read())
        checksum = d.pop("checksum")
        if hashlib.sha256(json.dumps(d, sort_keys=True).encode()).hexdigest() != checksum:
            return None, "journal checksum mismatch (corrupt or tampered)"
        if d.get("version") != 1:
            return None, "journal version unknown"
        if d.get("state") not in JOURNAL_STATES:
            return None, f"journal state unknown: {d.get('state')!r}"
        for key in ("run_id", "target", "staging", "old_tree", "zip_path"):
            if key not in d:
                return None, f"journal missing field: {key}"
        for key in ("staging", "old_tree"):
            value = d.get(key)
            if value is not None:
                if os.path.dirname(value) != parent or \
                        not os.path.basename(value).startswith((".nas-staging-", ".nas-old-")):
                    return None, f"journal path for {key} is not a recognised staging/old folder"
        return d, None
    except Exception as e:
        return None, f"journal unreadable: {type(e).__name__}: {e}"

def delete_journal(parent):
    try:
        os.unlink(journal_file(parent))
    except FileNotFoundError:
        pass
    fsync_dir(parent)

# ---------------------------------------------------------------- archive checks
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
    the restored tree plus a 10% margin."""
    need = int(total_uncompressed(infos) * 1.1)
    anchor = target
    while not os.path.exists(anchor):
        anchor = os.path.dirname(os.path.abspath(anchor))
    free = shutil.disk_usage(anchor).free
    if free < need:
        return (f"not enough free space at {anchor}: need ~{need} bytes, "
                f"only {free} free — restore refused before writing anything")
    return None

def inspect_zip(z):
    """All read-only ZIP checks shared by verify-only and restore.
    Returns (infos, data_json, manifest, error)."""
    infos = [i for i in z.infolist() if not i.is_dir()]
    names = {i.filename for i in infos}
    for info in infos:
        problem = check_entry_safety(info)
        if problem:
            return None, None, None, f"unsafe entry: {problem}"
    limit_problem = check_archive_limits(infos)
    if limit_problem:
        return None, None, None, f"archive limit: {limit_problem}"
    bad_crc = z.testzip()
    if bad_crc:
        return None, None, None, f"corrupt entry (CRC): {bad_crc}"
    missing = [r for r in REQUIRED if r not in names]
    if missing:
        return None, None, None, f"required files missing: {missing}"
    d = json.loads(z.read("NAS-STUDIO/data.json").decode("utf-8"))
    if not (d.get("schema_version") == 2 and "projects" in d and "characters" in d):
        return None, None, None, ("data.json schema mismatch (need schema_version 2 "
                                  "with projects[] and characters[])")
    manifest = None
    if "MANIFEST.json" in names:
        manifest = json.loads(z.read("MANIFEST.json").decode("utf-8"))["files"]
        # Two-directional check (review finding #1). MANIFEST.json is
        # handled separately and is never one of its own hash entries.
        listed = set(manifest.keys())
        present = names - {"MANIFEST.json"}
        extra = sorted(present - listed)
        absent = sorted(listed - present)
        if extra or absent:
            return None, None, None, (f"manifest/ZIP mismatch: unlisted files in ZIP: "
                                      f"{extra}; listed files missing from ZIP: {absent}")
        mismatched = [f"{arc} (SHA-256 mismatch)" for arc, want in manifest.items()
                      if sha256_bytes(z.read(arc)) != want]
        if mismatched:
            return None, None, None, f"manifest verification failed: {mismatched}"
        print(f"Manifest verified: {len(manifest)} files, SHA-256 all match, "
              f"no unlisted files.")
    return infos, d, manifest, None

def verify_tree(root, manifest, infos):
    """Hash-verify (or, without a manifest, size/set-verify) the tree
    whose files live under <root> with their full NAS-STUDIO/... paths.
    Returns (ok, detail)."""
    if manifest:
        bad = []
        for arc, want in manifest.items():
            p = os.path.join(root, arc)
            if not os.path.exists(p):
                bad.append(f"{arc} (missing)")
                continue
            h = hashlib.sha256()
            with open(p, "rb") as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    h.update(chunk)
            if h.hexdigest() != want:
                bad.append(f"{arc} (SHA-256 mismatch)")
        return (not bad), bad
    expected = {i.filename: i.file_size for i in infos if i.filename != "MANIFEST.json"}
    bad = []
    for arc, size in expected.items():
        p = os.path.join(root, arc)
        if not os.path.exists(p) or os.path.getsize(p) != size:
            bad.append(arc)
    return (not bad), bad

# ---------------------------------------------------------------- crash recovery
def process_journal(parent, target):
    """Act on a leftover journal. Caller must hold the lock.
    Returns (report, error): exactly one of them is set, or both None
    when there is no journal."""
    d, err = read_journal(parent)
    if err:
        return None, (f"a restore journal exists but cannot be trusted ({err}) — "
                      f"nothing was touched; inspect {journal_file(parent)} manually")
    if d is None:
        return None, None
    final = os.path.join(target, "NAS-STUDIO")
    staging = d["staging"]
    old_tree = d["old_tree"]
    state = d["state"]
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    if state == "staging":
        if os.path.exists(staging):
            shutil.rmtree(staging, ignore_errors=True)
        delete_journal(parent)
        return ("interrupted restore (staging phase) cleaned up; "
                "the existing studio was never touched"), None
    if state == "old-aside":
        if old_tree and os.path.exists(old_tree) and not os.path.exists(final):
            os.rename(old_tree, final)
            fsync_dir(parent)
            fsync_dir(target)
            if os.path.exists(staging):
                shutil.rmtree(staging, ignore_errors=True)
            delete_journal(parent)
            return ("interrupted swap found (old studio set aside, new one not "
                    "in place) — original studio automatically restored"), None
        return None, ("journal says the old studio was set aside, but the folders "
                      "do not match that state — nothing was touched")
    if state == "swapped":
        zip_path = d["zip_path"]
        ok, detail = False, "recorded export ZIP is unavailable for verification"
        if zip_path and os.path.exists(zip_path):
            try:
                z = zipfile.ZipFile(zip_path)
                infos, _d, manifest, ierr = inspect_zip(z)
                if ierr is None:
                    ok, detail = verify_tree(target, manifest, infos)
            except Exception as e:
                detail = f"verification could not run: {e}"
        if ok:
            if old_tree and os.path.exists(old_tree):
                shutil.rmtree(old_tree, ignore_errors=True)
            if os.path.exists(staging):
                shutil.rmtree(staging, ignore_errors=True)
            delete_journal(parent)
            return ("interrupted restore (post-swap) completed: the new studio "
                    "verified in place, the old tree was removed"), None
        if old_tree and os.path.exists(old_tree) and os.path.exists(final):
            grave = os.path.join(parent, f".nas-failed-{stamp}")
            os.rename(final, grave)
            os.rename(old_tree, final)
            fsync_dir(parent)
            fsync_dir(target)
            if os.path.exists(staging):
                shutil.rmtree(staging, ignore_errors=True)
            delete_journal(parent)
            return (f"interrupted restore's new studio FAILED verification "
                    f"({detail}) — rolled back to the original studio; "
                    f"failed tree kept at {grave}"), None
        return None, ("journal says the swap completed but verification failed "
                      "and the old tree is missing — nothing was touched")
    return None, f"unhandled journal state: {state}"

# ---------------------------------------------------------------- test hooks
def crash_hook(point):
    if os.environ.get("NAS_RESTORE_CRASH_AT") == point:
        print(f"[test hook] hard kill at {point}", flush=True)
        os._exit(86)

# ---------------------------------------------------------------- restore
def do_restore(zip_path, target):
    parent = os.path.dirname(os.path.abspath(target))
    os.makedirs(parent, exist_ok=True)
    lock = RestoreLock(parent)
    try:
        lock.acquire()
    except LockHeld as held:
        print(f"RESTORE REFUSED — another restore holds the lock at {lock.path}: "
              f"{held.existing if held.existing else '(lock contents unreadable)'}. "
              f"If that process is dead, run: restore_studio.py --recover <target-folder>")
        return 3
    try:
        report, jerr = process_journal(parent, target)
        if jerr:
            print(f"RESTORE REFUSED — {jerr}")
            return 2
        if report:
            print(f"Previous interrupted restore handled: {report}")

        z = zipfile.ZipFile(zip_path)
        infos, d, manifest, ierr = inspect_zip(z)
        if ierr:
            print(f"RESTORE ABORTED — {ierr}")
            return 1
        space_problem = check_free_space(infos, target)
        if space_problem:
            print(f"RESTORE ABORTED — {space_problem}")
            return 1

        staging = tempfile.mkdtemp(prefix=".nas-staging-", dir=parent)
        journal = {"version": 1, "state": "staging", "run_id": lock.run_id,
                   "pid": os.getpid(), "target": os.path.abspath(target),
                   "staging": staging, "old_tree": None,
                   "zip_path": os.path.abspath(zip_path),
                   "updated": datetime.datetime.now().isoformat(timespec="seconds")}
        write_journal(parent, journal)
        restored = 0
        total_bytes = 0
        try:
            count = 0
            for info in infos:
                if info.filename == "MANIFEST.json":
                    continue
                dest = os.path.join(staging, info.filename)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                # Stream in 1 MB chunks: a large entry never sits fully in
                # memory. Nested archives are copied as inert data files.
                with z.open(info) as src, open(dest, "wb") as out_f:
                    shutil.copyfileobj(src, out_f, 1024 * 1024)
                    fsync_file(out_f)
                restored += 1
                total_bytes += info.file_size
                count += 1
                if count == 1:
                    pause = os.environ.get("NAS_RESTORE_PAUSE")
                    if pause:
                        print(f"[test hook] pausing {pause}s while holding the lock",
                              flush=True)
                        time.sleep(float(pause))
                    crash_hook("during-staging")
            ok, detail = verify_tree(staging, manifest, infos)
            if not ok:
                print(f"RESTORE ABORTED — staged verification failed: {detail}; "
                      f"existing studio untouched.")
                shutil.rmtree(staging, ignore_errors=True)
                delete_journal(parent)
                return 1
            print(f"Staged verification: "
                  f"{len(manifest) if manifest else len(infos)} files verified.")
        except Exception as e:
            print(f"RESTORE ABORTED — extraction failed in staging "
                  f"({type(e).__name__}: {e}); existing studio untouched.")
            shutil.rmtree(staging, ignore_errors=True)
            delete_journal(parent)
            return 1

        existing = os.path.join(target, "NAS-STUDIO")
        if os.path.exists(existing):
            backup_path = backup_existing_tree(target)
            check = zipfile.ZipFile(backup_path)
            if check.testzip() is not None:
                print(f"RESTORE ABORTED — pre-restore backup {backup_path} failed "
                      "its CRC check; existing tree left untouched.")
                shutil.rmtree(staging, ignore_errors=True)
                delete_journal(parent)
                return 1
            print(f"Existing studio tree backed up before restore: {backup_path}")
        os.makedirs(target, exist_ok=True)

        # THE SWAP, journal-guarded at every step.
        staged_tree = os.path.join(staging, "NAS-STUDIO")
        old_tree = None
        if os.path.exists(existing):
            stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            old_tree = os.path.join(parent, f".nas-old-{stamp}")
            journal.update({"state": "old-aside", "old_tree": old_tree,
                            "updated": datetime.datetime.now().isoformat(timespec="seconds")})
            write_journal(parent, journal)
            os.rename(existing, old_tree)
            fsync_dir(parent)
            fsync_dir(target)
        crash_hook("after-old-aside")
        try:
            os.rename(staged_tree, existing)
        except Exception as e:
            if old_tree and os.path.exists(old_tree):
                os.rename(old_tree, existing)
                fsync_dir(parent)
                fsync_dir(target)
                print(f"RESTORE ABORTED — replacement failed ({type(e).__name__}: {e}); "
                      f"original studio automatically restored.")
            else:
                print(f"RESTORE ABORTED — replacement failed ({type(e).__name__}: {e}).")
            shutil.rmtree(staging, ignore_errors=True)
            delete_journal(parent)
            return 1
        fsync_dir(parent)
        fsync_dir(target)
        journal.update({"state": "swapped", "old_tree": old_tree,
                        "updated": datetime.datetime.now().isoformat(timespec="seconds")})
        write_journal(parent, journal)
        crash_hook("after-swap")

        if os.environ.get("NAS_RESTORE_CORRUPT_AFTER_SWAP") == "1" and manifest:
            victim = os.path.join(target, sorted(manifest.keys())[0])
            with open(victim, "r+b") as f:
                first = f.read(1)
                f.seek(0)
                f.write(bytes([first[0] ^ 0xFF]) if first else b"X")
            print(f"[test hook] corrupted one byte in {victim}", flush=True)

        ok, detail = verify_tree(target, manifest, infos)
        if not ok:
            stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            grave = os.path.join(parent, f".nas-failed-{stamp}")
            os.rename(existing, grave)
            if old_tree and os.path.exists(old_tree):
                os.rename(old_tree, existing)
            fsync_dir(parent)
            fsync_dir(target)
            shutil.rmtree(staging, ignore_errors=True)
            delete_journal(parent)
            print(f"RESTORE FAILED — the swapped-in studio failed verification "
                  f"({detail}); original studio automatically restored; "
                  f"failed tree kept at {grave}")
            return 1
        print("Post-swap verification: new studio verified in place.")

        if old_tree:
            shutil.rmtree(old_tree, ignore_errors=True)
        shutil.rmtree(staging, ignore_errors=True)
        delete_journal(parent)
        print(f"RESTORE COMPLETE — {restored} files, {total_bytes/1e6:.1f} MB restored to "
              f"{target}/NAS-STUDIO; projects: {len(d['projects'])}, "
              f"characters: {len(d['characters'])}; "
              f"manifest: {'verified' if manifest else 'absent (older export — CRC + schema verified only)'}")
        return 0
    finally:
        lock.release()

# ---------------------------------------------------------------- recover mode
def do_recover(target, force_stale_lock):
    parent = os.path.dirname(os.path.abspath(target))
    lock_path = os.path.join(parent, LOCK_NAME)
    # A corrupt journal stops recovery before the lock is even considered:
    _d, jerr = read_journal(parent)
    if jerr:
        print(f"RECOVERY REFUSED — {jerr}. Nothing was touched. "
              f"Inspect {journal_file(parent)} manually.")
        return 2
    claimed_from = None
    if os.path.exists(lock_path):
        try:
            existing = json.loads(open(lock_path, encoding="utf-8").read())
        except Exception:
            existing = None
        if existing is None:
            if not force_stale_lock:
                print(f"RECOVERY REFUSED — the lock at {lock_path} is unreadable, so "
                      f"its owner cannot be assessed. Nothing was touched. If you "
                      f"have confirmed manually that no restore is running, re-run "
                      f"with --force-stale-lock.")
                return 2
            existing = {"_under_override": True}
        verdict, evidence = ("unknown", "lock unreadable — assessed under operator override") \
            if existing.get("_under_override") else assess_lock_owner(existing)
        if verdict == "alive":
            print(f"RECOVERY REFUSED — the lock's owner is alive ({evidence}). "
                  f"An active process's lock is never modified.")
            return 3
        if verdict == "unknown" and not force_stale_lock:
            print(f"RECOVERY REFUSED — the lock owner's state cannot be proven "
                  f"({evidence}). Nothing was touched. Confirm manually that no "
                  f"restore is running, then re-run with --force-stale-lock.")
            return 2
        if verdict == "unknown":
            print(f"Operator override: owner unprovable ({evidence}); proceeding "
                  f"under --force-stale-lock.")
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        claimed_from = lock_path + f".recovered-{stamp}"
        try:
            os.rename(lock_path, claimed_from)
        except OSError as e:
            print(f"RECOVERY REFUSED — could not claim the stale lock ({e}); "
                  f"another recovery may be running.")
            return 3
        fsync_dir(parent)
        print(f"Stale lock claimed (owner: {evidence}); preserved at {claimed_from}")
    lock = RestoreLock(parent)
    try:
        lock.acquire()
    except LockHeld as held:
        print(f"RECOVERY REFUSED — a lock appeared during recovery: {held.existing}")
        return 3
    try:
        report, jerr = process_journal(parent, target)
        if jerr:
            print(f"RECOVERY REFUSED — {jerr}")
            return 2
        if report:
            print(f"RECOVERY DONE — {report}")
        elif claimed_from:
            print("RECOVERY DONE — no interrupted restore was recorded; "
                  "only the stale lock was cleared.")
        else:
            print("Nothing to recover: no journal and no lock.")
        return 0
    finally:
        lock.release()

# ---------------------------------------------------------------- main
def main():
    args = sys.argv[1:]
    if args and args[0] == "--recover":
        if len(args) < 2:
            print(__doc__)
            return 1
        return do_recover(args[1], "--force-stale-lock" in args)
    if len(args) < 2:
        print(__doc__)
        return 1
    zip_path = args[0]
    if args[1] == "--verify-only":
        z = zipfile.ZipFile(zip_path)
        infos, d, manifest, ierr = inspect_zip(z)
        if ierr:
            print(f"VERIFY FAILED — {ierr}")
            return 1
        print(f"VERIFY-ONLY PASSED — {len(infos)} files; required: all present; "
              f"projects: {len(d['projects'])}, characters: {len(d['characters'])}; "
              f"manifest: {'verified' if manifest else 'absent (older export)'}")
        return 0
    return do_restore(zip_path, args[1])

if __name__ == "__main__":
    sys.exit(main())
