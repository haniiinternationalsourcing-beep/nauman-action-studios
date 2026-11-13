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
    REJECTED (zip-slip / link attacks) and abort the restore. Windows
    path forms are rejected too: drive-letter (absolute or relative),
    UNC, device-namespace and any colon-bearing, trailing-space/dot or
    reserved-name component. Extraction resolves every destination and
    verifies containment inside the staging folder immediately before
    writing, creates files exclusively (O_EXCL, O_NOFOLLOW where
    available), and refuses to walk through symlinked folders.
    (Audit fix phase 3, 2026-11-13.)
  - Directory fsyncs FAIL CLOSED: only explicitly unsupported cases
    degrade — with a printed notice — to file fsyncs + journal
    checksums. Genuine I/O errors (EIO, ENOSPC, ...) at the mandatory
    durability points (journal writes, swap renames) abort the
    operation before any further change; the journal left on disk
    stays checksum-valid and recoverable. (Audit fix phase 3,
    2026-11-13.)
  - The unsupported classification is NARROW (audit fix phase 4,
    2026-11-13): an error is 'unsupported' only when it is positively
    identified — a filesystem-level EINVAL/ENOTSUP/EOPNOTSUPP from the
    fsync itself, or, on Windows, the specific case proven by a
    one-time control probe on a neutral directory: os.open() cannot
    open a directory handle for fsync there (PermissionError). The
    exact documented limitation is that limitation of the os.open
    mechanism on Windows — nothing more. EACCES on other platforms,
    and EIO/ENOSPC/EROFS or any unexpected error on ANY platform
    (Windows included), are genuine failures and fail closed.
    File-level fsync failures are genuine on every platform and are
    reported as durability failures (exit 4), never as tracebacks.
    On Windows the deliberate fallback is: file-level fsyncs (which
    do work there) + journal checksums + evidence-based recovery —
    and no stronger durability is claimed than that.
  - The journal's temporary file is created EXCLUSIVELY (O_EXCL +
    O_NOFOLLOW where available) under its fixed name (audit fix
    phase 4, 2026-11-13): a pre-existing temp that is a symlink or
    not a regular file is refused untouched (possible plant); a stale
    regular temp is preserved — never overwritten — by an
    overwrite-safe, race-safe rename-aside (hardlink claim; the
    existing destination is never replaced) with its SHA-256 and
    exact path printed as evidence.
  - A journal is acted on ONLY for the target it records: the recorded
    target is compared, canonically (platform-aware: Windows case
    folding, path normalisation, symlink resolution), with the target
    the operator supplied, and the staging/old-tree paths are validated
    against the recorded target's parent — all before any filesystem
    mutation. A journal for another target, or one moved to another
    folder, is refused untouched. (Audit fix phase 3, 2026-11-13.)
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
import socket, time, re, errno

REQUIRED = ["NAS-STUDIO/README.md", "NAS-STUDIO/OPERATOR-MANUAL.md",
            "NAS-STUDIO/data.json",
            "NAS-STUDIO/00-master-control/approvals-log.csv",
            "NAS-STUDIO/03-video-center/GENERATION-LOG.md"]

JOURNAL_NAME = ".nas-restore-journal.json"
LOCK_NAME = ".nas-restore.lock"
JOURNAL_STATES = ("staging", "old-aside", "swapped")

# ---------------------------------------------------------------- durability
class DurabilityError(Exception):
    """A mandatory directory fsync failed with a genuine I/O error.
    The operation must stop before any further mutation; the journal
    on disk (if any) stays checksum-valid and recoverable."""

_DIR_FSYNC_UNSUPPORTED_ERRNOS = {
    errno.EINVAL,
    getattr(errno, "ENOTSUP", errno.EINVAL),
    getattr(errno, "EOPNOTSUPP", errno.EINVAL),
}
_dir_fsync_notice_shown = False
_dir_fsync_probe = {"done": False, "unsupported": False}

def _degrade_dir_fsync():
    """Print the unsupported notice once per process; return False."""
    global _dir_fsync_notice_shown
    if not _dir_fsync_notice_shown:
        _dir_fsync_notice_shown = True
        print("note: directory fsync is not supported via os.open on this "
              "platform/filesystem \u2014 durability relies on file-level "
              "fsyncs and journal checksums.", file=sys.stderr)
    return False

