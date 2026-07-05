# Handoff — 2026-07-05 Session 37 (overnight beta buildout)

Alex (going to sleep): "Make/use the plan to implement everything we have
discussed. Use opus subagents to build out the full list of things we
needed/should do before beta testing — go all the way."

Plan: `brain/plan-2026-07-05-beta-buildout.md` (binding contracts). Evidence
base: `brain/beta-roadmap-2026-07-05.md` + `research-2026-07-05-beta-evidence.md`.
Seven Opus builders, sequential, three phases; a Sonnet review fleet +
adversarial refuters after every phase; all confirmed findings fixed the same
night. **Suite 3,104 passed / 0 failed (was 2,968); vitest 199/21 files; tsc +
vite build clean; exe rebuilt + production/ mirrored + frozen web smoke. PUSH
HELD (~14 commits tonight).**

## What shipped (by phase)

**Phase 1 — beta blockers**

- B1 `2a06c95`: first-run **quick pass** (a project's very first daily run
  defaults max_pages=1, one console line explains it; body override wins);
  warm expectation copy while a first run streams; **update check** (Settings →
  "Check for updates": GitHub releases, 24h cache, graceful null on any
  failure; config.UPDATE_REPO) + `/api/meta/*`; **Send feedback** (mailto to
  config.FEEDBACK_EMAIL, version-tagged subject).
- B2 `c2ad8da`: **web create-project / new-person flow** — the biggest parity
  gap closed. Topbar dropdown → "New project…" dialog (name, optional person,
  switch-now default on) → POST `/api/project/create` (validation 400,
  duplicate 409, origin-gated, pin-aware pending switch). Onboarding wizard
  appears naturally for the fresh project.
- B3 `35985c5`: **PRIVACY.md** (5-line core), **EULA.txt** (as-is beta +
  you-query-sources-on-your-own-behalf; LICENSE = Alex's pending call),
  README wedge rewrite, two Guide sections (referral numbers + ghost
  shielding), build_package emits **SHA256SUMS.txt** + ships trust docs,
  `packaging/winget/` manifest template.

**Phase 2 — outcome-movers (all BYO-AI, zero API keys)**

- B4 `d2e8198`: **referral engine** — `network.py` + `/api/network/*`:
  LinkedIn Connections.csv / Google Contacts import (client-side file read →
  local store at USER_DATA_DIR/network.json, gitignored, never leaves the
  machine), canonical company matching, "Your network: N people at {company}"
  in Inbox detail + JobDialog, Sources-tab import card, **"Find my path in"**
  warm-path prompt (ranked paths, self-run LinkedIn search strings, 2 outreach
  drafts, one-follow-up rule) via `outreach.py`.
- B5 `6bb97c5`: **Draft follow-up / thank-you** (stage auto-selected from
  status/rounds; etiquette rules embedded) + **Interview prep** prompt
  (10 questions, STAR sketches from the user's real experience, questions to
  ask, red flags) — JobDialog buttons + Tracker "Draft it" link on due rows.
- B6 `8f029ba`: **Insights tab** — funnel (tracked→applied→interview→offer→
  accepted + rates), "Where your interviews come from" per-source table,
  pure-CSS weekly cadence chart + 10–20/week guidance. `insights.py` wraps the
  existing tracker analytics; applications DO carry source (no fallback
  needed).

**Phase 3 — differentiators**

- B7 `8588a22`: **ghost badges on Inbox rows** (`ghost:{level,reasons}` in the
  list serializer; subtle amber Aging/Stale chips w/ humanized tooltip —
  flags, never hides), **company ghost memory** ("This company left you on
  read before (N×)" in detail + JobDialog), **new-since-last-visit** banner
  (per-project localStorage), **copy application pack** in Queue detail
  (contact/work/education plaintext + tailored-resume path). Guide ghost
  section verified truthful post-ship (no hedging needed).

## Review waves (all confirmed findings fixed same-night)

- P1: **CRITICAL** `017c0d9` — workspace.create_project's fresh-registry
  repair silently overrode make_active=False (switch:false ignored on first
  project); now prefers the default root. + spinner minor `e96a205`.
- P2: 1 minor `8399081` — network dedup collapsed distinct no-company
  contacts sharing a name (position now widens the key).
- P3: 1 major `8f3f84c` — detail-pane GhostBanner guarded on a nonexistent
  "warn" level so Aging rows showed nothing there while the list badge showed;
  banner now covers stale+aging.
- Orchestrator: `cc4ae26` — B3's README rewrite broke the pre-existing
  positioning-copy pins (test_positioning_copy); the cited "Why Zaggregate"
  section restored.

## Verified live (dad's real project)

Insights tab (121-tracked funnel + source table + cadence), Inbox ghost
badges (real Aging/Stale rows), first-run copy, all on the restarted :5002
preview. Frozen exe rebuilt with the final bundle; production/ mirrored; the
env-gated web smoke validated the packaged app serves the new routes+static.

## Needs Alex (morning list)

1. **Eyeball the app** — http://127.0.0.1:5002/app (or
   `production\JobProgram\JobProgram.exe --desktop`): New project… flow,
   Insights, ghost badges, network import (Sources), the four new prompt
   buttons (JobDialog + Inbox detail), copy pack (Queue), Check for updates +
   Send feedback (settings menu).
2. **Push decision** (~14 commits held tonight).
3. **Beta-cohort go**: cohort recruiting + the free API keys (previous list)
   - the LICENSE choice (EULA §6 placeholder) + Microsoft Store / signing
     decision (Store registration is FREE now — see roadmap §3).
4. **Try the referral flow yourself**: export LinkedIn connections (Settings →
   Data privacy → Get a copy of your data → Connections) and import in
   Sources — then open any tracked job.

## Still queued (post-beta / not tonight)

Filter URL sync · ATS autofill assist (research says review-before-submit
only) · sector source for mech/manufacturing · local-IMAP status detection
(market-wide gap = differentiator) · get_conn() reuse redesign · Windows
toast for high-fit matches.
