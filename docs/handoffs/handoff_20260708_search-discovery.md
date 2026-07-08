# Handoff — Search Discovery (2026-07-08) — BUILT, suite green, push held

Alex: "reexamine the Zaggregate app search UX… hard to set up even with AI… the AI
prompt limits what jobs the user can find… make not-using-AI more convenient (a
large pool of keywords to select from + experience levels)… research how LinkedIn/
Indeed do it… create a plan… then: begin buildout, use subagents to parallelize."

**Status: fully implemented, Python suite green (3388), frontend typecheck clean +
272 vitest, NOT pushed (push held per repo rule).** Ran concurrently with Session 45
(velopack) on the same `feature/search-discovery` branch — histories interleave
cleanly. Plan: [[search-discovery-plan]].

## The three problems fixed

- **P1 — the AI-setup prompt capped recall.** It asked the pasted AI for "1-5 job
  titles" + one `field` from a hardcoded 25-token list; those titles became the
  ENTIRE `cfg['keywords']` set. The ceiling was pure prompt wording (no downstream
  cap). Now: a tiered, UNCAPPED schema (`keywords.core/adjacent/exploratory`) + a
  FREE-TEXT field (generic-resolving fields accepted for full reach). Legacy
  `target_titles` blocks still parse (backward-compat).
- **P2 — no-AI setup needed you to already know your field's title vocabulary.** New
  Search Discovery: type a field → get a rich, selectable keyword pool from the
  bundled O*NET taxonomy, with opt-in live "openings nearby" and corpus mining.
- **P3 — experience level was scoring-only.** Now also generates keyword variants
  (entry/mid only; senior/manager/exec = ∅ to avoid recall collapse), while the
  existing rubric path stays byte-identical.

## Research (42-agent workflow, adversarially fact-checked)

Winner = corpus-mined/empirical, with taxonomy-first + résumé-prefill grafted in.
20/24 load-bearing external claims were CORRECTED by a hostile fact-check pass —
key finding: LinkedIn/Indeed URL facet params (`f_E`, `explvl`, etc.) are
reverse-engineered scraper folklore, NOT documented contracts; we borrowed the
_patterns_ (entity resolution, title auto-expansion, faceted chips), integrated
none of them. Full synthesis in [[search-discovery-plan]] §2.

## What shipped (4 commits: cb3da59, f637d01, 248a73b/fb133a4-adjacent, 992c18d)

**Data + store (Layer 0):**

- `src/data_static/onet_related_occupations.tsv` (1.35 MB, 18,460 rows, O*NET 30.3,
  **CC-BY 4.0** — resolves the plan's #1/#2 license+size risks; built by new
  `scripts/build_taxonomy_extra.py`). The cross-occupation relatedness graph that
  powers the adjacent/exploratory tiers. (Technology-Skills file 404'd at O*NET →
  skill chips deferred; propose returns `skills:[]`.)
- `keyword_pool` table, **schema v7→v8** (`tracker/db.py`). CRUD spine in
  `search/discovery/pool.py` (upsert never downgrades an active term; prune only
  touches suggestions).

**`search/discovery/` package (Tk-free, one concern per module):**

- `propose.py` — offline core/adjacent/exploratory tiers. **Reverse-SOC fallback**:
  `industry_profile.resolve_soc` returns None for eng/tech fields, so a lookup via
  the alt-titles index recovers the SOC (mech-eng→17-2141, sw-eng→15-1252) — without
  it, engineers (the primary audience) got empty adjacency. + `keyword_suggest`
  typeahead.
- `probe.py` — opt-in live Adzuna page-1 yield, **10/day** budget (per-project JSON
  counter), own-process RateLimiter at the Adzuna ceiling.
- `mine.py` — opt-in corpus mining (inbox/applications SQL freq + generic feed-cache
  title scan via new `single_feed_client.cached_titles()`), **gated behind
  `cfg['discovery_enabled']`** — never opened the panel = zero cost.
- `flag.py` — low-activity nudges with a **min-activation-age guard**; never
  auto-deactivates.
- `levels.py` — entry/mid query variants; **senior/manager/exec = ∅** (hard invariant,
  test-pinned; mirrors `keyword_strategy.deseniorize`).

**API:** `webui/api/discovery.py` — propose/keywords/pool/probe/mine/levels/activate/
deactivate/excludes. Mutations `@require_local_origin` (route-audit meta-test passes).

**Scorer:** `suggested_excludes` = bounded **−6 downrank**, never a drop (contrast
gate.py `hard_no_titles`); `None`-default → **byte-identical** for every existing
config (parity holds). Threaded through all 7 `score_jobs` call sites.

**UI:** web `tabs/search/KeywordPoolPanel.tsx` (grouped chips, jargon-free copy,
built from existing shadcn primitives, no new dep) embedded in SearchTab + RolesStep
(replaces the fixed field `<select>`); Tk `DiscoverKeywordsDialog` in `tab_search.py`
(pure helpers mirror the web activate/deactivate contract byte-for-byte).

## Contract preserved

`cfg['keywords']` stays the single search source of truth; an `active` pool term
MIRRORS it. **Inclusion over precision** held throughout: no control here ever drops
a job — low/zero counts are shown ("hasn't found much lately"), never hidden.

## Execution

Dependency-ordered rounds; within each, parallel Sonnet subagents on **strictly
disjoint files** (never running pytest/the app — the "two DB processes" rule); the
orchestrator ran the full suite + committed between rounds. One real gap caught in
integration (eng adjacency) → fixed via a targeted agent follow-up.

## Open / next (Alex's calls — plan §8)

1. Daily probe budget 10/day — instrument, raise if uncontended. (const in probe.py)
2. `suggested_excludes` downrank magnitude — flat −6 (`scorer.SUGGESTED_EXCLUDE_PENALTY`).
3. Skill chips (O*NET Technology Skills) — deferred; `build_taxonomy_extra.py` extends.
4. **daily_run auto-mine hook** — mine.py is opt-in via the /mine route only; wiring a
   gated `mine_corpus()` call into `daily_run` (so the corpus self-refreshes) was
   deferred to keep the hot/parity path untouched. Recommended follow-up.
5. Human smoke of both UIs (web panel + Tk dialog) — logic is tested; visual/UX pass pending.
