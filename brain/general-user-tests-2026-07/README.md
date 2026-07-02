# General-User Tests — 2026-07 Corpus Index & Outcomes

This folder is the source-of-truth corpus for the **Session 31** 8-persona general-user readiness
tests and the **Session 32** buildout that acted on them. The historical reports below are
**point-in-time records** — do not rewrite them. This README is the current-status lens: it maps
the S31 headline findings to the S32 fix that landed and the live-smoke evidence that proved it.

**Lineage:** S31 (2026-07-02 overnight) ran the tests and wrote the improvement plan →
S32 (2026-07-02) BUILT the entire plan (3 builder waves + a 20-agent review fleet + 5 fix builders

- live smoke + a probe-verdict follow-up). Full narrative:
  `docs/handoffs/handoff_20260702_session32.md`. Plan: `brain/improvement-plan-2026-07-02-general-user.md`.

---

## What each file is

**8 persona reports** (S31 — blank-slate general users, each ran setup → seed → run → BYO-AI top-10 → tracked lifecycle):

- `persona-swe-newgrad-austin.md` — Jordan Rivera, SWE new grad, Austin TX (48% Adzuna; SE III scored 100).
- `persona-consultant-chicago.md` — Priya Nair, management consulting, Chicago (95% Adzuna; engagement-manager ambiguity).
- `persona-data-changer-phoenix.md` — Nicole Adams, data-analytics career-changer, Phoenix AZ (40-min setup; Workday marquees unreachable).
- `persona-nurse-boise.md` — Maria Santos, RN, Boise ID (76% Adzuna; RNJobSite 244→0 through gate).
- `persona-teacher-columbus.md` — David Chen, 7-12 math teacher, Columbus OH (74% Adzuna; K-12 districts on Frontline/NEOGOV unreachable).
- `persona-mecheng-seattle.md` — Alan Park, mechanical engineer, Seattle WA (81% Adzuna; industry-tag bug hid 8 seeds).
- `persona-warehouse-memphis.md` — Terrence Brooks, warehouse/logistics, Memphis TN (100% Adzuna; careers=0 from the multi-word bug).
- `persona-marketing-remote.md` — Sofia Alvarez, digital marketing, remote-only (0% Adzuna; the only "does not beat manual").

**4 S31 review lenses + the orchestrator note** (code-verifying passes over the persona corpus):

- `review-onboarding.md` — onboarding & time-to-first-value lens.
- `review-coverage.md` — coverage & breadth lens (where jobs come from per vertical/metro).
- `review-ranking.md` — ranking & scoring quality lens (local scorer composite honesty).
- `review-lifecycle.md` — tracking lifecycle & product-surface lens.
- `review-orchestrator.md` — the orchestrating session's independent cross-persona synthesis (10-point blast-radius ranking).

**3 research reports** (S31 web research subagents):

