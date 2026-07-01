# Handoff — Session 21 (2026-06-30, cheap-backend) — controls smoke test + AI-pipeline optimization (decompose ranking for cheap/local models)

> Two things: (1) a controls-engineering **smoke test** of the company-build + ranking
> pipeline; (2) designed + built the **model-agnostic spine** that makes AI ranking cheap,
> cached, and well-scoped — extract → gate → compact-prompt — and **wired it into the live
> GUI**. Built on the cheap/3rd-party backend, inline (no delegate). Local-model
> integration **deferred** by Alex.

## Relationship to Session 20

Built in a cheap-backend session and committed (`7d9a721 feat(ai): commit Session-20
AI-pipeline spine`); the Opus **Session 20** deep-review then **reviewed + hardened** its
heuristics (`02471d7 fix(match): clearance-negation, experience-qualified required_years,
manager role_type` = S20 findings F4/F5/F10). All pushed together. So `handoff_20260630_session20`
covers the _review remediation_; THIS doc covers the _AI-pipeline design_ + the _controls smoke test_.

## Part 1 — Controls smoke test

- **Company list (wide net):** the controls registry was already broad (~98 entries from
  prior enumerate/discovery). A 3-pass direct-slug **probe-verify** (real `probe_count`)
  across robotics/AV/space/defense/eVTOL/EV/fusion/semiconductor/medical/manufacturing
  added **8 net-new live boards** → `companies.json`: Samsara, PsiQuantum, Neuralink,
  Epirus, Noah Medical, Tenstorrent, Shield AI, Crusoe.
  - **Finding:** `enumerate_companies.py`'s _discovery_ path (domain→ATS via
    `find_career_url`) yields only ~1/10 — it reads robots/sitemap + homepage anchors, but
    modern ATS boards are JS-rendered SPAs invisible to it. The LLM step is fine; the
    **resolver** is the weak link → direct-slug+probe is far higher-yield.
- **Profile anchored:** `projects/controls-cincinnati/preferences.md` was the blank template
  → wrote Alex's controls profile distilled from `experience.md` (JOB SEARCH CRITERIA +
  Target Tracks). This is the "what I want" the ranker reads.
- **Ranking tested:** careers-only scrape (discovery off) → **1514 jobs in ~84s** (warm 7s),
  local `score_jobs` (median 44, max 87, 35 ≥70) → AI-ranked the top 18 via the real
  `ranker` round-trip anchored to the profile → wrote fit + Top Picks rank into the
  **controls-cincinnati** inbox. The AI layer demoted seniority/role-type/specialization
  mismatches the local scorer over-credits (intern, Senior Manager, Japan-visa,
  EM-specialist) and promoted entry/remote/hands-on roles.

## Part 2 — AI-pipeline optimization (the spine)

Spec: `brain/spec-2026-06-29-ai-pipeline-optimization.md`. **Insight:** the expensive part
wasn't the ranking AI (18 jobs is cheap) — it was a frontier agent doing/supervising
deterministic work interactively + hand-enumerating companies. Fix = decompose so
deterministic code + (later) a local model do the recurring work; frontier rarely/never in
the loop. Each remaining AI step is narrow, specified, cached.

Built (model-agnostic, deterministic today; **same `parse_response` contract** so consumers
are unchanged):

- **`match/facts.py`** — deterministic fact extraction (seniority, required_years, role_type,
  clearance, location_type, restriction, comp, top_skills) from a posting, **cached by
  job_key**. _(S20 hardened: clearance-negation, experience-qualified years, manager role.)_
- **`match/rubric.py`** — builds a scoring rubric from preferences/config (+ profile prose).
- **`match/gate.py`** — drops structural non-fits (intern / clearance / foreign-visa /
  people-management / excluded-title / over-senior) **before any AI spend**. drop = excluded
  from the AI batch, NOT hidden; the job keeps its local score.
- **`claude_bridge.build_fit_prompt_compact`** — feeds compact facts, not raw HTML.
- **`ranker.build_compact_request` / `ranker.prepare_compact`** — the streamlined entry
  point (extract → gate → compact prompt).
- **`tracker/service.compact_fit_prompt_for_rows` + `mark_inbox_gated`** — GUI service verbs.
- **Wired live:** both **"Ask AI to rank these"** buttons (Inbox + Apply Queue) now use the
  compact, gated path; gated inbox jobs get a low fit + **"Auto-filtered: \<reason\>"** so
  they don't re-surface; status reports the auto-filtered count.

**Effect:** ~⅓ the tokens per rank (live smoke: 20 → 18, prompt **71% smaller** ~8.5k → 2.4k
tok; the 2 dropped were clearance-required roles), never wastes AI on a structural non-fit,
fully deterministic/offline. Tests **+29** this session (725 → 754; now part of the 841 suite).

## Deferred — local-model integration (Alex's call; note for next session)

Spec §11b. `LocalRanker`/`score_via_local` to Ollama; the **granite-vs-gemma-vs-frontier**
correlation eval (Spearman vs the frontier reference on the 18 jobs) to pick the SCORE-tier
model; endpoint choice (native-Anthropic vs OpenAI-compat). When picked up, only _who runs
the prompt_ changes — the spine stays. Recommended cascade from the design discussion:
**frontier (cached) for EXTRACT + RUBRIC** (comprehension/judgment; extraction errors
propagate, so spend smarts there), **small/fast model (granite) for SCORE** on pre-extracted
facts (low load, long-ctx batches), deterministic for gates/harvest.

## Repo state / Needs Alex

- master is **PUSHED** (origin even) as of this handoff — the Session-20 79-commit hold is
  RESOLVED. Suite **841 passing**.
- **1 uncommitted file:** `tests/test_scorer_compress.py` — I made `test_confidence_marker_data_rich`
  **hermetic** (passes explicit `skill_terms`). It was red on master because the active project
  drifted to **dad-health-informatics** (0 skill terms → `conf 4/5`, which is _correct_ product
  behavior — the test just assumed a skills-rich ambient project). **Commit + push this** (plus
  the new handoff/brain/index/memory doc edits).
- **Active project is `dad-health-informatics`** right now — if you're doing controls work,
  switch back via the GUI project dropdown (it drives scoring/skills + which inbox you see).
  The controls smoke-test data (Top Picks, the 18 ranked jobs) lives in **controls-cincinnati**.
- Local-model integration deferred (above).

## Pointers

- Spec: `brain/spec-2026-06-29-ai-pipeline-optimization.md` (§11b deferral). Brain §"Session 21".
  Memory `project-job-search`. Session-20 remediation: `handoff_20260630_session20.md`.
