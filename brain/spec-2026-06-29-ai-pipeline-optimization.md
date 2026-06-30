---
title: AI Pipeline Optimization — decompose for cheap/local models
date: 2026-06-29
status: spec (design only — not approved for build)
tags: [spec, ai, cost, local-model, ranking, enumeration]
---

# AI Pipeline Optimization — decompose the controls sweep for cheap/local models

> Goal: make the "build companies → scrape → rank against my profile" loop fast and
> cheap enough to run routinely, with the recurring AI work running on a **local
> model** (Ollama / Gemma-4-12B-QAT). Spec-only; no code until approved.

## 1. Problem & diagnosis

The 2026-06-29 controls smoke test worked but felt slow and token-heavy. Measured
breakdown of where the cost actually went:

| Step                         | Time               | AI cost      | Reality                                                                 |
| ---------------------------- | ------------------ | ------------ | ----------------------------------------------------------------------- |
| Scrape 88 boards             | 84s cold / 7s warm | **$0**       | network-bound; already cached 24h                                       |
| Probe-verify companies       | ~15s               | **$0**       | pure HTTP, deterministic                                                |
| Company candidate generation | —                  | **real**     | hand-wrote ~115 companies ×3 passes @ ~30% hit — wasteful model output  |
| Local 0–100 scoring          | instant            | **$0**       | already deterministic (`match/scorer.py`)                               |
| AI fine-rank (18 jobs)       | —                  | **modest**   | one batch; scales with job count + re-runs                              |
| **Driving it interactively** | most wall-clock    | **dominant** | a frontier agent read ~20 files, narrated, hand-orchestrated every step |

**Key insight:** the ranking AI was cheap (18 jobs). What was expensive was using a
**frontier agent to do and supervise deterministic work in one long interactive
session**, plus hand-enumerating companies a frontier model never needed to brainstorm.

**Therefore the optimization is not mainly "smaller model for ranking."** It is:

1. Take the frontier model **out of the loop** for everything that isn't genuine judgment.
2. Make the judgment that remains a **small, cached, local-model call** on compressed input.
3. Make company-building **deterministic** (harvest, don't brainstorm).

This matches the "break parts down for AI with descriptions of specifics/goal" intent:
each remaining AI step becomes a narrow, individually-specified, cacheable sub-task that
a local model can run.

## 2. Goals / non-goals

**Goals**

- Recurring controls (or any-project) sweep runs with **$0 frontier tokens by default**.
- The two recurring AI needs (extract, score) run on a **local model via Ollama**.
- **Re-runs are near-free**: only net-new postings incur any AI work (cache + freshness).
- Company-building uses the existing Common-Crawl harvest instead of LLM slug-guessing.
- Each AI step has a crisp spec (goal / input / output schema / model tier).

**Non-goals**

- Not changing the 0–100 local scorer's math (it's good; reuse it).
- Not removing the Bridge / File / API ranker routes (keep them for no-local/manual use).
- Not a UI rewrite. GUI keeps calling the same service verbs.
- Not auto-applying. Still "assisted, never auto-apply."

## 3. Three tiers of "who does the work"

- **D — Deterministic code** (free, instant): scrape, probe, Common-Crawl harvest,
  dedup, hard-gate, 0–100 score, regex seniority/role/visa/clearance gates.
- **L — Local model** (free, offline; Ollama / `gemma4-12b-qat-cc`): the two narrow
  recurring tasks — **extract** structured facts, **score** against a rubric.
- **F — Frontier model** (paid, rare/optional): final shortlist polish, resume
  tailoring, or a periodic calibration audit of the local model's scores. **Off by default.**

## 4. Target pipeline (recurring rank path)

```
[D] Scrape (cached 24h) + dedup                       (search_engine / careers_client)
[D] Hard gate (preferences.json: salary/location/remote/dealbreakers/work_auth)
[D] Local 0–100 score                                  (match/scorer.py — unchanged)
[D] Freshness: mark is_new  → only NEW jobs proceed    (search/freshness.py — exists)
[D] Take top K of new jobs (e.g. K=40 by local score)
[L] EXTRACT structured facts per job (cached by job_key)        ← Task A
[D] Re-gate on extracted facts (seniority / visa / clearance / role_type)
[L] SCORE {fit, why} from compressed facts + rubric (batched ~10/call)  ← Task B
[D] Write fit + Top Picks rank to inbox                (tracker/service.py — exists)
[F?] (optional) Polish top 10 / resume tailoring
```

**Why this is cheap:** extraction is immutable per posting → cache forever (keyed by
`job_key`), so a re-run only extracts net-new jobs. Scoring runs on ~60-token fact
summaries, not 1500-char HTML — ~15× smaller context per job — and runs local = $0.
A re-run with no new jobs and an unchanged rubric is all cache hits: seconds, $0.

