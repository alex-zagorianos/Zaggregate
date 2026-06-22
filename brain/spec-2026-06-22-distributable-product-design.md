---
title: Distributable AI-native Job Search — Product Design Spec
created: 2026-06-22
status: approved (design) — pending spec review, then implementation plan
supersedes: extends the hardening backlog (review-2026-06-15) + the claude-allfixes branch
related: [[review-2026-06-15]], [[project-status]], zag0005-allfixes/brain/claude-allfixes-2026-06-16.md
---

# Distributable AI-native Job Search — Design Spec

## 1. Context & goal

`Job-Program` (ZAG0005) is a mature personal job-search aggregator + scorer + tracker +
resume generator + browser extension + tkinter GUI. Two goals drive this evolution:

1. **Distribute it** — package it so friends/others can run their _own_ job search with
   their _own_ Claude/Claude Code plans, with zero personal data of Alex's shipped.
2. **Wide net, but tailored** — fetch as broadly as possible, then let AI rank/sort results
   to each person's preferences. AI integration is the tailoring layer that makes "wide" usable.

This builds **on top of** the `claude-allfixes` branch (already verified: 290 tests), which
added the exact substrate needed: a `DATA_DIR`/`WRITABLE_DIR` split in `config.py`, a
committed PyInstaller `app.spec` (onedir, windowed GUI), and a `tracker/service.py` intent-verb
seam. Phase 0 lands that branch; Phases 1–4 build the product.

## 2. Decisions locked

- **AI integration = two channels, one engine:**
  - Channel 1 — **EXE** with **hybrid** AI: clipboard bridge by default (any Claude.ai plan,
    zero key), optional API-key auto-mode if a key is present.
  - Channel 2 — **MCP server + Claude Code skill**: `claude` runs in the data folder and drives
    search + ranking via subagents.
- **Tailoring = NL profile + thin hard-filters:** `preferences.md` (free text, the AI's nuanced
  signal) + `preferences.json` (cheap hard gates: salary floor, locations, remote-ok, work-auth,
  dealbreakers).
- **Defaults (vetoable):** friend-facing brand "JobScout" (internal names stay `JobProgram`);
  resume generator included in friend build; auto-mode model = `claude-sonnet-4-6`.

## 3. Non-goals (YAGNI)

- No hosted/multi-tenant web service, accounts, or cloud sync. Each install is local + single-user.
- No auto-apply. The tool ranks/preps; the human submits (unchanged philosophy).
- No new scraper sources in this effort (the existing free + careers/ATS set is the "wide net").
- No rewrite of the GUI; it is decomposed/hardened, not replaced.
- Browser extension stays as-is (not part of the friend package v1).

## 4. Architecture — the spine

One core engine → one data-folder contract → two channels. No channel forks the search/score/
track logic; both call the same `tracker/service.py` + engine over the same data folder.

```
   core engine (existing, hardened): search clients · scorer · tracker DB · resume gen · service seam
                                   │ reads/writes
                          USER DATA FOLDER (the contract)
              preferences.md · preferences.json · experience.md · companies.json
                       · tracker.db · cache/ · output/ · secrets/
                          │                                   │
              Channel 1: EXE                       Channel 2: MCP + Claude Code
   hybrid AI (bridge default, API auto)     `claude` in the data folder drives it via subagents
```

## 5. Components

### 5.1 Core engine (no fork)

Unchanged post-hardening. Both channels invoke `tracker/service.py` (intent verbs) and the engine
modules. This is why two channels cost ~1.2× one, not 2×.

### 5.2 Data folder — three tiers (extends `config.py`)

Today `config.py` has two tiers: `DATA_DIR` (`_MEIPASS` when frozen, read-only bundle) and
`WRITABLE_DIR` (`<exe>/JobProgram`, runtime state). We add a third, explicit **user data folder**:

- **Bundle (`DATA_DIR`, read-only):** code + **templates only** — `experience.template.md`,
  `preferences.template.md`, `preferences.json` default, a starter `companies.json`. No personal data.
- **User data folder (NEW, external, editable):** resolved `--data <path>` › `./data` beside the
  exe › `%LOCALAPPDATA%/JobProgram`. Holds the user's real `preferences.md`, `preferences.json`,
  `experience.md`, their `companies.json`, `tracker.db`, `cache/`, `output/`, `secrets/`.