def _probe_dir_fsync_platform():
    """One-time CONTROL experiment on a neutral directory (the system
    temp dir): can this platform fsync a directory through os.open at
    all? 'Unsupported' is concluded ONLY from positive identification:
    on Windows, os.open() raising EACCES/EPERM for a directory (the
    documented os.open limitation there), or EINVAL/ENOTSUP from the
    attempt. Every other outcome \u2014 success, or a genuine error \u2014
    leaves the platform classified as 'supported', so real failures
    are never re-labelled as unsupported."""
    if _dir_fsync_probe["done"]:
        return _dir_fsync_probe["unsupported"]
    _dir_fsync_probe["done"] = True
    result = False
    try:
        fd = os.open(tempfile.gettempdir(), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError as e:
        if os.name == "nt" and e.errno in (errno.EACCES, errno.EPERM):
            result = True
        elif e.errno in _DIR_FSYNC_UNSUPPORTED_ERRNOS:
            result = True
    _dir_fsync_probe["unsupported"] = result
    return result

def _dir_fsync_failed(e, path, mandatory):
    if mandatory:
        raise DurabilityError(f"directory fsync failed for {path}: {e}")
    print(f"warning: directory fsync failed for {path}: {e}", file=sys.stderr)
    return False

def fsync_dir(path, mandatory=True):
    """Directory fsync with explicit, NARROW failure handling
    (audit fixes 3+4).

    Returns True when the fsync was performed. Degradation (printed
    notice, returns False) happens ONLY for positively identified
    unsupported cases: a filesystem-level EINVAL/ENOTSUP/EOPNOTSUPP
    from the fsync itself, or \u2014 on Windows \u2014 an open-time
    EACCES/EPERM when the control probe has proven that os.open
    cannot open directory handles for fsync on this platform.
    Everything else (EIO, ENOSPC, EROFS, EACCES elsewhere, unexpected
    errors on ANY platform) is a genuine I/O failure: at a mandatory
    durability point it raises DurabilityError (fail closed); at a
    non-mandatory point it prints a warning."""
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError as e:
        if e.errno in (errno.EACCES, errno.EPERM) and os.name == "nt" \
                and _probe_dir_fsync_platform():
            return _degrade_dir_fsync()
        return _dir_fsync_failed(e, path, mandatory)
    try:
        os.fsync(fd)
    except OSError as e:
        if e.errno in _DIR_FSYNC_UNSUPPORTED_ERRNOS:
            return _degrade_dir_fsync()
        return _dir_fsync_failed(e, path, mandatory)
    finally:
        os.close(fd)
    return True

def fsync_file(f):
    """File fsync. A failure is a genuine I/O error on every platform:
    it is raised as a DurabilityError so the operation fails closed
    with a clear message instead of a raw traceback."""
    try:
        f.flush()
        os.fsync(f.fileno())
    except OSError as e:
        raise DurabilityError(f"file fsync failed: {e}")

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
        fsync_dir(self.parent, mandatory=False)

    def release(self):
        """Delete ONLY our own lock: re-read and match the run id first."""
        try:
            current = json.loads(open(self.path, encoding="utf-8").read())
            if current.get("run_id") == self.run_id:
                os.unlink(self.path)
                fsync_dir(self.parent, mandatory=False)
        except Exception:
            pass

# ---------------------------------------------------------------- journal
def canonical(p):
    """Platform-aware canonical path for comparisons: absolute, fully
    normalised, symlinks resolved, and case-folded where the platform
    folds case (os.path.normcase lowercases on Windows, identity on
    POSIX)."""
    return os.path.normcase(os.path.realpath(os.path.abspath(p)))

def journal_file(parent):
    return os.path.join(parent, JOURNAL_NAME)

class JournalError(Exception):
    """The journal could not be written safely (e.g. a suspicious
    pre-existing temp file). Nothing was overwritten; the operation
    refuses instead of guessing."""

def _now_stamp():
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")

def _preserve_stale_temp(tmp):
    """Preserve a stale REGULAR journal temp without ever overwriting
    anything (audit fix 4): the temp is claimed aside by hardlink to
    the first free '.stale-<stamp>' name \u2014 os.link fails atomically
    if the name is taken, so an existing destination is NEVER replaced
    and the claim is race-safe \u2014 then the temp name is unlinked.
    If hardlinking is unavailable on this filesystem, an exclusive-
    create copy is used instead (still never replacing). Prints the
    evidence line and returns (aside_path, sha256, size)."""
    with open(tmp, "rb") as f:
        data = f.read()
    digest = hashlib.sha256(data).hexdigest()
    stamp = _now_stamp()
    aside = None
    for i in range(1, 100):
        candidate = tmp + f".stale-{stamp}" + ("" if i == 1 else f"-{i}")
        try:
            os.link(tmp, candidate)
            aside = candidate
            break
        except FileExistsError:
            continue
        except OSError:
            try:
                fd = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                             | getattr(os, "O_NOFOLLOW", 0), 0o644)
            except FileExistsError:
                continue
            with os.fdopen(fd, "wb") as out:
                out.write(data)
                fsync_file(out)
            aside = candidate
            break
    if aside is None:
        raise JournalError(f"could not preserve the stale journal temp {tmp}: "
                           f"no free aside name found")
    os.unlink(tmp)
    fsync_dir(os.path.dirname(tmp) or ".", mandatory=False)
    print(f"note: a stale journal temp was preserved at {aside} "
          f"(sha256 {digest}, {len(data)} bytes) and a fresh temp was used")
    return aside, digest, len(data)

