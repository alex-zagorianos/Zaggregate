# Plan — Session 26: Scale + Onboarding company-list builder (2026-07-01, Opus/ultracode)

**Mandate (Alex):** (1) add anything that improves the **scale of jobs found** — do these FIRST; (2) optimize
**onboarding** — a way to build the target-company list for ANY field, either **fed to AI** or via a **search
tool**, because assembling dad's company list by hand was slow. Terse. Agnostic use case.

Grounded in a 4-agent subsystem map (onboarding flow, acquisition infra, source architecture, agnostic field
mapping). Every item is **additive + opt-in; Alex's engineering daily run stays byte-identical.**

## Backbone that already exists (reuse, do not rebuild)

- Field-agnostic **resolve→verify→save** pipeline: `career_link.find_career_url` → `discover/detect.detect_ats`
  → `scrape/ats_detect.probe_count` (live open-job count) → `scrape/company_registry.save_companies`
  (dedup on `(ats_type,slug)`|name). Every acquisition path funnels through this.
- **LLM enumerator** `discover/enumerate.py` + `enumerate_companies.py`: metro+industry → genre-aware angles →
  `{name,domain}` → resolve+probe-verify+save. API mode (`enumerate_via_api`) OR clipboard bridge
  (`--print-prompt`/`--in`) = the two onboarding modes Alex asked for, already built but CLI-only.
- `CompanyEntry(name, ats_type, slug, industries[])` + shared `companies.json`; arbitrary `industries` tag =
  any field supported with zero code change. `tracker.db.inbox_company_counts()` already returns distinct
  employer names seen in results.

## Workstream A — SCALE (build first)

- **A1. Inbox→registry harvest** (`discover/inbox_harvest.py` + CLI + opt-in daily_run post-run hook).
  Real employer names we've _already seen hiring_ (`inbox_company_counts()`) → name→domain guess →
  resolve→probe-verify→save. Free, deterministic, no key, **compounds every run**. Also the onboarding backbone.
  Opt-in (`HARVEST_INBOX` config, default off) → eng run byte-identical.
- **A2. BambooHR ATS scraper** (`scrape/bamboohr_scraper.py`, mirror `recruitee_scraper.fetch(slug,*,keyword)`).
  #1 non-tech reach (~30k SMB: dental/local-mfg/nonprofit/retail). Route through `stealth_fetch` (403 anti-bot),
  inject fetcher for testability. `source_api="careers"`. Wire dispatch + 4 detection layers + lift fixture.
  Inert until a `bamboohr` entry exists in companies.json → eng byte-identical.
- **A3. Socrata/SODA municipal client** (`search/socrata_client.py`, `JobAPIClient`). Searchable per-city gov
  job index (archetypal non-tech local jobs). Config-driven `(city→dataset_id)` map, optional app token,
  free. New `source_api="socrata"`. **NOT in `DAILY_SOURCES` by default** + only active when a city is
  configured → eng byte-identical.
- **A4. Rippling detection gap** — scraper exists but no host auto-detect; add `.rippling.com` to `ats_detect`
  - `discover/detect` + `discoverer` so discovered/pasted Rippling boards are picked up. Small.

## Workstream B — ONBOARDING builder

- **B1. `build_company_list.py` orchestrator** — one command, field+location (derived from the active project
  config, killing the Alex-specific `cincinnati`/eng defaults): chains **inbox-harvest (free)** → **LLM
  enumerate** (auto if API key, else print the paste-to-AI prompt = "fed to AI" mode) → optional dataset seed
  → classify relevance → coverage-until-dry loop signal. The "search tool" Alex asked for = enumerator + inbox
  harvest behind one button.
- **B2. GUI wiring** — replace the wizard's dead `_maybe_offer_discovery` popup (currently only _tells_ the user
  to go run a CLI) with a real "Build My Company List" action (threaded, progress) + a Search-tab button. Code
  only; Alex eyeballs `py gui.py` live.

## Deferred (needs Alex — data/keys, documented not built)

- Bulk **jobhive/OpenJobs seed** (needs the dataset downloaded) — `seed_companies.py` path already exists.
- **Enable serpapi/jsearch in daily runs** to create the cross-source overlap capture-recapture needs (the
  live `eng2` reach snapshot showed f2=0 / disjoint sources → "cannot certify %"). Keys/quota = Alex's call.

## Execution

1. Phase 1 — parallel Sonnet **builders on worktrees**, each a self-contained NEW module + unit tests, **no
   shared-file edits**: A2 bamboohr, A3 socrata, A1 inbox_harvest, B1 orchestrator (clean interface contract so
   B1 composes A1).
2. Phase 2 — **inline (Opus):** all shared wiring (careers dispatch, 4 detection layers for bamboohr+rippling,
   cli `ALL_SOURCES`/`build_clients` + config for socrata, opt-in daily_run harvest hook, GUI B2, lift fixtures).
   Full suite green.
3. Phase 3 — **adversarial review** over the diff (eng byte-identical, new-source correctness, legal/stealth,
   no-key degradation) → fix → finalize. Push held per standing gate.
