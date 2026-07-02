# Handoff — Session 19 (2026-06-25, cheap-backend, ultracode) — company-acquisition pipeline + remote-first-class

> Research → plan → build. Started by researching how LinkedIn/Indeed data is
> acquired and how jobs are actually found (6-angle web workflow + adversarial
> fact-check), which concluded **the company registry is the binding coverage
> constraint** and LinkedIn/Indeed are mostly ATS syndication. Then planned (plan
> mode, approved) and built a 4-phase pipeline to grow a Cincinnati-metro company
> DB + make remote first-class. **ALL COMMITTED LOCAL, push still HELD.** TERSE.

## TL;DR

- master → **+5 build commits** (now **37 ahead** of origin), tree clean.
  **Suite 696 → 725** (`py -m pytest -q`; 1 display-gated skip). Plan file:
  `~/.claude/plans/shimmering-moseying-wadler.md`.
- Pre-push adversarial review (1 agent over the 4-phase diff): **no real bugs**;
  one minor refinement applied (cold-tier activation).

## Why (research finding)

For JobScout's segment, LinkedIn/Indeed are **syndication layers on top of the
ATS** (Greenhouse Limited Listings / Indeed XML feeds are fed FROM the ATS), so a
comprehensive local **company-careers/ATS registry captures the canonical posting
— often earlier**, and skipping the boards costs little for tech-forward roles.
The "80% hidden / 85% networking" stats are debunked folklore; measured ATS data
(Ashby) says inbound/posted applications dominate tech hires. The residual gap is
the no-ATS SMB/industrial/agency tail (Indeed-only) — that's what the browser
extension supplements. Two refinements drove the build: (1) Cincinnati industrials
run Workday/iCIMS/Taleo (under-covered); (2) remote was unfairly scored.

## What shipped (4 phases)

| Phase                      | Commit                | What                                                                                                                                                                                                                                                                                                                                 |
| -------------------------- | --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **1 — remote first-class** | `dbcc793`             | `_location_score(…, remote_ok)`: an acceptable-remote role gets full location credit (was 0, capping remote at 85/100). Threaded `remote_ok` through `score_job`/`score_jobs`; sourced from `preferences.json` at daily_run / browser_receiver / GUI search. (Remote feeds were already enabled.)                                    |
| **2 — metro enumeration**  | `67cd176`             | `discover/enumerate.py` (LLM proposes {name,domain}; Bridge/Api duality like `ranker`) + `enumerate_companies.py` (enumerate → resolve via `career_link`+`detect_ats` → **probe-verify gate** → `save_companies`). The probe gate makes LLM enumeration safe — hallucinated/dead companies resolve to no live board and are dropped. |
| **3 — enterprise-ATS**     | `c520849`             | Workday public-URL → `tenant:N:site` (already worked; tested). iCIMS/Taleo/SuccessFactors: detect by host, route to the existing `jsonld_scraper` (their pages carry JobPosting JSON-LD), `probe_count` JSON-LD branch so enumeration can vet them. Lightweight — no bespoke fragile scrapers.                                       |
| **4 — tiered scheduling**  | `e5375d6` + `111bd84` | `scrape/tiering.py` (pure: hot=daily/warm=weekly/cold=monthly; never starves an active board). `CareersClient` opt-in `tiered` (default OFF → identical behavior); `daily_run` opt-in via `tiered_scrape` config. Keeps a big registry fast.                                                                                         |

**Reused ~70%:** `discover/funnel` + `career_link` + `detect_ats`, `verify_and_add`
probe pattern, `scrape/company_registry.save_companies`, `coverage/` benchmark +
lift-gate, `geo/filter` + `coverage/geography.metro_variants`, `ranker` key/SDK
pattern + `claude_bridge._extract_json`, `FileCache`/`RateLimiter`/ThreadPool.

## Deviations from the plan (justified)

- **No hardcoded Cincinnati seed list.** Guessing Workday/iCIMS slugs risks dead
  entries — the exact pollution the verify gate prevents. `enumerate_companies.py`
  now discovers them correctly via the new detection instead.
- **Skipped adding `arbeitnow`** to project sources (EU-heavy → noise the metro
  filter culls); the 4 remote feeds already enabled + the scoring fix are the
  substantive remote change.

## How to use it (Alex)

1. **Enumerate Cincinnati companies** (the high-leverage move): `py
enumerate_companies.py --metro Cincinnati --industries controls,software,applied-ai,mechanical --dry-run`
   to preview. With an Anthropic key it runs automatically; without one,
   `--print-prompt` → paste into claude.ai → `--in reply.json`. Drop `--dry-run`
   to write verified adds to `companies.json`.
2. **Remote** is now scored fairly — set `remote_ok` in `preferences.json` (default
   true); a strict-local user sets it false.
3. **Tiered scrape** (only when the registry gets large): set `"tiered_scrape": true`
   in the project config; the daily run then scrapes only due boards.

## Needs Alex (unchanged + new)

- Eyeball `py gui.py` (light+dark from S18) → **push the 37 local commits**.
- Reload the unpacked extension (S18 manifest 1.3); live `selector_check.js`.
- Run the enumeration on Cincinnati to actually grow the registry (decision/data).

## Open minor (noted, not blocking)

- Location-_sort_ tiebreak (`sort_by="location"`) uses `remote_ok=True` hardcoded,
  so a strict-local user sorting by location sees remote first. Inbox **scoring**
  honors prefs correctly; only the CLI/search sort tiebreak doesn't. Low value.

## Pointers

- Brain: `brain/project-status.md` §"Session 19". Memory: `project-job-search`.
- Research output is in the workflow transcript; key sources cited in the brain.
