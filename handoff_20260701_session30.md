# Handoff — Session 30 (2026-07-01, Fable 5 + Opus subagent) — LIVE TEST RUNS + SETUP DEPTH

Same-day continuation after the S29 finalization. Theme: prove the S29 overhaul on
live blank-canvas runs, fix what the runs caught, deepen onboarding, and note (not
build) the AI-assisted seeding plan.

## 1. Live blank-canvas test runs (Alex controls + Dad health-informatics)

Method: cloned both real profiles into fresh test projects (`test-controls`,
`test-dad-health`) — empty tracker.db, fresh freshness baselines, SHARED seeded
companies.json — ran `daily_run.py --project <slug>` sequentially, then AI-re-ranked
(me = the BYO-AI) and delivered a top 10 for each in chat.

- **Controls:** 4,007 raw -> 2,114 dedup -> 1,162 >=40 -> **685 inboxed** (~11 min).
  Caps worked (Anduril 183 / SpaceX 142 / Caterpillar 43 capped). Top 10 headliners:
  Standard Bots firmware/controls, anysignal embedded motor control, ACS motor/motion,
  Cleaning Technologies Group (Cincinnati local), Oklo mechatronics (remote-ok),
  Jobot custom-machinery design Cincinnati $100-120k.
- **Dad:** 2,596 raw -> 1,541 dedup -> hard-gate cut 1,209 (1,179 location) -> 332 ->
  **19 inboxed** (~1 min warm cache). Supply-bound as S27 found, not a pipeline bug.
  Seeds delivered: Bon Secours ~66 matches, Cincinnati Children's ~22, TriHealth 10,
  UC Health 1. Top 10 headliners: GAI AVP/VP Enterprise Analytics (local), Arcadia
  Director Analytics (remote), TriHealth Epic/pop-health manager (local, found BOTH
  via Adzuna and the seeded Oracle board).
- **Source-mix measurement (the reliance question):** controls inbox = 85% careers /
  14% adzuna / ~1% keyless feeds; dad = 58% careers / 37% adzuna. Keyless
  out-of-box tier contributed ZERO top-10 slots. companies.json SHIPS as the starter
  registry (build_package + userdata.bootstrap), so registry wins reach any user —
  but its local-employer layer is Cincinnati-shaped; Adzuna (free key) carried every
  non-seeded local win. CareerOneStop = the general-user equalizer, still unkeyed.
- Test projects KEPT for eyeballing (GUI active = `test-controls`); real projects
  untouched. Delete `projects/test-controls` + `projects/test-dad-health` + their
  registry entries whenever done.

## 2. Fixes the runs caught (commit `5911855`, suite 1734 green)

1. **FileCache Windows filename bug:** jobicy cache key `feed:engineering` — ':' is
   an NTFS ADS marker -> os.replace WinError 87 -> the feed ran UNCACHED forever on
   Windows. FileCache now sanitizes `<>:"/\|?*` in keys; 3 regression tests.
2. **Oracle ORC display name:** TriHealth rows showed company "Fa Evly Saasfaprod1"
   (tenant host slug). Mirrored the ADP fix — registry display name threaded through
   fetch/_map + dispatch.
3. **freshness log** mixed counts ("1162 of 685 newly-inboxed") — n_new is over
   qualified, added is post-cap; message now reports both honestly.

**OPEN (needs a design decision):** same req double-lists when company display names
differ across boards — "Allen Control Systems" (Ashby) vs "allencontrolsystems"
(Greenhouse); TriHealth (Adzuna) vs the Oracle board row. company_canon differs ->
job_key never collides. Fix = company-name canonicalization/aliasing in job_key;
small design pass first (dedup was reviewed hard in S29; don't hot-patch it).

## 3. Setup depth (commit `2a14f55`)

- **In-app Guide** (`ui/help.py`): new "Set up your sources — the 10 minutes that
  matters most" section — the two keys that matter (Adzuna, CareerOneStop) with the
  measured why, remaining key tier (Jooble/Careerjet/USAJobs/SerpApi reach badge),
  **local-employer seeding via Add Companies including the ask-your-own-AI flow**
  (works today: AI generates "Name | link" lines, paste, probe verifies, junk fails
  harmlessly), industry-answer importance, daily scheduler. Plus AI-on-setup-duty
  bullet, local Anthropic-compatible endpoint note, honest pay FAQ. Guide test pins it.
- **HELD plan** (Alex: build later): `brain/plan-2026-07-01-ai-assisted-setup-seeding.md`
  — "Seed My Area": Leg A = BYO-AI clipboard seeding (prompt generator -> existing
  parse/probe pipeline -> MCP `seed_companies` twin); Leg B = CareerOneStop Business
  Finder API (free employer directory, same key) -> zero-AI seed-my-metro button;
  TheirStack paid option; persona follow-ups. K-12 ATS (Frontline) = illustrative
  example only, backlog. Success metric: non-Cincinnati persona seeds a verified
  local registry in <20 min unassisted.

## 4. Breadth (Opus subagent; commit `58e3202`, suite 1744 green)

- **Consulting taxonomy entry** in industry_profile._RULES (was falling through to
  generic O*NET): triggers consulting/consultant/advisory/strategy-consulting; placed
  before operations/management so "management consulting" routes here; bare
  "strategy"/"management" behavior unchanged; knowledge-work gating verified. +3 tests.
- **SmartRecruiters:** fetcher ALREADY EXISTED and was wired (my "no fetcher" claim
  was stale — it does capped per-match detail fetches, max 15). Subagent live-validated
  read-only (visa + mcdonaldscorporation; public URL form
  `jobs.smartrecruiters.com/{slug}/{id}` confirmed 200; end-to-end JobResults with
  registry display name) and added 6 tests over the thin prior coverage.

## State

- Suite **1744 passed / 1 skipped**. Master = `58e3202` + this handoff commit,
  **~115 ahead of origin, PUSH STILL HELD**, tree clean.
- GUI closed; registry active project = `test-controls`.

## Needs Alex

1. **Push decision** (~115 commits; README/CI exist; experience.md PII history
   question still open from S29).
2. **Free key signups** (biggest reach unlock, now documented in-app): CareerOneStop
   > Adzuna-already-keyed > Jooble/Careerjet; SerpApi for the reach badge.
3. **Dedup canonicalization** design go/no-go (item 2 OPEN above).
4. Browse the test inboxes; delete the two test projects when done.
5. Seed-My-Area build go-ahead when wanted (plan doc has the build order).
