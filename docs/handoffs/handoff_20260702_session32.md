# Handoff — Session 32 (2026-07-02, Fable 5 orchestrating Opus fleet) — FULL IMPROVEMENT-PLAN ROLLOUT

Alex: "start rolling out fixes/changes/improvements using opus subagents — anything
that increases search breadth/quality is a yes"; then "once all agents land, send
more out, keep going until all changes are made and reviewed." This session built
the ENTIRE S31 improvement plan (`brain/improvement-plan-2026-07-02-general-user.md`)
in three builder waves + a review-fix wave + live smoke. **19 Opus builders + a
20-agent review fleet + smoke agent. Suite 1744 → 2176+ green. PUSH STILL HELD.**

## Wave 1 (7 builders, all merged): the P0s

- **P0-1** token-aware industry matching (`_normalize_industry`, whole-token rules)
  — fixes multi-word zero AND wrong-vertical bleed. **P0-6** probe-gated Add
  Companies (unverified flag + exclusion from scraping).
- **P0-3/QW-2/QW-3** scoring honesty: facts.py seniority wired into score+gate
  (gated on seniority_target/years_cap), country-aware remote credit
  (remote_regions_ok escape), body-salary floor, Adzuna label distrust,
  title_context_required opt-in cap.
- **P0-5** Adzuna/USAJobs remote queries (live: 0 → 50 rows) + RNJobSite/HigherEd
  national-feed localization via new `search/remote_intent.py`.
- **Workday `wday/cxs` public-JSON fetcher** (`scrape/workday_cxs_scraper.py`) —
  live-validated (Marsh McLennan/Caterpillar/NVIDIA); Cloudflare-fronted tenants
  (FedEx, Banner...) still 422 → fail-soft; detection type `workday_cxs`.
- Taxonomy: marketing (kills Hydroelectric SOC bleed), nursing, warehouse
  (is_knowledge_work flip), education entries + ordering guards.
- **P0-4** daily_run --project no longer flips global active; **P0-7**
  UnknownFieldError; Top Picks fit-fallback; round/status coherence; warn_once.
- **P0-2** wizard keys step + .env.example keys + keyless-skip badge in Inbox.

## Wave 2 (6 builders, all merged): onboarding + strategic bets

- **Wizard v2**: field-preset picker (canonical tokens), bundled DEMO sample inbox
  (retired on first real run), "Update my Inbox now" terminal action, keys-step
  deep-links/paste-detect/inline-test, actionable reach badge, "Jobs For You" framing.
- **ui/ai_setup.py**: BYO-AI "set me up with my AI" prompt+strict parser (canonical
  config block), shared preferences scaffold in create_project, careers-URL-only
  seed prompts, MCP `seed_companies`, curated SOC aliases (exact-only).
- **Seed-My-Area Leg B**: CareerOneStop Business Finder client + seed_my_metro
  pipeline + Tools dialog — KEY-GATED (endpoint provisional; `COS_BF_FIXTURE`
  verify-once toggle when Alex gets a key).
