# Editor Agent — actual pipeline (specified 2026-11-13)
Tools: ffmpeg (local, scripted — the same pipeline that cut the first film) + optional CapCut (manual polish only, owner's device).
Steps:
1. Ingest approved clips → project/clips/ (originals untouched).
2. Edit Decision List (EDL) written by Editor Agent: clip order, in/out trims to narration/action beats.
3. Assembly script (ffmpeg): trim + concat per EDL, picture lock first.
4. Audio: dialogue takes placed on beats; music beds per act (licensed sources only, logged); SFX from project/audio/; loudness normalised (-16 LUFS target for YouTube), dialogue ducking under music.
5. Grade: consistent contrast/saturation pass (ffmpeg filters) — no per-clip look drift.
6. Subtitles: .srt generated from locked dialogue, burned or sidecar per release.
7. Exports: 720p master (yuv420p, faststart — phone-safe), 1080p version (Flow upscale where applicable), archive master. QC plays every export fully before delivery.