## 5. The per-task model specs (the decomposition)

### Task A — EXTRACT (local model; extraction, not judgment)

- **Goal:** turn a messy job description into structured facts so downstream gating and
  scoring are cheap and deterministic.
- **Input:** `title` + `company` + truncated `description` (~1500 chars).
- **Output (strict JSON):**
  ```json
  {
    "required_years": 0,
    "seniority": "entry|mid|senior|lead|manager|director|intern",
    "role_type": "build|test|integrate|maintain|research|manage|sales",
    "top_skills": ["<=6 short tokens"],
    "clearance_required": false,
    "location_type": "onsite|hybrid|remote",
    "restriction": "e.g. US work auth | Japan visa | null",
    "comp_min": null,
    "comp_max": null
  }
  ```
- **Model tier:** **L (local).** Schema-constrained extraction is exactly what a small
  model does reliably (scoreboard: Gemma-12B "fast AND correct" on structured tasks).
- **Cache:** `cache/extracted/<job_key>.json`, immutable. Re-runs skip cached jobs.
- **Fallback:** several fields are recoverable by regex (comp via existing
  `salary_from_text`; seniority/clearance via keyword lists) — extraction can be regex-first
  and only call the model for the residue, or skip the model entirely for these.

### Task B — SCORE (local model; compressed judgment)

- **Goal:** rate fit of one job to the candidate against a fixed rubric.
- **Input:** the candidate **RUBRIC** (~150 tokens, built once per run) **+ the job's
  EXTRACTED FACTS** (~60 tokens). **Not** the raw description.
- **Output (strict JSON):** `{"fit": 0-100, "why": "<=12 words", "flags": "string|empty"}`
- **Model tier:** **L (local).** Batched ~10 jobs/call.
- **Why ~15× cheaper than the smoke test:** the test fed full HTML descriptions ×18
  (~400 tok/job); this feeds ~60-tok fact summaries and runs local.

### Task C — RUBRIC distillation (rare; cached per profile)

- **Goal:** convert `preferences.md` (prose) → an explicit weighted rubric the SCORE task
  can apply consistently: e.g. `{must_haves:[...], hard_noes:[intern, manager, clearance,
visa], boosts:[real-time control, embedded, motion, hands-on build, smaller company],
penalties:[pure maintenance, sales, people-mgmt], seniority_target: entry-mid,
comp_floor: 85000}`.
- **Input:** `preferences.md` + a short experience summary.
- **Output:** rubric JSON, cached; rebuilt only when `preferences.md` changes (mtime key).
- **Model tier:** **F once** (best quality) **or L** — runs at most once per profile edit,
  so a frontier call here is negligible. Could also be hand-authored.

### Task D — COMPANY relevance classify (optional; local or deterministic)

- **Goal:** decide whether a harvested live board is relevant to the project's industry.
- **Input:** company name + a sample of its job **titles** (already scraped) + the
  industry's role-keywords.
- **Output:** `{relevant: bool, subsector: "string"}`.
- **Model tier:** **D first** (keyword match on titles), **L** only for ambiguous boards.
  Replaces the frontier "brainstorm 115 company names" step entirely.

## 6. Company-building sub-pipeline (occasional, not per-run)

Replace LLM slug-guessing (the 3-pass, ~30%-hit method) with the harvest path that
`discover/funnel` already provides:

```
[D] Harvest: Common-Crawl CDX → universe of greenhouse/lever/ashby/smartrecruiters slugs
[D] Probe:   probe_count each (threaded) → keep live boards (>0)            (exists)
[D/L] Classify (Task D): keep boards whose titles match the industry's role-keywords
[D] Save:    registry.merge_discovered (user-wins, additive, lift-gated)    (exists)
```

AI involvement: **zero** by default (or a tiny local classifier for ambiguous boards).
This eliminates the wasteful enumeration and the slug-guessing miss rate.

> Finding from the smoke test: the `enumerate_companies.py` _discovery_ path
> (domain→ATS via `find_career_url`) yields only ~1/10 — it reads robots/sitemap +
> homepage anchors, but modern ATS boards are JS-rendered SPAs it can't see. The LLM
> step is fine; the **resolver** is the weak link. The harvest path sidesteps it.

## 7. Model routing & local wiring

- Add a **`LocalRanker`** route to `ranker.py` (mirrors `ApiRanker`) calling Ollama at
  `OLLAMA_BASE_URL` (native Anthropic endpoint per the `nemotron-claude-code-driver`
  memory, or OpenAI-compat `/v1/chat/completions`). Default model `gemma4-12b-qat-cc`.