def write_journal(parent, payload):
    body = dict(payload)
    body["checksum"] = hashlib.sha256(
        json.dumps(body, sort_keys=True).encode()).hexdigest()
    tmp = journal_file(parent) + ".tmp"
    # Stale-temp protocol (audit fix 4): the temp is created
    # EXCLUSIVELY below, so anything already at that path is dealt
    # with first \u2014 a symlink or non-regular object is refused
    # untouched (possible plant); a stale regular file is preserved
    # aside, never overwritten.
    try:
        st = os.lstat(tmp)
    except FileNotFoundError:
        st = None
    if st is not None:
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
            raise JournalError(
                f"the journal temp {tmp} already exists and is not a "
                f"regular file (possible planted link) \u2014 refusing to "
                f"write the journal; nothing was overwritten. Inspect "
                f"and remove it manually.")
        _preserve_stale_temp(tmp)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(tmp, flags, 0o644)
    except FileExistsError:
        raise JournalError(
            f"the journal temp {tmp} appeared during the write "
            f"(possible race or planted file) \u2014 refusing to overwrite "
            f"it. Inspect it manually.")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(json.dumps(body, indent=2))
        fsync_file(f)
    try:
        os.rename(tmp, journal_file(parent))
    except FileNotFoundError:
        raise JournalError(
            f"the journal temp {tmp} disappeared during the write "
            f"(removed by another process) — the journal write was "
            f"refused safely rather than guessed at.")
    fsync_dir(parent)

def read_journal(parent, expected_target=None):
    """(payload, None) or (None, error). A journal that cannot be fully
    validated is an error, never a guess. When expected_target is given,
    the journal is additionally bound to that target (audit fix 3): the
    recorded target must canonically equal the supplied one, and the
    staging / old-tree paths must sit in the RECORDED target's parent."""
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
        recorded = d.get("target")
        if not isinstance(recorded, str) or not recorded:
            return None, "journal target field is not a usable path"
        rec_parent = os.path.dirname(canonical(recorded))
        if rec_parent != canonical(parent):
            return None, ("journal target's parent does not match the folder "
                          "the journal was found in (journal moved or copied?)")
        if expected_target is not None and canonical(recorded) != canonical(expected_target):
            return None, (f"journal target mismatch: the journal records "
                          f"{recorded} but the supplied target is "
                          f"{expected_target} — a journal is never acted on "
                          f"for another target")
        for key in ("staging", "old_tree"):
            value = d.get(key)
            if value is not None:
                if os.path.dirname(canonical(value)) != rec_parent or \
                        not os.path.basename(value).startswith((".nas-staging-", ".nas-old-")):
                    return None, f"journal path for {key} is not a recognised staging/old folder in the recorded target's parent"
        return d, None
    except Exception as e:
        return None, f"journal unreadable: {type(e).__name__}: {e}"