- **Education**: REAP (robots-honored; TLS intermediate bundled properly) + EdJoin
  (site's own JSON endpoint; CA-centric graceful) + Himalayas `search?country=US`
  (region-locked 9/20 → 0/20) + no-Jooble-forwarding ToS guard.
- **Product**: Kanban "Board" tab (service-driven, no-downgrade), local ATS match
  hint (`match/ats_hint.py`, no LLM/network), README/Guide positioning (QW-7).
- **Browser clip-to-seed**: `/clip` receiver endpoint + `resolve_board` + ext v1.5
  ("Add this employer's board to my registry", verified-at-clip). **Alex must
  reload the unpacked extension** (manifest 1.5, new tabs permission).

## Wave 3 + registry migration

- Wizard ↔ AI-setup express-lane (optional early step, prefills, zero-AI path
  intact); `scripts/migrate_workday_cxs.py` (dry-run default); copy/env sweep.
- **Migration APPLIED**: Cincinnati Children's (479 jobs) + Bon Secours (96) —
  the two legacy workday registry rows now pull live via cxs (Dad's verticals).

## Review fleet → fix wave (all merged)

7 dimensions → 22 crit/major findings verified adversarially → **13 CONFIRMED,
0 refuted** → 5 fix builders:

- **CRITICAL: rescore drift** — daily_run's end-of-run rescore erased all four new
  scoring levers (S24-class drift; parity test was structurally blind). Fixed +
  lever-tripping parity test.
- Salary gate: bonus/commission figures no longer parsed as comp. Label distrust:
  bare-city body mention = confirmation.
- REAP was inert from GUI/MCP (location never threaded) — fixed. National-feed
  filter now state-aware ('Columbus, GA' can't pass an OH filter; suburbs kept).
  Adzuna remote tag survives cache hits. EdJoin de-spoofed (honest UA verified
  live) + robots fail-closed.
- **applog secret-scrubber was INERT since S29** (wrong-arity resolve_secret,
  TypeError swallowed) — armed + CareerOneStop userId path redaction + source
  re-raise + end-to-end leak tests.
- Registry: re-verify now UPGRADES unverified boards (was permanent lockout);
  ToS-blocked-host guard on programmatic seed paths; save_companies write lock.
- GUI: new-person wizard closing step honored; demo rows blocked from AI export;
  modal sequencing; Kanban stage-clock + live cross-tab refresh; Guide copy sync.

## Live smoke (blank slates, post-fix; report: `brain/general-user-tests-2026-07/smoke-2026-07-02-post-fix.md`)

- **marketing-remote: 8 → 36 inboxed (4.5×), Adzuna remote 0 → 114 raw/32 inboxed**
  — the unambiguous P0-5 win.
- warehouse-memphis: machinery PROVEN (industry match 0→15 seeds; 15/15 tenants
  probed via cxs; Terminix live 500 jobs) but inbox mix unchanged — marquee tenants
  Cloudflare-walled (expected), Terminix has no warehouse titles. Honest partial.
- teacher-columbus: REAP 0 → 13 raw OH rows (out-ranked by Adzuna's district rows
  this run); EdJoin graceful 0.
- **P0-4 verified live** (active project never flipped). Registry restored
  byte-exact; `gs-*` smoke projects kept for browsing.
- Follow-up defect found + fixed in a final builder: workday_cxs 422-walled tenants
  were saving as "verified-empty" — probe verdict now distinguishes walled
  (unreachable/unverified) from live-but-0 (verified).

## State

- Master ≈195 ahead of origin, **PUSH HELD**, tree clean, suite 2176+ green
  (exact final count in the finalize commit).
- Registry: shipped + 2 migrated workday_cxs rows; all test seeding restored away.
- Projects kept for browsing: 8 `gu-*` (S31), 3 `gs-*` (smoke), `test-controls`
  (active), `test-dad-health`. Delete when done.
- Worktrees pruned (only the pre-existing `ZAG0005-wt-12b-qat-t2f` remains).

## Needs Alex

1. **Eyeball `py gui.py`** — the UI grew: wizard (AI express-lane, presets, keys
   step, demo inbox), Board tab, Jobs For You header, badges, Tools items
   (AI setup / Seed my area). Then the **push decision** (~195 commits; experience.md
   PII history question still open from S29).
2. **Reload the unpacked browser extension** (manifest 1.5).
3. **CareerOneStop key** — unlocks the daily source AND Seed-My-Area Leg B
   (drop one real Business Finder response at `COS_BF_FIXTURE` to confirm mapping).
4. Cloudflare-walled Workday marquees (FedEx/Banner/etc.): only compliant paths are
   the extension capture or a real browser layer — future decision.
5. Cross-board company-canon dedup design (Cengage/CCSD fan-out reconfirmed it).
6. Delete test projects when done browsing.