- **First run:** empty user folder → scaffold from bundle templates → launch setup wizard (§5.6).

Implementation: add `USER_DATA_DIR` resolution to `config.py` as the **single writable + user
root** (it subsumes allfixes's `WRITABLE_DIR`, which becomes an alias of `USER_DATA_DIR` for
back-compat — same resolution order: `--data` › `./data` beside the exe › `%LOCALAPPDATA%`).
Repoint `EXPERIENCE_FILE`, `COMPANIES_JSON`, `tracker.db`, `CACHE_DIR`, `OUTPUT_DIR`,
`USER_CONFIG_JSON`, and the new `PREFERENCES_MD`/`PREFERENCES_JSON` at `USER_DATA_DIR`.

`companies.json` precedence (uses the existing `company_registry` merge, user-wins): the bundle's
starter file is the read-only seed copied into the data folder on first-run scaffold; thereafter the
**user's** `data/companies.json` is authoritative and merges over the hardcoded registry.

**Hard guarantee:** Alex's `experience.md`/preferences NEVER ship — the bundle carries neutral
templates only. The friend package contains zero personal data. (Repo-private confirmed in Phase 0
before any further push; see §9 R1.)

### 5.3 Preferences contract

- `preferences.md` — free-text "what I want": target roles, what I love/avoid, relocation appetite,
  seniority comfort. The AI ranker reads this verbatim.
- `preferences.json` — hard gates applied cheaply before any AI call:
  `{ salary_min, locations[], remote_ok, work_auth, dealbreakers[], seniority_exclude[] }`.
- Back-compat: the existing `user_config.json` (keywords/exclude_titles/salary_min) is derived from
  / merged with `preferences.json`; the scorer keeps working. A migration seeds `preferences.*`
  from any existing `user_config.json` so Alex's own setup converts cleanly.

### 5.4 Wide-net + tailored ranking flow (the core mechanic)

```
WIDE FETCH                 HARD GATE              CHEAP PRE-SCORE        AI FINE-RANK
all free + careers/ATS  →  preferences.json   →   match/scorer.py   →   top-N vs preferences.md
sources, full registry,    (salary/location/      (coarse 0–100,        (nuanced order +
loose/empty keyword        remote/work-auth/       cuts long tail)       per-job fit rationale)
gates                      dealbreakers)                                 → ranked inbox
```

- **Zero-key by default:** no-key sources (TheMuse, RemoteOK, Remotive, Jobicy, Himalayas, HN) +
  careers/ATS scrapers (Greenhouse/Lever/Ashby/SmartRecruiters — no key) + the ~240-board
  `companies.json` give wide coverage with no API keys. Keyed sources (Adzuna/JSearch/USAJobs) are
  optional: a friend may add their own free keys in `secrets/` for more volume.
