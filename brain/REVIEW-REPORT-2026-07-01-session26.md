# Session 26 — Scale + Onboarding: adversarial review (2026-07-01, Opus/ultracode)

Diff reviewed: `8a1b294..fdcdc6f` (4 builder merges + integration). A 6-dimension review
workflow (13 agents, per-finding adversarial verification, all Sonnet) surfaced **7
confirmed findings (0 dismissed)** — 6 distinct defects (the discoverer issue was caught
independently by two dimensions). All were in this session's new code; all `major`; all
fixed + regression-tested. Full suite green after fixes.

## Findings + fixes

1. **Byte-identical break via Brave auto-discovery** (`scrape/discoverer.py`) — adding
   `bamboohr`/`rippling` to `_ATS_SITES` meant any user with `BRAVE_SEARCH_API_KEY` set
   would, on a normal daily `careers` run, start discovering→scraping→persisting new
   BambooHR/Rippling boards with **no companies.json entry** — a behavior change against
   the "inert until a registry entry exists" invariant (Alex himself has no Brave key, so
   his run was unaffected, but the invariant was violated for the general/future case).
   **Fix:** removed both from `_ATS_SITES` (kept detection in `ats_detect`/`discover.detect`
   so pasted URLs + inbox-harvest still resolve them — the intended reach path). _(Found by
   both `byte-identical` and `integration` dimensions.)_

2. **BambooHR: one malformed row crashed the whole board** (`scrape/bamboohr_scraper.py`) —
   the per-job loop sat outside the fetch/parse try/except, so a `null`/soft-deleted entry
   in `result[]` raised `AttributeError`, and the caller's generic guard then discarded
   _all_ of that board's jobs (contradicting the module's "never raise → []" contract).
   **Fix:** skip non-dict entries in the loop. (Same latent pattern exists in the sibling
   workable/recruitee/rippling/personio scrapers — pre-existing, noted not fixed.)

3. **Probe/scrape User-Agent mismatch** (`scrape/ats_detect.py` `probe_count`) — the
   BambooHR verify-gate sent `Mozilla/5.0` while the production scraper sends
   `JobSearchTool/1.0 (personal use)` to the _same_ endpoint, so a board could verify at
   onboarding then behave differently on every real run. **Fix:** `probe_count` now imports
   and reuses the scraper's own `_HEADERS` — what verifies is what scrapes.

4. **Inbox harvest lowercased the saved company name** (`discover/inbox_harvest.py`) —
   `tracker.db.inbox_company_counts()` returns **lowercased** keys, which flowed straight
   into `CompanyEntry.name`, permanently corrupting the display name (GUI/resume/tracker)
   and, because `save_companies` dedups by `name.lower()`, blocking any later correctly-cased
   add. **Fix:** added `tracker.db.inbox_company_display_names()` (lowercased→original-cased)
   and the harvester now saves the cased spelling.

5. **Inbox harvest could save an unrelated company** (`discover/inbox_harvest.py`) —
   `_domain_guesses` shortened a multi-word name to its bare first word (`"Apex Controls"`
   → `apex.com`); the probe gate only checks a board is _live_, not that it's the _same_
   employer, so a common-word domain owned by an unrelated live company would be saved under
   the wrong name. **Fix:** dropped the bare-first-word guess for multi-word names (keep the
   specific full-token guesses like `apexcontrols.*`); anything missed is left to the LLM
   path.

6. **GUI `redirect_stdout` race** (`gui.py` `BuildCompanyListDialog`) — the worker wrapped
   the orchestrator in `contextlib.redirect_stdout` (process-global) for the whole 1–2 min
   run; an in-flight Search thread's `print()` output would be captured into the Build
   dialog's log (or vanish from a console). **Fix:** gave `build_company_list()` a `log`
   callback (each stage rebinds `print` locally to it); the GUI passes a thread-safe
   `self.after`-based sink — no global stdout mutation. CLI unchanged (`log` defaults to
   `print`).

## Not changed (deliberate)

- Sibling scrapers' identical per-job-loop pattern (finding 2) — pre-existing, out of scope.
- Rippling/BambooHR still fully usable via paste (Add Companies) + inbox-harvest + LLM
  enumerate; only the _Brave auto-discovery_ wiring was pulled (finding 1) to honor
  byte-identical.

Tests added: bamboohr malformed-entry skip; inbox display-casing preserved; inbox
first-word-guess dropped. Suite: 1163 → (see commit) passed.
