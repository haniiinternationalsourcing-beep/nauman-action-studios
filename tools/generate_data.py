#!/usr/bin/env python3
"""CANONICAL studio data builder — the single source of truth for data.json.

This exact file is the one embedded in the Control Room app and the one kept
in tools/. If the two ever differ, THIS disk copy wins and the app copy must
be re-synced. (Divergence was audit issue #1, fixed 2026-11-13.)

Scans NAS-STUDIO and writes NAS-STUDIO/data.json — schema v2:
  schema_version, generated_from, projects[], characters[], approvals[],
  budget_ledger_md, generation_log_md   (ALL keys always present)

Record compatibility with the Control Room app:
  - projects[] entries carry the folder fields {id, doc, subfolders} PLUS
    {code, title, status_note} parsed from PROJECT.md, which the app's
    studioToAppData() adapter maps onto its project cards.
  - characters[] entries are the character JSON files unchanged (they carry
    name / role / status + description fields the app displays).
  - approvals[] entries are the approvals-log.csv rows unchanged
    {date, item, cost, status, note}.
LOCAL use only: never upload real output to public hosting.
"""
import json, os, csv

ROOT = os.path.join(os.path.dirname(__file__), "..", "NAS-STUDIO")

def read(p):
    try:
        with open(p, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""

def parse_project_doc(doc):
    """Pull a display title + status note out of a PROJECT.md, honestly:
    title = first '# ' heading (text after an em dash when present);
    status_note = first line mentioning STATUS, else empty string."""
    title, status_note = "", ""
    for line in doc.splitlines():
        if not title and line.startswith("# "):
            heading = line[2:].strip()
            title = heading.split("—", 1)[1].strip() if "—" in heading else heading
        if not status_note and "STATUS" in line.upper():
            status_note = line.strip()[:160]
        if title and status_note:
            break
    return title, status_note

data = {"schema_version": 2, "generated_from": "NAS-STUDIO",
        "projects": [], "characters": [], "approvals": [],
        "budget_ledger_md": "", "generation_log_md": ""}

pdir = os.path.join(ROOT, "01-projects")
if os.path.isdir(pdir):
    for name in sorted(os.listdir(pdir)):
        full = os.path.join(pdir, name)
        if os.path.isdir(full):
            doc = read(os.path.join(full, "PROJECT.md"))
            title, status_note = parse_project_doc(doc)
            data["projects"].append({
                "id": name,
                "code": name.replace("-", " "),
                "title": title or name,
                "status_note": status_note,
                "doc": doc[:4000],
                "subfolders": sorted(os.listdir(full)),
            })

cdir = os.path.join(ROOT, "02-characters")
if os.path.isdir(cdir):
    for fn in sorted(os.listdir(cdir)):
        if fn.endswith(".json"):
            try:
                with open(os.path.join(cdir, fn), encoding="utf-8") as f:
                    data["characters"].append(json.load(f))
            except Exception as e:
                data["characters"].append({"file": fn, "error": str(e)})

alog = os.path.join(ROOT, "00-master-control", "approvals-log.csv")
if os.path.exists(alog):
    with open(alog, encoding="utf-8") as f:
        data["approvals"] = list(csv.DictReader(f))

data["budget_ledger_md"] = read(os.path.join(ROOT, "06-budget", "BUDGET-LEDGER.md"))
data["generation_log_md"] = read(os.path.join(ROOT, "03-video-center", "GENERATION-LOG.md"))

out = os.path.join(ROOT, "data.json")
with open(out, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
print(f"data.json v2 written: {out} — projects: {len(data['projects'])}, "
      f"characters: {len(data['characters'])}, approvals: {len(data['approvals'])}")
