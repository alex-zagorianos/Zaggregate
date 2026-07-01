# Handoff — Session 26 (2026-07-01, Opus 4.8 / ultracode) — SCALE + ONBOARDING

**Task (Alex):** add anything that improves the **scale of jobs found** (do FIRST); optimize
**onboarding** — a way to build the target-company list for ANY field, either **fed to AI** or
via a **search tool** (assembling dad's company list by hand was slow). Terse. **All free.**
Continues the Session-25 reach buildout.

## What happened

4-agent subsystem map (onboarding flow / acquisition infra / source architecture / agnostic
field mapping) → concise plan → built the new modules via **4 parallel Sonnet worktree builders
(new-files-only)** + **inline Opus** wiring → **6-dimension adversarial review (13 agents,
per-finding verify) found 6 real defects, ALL fixed.** All additive + opt-in; **Alex's
engineering daily run is byte-identical** (verified). **10 commits local (`bcd2290`→`452d00c`),
1111 → 1165 tests green, PUSH HELD** (origin 10 behind).

Read-me-first: `brain/plan-2026-07-01-session26-scale-onboarding.md` (plan) +
`brain/REVIEW-REPORT-2026-07-01-session26.md` (the 6 findings + fixes).

## Shipped (all free, additive, opt-in)

- **BambooHR ATS** (`scrape/bamboohr_scraper.py`) — `{slug}.bamboohr.com/careers/list` JSON;
  dispatch in `careers_client`, host-detect in `ats_detect`/`discover.detect`, fail-soft probe.
  Inert until a `bamboohr` entry exists in `companies.json`. NOT wired into Brave auto-discovery
  (review pulled that — it broke byte-identical for Brave-key users).
- **Socrata/SODA municipal** (`search/socrata_client.py`) — free per-city gov job index,
  `DatasetSpec` per city (NYC seeded). Registered in `cli.ALL_SOURCES`; **NOT in `DAILY_SOURCES`**;
  inert until `config.SOCRATA_CITIES` is set (e.g. `["nyc"]`).
- **Rippling** detection gap filled (scraper existed, no host auto-detect).
- **Inbox→registry harvest** (`discover/inbox_harvest.py`) — employers already seen hiring
  (`tracker.db.inbox_company_counts`) → domain-guess → probe-verify → save. Free, deterministic,
  compounds. Opt-in `daily_run` hook `"harvest_inbox": true` (default OFF). CLI:
  `py -3.12 discover/inbox_harvest.py --dry-run`.
- **`build_company_list.py`** — ONE onboarding command for ANY field: inbox-harvest →
  LLM-enumerate (auto with an API key = "search tool" mode; else prints a copy-paste-to-AI prompt
  = "fed to AI" mode, import the reply with `--in`) → optional dataset seed → classify →
  coverage-until-dry. Field+metro derived from the active project (no Cincinnati/eng default).
- **GUI "✨ Build My List"** (`gui.py` BuildCompanyListDialog) — Search-tab button + wizard nudge.
  Auto / Get-AI-prompt / Load-AI-reply. Thread-safe log sink.

## Review fixes (`452d00c`, all regression-tested)

1. removed bamboohr/rippling from Brave `_ATS_SITES` (auto-discovery scraped+persisted boards
   with no registry entry for a `BRAVE_SEARCH_API_KEY` user → byte-identical break).
2. bamboohr: skip null/soft-deleted rows (one bad row was crashing the whole board).
3. bamboohr probe reuses the scraper's own `_HEADERS` (verify-gate and daily scrape now agree).
4. inbox-harvest: added `tracker.db.inbox_company_display_names()` — counts keys are lowercased,
   was corrupting the saved display name + blocking later cased re-adds.
5. inbox-harvest: dropped the bare-first-word domain guess (could save an unrelated live company
   under the wrong name).
6. `build_company_list`+GUI: `log` callback + thread-safe `self.after` sink replaced a
   process-global `redirect_stdout` that raced with other threads' output.

## Needs Alex

1. **Eyeball `py gui.py`** → Search tab → **Build My List**, then authorize the push (10 commits).
2. Activate when ready: `config.SOCRATA_CITIES = ["nyc"]` (Socrata) and/or `"harvest_inbox": true`
   in the project config (daily harvest).
3. **Certification note:** the new sources widen _raw_ reach but are disjoint slices, so they do
   NOT create the cross-source overlap capture-recapture needs — the reach `%` still requires the
   Google-Jobs proxies (serpapi/jsearch) enabled. Live `eng2` snapshot: 8 families, f2=0 → honest
   "cannot certify %".

## In progress (Session-26 round 2, free-only)

WeWorkRemotely + WorkingNomads free feeds, Socrata city expansion, Reach GUI badge, BambooHR
live-slug validation. (See the round-2 review report when it lands.)

## Env

`py -3.12` (NOT python/uv). Nothing here is fleet-safety; everything additive + reversible; push
held per standing gate. Output mode: terse.
