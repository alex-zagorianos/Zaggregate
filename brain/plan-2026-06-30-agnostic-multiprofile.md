---
title: Plan — field/persona-agnostic (GOAL 1) + multiple people on one install (GOAL 2)
date: 2026-06-30
status: plan (approved-for-later; NOT built)
author: Opus planner subagent
tags: [plan, agnostic, multi-user, onboarding, tokens]
---

# Plan: make JobScout field/persona-agnostic + multi-person

> Planned by an Opus subagent while live-testing continued. Not built yet.
> Token invariant to protect: **no new field in `facts_summary`, no new line in
> `rubric_text`** → ranking stays ~94 tok/job (cheap-plan fit).

## Verified context

- Ranking cost = `claude_bridge.build_fit_prompt_compact` (per-job: token+title+company+
  location+salary+`facts.facts_summary` ~30-40 tok) + one shared rubric/profile block.
  Any GOAL-1 change that only alters _which strings_ fill role_type/skills/angles/copy
  costs **0 extra tokens** as long as facts_summary shape + rubric line count hold.
- Config precedence is `cfg.get(x) or config.DEFAULT_x` everywhere (daily_run, cli,
  mcp_server, browser_receiver, gui), so config already overrides the eng defaults;
  they only bite a user who never onboarded.
- `coverage/entity.py` title→SOC is **already occupation-general** (data-driven from
  `data_static/onet_soc_alt_titles.tsv`, ~1000 SOC). No change needed.
- `match/rubric.py` exec-intent is already keyword-derived + field-neutral (extend, not fix).
- Projects layer already partitions experience.md/preferences/config/tracker/output per
  `projects/<slug>/`; ranking picks the ACTIVE project's experience automatically. Shared
  (NOT per-project): companies.json, cache/, .env keys.

---

## GOAL 1 — field/persona-agnostic

Bias is in hardcoded fallback constants + onboarding copy, not logic. BC rule:
**every default stays exactly as today when config is empty / industry unset.**

### 1A — neutral wizard copy + optional field/level answers (high value, low effort, 0 tok)

- `ui/setup_wizard.py`: `_step_welcome` drop "finds engineering jobs"→neutral; `_step_roles`
  neutral cross-field examples; add optional **Field/industry** StringVar + optional
  **Career level** {Entry,Mid,Senior,Manager/Exec}. `_collect` adds `industry`,`level`.
  `build_preferences`/`_search_config` write `industry` + translate `level`→
  `seniority_target`/`allow_management`/`years_cap`/`allow_intern` (only when non-default).
  `prefill_from_existing` reads them back. Signatures unchanged (additive keys).
- Tests: nursing persona → correct target_roles + industry, no eng leak; level=Exec →
  allow_management etc.; blank level/industry → byte-identical to today for Alex.

### 1B — config-authoritative defaults (low)

Keep `DEFAULT_KEYWORDS`/`DEFAULT_LOCATION` (Alex relies on them); document as "seed
fallback only". Do NOT genericize the constants (footgun, low payoff). Open Q #1.

### 1C — industry-parameterized enumeration angles + neutral AddCompanies (high value, low effort)

- `discover/enumerate.py`: `DEFAULT_ANGLES`→fallback; add `angles_for_industry(industry)`
  returning neutral size/type-spread angles naming the user's field; keep eng angles when
  industry is eng (Alex unchanged). Wire industry through `enumerate_via_api(angles=)`.
- `enumerate_companies.py`: add `_resolve_industries(arg)` (mirror `_resolve_metro`) →
  prefer config `industry`/`keywords`; pass to `angles_for_industry`.
- `gui.py:1881` already reads `cfg.industry` for AddCompanies → "just works" once 1A sets it.
- Token cost: enumeration is a separate occasional call; ranking budget untouched.

### 1D — first-run company acquisition = $0 discover, not eng seeds (high value, med effort)

Seed registry = 186 tech/eng cos (health_informatics only 2). Non-tech users get an empty
useful registry. Fix: wizard, after apply(), offers **"Find employers near you (free)"** =
`search.cli --discover`/enumeration bridge for metro+industry when industry is non-eng or
registry has 0 industry matches. Add `company_registry.has_industry(industry)` helper.
Per-industry seed packs = optional later (curation/staleness); discover-first.

### 1E — generalize facts role taxonomy + profile-derived skills (med value, med effort — THE trap)

- `match/facts.py`: extend `_ROLE_KEYWORDS` with universal buckets (care/admin/finance/
  trade + keep tech verbs). **Recommend industry-gated**: tech industry → today's map
  exactly (byte-identical for Alex); else merge universal buckets.
