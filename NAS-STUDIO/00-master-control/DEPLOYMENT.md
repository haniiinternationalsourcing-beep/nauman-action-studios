# Control Room — build & deployment (SECURE DATA MODEL, fixed 2026-11-13)
## The flaw that was fixed
Old plan generated a data.json snapshot of REAL studio data and uploaded it with the public app — that would expose private scripts, budgets and project data to anyone with the link. REMOVED.
## The secure model (binding)
1. The hosted app ships with DEMO DATA ONLY. No real script, budget or project data is ever uploaded to public hosting.
2. Real data never leaves the studio folder by default. To view real data, the app has a "Load studio data" action: the owner picks the local data.json (produced locally by tools/generate_data.py) — the file is read in the browser on HIS device and is NOT uploaded anywhere.
3. Netlify (his account) hosts only the empty shell + demo data. Losing the link exposes nothing private.
4. Source code lives in studio-app/ beside this file; rebuild/redeploy ~1 minute.
## Build notes
Static HTML/CSS/JS, no backend, no keys, no secrets in code. Works from any static host or a local file.
