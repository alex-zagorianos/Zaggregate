# S35 — Weakness sweep (edge cases, cheap-AI onboarding, coverage gaps)

**Date:** 2026-07-03 · **Model:** Fable 5 (ultracode) · **Baseline:** `6be40b9`, 2311 green
**Goal (Alex):** "get any user access to as many jobs as possible… work for a wide
range of companies and people… make sure cheap AIs can set up onboarding with ease…
find cases we're weak in."

## How it was tested

1. **Empirical cheap-AI onboarding** — fed the REAL `build_setup_prompt` + 8 diverse
   personas (SWE, nurse, warehouse, career-changer, UK, India, HVAC trade, fresh grad)
   to two local cheap models (granite:micro 2B worst-case, gemma-12b), then ran each
   model's raw reply through the ACTUAL `parse_setup_block` validator. Plus a
   deterministic adversarial-format harness (19 setup + 9 seed inputs).
2. **39-finding fleet audit** — 8-dimension find → adversarial-refuter verify workflow
   (51 Sonnet agents; onboarding-parser, international, non-tech, zero-key, receiver,
   silent-failures, inefficiency, matching-bias). 43 raised → **39 confirmed, 3 refuted**.

## Key empirical result

The **parser is robust** (all 8 personas parsed even on a 2B model). The real defects
are model-INDEPENDENT: hard-blocks on plausible value formats, and field-quality drift
that softens on stronger AIs (granite mis-mapped UX→SWE and HVAC→engineering; gemma-12b
got both right + inferred remote). So the fix target = the hard-blocks, not the models.

---

## FIXED this session (5 commits, ~50 regression tests, suite 2360 green — PUSH HELD)

### `65454d0` — cheap-AI onboarding parser hardening (the bullseye)

- **salary**: `"140k"`, `"$120,000 per year"`, ranges, `"1.4m"` now coerce (were hard-blocks)
- **radius**: `"25 miles"` coerces
- **seniority**: director/VP/C-level/CEO/intern/associate/… alias to the 4 tokens
- **titles**: a comma-joined STRING splits into separate searchable titles
- **smart/curly quotes** normalized + `//` `/* */` comments stripped before JSON parse
- **two fenced blocks** → picks the most-complete object (was: grabbed the partial one)
- **O\*NET trades** (machinist, barista, welder) accepted as fields; only pure-typo
  `generic` (quantum astrology) still rejects
- setup prompt now says "use other if unsure", allows "City, Country", numbers-only salary

### `4aaf9d5` — international breadth

- **Adzuna** now routes to the user's country (`London,UK`→/gb/, `Bangalore,India`→/in/);
  was always /us/. No-op for US (Indianapolis, IN stays 'us' — no India collision).
- **metro_variants** adds the bare city for non-US metros so "London"/"London, England"
  classifies LOCAL for a "London, United Kingdom" user (was hidden as 'elsewhere' in the
  default Inbox view). Guarded on no-CBSA-match → US metros byte-identical.

### `d19c9f6` — browser receiver hardening

- **/track dedup** (new `tracker.db.url_is_tracked`): 'Track All' twice no longer
  duplicates rows; response gains `skipped`; popup shows "All N already tracked"
- **/clip** no longer 500s on a non-string url/page_title (coerce to str)
- **MAX_CONTENT_LENGTH = 8 MB** caps runaway/oversized POSTs

### `24605fb` — generic_capture JSON-LD scan bounded (≤40 blocks, skip >1 MB)

---

## ALEX'S DECISIONS (same day, after the report)

> "I don't want anything to get over dropped, I want as much as possible, let the
> users drop jobs but mark this down as a known issue, and the design philosophy is
> to get as many potential jobs in front of the users. That being said we don't want
> to waste users time by showing completely unrelated jobs. Lets wait on blue collar
> but lets keep building out the seeded company list for a different session."

Applied: **#7 FIXED** (`78fbc67` — word-boundary blockers; over-DROPS approved).
Philosophy codified in CLAUDE.md (Design philosophy) + new `docs/KNOWN_ISSUES.md`.
**#28/#37/#38 stay held** — they are RANKING accuracy, not drops (jobs still shown);
listed in KNOWN_ISSUES. **#4 blue-collar: wait**; seeded-company-list buildout is a
planned FUTURE SESSION. Also fixed same batch: a pre-existing wall-clock time-bomb
test (`3ac80fa` — hardcoded created-date crossed a recency-rounding boundary today).
Suite 2363 green.

## Held ranking refinements (not drops — see KNOWN_ISSUES)

| #   | Finding                                                                                                     | File                    | Recommended fix                      |
| --- | ----------------------------------------------------------------------------------------------------------- | ----------------------- | ------------------------------------ |
| 28  | `_EXEC_RE` fires on IC titles containing "manager" (e.g. "Manager of one product") → flips rubric to senior | match/rubric.py:27      | tighten regex / require exec context |
| 37  | SOC penalty-role exemption only covers sales+maintenance, not other blue-collar SOCs                        | industry_profile.py:250 | broaden exemption set                |
| 38  | Skill-overlap component abstains to neutral for a thin résumé → dilutes title signal                        | match/scorer.py:346     | weight-shift when skills absent      |

## DEFERRED — coverage/data & resilience (bigger or needs direction)

**Non-tech / blue-collar breadth (the biggest "help more people" lever):**

- **#4** shipped starter registry has ZERO blue-collar/service employers (only tech/health/defense). Curating warehouse/healthcare/retail/trades employer boards per metro is the highest-impact next build — needs Alex's steer on target sectors/regions.
- **#15** discovery ATS hosts omit UKG/Kronos, Paycom, Ceridian/Dayforce, iCIMS, Iac — the platforms non-tech employers use. **#31/#17** SOC routing + sector feeds thin for protective/farming/production.

**International:** **#12** US-only sources (USAJobs, CareerOneStop, REAP, EdJoin) still register + burn time for non-US users; **#13** jobs.ac.uk not in DAILY_SOURCES; **#30** careerjet/jooble pass no country param (same class as the Adzuna fix — safe to do, wanted live-API check first).

**Resilience / silent failures (users lose jobs without knowing):** **#5** sector-feed RSS parse errors swallowed AND the empty result cached; **#6** per-company CareersClient failures never reach the run health summary; **#22** Brave discovery key/429 failures unsurfaced; **#23** `build_clients` has no top-level guard — one client's non-ValueError ctor exception aborts the whole run (safe quick win: per-source try/except).

**Zero-key transparency:** **#18/#32/#19** the "which sources skipped for lack of a key" signal is wired on only 1 of 3 entry points; a zero-key user can't tell "no key" from "ran, found nothing."

**Inefficiency:** **#24** CareersClient re-walks the whole registry once per keyword; **#25** Brave re-fires 5 site: queries per keyword daily; **#26** harvest has no negative-cache (re-probes never-resolving names); **#36** cache GC only runs at end of a clean run.

## REFUTED (3) — not real

- run_funnel "never invoked by daily_run" (it is, via a different path)
- "no test exercises keyless-skip wiring" (build_clients test does)
- storeCapturedJob "dedup compares url to itself" (typo claim — compares correctly)

## Safe quick-wins available next (no Alex approval needed, byte-identical for his run)

#23 build_clients per-source guard · #26 harvest negative-cache · #30 careerjet/jooble
country param · #36 cache-GC on abort. Say the word and I'll batch these.
