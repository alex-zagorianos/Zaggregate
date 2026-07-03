# Handoff — Session 35 (2026-07-03, Fable 5 ultracode) — WEAKNESS SWEEP

## What Alex asked

"Run back through more test cases, try edge cases. Look for flaws and
inefficiencies. Make sure cheap AIs can set up onboarding with ease. The goal is
to get any user access to as many jobs as possible… help as many people as
possible. Think of cases we're weak in."

## How I tested

- **Empirical cheap-AI onboarding**: generated the REAL `build_setup_prompt`, fed it
  - 8 diverse personas (SWE, RN, warehouse/forklift, retail→UX career-changer, UK
    marketing, India data, HVAC trade, thin fresh-grad) to two cheap LOCAL models
    (`granite:micro` 2B = worst case, `gemma4-12b-qat-cc`), and ran EACH model's raw
    reply through the ACTUAL `parse_setup_block`. Plus a deterministic adversarial
    harness (19 setup + 9 seed hand-crafted "plausible but imperfect" inputs).
    Harness + outputs in the session scratchpad (`run_cheapai_setup.py`,
    `adversarial_parse.py`, `cheapai_setup_*.json`).
- **39-finding fleet audit**: 8-dimension find → adversarial-refuter verify Workflow
  (51 Sonnet agents). 43 raised → **39 confirmed / 1 plausible / 3 refuted**. Full
  JSON persisted; disposition in `brain/review-2026-07-03-s35-weakness-sweep.md`.

## Headline finding

The onboarding **parser is robust** — all 8 personas parsed even on a 2B model. The
real defects are model-INDEPENDENT hard-blocks on plausible AI output, and field
mis-categorization that softens on stronger AIs (granite mapped UX→SWE and
HVAC→engineering; gemma-12b got both right and inferred remote). So the fix target
was the hard-blocks + the source/geo routing, not the models.

## Fixed (5 commits on master, ~50 new tests, suite 2311 → 2360, 0 failed — PUSH HELD)

- `65454d0` onboarding parser: salary shorthand ("140k"/"$120k per year"/ranges),
  radius "25 miles", seniority aliases (director/VP/C-level/CEO/intern/associate),
  comma-string titles split, smart-quote + `//` comment tolerance, two-fence
  best-object selection, **O\*NET-resolved trades accepted as fields** (machinist,
  barista, welder — pure-typo `generic` still rejected), prompt guidance improved.
- `4aaf9d5` international: **Adzuna routes to the user's country** via the existing
  `config.adzuna_country_for` (London→/gb/, Bangalore→/in/; US byte-identical,
  Indianapolis "IN" ≠ India); **metro_variants** adds the bare city token for non-US
  metros so a "London"/"London, England" posting classifies LOCAL (was hidden as
  'elsewhere' in the default Inbox view). Guarded on no-CBSA-match → US byte-identical.
- `d19c9f6` receiver: **/track dedup** (`tracker.db.url_is_tracked` — 'Track All'
  twice no longer duplicates; response gains `skipped`; popup shows "All N already
  tracked"), /clip no longer 500s on non-string url/title, `MAX_CONTENT_LENGTH = 8 MB`.
- `24605fb` generic_capture: JSON-LD scan bounded (≤40 blocks, skip >1 MB).

## Deferred — needs Alex's approval (CLAUDE.md byte-identical scoring/filter rule)

These change which jobs survive/rank for Alex's own eng daily run, so I did NOT
touch them. Each is one-shot approve-and-apply:

- **#7** `hard_gate` title blocklist is plain substring → a blocker "sales" drops
  "Salesforce Engineer", "it" drops "Editor". Fix: word-boundary `\b…\b`.
- **#28** `_EXEC_RE` fires on IC titles containing "manager" → wrong senior rubric.
- **#37/#38** SOC penalty-exemption + skill-overlap abstain gaps.

## Deferred — design/data (bigger; the real "help more people" levers)

- **#4 (biggest)** the shipped starter registry has ZERO blue-collar/service
  employers — only tech/health/defense. Curating warehouse/healthcare/retail/trades
  boards per metro is the highest-impact next build; needs Alex's steer on sectors.
- **#15** discovery ATS hosts omit UKG/Paycom/Ceridian/iCIMS (non-tech platforms).
- **Silent failures #5/#6/#22/#23** — sources failing quietly (swallowed RSS errors +
  empty-cache, unsurfaced CareersClient/Brave failures, no build_clients top-guard).
- **Zero-key transparency #18** — the "source skipped, needs key" signal is wired on
  only 1 of 3 entry points.
- **Inefficiencies #24/#25/#26/#36** (per-keyword registry re-walks, Brave re-fires).

## Safe quick-wins queued (no approval needed, byte-identical for Alex)

#23 build_clients per-source guard · #26 harvest negative-cache · #30 careerjet/jooble
country param · #36 cache-GC-on-abort. Batch these on request.

## State

- master = `24605fb` (5 S35 commits ahead of pushed `6be40b9`). PUSH HELD.
- Suite 2360 passed / 0 failed. graphify self-maintains via post-commit watcher.
- Old worktree `ZAG0005-wt-12b-qat-t2f` still present (pre-existing).

## Needs Alex

1. Approve/decline the scoring/filter fixes (#7, #28, #37, #38).
2. Steer the blue-collar registry build (#4) — which sectors/metros first.
3. Say "push" when ready (5 commits held).
4. (Carried) reload extension, re-clip edisonsmart, delete pre-fix junk tracker rows,
   CareerOneStop key, experience.md PII-history decision.