- Skills profile-first: prefer `scorer.extract_skill_terms()` (from the active
  experience.md) over the fixed `_SKILL_VOCAB`; fall back only when profile empty. Same
  `top_skills` limit=6 → same token size. New optional param `skill_terms=` threaded
  `ranker.prepare_compact/build_compact_request → facts_for → extract_facts`.
- ⚠️ **Correctness trap:** the facts cache is keyed by `job_key` only. Profile-dependent
  skills would leak across people/projects. Fix: compute `top_skills` AFTER the cache read
  using the active profile (simplest), or add a profile-skills hash to the cache filename.
- Tests: nurse posting → role=care + resume skills; tech posting+eng industry →
  byte-identical facts (Alex regression); two projects don't cross-contaminate top_skills.

### 1F — scorer/rubric assumptions (low)

`scorer._STOPWORDS` has "engineer/engineering" (benign for non-eng); optionally derive
stopwords from the user's keywords. `DEFAULT_EXCLUDE_TITLES=()` already empty (good).
rubric already reads `seniority_target/allow_management/years_cap/allow_intern` via
`cfg.get` → 1A writing them is sufficient; verify key names match.

GOAL-1 order: 1A → 1C → 1D → 1E → (1B/1F docs).

---

## GOAL 2 — multiple people on one install

**Decision: reuse the project layer; a person = a project.** projects/<slug> already
partitions experience/preferences/config/tracker/output, and ranking already picks the
active project's experience.md (`build_profile→profile_summary→load_experience→
workspace.experience_file`). Add a thin **person label + template** layer, not a new axis.

### 2A — person metadata on the registry (high value, low effort, 0 tok)

- `workspace.create_project(..., person=None)` stores `person` in the registry entry; add
  `people()` and `projects_for_person(person)`. `_ensure_default_root_registered` gives the
  default `person=None`. No new on-disk layout (persons live in projects.json). Additive;
  old entries without `person` = None.
- Tests: create_project(person="Dad") → people()/projects_for_person filter; pre-migration OK.

### 2B — GUI Add/Switch Person (high value, med effort)

- `gui.py` project bar (`:3024-3099`): two-level label or a "Person:" combobox when >1
  person; single-combobox flow unchanged for Alex. `_new_project` offers **New Person…**
  (name + launch `setup_wizard.run()` scoped to the new active project) vs New Campaign.
- Wizard already writes to the ACTIVE project (slug-less paths) → onboarding a new person
  needs no wizard change beyond GOAL-1. `.onboarded` marker is global but Add-Person calls
  `setup_wizard.run()` (ignores marker) → fine. Resume-copy defaults to No (existing C1 guard).

### 2C — ranking picks active person automatically (verify only, 0 code)

Already true via slug-less workspace paths (build_profile, extract_skill_terms,
preferences.load, resume gen). Add regression test: after `set_active(other)`, profile +
skill terms reflect the other person. Scorer cache is path-keyed (safe); the GOAL-1 facts
cache is the shared risk (same fix as 1E).

### 2D — migration (none)

First New-Person auto-registers root as "default" (person None = Alex). No script needed.

### 2E — interaction with GOAL 1 (design)

Each person = own config (industry/keywords/location/seniority) + own experience.md →
agnosticism is per-person for free. companies.json shared but industry-tag-filtered at
query (`get_registry(industry=...)`). Caveat: mixed household can bloat the shared registry;
tag-filtering keeps it relevant.

GOAL-2 order: 2A → 2C/2D (tests) → 2B (visible feature) → 2E (design).

---

## Risks

- **Facts-cache cross-contamination (top priority)** — profile skills from a job_key-only
  cache leak across people. Fix: compute top_skills post-cache from active profile.
- **Regressing Alex's ranking** — gate universal buckets behind `cfg.industry`; byte-identical
  facts regression test; freeze facts_summary shape.
- **Token creep** — invariant: no new facts_summary field / rubric line; add a length test.
- **Empty registry for non-tech first run** — 1D $0-discover default.
- **Global `.onboarded` marker** — Add-Person forces the wizard; documented.

## Open questions

1. Blank the eng `DEFAULT_KEYWORDS`/`DEFAULT_LOCATION` for a truly generic binary (costs
   Alex's no-config run)? Plan keeps them + relies on onboarding→config.
2. Universal role buckets: industry-gated (safe) vs always additive? Plan = industry-gated.
3. GUI "Person" as a distinct concept vs relabel "New Project"→"New Person/Campaign"?
4. Facts-cache fix: profile-hash in key vs compute-skills-post-cache (simpler)?

## Could not verify

- ONET TSV occupational breadth for nursing/trades/legal (mechanism is general).
- Frozen .exe bundles discover/`search.cli` for a stranger's first run (confirm before
  relying on 1D for non-dev users).
- Whether a dedicated `tests/test_setup_wizard.py` exists (add if absent).