def delete_journal(parent):
    try:
        os.unlink(journal_file(parent))
    except FileNotFoundError:
        pass
    fsync_dir(parent, mandatory=False)

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

_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:")
_RESERVED_STEMS = ({"CON", "PRN", "AUX", "NUL"}
                   | {f"COM{i}" for i in range(1, 10)}
                   | {f"LPT{i}" for i in range(1, 10)})

def check_entry_safety(info):
    """Reject any entry whose name could escape or confuse the target
    folder on ANY supported platform (audit fix 3): absolute paths, UNC
    and device-namespace paths, Windows drive-letter paths (absolute or
    drive-relative), '..' or empty components, colon-bearing components,
    components with trailing spaces/dots (which Windows silently trims),
    Windows reserved device names, and symlink entries."""
    name = info.filename
    if not name or "\x00" in name:
        return f"empty or NUL-containing entry name: {name!r}"
    if name[0] in "/\\" or name.startswith("//"):
        return f"absolute/UNC/device path entry: {name}"
    if _DRIVE_PREFIX.match(name):
        return f"Windows drive-letter path entry: {name}"
    parts = re.split(r"[/\\]", name)
    if name.endswith("/"):
        parts = parts[:-1]  # directory entry: drop the trailing empty part
    for part in parts:
        if part in ("", ".", ".."):
            return f"unsafe path component {part!r} in entry: {name}"
        if ":" in part:
            return f"colon in path component of entry: {name}"
        if ".." in part:
            return f"double-dot in path component of entry: {name}"
        if part != part.strip() or part.endswith("."):
            return f"Windows-unsafe path component (edge space/dot) in entry: {name}"
        stem = part.split(".")[0]
        if stem != stem.strip() or stem.endswith("."):
            return f"Windows-unsafe path component (stem edge space/dot) in entry: {name}"
        for seg in part.split(".")[1:]:
            if seg and (seg.strip() == "" or seg.strip(".") == ""):
                return f"Windows-unsafe path component (blank segment) in entry: {name}"
        if part.split(".")[0].upper() in _RESERVED_STEMS:
            return f"Windows reserved device name in entry: {name}"
    mode = (info.external_attr >> 16) & 0xFFFF
    if stat.S_ISLNK(mode):
        return f"symlink entry refused: {name}"
    return None

def contained_dest(root, arc):
    """Resolve arc under root and refuse anything that lands outside
    the resolved root (audit fix 3). Symlinks in the already-existing
    prefix are resolved by realpath, so a planted link is caught here;
    the result is checked again implicitly by extract_entry's chain
    walk and exclusive create."""
    root_real = os.path.realpath(root)
    dest = os.path.realpath(os.path.join(root_real, *arc.split("/")))
    if dest != root_real and not dest.startswith(root_real + os.sep):
        raise ValueError(f"entry destination escapes its folder: {arc}")
    return dest

def _ensure_parent_chain(root, dest):
    """Create dest's parent folders one level at a time under root,
    refusing to walk through a symlink or a non-folder (audit fix 3)."""
    root_real = os.path.realpath(root)
    rel = os.path.relpath(os.path.dirname(dest), root_real)
    cur = root_real
    if rel == ".":
        return
    for part in rel.split(os.sep):
        cur = os.path.join(cur, part)
        if os.path.islink(cur):
            raise ValueError(f"refusing to extract through a symlinked folder: {cur}")
        if os.path.exists(cur):
            if not os.path.isdir(cur):
                raise ValueError(f"extraction path blocked by a non-folder: {cur}")
        else:
            os.mkdir(cur)