- A new "wide" search mode loosens keyword gating (the AI does the tailoring keywords can't).
- `rank_to_preferences` re-orders the pre-scored top-N and writes fit rationale to the inbox.

### 5.5 AI integration (hybrid, one prompt)

A single `rank_to_preferences(top_n, preferences_md)` builds ONE prompt, routed three ways with no
logic fork (extends `claude_bridge.py` + `resume/service.py` lazy-API path):

- **Clipboard bridge (default):** copy prompt → paste into any Claude.ai plan → paste JSON back.
- **API auto (if `secrets/anthropic_key` / `ANTHROPIC_API_KEY`):** direct API call, no paste.
- **MCP tool (Channel 2):** same op exposed as a tool Claude Code calls directly.
  Resume/cover generation rides the same three routes. Output everywhere: ranked order + per-job
  fit rationale → inbox.

### 5.6 Channel 1 — the EXE

- Extend `app.spec` (onedir, windowed). Add `USER_DATA_DIR` resolution + a **first-run setup
  wizard** in the GUI: detect/scaffold the data folder → open `preferences.md` with inline
  guidance → set hard filters → optional API-key paste → "Run first wide search."
- **Package a friend receives** (zip): `JobScout/` app folder (`JobProgram.exe` + `_internal/`) +
  sibling `data/` (templates + a filled example) + `README.txt`. Unzip → edit `data/preferences.md`
  → run.

### 5.7 Channel 2 — MCP + Claude Code skill

- **Stdio MCP server** wrapping the engine: tools `search_jobs`, `score_jobs`,
  `rank_to_preferences`, `list_inbox`, `track_job`, `generate_resume` — all over the data folder.
- **Claude Code skill** `find-jobs`: load prefs → wide search → rank → present, via CC subagents.
  Shipped as a small `claude-code/` folder (skill + MCP config) for technical friends; this is also
  Alex's own primary path.

## 6. Data flow (one cycle)

1. Resolve `USER_DATA_DIR`; load `preferences.{md,json}` (+ derived `user_config.json`).
2. Wide fetch across enabled sources → raw JobResults.
3. `preferences.json` hard-gate (drop sub-floor salary, wrong location, dealbreakers).
4. `match/scorer.py` cheap pre-score → keep top-N.
5. `rank_to_preferences` (bridge/API/MCP) → ranked order + rationale.
6. Write to inbox (`tracker.db`); GUI/CC presents; user tracks/applies.

## 7. Error handling & edge cases

- No prefs files → scaffold from templates + wizard; never crash on first run.
- No AI available (no key, user skips paste) → fall back to local pre-score ordering; clearly labeled.
- Read-only bundle dir → all writes go to `USER_DATA_DIR` (never `_MEIPASS`); `config._dir_writable`
  probe + `%LOCALAPPDATA%` fallback already exists, extend to user folder.
- Malformed AI JSON → existing `claude_bridge` tolerant parse (trailing-comma repair, span guard,
  echo-back token check from allfixes) applies.
- Frozen exe: global Tk exception handler (C4, in allfixes) surfaces errors instead of dead buttons.

## 8. Testing strategy

- Unit: `USER_DATA_DIR` resolution (arg/cwd/LOCALAPPDATA precedence, read-only fallback); template
  scaffolding; `preferences.json` hard-gate; `preferences.*` ↔ `user_config.json` migration;
  `rank_to_preferences` prompt build + parse for all three routes (mock API).
- Integration: first-run-from-empty → scaffold → wide search (no-key sources, cached) → gate →
  pre-score → mock-rank → inbox populated.
- MCP: tool-call smoke for each exposed tool against a temp data folder.
- Packaging: a build smoke (the `.spec` builds; exe launches; writes only under the data folder).
- Keep the suite ≥290 after merge; each phase adds tests and stays green.

## 9. Open items / risks

- **R1 — repo must be private before further push.** `experience.md` (real PII) is tracked and on
  `origin`. Confirm `alex-zagorianos/Job-Program` is private in Phase 0; never bundle it into the
  friend package (templates only).
- **R2 — his-data-never-ships** is a guarantee the build must enforce: the package builder bundles
  `*.template.*` + a neutral `companies.json`, explicitly NOT the working `experience.md`/prefs.
- **R3 — keyed sources** degrade gracefully to zero-key mode; the wizard must make "works with no
  keys" obvious so non-technical friends aren't blocked.
- **R4 — name/brand** "JobScout" is a package/README label only; if Alex wants a full rename it's a
  later cosmetic swap.

## 10. Phasing

- **Phase 0 — Harden** (mapped): confirm repo private → commit relaunch work → merge `claude-allfixes`
  (resolve 3 resume conflicts) → fold T4 `status_history` → drop 6 superseded delegate branches +
  prune worktrees → address remaining-open criticals not in allfixes (C1 recurrence guard) →
  verify ≥290 tests → push `master`. Done = clean master, tests green, branch landed.
- **Phase 1 — Data folder + preferences contract:** 3-tier paths, templates, `preferences.{md,json}`,
  scaffold + migration. Done = Alex's install runs from an external data folder; tests green.
- **Phase 2 — Wide-net + AI ranking:** wide fetch mode, json hard-gate, `rank_to_preferences` +
  hybrid routing. Done = wide search → tailored ranked inbox via bridge/API.
- **Phase 3 — EXE + setup wizard:** extend `app.spec`, package builder, README, first-run wizard.
  Done = a zip a non-technical friend can unzip + run + get tailored results.
- **Phase 4 — MCP + Claude Code skill:** stdio MCP server + `find-jobs` skill. Done = `claude` in the
  data folder runs a tailored search end-to-end.
