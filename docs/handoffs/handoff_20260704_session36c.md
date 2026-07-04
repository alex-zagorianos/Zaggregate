# Handoff — 2026-07-04 Session 36c (search optimization + full review + desktop app)

Alex (stepping away, full autonomy): "optimize our searching methods… test
using all of my job search roles… as well as my dads. Go in depth and try to
get the jobs found as large as possible, particularly jobs that are actually
relevant… then go back through the entire frontend for UI/UX cleanup + a full
backend efficiency review. We want this professional. Also will this run as a
desktop app? that is what we want — if it won't, make it able to do that."

Everything delivered. **Suite 2,968 passed / 0 failed; vitest 176/176; tsc +
vite build clean; frozen exe rebuilt + desktop-window smoke PASSED;
production/ mirrored. PUSH STILL HELD.**

## 1. Multi-role live search test (Phase A) — all six real projects

Sequential deep runs (`--max-pages 3`), results + per-source detail in
`brain/findings-2026-07-04-search-optimization.md`:
mechdesign 0→784 · software 0→2,246 · applied-ai 781→969 · controls 660→782 ·
controls-cincinnati 1,523→1,822 · dad 35→35 (403 found, all previously seen).
**Alex's five role inboxes: 2,964 → 6,603 rows in one pass.**

## 2. Search-method optimization (Phase B) — fetch-side only, scorer untouched

- Metro satellite-city variants (`data_static/metro_satellites.csv`, 32
  Cincinnati MSA municipalities, state-suffixed) `3a299f4` + review fix
  (state-qualified hyphen-split pieces) `a6b8676`.
- Curated eng query synonyms — the eng_like branch pinned `syn=[]` forever;
  controls/mech/AI/software sub-lists now feed the query tier `4055d79`.
  **Measured: mechdesign re-run 35 min later ran 17 query keywords (was 10),
  raw pull 4,274 → 5,079 (+19%), +17 new rows same-afternoon.**
- Config levers (user data): jsearch:true on software+applied-ai (manual runs
  only); `industry` set on software/applied-ai/controls.
- **NEEDS ALEX (~15 min, biggest untapped lever): free key signups —
  CareerOneStop, Brave Search, Jooble, Careerjet, SerpApi** (all wired,
  auto-on once keyed; §4 of the findings doc has links/impact).

## 3. Frontend UI/UX professional pass (Phase C) — `0f36946` + `e0317d1` + `6576912`

Shared `row-actions`/`kbd`/`SelectPrompt`/`statusChipStyle`/`relative-time`/
`friendly-error` components (≈200 duplicated lines removed, 4 tabs each);
score-note label map (no more raw snake_case in the detail pane); Toaster now
follows dark mode; queue single-dismiss aligned to the undo-toast house
pattern; copy fixes (Add-count, "Close — keeps running", resume length hint);
board keyboard reveal; truncation/zg-num consistency. Aegean identity
untouched.

## 4. Backend efficiency pass (Phase D) — `4009932`

`description` stripped from all five LIST payloads (~100-250 KB/page saved;
detail routes unchanged); board N+1 → one batched status_history query;
ghost_score cached (+ review fix: UTC-day in the key so staleness still ages,
`a6b8676`); JobRunner evicts finished jobs (TTL 1h + cap 100, subscriber-
guarded — real leak for a long-lived desktop process); immutable cache headers
for hashed assets, no-cache index.html. **Deferred (needs Alex): get_conn()
per-call connection redesign — highest win, biggest blast radius (S27 pin
interactions); inbox composite index rejected (idx_inbox_company already
covers the partition).**

## 5. Desktop app (Phase E) — YES, shipped

`JobProgram.exe --desktop` (and `py -m webui --desktop`) opens the app in a
native Edge WebView2 window (pywebview 6.2.1) — no browser chrome, own
taskbar entry, closing the window exits; localStorage persists
(private_mode=False) so the theme sticks. Missing pywebview → graceful
browser fallback. Frozen smoke verified: server up, window "Zaggregate",
WebView2 children live. `--web` unchanged. QUICKSTART.md updated. Flipping
the exe DEFAULT from tk to desktop is a one-liner in gui.main — Alex's call.

## 6. Onboarding gate fix (found live)

Legacy projects (dad-health-informatics) re-gated behind the wizard on every
web load — `is_onboarded` now infers from a keyword-carrying config
(`75b1d76`), with a `.wizard-in-progress` sentinel protecting the mid-wizard
AI-paste flow (`a6b8676`).

## 7. Adversarial review wave

3 reviewers + per-finding refuters over the whole day's diff: 5 confirmed
findings, all fixed same-session (see findings doc §4.5). Everything
re-verified green afterwards.

## Needs Alex

1. **Push decision** — big local stack held (this session ~60 commits total).
2. **Free API keys** (§2) — 15 minutes, biggest recall unlock.
3. tk-tab retirement + tk-vs-desktop default; `tracker/app.py` deletion.
4. get_conn() connection-reuse redesign (deferred by design).
5. Eyeball the desktop window: `production/JobProgram/JobProgram.exe --desktop`.

## Next-session queue

Web create-project/new-person flow (still the biggest parity gap) · filter
URL sync · sector source for mech/manufacturing (research first) · periodic
`--discover --discover-enterprise` cadence · description retransmission
follow-ups (list payloads done; detail N+1 acceptable) · MINOR queue in
`brain/findings-2026-07-04-webui-scenarios.md` is now EMPTY (all fixed).
