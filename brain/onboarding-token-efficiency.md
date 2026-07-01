---
title: Onboarding inputs + token-efficiency audit (cheap-plan fit)
date: 2026-06-30
status: living doc
tags: [onboarding, cost, tokens, ai, gate, persona]
---

# Onboarding inputs + token efficiency — "does it fit a $20 (or free) Claude plan?"

Stress-tested with a deliberately off-profile persona: **Alex's dad — VP-level
Health Informatics, Cincinnati + remote, max-coverage company enumeration.**
Goal: confirm a non-technical user on a cheap AI plan can run this, and record
exactly what onboarding needs + the cheapest correct way to supply it.

## TL;DR verdict

- **Token cost is a non-issue.** A full day of use ≈ **1 AI message**; even
  max-coverage setup is a handful of one-time messages. Fits **$20 Pro trivially
  and the FREE tier comfortably**. On the API it's **~$0.50–1/month** (Haiku).
- **The real risk was correctness, not cost:** the pre-AI gate was hard-tuned for
  an entry-mid IC and **dropped 100% of VP/Director/Chief roles before any AI ran**
  → a VP search returned zero fits. **FIXED** this session (auto-detect exec intent
  from the user's own keywords). See "Findings".

## Onboarding inputs — what the app needs, where it comes from, token cost

| Input                   | Collected by                                                                                    | Feeds                                             | Tokens                           |
| ----------------------- | ----------------------------------------------------------------------------------------------- | ------------------------------------------------- | -------------------------------- |
| Target roles / keywords | Setup wizard (step 2) → `target_roles` / `cfg.keywords`                                         | search, scorer, rubric, **exec-intent detection** | 0                                |
| Location + remote-ok    | wizard (step 3) → `hard.locations`, `hard.remote_ok`                                            | search, scorer                                    | 0                                |
| Salary floor (opt)      | wizard (step 3) → `hard.salary_min`                                                             | hard-gate                                         | 0                                |
| Profile / "about" (opt) | wizard (step 2) → `preferences.md`                                                              | AI rubric/ranking                                 | 0 to store; part of rank prompt  |
| Resume (opt)            | wizard (step 4) → `experience.md`                                                               | scorer + AI background                            | 0 to store                       |
| **Company list**        | **seed `companies.json`** + `search.cli --discover` (harvest) or `enumerate_companies.py` (LLM) | careers scraping                                  | harvest **0** / LLM ~5k one-time |

The **wizard itself spends 0 tokens** (pure form → JSON/MD). It does **not**
collect companies — that's a separate step.

## Measured token sizes (chars/4 proxy, realistic postings)

- **AI re-rank (recurring, the compact path):** **~94 tokens/job** (facts+rubric)
  vs ~419 raw — ~4.5× smaller. A 40-job day ≈ 3.8k in + ~1.2k out ≈ **one message**.
- **Company enumeration (LLM, max coverage):** 5 angles × 1 call, ~132 tok prompt +
  ~900 tok output each ≈ **~5k tokens, one-time per metro** (≈ 5 pastes on the bridge).
- **Rubric:** now **deterministic** (`match/rubric.py`) — **0 tokens**.
- **Local 0–100 score, hard-gate, deterministic gate, probe-verify:** **0 tokens**.

### Max-coverage cost for the dad persona (worst case)

one-time companies ≈ 5 messages (or ~$0.02–0.10 API) · daily rank ≈ 1–3 messages
(~150-job day) · **month on API (Haiku) ≈ $0.50–1**. The $20 plan is overkill on
tokens; its only benefit is bigger paste limits / convenience.

## Most efficient way to supply each need

1. **Companies — prefer the deterministic harvest** (`py -m search.cli --discover`,
   Common-Crawl → `companies.json`): **$0**, and measurable via `company_coverage.py`.
   Use LLM enumeration only for the long tail of an unusual metro/field (bounded,
   ~5k tokens one-time, behind the probe-verify gate).
2. **Ranking — clipboard bridge on free/Pro claude.ai** (paste compact prompt, paste
   reply). Re-runs are cached, so only net-new jobs cost a message. API key optional
   (~pennies/mo) for hands-off auto-rank.
3. **Rubric/gates — deterministic, free.** No AI needed to personalize ranking floors.

## Findings & status

- 🟢 **FIXED — exec/management seekers were fully gated out.** `match/gate.py`
  hard-dropped `seniority∈{manager,director} & role_type=manage` ("people-management
  role") with **no override** → a VP/Director/Chief search dropped every role before
  the AI. Now `match/rubric.py` **infers management intent from the user's target
  roles** (`_EXEC_RE`: vp/svp/evp/chief/cxo/president/head of/director/executive/
  manager/managing director) and sets `allow_management`, `seniority_target=senior-exec`,
  `years_cap=25`, drops the "manage" penalty — all overridable via project config.
  `gate.py` honors `allow_management` for both the management-drop and the
  senior-"stretch" downrank. Zero extra questions, zero tokens. Tests:
  `tests/test_exec_seniority.py`. (Local scorer was already persona-neutral —
  `DEFAULT_SENIORITY_EXCLUDE = ()`.)
- 🟡 **Open — seed `companies.json` is tech/health-informatics biased.** Fine for
  dad (health informatics!), wrong for other fields → those users must harvest/enumerate.
  Efficient fix later: ship per-industry seed packs, or make `--discover` the
  default first-run company step.
- 🟡 **Open — LLM enumeration angles are engineering-flavored** (`DEFAULT_ANGLES`
  in `discover/enumerate.py`: "automation, robotics, controls…"). The `industries`
  param still drives it, but the angles nudge eng. Efficient fix later: derive angles
  from the user's industry instead of hardcoding.
- 🟡 **Open — no explicit "career level" in the wizard.** Not needed now (inferred
  from keywords), but an explicit toggle would be more robust than keyword sniffing
  for edge cases (e.g. "informatics leadership" with no title word).

## Efficient-onboarding checklist (for "make it easier later")

- [x] Wizard captures roles/location/remote/salary/about/resume at $0.
- [x] Ranking uses compact facts+rubric (~94 tok/job) + cache + gate.
- [x] Gate adapts to exec/management seekers automatically.
- [ ] First-run company step defaults to the $0 harvest (not LLM).
- [ ] Industry-derived enumeration angles + per-industry seed packs.
- [ ] Optional explicit "career level" in the wizard.