- Add an `extract` helper using the same local client.
- **Per-stage model tier** in `config.py`: `EXTRACT_MODEL`, `SCORE_MODEL`, `POLISH_MODEL`,
  each one of `local | api | bridge | off`. Lets you dial each stage independently.
- Existing Bridge / File routes stay for the no-local / manual / friend-distributable case.

## 8. Cost / latency: before → after (rough)

| Scenario            | Before (smoke test)                   | After (this design)                                              |
| ------------------- | ------------------------------------- | ---------------------------------------------------------------- |
| First controls run  | frontier agent, full descs, hand-enum | D + L only; local extract/score on ≤40 new jobs; **$0 frontier** |
| Re-run, no new jobs | re-do everything                      | all cache hits; **seconds, $0**                                  |
| Re-run, 20 new jobs | re-rank all                           | extract+score 20 jobs local; **$0 frontier**                     |
| Company expansion   | LLM brainstorm ×3 passes              | deterministic harvest+probe; **$0**                              |

## 9. Implementation surface (for the later plan — NOT building now)

- `match/extract.py` — extraction + `cache/extracted/<job_key>.json`.
- `match/rubric.py` — `preferences.md` → rubric (mtime-cached).
- `match/gate.py` (or extend `preferences.hard_gate`) — seniority/role/visa/clearance gates
  from extracted facts (deterministic).
- `ranker.py` — `LocalRanker` + `rank_via_local`; `score_via_local` on rubric+facts.
- `config.py` — `OLLAMA_BASE_URL`, per-stage model tiers.
- `enumerate_companies.py` — `--harvest` path (funnel → probe → classify) as the bulk
  default; keep LLM enum as a supplement.
- Tests: extraction schema + cache; gate rules; local-route (mocked Ollama); rubric
  caching; harvest lift-gate (must not lower coverage).

## 10. Staging (so it can land incrementally)

1. **Deterministic-first** (no local infra): `match/gate.py` seniority/role/visa/clearance
   - `--harvest` company path. Immediately shrinks what any AI sees and kills slug-guessing.
2. **Local swap:** `LocalRanker` (Ollama) so SCORE stops hitting the frontier model.
3. **Extract + cache:** `match/extract.py` + the compressed SCORE input + rubric cache —
   the full payoff (near-free re-runs, fully offline).

Each stage is a strict subset of the next and independently shippable.

## 11. Risks / open questions

- **Local JSON reliability** — mitigate with strict schema + retry + the tolerant
  `claude_bridge._extract_json` parser. Gemma-12B is reliable for structured output, but
  extraction at scale needs the retry wrapper.
- **Ollama endpoint shape** — native-Anthropic vs OpenAI-compat; pick one (both tested
  per memory). Decision needed.
- **Rubric quality** — a bad rubric → bad local scores. Keep the optional **F audit**
  (frontier spot-checks N local scores) as a calibration safety net.
- **Common-Crawl harvest** is network-heavy → run occasionally, not per search (funnel
  docstring already says so).
- **Extraction cache invalidation** — keyed by `job_key`; an edited posting may keep its
  key. Acceptable (rare); a TTL is the fallback.

## 11b. DEFERRED — local-model testing & integration (decided 2026-06-29)

Per Alex: the **local-model** half is deferred to a later session. Specifically deferred:

- Wiring `LocalRanker` / `score_via_local` to Ollama, and the per-stage model-tier config.
- The empirical **granite-vs-gemma-vs-frontier** correlation eval on the 18 controls jobs
  (Spearman vs the frontier reference) to pick the SCORE-tier model.
- Choosing the Ollama endpoint shape (native-Anthropic vs OpenAI-compat) and the model
  (`gemma4-12b-qat-cc` for extract, `granite-tiny` candidate for score).

**Built now (this session) — model-agnostic spine only:** deterministic facts extraction
(`match/facts.py`, cached), deterministic gates (`match/gate.py`), deterministic rubric
(`match/rubric.py`), and the **compact AI request** (`ranker.build_compact_request`) that
feeds compressed facts + rubric instead of raw HTML. These run through the EXISTING ranker
routes (bridge / me-as-ranker) today and accept the local model later by swapping the tier —
no rework. The cascade allocation (frontier-for-extract/rubric, small-model-for-score) and
the local route land when the deferred work is picked up.

## 12. Decision points for review

- Confirm **local model** = `gemma4-12b-qat-cc`, and **endpoint** (native-Anthropic vs
  OpenAI-compat).
- Confirm **EXTRACT** should be regex-first (cheaper, maybe no model) vs model-first.
- Confirm **RUBRIC** distillation tier (one frontier call per profile edit, or hand-author).
- Confirm the **staging order** (1→2→3 above) and where to stop.
