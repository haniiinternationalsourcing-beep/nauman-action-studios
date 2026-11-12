# 15 AI Agent Roles — real responsibilities & workflow
Each role is performed by the operator (Naumii/sub-agents) and leaves a real output in the project folder.
1. Executive Producer — owns plan, budget gates, approvals queue → 00-master-control/
2. Director — scene intent, shot choices, performance notes → project/scenes/
3. Screenwriter — story + screenplay drafts/final → project/screenplay/
4. Storyboard Agent — shot-by-shot visual plan → project/storyboards/
5. Character Designer — character profiles + locked portraits → 02-characters/ + project/characters/
6. Cinematography Agent — camera/lighting language per scene → project/scenes/
7. Video Generation Agent — operates Flow/Kling/Seedance (manual/API as labelled), logs every generation → 03-video-center/
8. Voice Director — dialogue files, voice settings, take selection → 04-voice/
9. Sound Design Agent — SFX/music lists + licensed sources → project/audio/
10. Editor Agent — edit decision list + assembled cuts (real editing pipeline) → project/edit/
11. Continuity Supervisor — per-clip checklist (face/hair/clothes/props/direction) → project/scenes/ continuity notes
12. Quality Control — technical checks (resolution, audio levels, artefacts) before any delivery
13. Budget Manager — ledger, estimates before paid steps, credit tracker → 06-budget/
14. Copyright & Licensing Checker — music/SFX licences, no copied characters/likenesses
15. Marketing Agent — titles, descriptions, posters, release plan → 08-library/
Workflow: Screenwriter → Director → Storyboard → Character Designer → Video Generation → Continuity → Voice → Sound → Editor → QC → Marketing. Paid steps stop at the Approvals Queue.

## Manual vs Automated (added 2026-11-13)
- MANUAL (operator judgment, human-style decisions): Executive Producer, Director, Screenwriter (final), Character Designer (approval of looks), Voice Director (take selection), Continuity Supervisor, QC sign-off, Marketing.
- ASSISTED (AI drafts → operator/owner approves): Storyboard, Cinematography prompts, Video Generation (prompts drafted, generation executed in provider UI), Sound Design lists, Editor (edit decision list).
- AUTOMATED (deterministic scripts, no judgment): Budget ledger sums + cost-per-minute (tools/generate_data.py), data.json generation, ZIP export (tools/export_studio.py), generation-log formatting checks.
## Per-department input → output → test
- Projects: input = concept note → output = project folder + PROJECT.md → test: folder has all 11 subfolders + status line matches the real record.
- Characters: input = portrait + traits → output = .json profile + locked portrait → test: any clip can be checked against the 4-point checklist.
- Video Center: input = shot list → output = logged generations + clips → test: every clip file has a matching log line.
- Voice: input = locked dialogue → output = audio takes per character → test: take file name matches dialogue line ID.
- Post: input = approved clips → output = edit + exports → test: export plays end-to-end, audio in range.
- Budget: input = receipts/log → output = ledger + totals → test: totals equal the generation log's credit sums.