- `research-sources.md` — ToS-safe source expansion for the starving verticals (Workday cxs = headline #1).
- `research-competitors.md` — Zaggregate vs. the 2025-26 job-search tool landscape (own-your-data moat; Kanban/match-hint bets).
- `research-onboarding-ux.md` — onboarding / time-to-value UX patterns (sample data, field presets, motivated keys step).

**Structured data:**

- `_structured-results.json` — machine-readable persona results (setup min, inboxed, Adzuna share, verdict, gaps).

**S32 artifacts:**

- `review-2026-07-02-s32-fleet-findings.md` — the 20-agent review-fleet findings persisted (13 confirmed, 0 refuted, 9 minors) with per-finding fix commit. **NEW this doc-session.**
- `smoke-2026-07-02-post-fix.md` — live blank-slate re-runs proving the buildout widened search (marketing-remote 8→36, P0-1/cxs/REAP machinery, P0-4).

---

## OUTCOMES — S31 finding → S32 fix (merge commit) → live-smoke evidence

Merge commits from `git log 414bb03..HEAD`. Smoke evidence from `smoke-2026-07-02-post-fix.md`.

| S31 finding                                                           | Fix (merge commit)                                                                                                                                                                  | Live-smoke evidence                                                                                                                                                   |
| --------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **P0-1** multi-word `industry` zeroes the careers/registry path       | token-aware `_industry_tag_match` — `11e670b` → `6d017f8` (s32/registry)                                                                                                            | warehouse-memphis: `industry_company_count("warehouse logistics")` **0→15**; all 15 seeds returned to the careers path. Machinery proven.                             |
| **P0-2** CareerOneStop unkeyed & never surfaced                       | `.env.example` keys (`cd8f558`) + wizard keys step (`e843d5a`) + keyless-skip Inbox badge (`5788d26`) → `c3d442f` (s32/onboarding)                                                  | Env still keyless by design; smoke confirms sources self-skip and are now surfaced (reach "cannot certify" shown honestly). Daily source code-ready, unkeyed.         |
| **P0-3 / QW-2 / QW-3** seniority-/country-blind + body-salary scoring | scorer honesty levers (`0d65ca9`) + all-5-caller threading (`fdac6d1`) + regression tests (`bb763e0`) → `b86c3b3` (s32/scoring); **rescore-drift fix `025b0ce` → `80ce359`**        | marketing-remote top rows genuine US-remote; no non-US/non-English surfaced. Country-honesty holding.                                                                 |
| **P0-4** `daily_run --project` flips the global active project        | drop `set_active` on scoped path — `e5f3c20` → `266cb1c` (s32/lifecycle)                                                                                                            | **PASS live** — `active='test-controls'` before/during/after all three smoke runs; never flipped.                                                                     |
| **P0-5** remote-only returns 0 on keyed aggregators                   | Adzuna/USAJobs remote query + national-feed localization — `78defbe` → `75d80a8` (s32/remote)                                                                                       | **Headline win** — marketing-remote **8→36 inboxed (4.5×)**; Adzuna remote **0→114 raw / 32 inboxed**. USAJobs remote query issued (fed remote-only came back empty). |
| **P0-6** `+ Add Companies` saves unreachable/junk boards              | probe-status gates saving+scraping — `5c7864c` → `6d017f8`; **re-verify upgrade path `c2c9589`+`8249683` → `b5e3ba6`**; **walled-vs-empty verdict `b67a85e`+`62f449e` → `f3b07ee`** | warehouse-memphis: 15/15 tenants probed via cxs; verified/walled distinguished after the s32e follow-up.                                                              |
| **P0-7** `tracker.db.update_job` silently drops unknown fields        | UnknownFieldError + round/status coherence — `9641d4b` → `266cb1c` (s32/lifecycle)                                                                                                  | Covered by regression tests (`bb763e0`); no live tracker leak in smoke.                                                                                               |
| **QW-1** broaden wizard field examples                                | validated field-preset picker — `ce57725` → `2e83a2a` (s32b/wizard)                                                                                                                 | Wizard v2 in the GUI (Alex eyeball pending).                                                                                                                          |
| **QW-4** dedup keyless-skip / verify-manually console noise           | warn-once — `a32b242` → `75d80a8`                                                                                                                                                   | Smoke runs clean; dedup'd warnings.                                                                                                                                   |
| **QW-5** file-import re-rank leaves Top Picks empty                   | fit-fallback shortlist — `265d180` → `75d80a8`                                                                                                                                      | Covered by lifecycle fix.                                                                                                                                             |
| **QW-7** market own-your-data + assisted-not-auto                     | positioning copy — `ed95263` → `c7f67e7` (s32b/product)                                                                                                                             | README/Guide positioning landed.                                                                                                                                      |
| **Workday `wday/cxs` unlock** (top coverage bet, SB-1)                | public-JSON fetcher + detection/dispatch/discovery — `e1db6ba`+`1babd2f` → `5762e3e`; migration `0f20b99`                                                                           | cxs live-validated (Terminix 500 jobs, Memphis HQ); CCH 479 + Bon Secours 96 migrated. Cloudflare-fronted tenants (FedEx/AutoZone/etc.) still 422-walled (expected).  |
| **SB-2** Seed-My-Area re-scoped                                       | CareerOneStop Business Finder + seed-my-metro (key-gated) — `e2b1238`+`05c37bb` → `6f87d00` (s32b/seedarea)                                                                         | Built KEY-GATED; awaits a CareerOneStop key + a `COS_BF_FIXTURE` response to confirm mapping.                                                                         |
| **SB-3** browser clip-to-seed                                         | `/clip` receiver + `resolve_board` + ext v1.5 — `272e7ea`+`ce953f3` → `a52a4e7` (s32b/clip)                                                                                         | Ext manifest 1.5 — Alex must reload the unpacked extension.                                                                                                           |
| **SB-4** "Jobs For You" curated-feed framing                          | inbox reframing + forced first action — `9a3d1a9` → `2e83a2a`                                                                                                                       | In wizard v2 / Inbox header.                                                                                                                                          |
| **SB-5** visual Kanban tracker view                                   | Board tab over the tracker DB — `f4a557d` → `c7f67e7`; stage-clock/event `963ebd4` → `ad6a432`                                                                                      | Board tab live (Alex eyeball pending).                                                                                                                                |
| **SB-6** reach badge actionable + local ATS match hint                | actionable reach (`4602bed`) + Jobscan-lite `match/ats_hint.py` (`493c4cc`) → `2e83a2a`/`c7f67e7`                                                                                   | Badge names the missing free key; match hint is local/no-LLM.                                                                                                         |
| **Education feeds** (K-12 coverage roadmap)                           | REAP + EdJoin + Himalayas country=US — `e03265e` → `1a02836` (s32b/education); GUI/MCP REAP threading `23af056` → `b686f40`                                                         | teacher-columbus: **REAP 0→13 raw OH rows** (out-ranked by Adzuna districts into the final inbox); EdJoin graceful 0; HigherEdJobs 4. Feed wired & returning OH data. |
| **BYO-AI setup** (onboarding §3)                                      | `ui/ai_setup.py` module + URL-only seed prompts + MCP `seed_companies` + SOC aliases — `ed3371b`+`bfa5144`+`c5f0b66` → `3f0a1fa`/`8887622`                                          | Set-me-up-with-my-AI express-lane in the wizard.                                                                                                                      |
| **Taxonomy holes** (nursing/marketing/warehouse/education)            | industry_profile breadth + ordering guards — `065626e` → `69ec5f6` (s32/taxonomy)                                                                                                   | marketing SOC bleed killed; warehouse `is_knowledge_work` flipped.                                                                                                    |

### Review-fleet outcomes (the S32 self-audit)

The 20-agent review fleet over the S32 diff surfaced **13 confirmed / 0 refuted / 9 minors** — all real,
all fixed in the s32d/s32e fix wave. See `review-2026-07-02-s32-fleet-findings.md` for the per-finding
map. The critical (rescore drift) and two inert-since-S29 security defects (applog scrubber, CareerOneStop
userId leak) are the notable catches.

---

## Current caveats (carried forward — see the handoff "Needs Alex")

- **SB-1 Workday cxs:** built; Cloudflare-fronted tenants remain walled (compliant capture = extension/browser layer, future decision).
- **SB-2 Leg B + P0-2 daily source:** built/code-ready but **key-gated** — awaiting a CareerOneStop key (then drop a Business Finder response at `COS_BF_FIXTURE`).
- **Cross-board company-canon dedup:** still a design-pass item (Cengage/CCSD city fan-out hit the per-company cap in smoke).
- **Push held** (~196 commits ahead); reload the unpacked extension (manifest 1.5); delete the `gu-*`/`gs-*`/`test-*` browsing projects when done.
