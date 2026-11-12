#!/usr/bin/env python3
"""Scan NAS-STUDIO and generate data.json — the single studio data schema (v2).
LOCAL use only: never upload real output to public hosting.
Schema v2 keys (ALL always present, restore-compatible):
  schema_version, generated_from, projects[], characters[], approvals[], budget_ledger_md, generation_log_md
"""
import json, os, csv
ROOT = os.path.join(os.path.dirname(__file__), "..", "NAS-STUDIO")
def read(p):
    try:
        with open(p, encoding="utf-8") as f: return f.read()
    except FileNotFoundError: return ""
data = {"schema_version": 2, "generated_from": "NAS-STUDIO",
        "projects": [], "characters": [], "approvals": [], "budget_ledger_md": "", "generation_log_md": ""}
pdir = os.path.join(ROOT, "01-projects")
for name in sorted(os.listdir(pdir)):
    full = os.path.join(pdir, name)
    if os.path.isdir(full):
        data["projects"].append({"id": name, "doc": read(os.path.join(full, "PROJECT.md"))[:4000],
                                 "subfolders": sorted(os.listdir(full))})
cdir = os.path.join(ROOT, "02-characters")
for fn in sorted(os.listdir(cdir)):
    if fn.endswith(".json"):
        try:
            with open(os.path.join(cdir, fn), encoding="utf-8") as f: data["characters"].append(json.load(f))
        except Exception as e:
            data["characters"].append({"file": fn, "error": str(e)})
alog = os.path.join(ROOT, "00-master-control", "approvals-log.csv")
if os.path.exists(alog):
    with open(alog, encoding="utf-8") as f: data["approvals"] = list(csv.DictReader(f))
data["budget_ledger_md"] = read(os.path.join(ROOT, "06-budget", "BUDGET-LEDGER.md"))
data["generation_log_md"] = read(os.path.join(ROOT, "03-video-center", "GENERATION-LOG.md"))
out = os.path.join(ROOT, "data.json")
with open(out, "w", encoding="utf-8") as f: json.dump(data, f, indent=2, ensure_ascii=False)
print(f"data.json v2 written: {out} — projects: {len(data['projects'])}, characters: {len(data['characters'])}, approvals: {len(data['approvals'])}")
