# Handoff — Session 31 (2026-07-02 overnight, Fable 5 orchestrating Opus fleet) — REPO REORG + 8-PERSONA GENERAL-USER TESTS + IMPROVEMENT PLAN

Alex's overnight directive: Opus subagent cleans up the folder structure; then deep
blank-slate testing for ~5-10 GENERAL users (only what ships) through find→track→
completion; review issues/breadth/inefficiencies + how easy setup-to-real-use is;
then research improvements. Orchestrator (me) only orchestrates/reviews/plans.
**No app code was changed — all fixes are held for Alex's approval.**

## 1. Repo reorg (commit `ecddfa7`)

Opus agent moved 27 root handoffs → `docs/handoffs/`, kickoff prompt → `docs/`,
5 one-off scripts → `scripts/` (sys.path bootstraps fixed), legacy artifacts
(`_trim_inbox.py`, `run_dad.bat`, `config_dad.json`, `candidates.json`,
`flatten_candidates.py`, `verify_and_add.py`, `job search/`) → `legacy/`;
`tracker.db.bak` deleted. `enumerate_companies.py`/`build_company_list.py` stay at
root (imported). Suite exactly 1744/1 after; `.gitignore` repointed. Gotcha
discovered: importing `scripts/setup_lanes.py` runs it (rewrote projects.json,
idempotent, no loss) — run it, never import it. **Handoffs now live in
`docs/handoffs/` — session-open readers look there.**

## 2. Persona tests (workflow wf_4f46f2a5-cf9; corpus commit `ba0482d`)

8 sequential Opus personas, each a true blank slate (shipped registry only,
fresh `gu-*` project; Adzuna/JSearch/USAJobs keyed = "user did the Guide's free
signups"; CareerOneStop deliberately unkeyed). Haiku janitor restored
companies.json byte-exact between personas. All 8 completed setup → AI seeding →
live run → BYO-AI top-10 → tracked apply/interview/offer/rejected/ghosted with
ZERO crashes. Verdicts 6-7/10, 8/8 would-stay, 7/8 beats-manual (exception:
remote-only marketer, 8 inbox rows). Setup 18-40 min, wizard clarity 8-9/10.
Full corpus: `brain/general-user-tests-2026-07/` (8 persona reports, structured
JSON, 4 lens reviews, 3 research reports, orchestrator review).

## 3. What it found (headline defects — all confirmed in code by review lenses)

1. **P0-1 `_industry_tag_match` space/underscore bug** (`scrape/company_registry.py`
   ~:239): any 2+-word industry matches 0 registry companies → careers path
   silently ZERO for warehouse (17 seeds→0 searched), mecheng (8→0), data (15→0).
   One-line fix, held.
2. **Adzuna = de-facto monopoly**: 48-100% of every metro inbox; CareerOneStop
   (Guide's #1 lever) unkeyed + silently dark in all 8 runs, never surfaced in-app.
3. **Remote-only broken on keyed aggregators**: Adzuna/USAJobs return 0 for
   location="Remote" (query construction, not API limit).
4. **Raw local Score misleads no-AI users**: "Sr."/"III"/"8+ YOE" tie an entry role
   (SE III scored 100 = #1 row in new-grad inbox); any "remote" gets full location
   credit country-blind; sub-floor comp ($1,500/mo) slips a $90k gate. The correct
   logic exists in `match/facts.py` but isn't wired into scorer/hard-gate. BYO-AI
   re-rank fixed every case — exposure is keyless users only.
5. **`+ Add Companies` probe is advisory** — junk/unreachable boards saved anyway;
   AI slug-guessing ~50% wrong; marquee employers (FedEx/Nike/Banner/Dignity/ASU/
   hospitals) sit behind Workday/CSRF → seeding contributed ~nothing to top-10s.
   Strongest evidence yet for Seed-My-Area Leg B over pure ask-your-AI.
6. **`daily_run --project X` flips GLOBAL active project** (set_active before
   pin_active) — confirmed live; I restored active=test-controls after the phase.
7. **Tracker minors**: file-import re-rank fills fit but Top Picks stays empty
   without new_rank col; `update_job` silently drops unknown fields; phone_screen
   status vs round-kind incoherence; status-note = phantom self-transition in CSV.
8. Taxonomy holes: nursing/marketing/warehouse unresolved ("demand generation
   manager" → Hydroelectric Production Manager SOC).

## 4. Improvement plan (the morning read)

**`brain/improvement-plan-2026-07-02-general-user.md`** — exec summary, persona
scorecard, 7 P0s w/ file:line + minimal fixes, quick wins, coverage roadmap by
vertical, onboarding roadmap (target: stranger → useful inbox <15 min via
wizard→source-keys resequence + sample-inbox TTFV), strategic bets, non-goals.
Top strategic find (research-sources.md): **Workday `wday/cxs` public JSON API** —
unauthenticated postings endpoint that unlocks exactly the CSRF-blocked marquee
employers 5 personas lost. Competitor teardown (Teal/Huntr/Simplify/Jobright/
LoopCV etc.) + BYO-key onboarding UX patterns also in corpus.

## State

- Master = this handoff commit on top of `ba0482d` + `ecddfa7`; **~118 ahead of
  origin, PUSH STILL HELD**, tree clean. Suite untouched since reorg verify
  (1744/1); no app code changed after that.
- Registry active = `test-controls`; companies.json byte-identical to pre-test.
- Projects KEPT for browsing: 8 × `gu-*` + `test-controls`, `test-dad-health`
  (S30). Delete + registry entries when done.
- Fleet stats: 25 agents, ~3.1M subagent tokens (personas 1.93M, review/research
  1.17M), zero persona failures; 2 research agents flubbed only their structured
  returns — their full reports are on disk.

## Needs Alex

1. **Read the improvement plan**; green-light the P0 fix wave (P0-1 is a one-liner).
2. **Push decision** (~118 commits; experience.md PII history question still open).
3. **CareerOneStop key** — now the single most evidenced unlock (all 8 runs); note
   plan's caveat: Jobs API governance-gated since 2024-08.
4. Workday `wday/cxs` fetcher go/no-go (top coverage bet).
5. Browse then delete test projects (10 total).
6. Standing from S30: company-canon dedup design; Seed-My-Area build (Leg B now
   strongly evidenced).