def extract_entry(z, info, staging):
    """Write one ZIP entry into staging safely (audit fix 3):
    containment is resolved and verified immediately before writing,
    parent folders are created without following symlinks, and the
    file itself is created exclusively (O_EXCL, plus O_NOFOLLOW where
    the platform offers it), so an existing file or link is never
    overwritten."""
    dest = contained_dest(staging, info.filename)
    _ensure_parent_chain(staging, dest)
    if os.path.islink(dest) or os.path.exists(dest):
        raise ValueError(f"destination already exists or is a link: {info.filename}")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(dest, flags, 0o644)
    # Stream in 1 MB chunks: a large entry never sits fully in memory.
    # Nested archives are copied as inert data files.
    with z.open(info) as src, os.fdopen(fd, "wb") as out_f:
        shutil.copyfileobj(src, out_f, 1024 * 1024)
        fsync_file(out_f)

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
        root_real = os.path.realpath(root)
        for arc, want in manifest.items():
            p = os.path.join(root, arc)
            if os.path.realpath(p) != root_real and \
                    not os.path.realpath(p).startswith(root_real + os.sep):
                bad.append(f"{arc} (escapes the verified folder)")
                continue
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
def _verify_recorded(target, d):
    """Verify the tree at <target>/NAS-STUDIO against the journal's
    recorded export ZIP. Returns (ok, detail)."""
    zip_path = d.get("zip_path")
    if not zip_path or not os.path.exists(zip_path):
        return False, "recorded export ZIP is unavailable for verification"
    try:
        z = zipfile.ZipFile(zip_path)
        infos, _d, manifest, ierr = inspect_zip(z)
        if ierr is not None:
            return False, ierr
        return verify_tree(target, manifest, infos)
    except Exception as e:
        return False, f"verification could not run: {e}"

def process_journal(parent, target):
    """Act on a leftover journal. Caller must hold the lock. The journal
    is validated against the supplied target before ANY filesystem
    mutation (read_journal refuses cross-target or moved journals).
    Returns (report, error): exactly one of them is set, or both None
    when there is no journal."""
    d, err = read_journal(parent, expected_target=target)
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
        if old_tree and os.path.exists(old_tree) and os.path.exists(final):
            # The process died after the swap rename but before the
            # 'swapped' journal write landed. Decide by EVIDENCE: verify
            # the in-place tree against the recorded export.
            ok, detail = _verify_recorded(target, d)
            if ok:
                shutil.rmtree(old_tree, ignore_errors=True)
                if os.path.exists(staging):
                    shutil.rmtree(staging, ignore_errors=True)
                delete_journal(parent)
                return ("interrupted restore (swap done, journal update lost) "
                        "completed: the new studio verified in place, the old "
                        "tree was removed"), None
            grave = os.path.join(parent, f".nas-failed-{stamp}")
            os.rename(final, grave)
            os.rename(old_tree, final)
            fsync_dir(parent)
            fsync_dir(target)
            if os.path.exists(staging):
                shutil.rmtree(staging, ignore_errors=True)
            delete_journal(parent)
            return (f"interrupted restore's in-place studio FAILED verification "
                    f"({detail}) — rolled back to the original studio; "
                    f"failed tree kept at {grave}"), None
        if (not old_tree or not os.path.exists(old_tree)) and os.path.exists(final) \
                and staging and os.path.exists(staging):
            # The journal write landed but the rename it announces never
            # happened (e.g. a durability failure aborted the operation at
            # the journal write): final still holds the untouched studio.
            shutil.rmtree(staging, ignore_errors=True)
            delete_journal(parent)
            return ("interrupted restore (journal written, swap never started) "
                    "cleaned up; the existing studio was never touched"), None
        return None, ("journal says the old studio was set aside, but the folders "
                      "do not match that state — nothing was touched")
    if state == "swapped":
        ok, detail = _verify_recorded(target, d)
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
                   "pid": os.getpid(), "target": canonical(target),
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
                extract_entry(z, info, staging)
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
        except DurabilityError:
            raise
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
    # A corrupt, moved or cross-target journal stops recovery before the
    # lock is even considered, and before any filesystem mutation:
    _d, jerr = read_journal(parent, expected_target=target)
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
    try:
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
    except DurabilityError as e:
        # Fail closed (audit fix 3): no further mutation happened after
        # the failed durability point, and the journal on disk (if any)
        # is checksum-valid, so --recover can finish or roll back.
        print(f"ABORTED — durability failure: {e}. No further changes were "
              f"made; run --recover on the target to reconcile the journal.")
        return 4
    except JournalError as e:
        # The journal could not be written safely (audit fix 4):
        # nothing was overwritten; a human inspects the temp path.
        print(f"REFUSED — journal safety: {e}")
        return 2

if __name__ == "__main__":
    sys.exit(main())
