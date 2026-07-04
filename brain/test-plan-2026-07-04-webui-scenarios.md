# Scenario Testing Plan — Web-UI Migration (S36, 2026-07-04)

Purpose: drive realistic users start-to-finish through the WEB surface (HTTP
API against a live local server, mirroring what the React app calls) and hunt
errors, inefficiencies, and improvement areas. Complements the deep-test plan
(unit/contract); this is journey-level.

Method: each scenario = one agent + one throwaway server process on its own
port (>=5090) with an ISOLATED `JOBPROGRAM_DATA` tmp data dir (real user data
untouched). `.env` keys resolve via env precedence, so keyed sources (Adzuna)
are live — mirroring the S35b validation lanes; daily runs use max-pages-1
equivalents where configurable and run SEQUENTIALLY (API politeness + the
one-run-at-a-time engine assumption). Every scenario records: step → expected
→ observed → verdict, timings per step, HTTP errors, and journey friction
(missing affordances vs the tk app, confusing responses, extra round-trips).

## Scenarios

- **SC1 — Fresh engineer, Cincinnati (the flagship journey).** Bootstrap →
  onboarding status (expect not onboarded) → wizard POST with blank industry
  (expect industry_detected derivation) → keys list (masked) → daily run via
  /api/runs/daily consuming the SSE stream to completion → inbox list +
  filters (min_score, q, location_mode) → detail → track 2 / dismiss 1 / bulk
  dismiss + undo → export-for-AI → synthesize scores file → import → top picks
  populated → tracker views → board move (valid + invalid target) → rounds +
  ics download → resume prompt → paste → DOCX download. End: funnel coherent.
- **SC2 — Nurse, Columbus (non-tech routing).** Same skeleton, nursing roles,
  blank industry (derivation must go non-generic); verify tech-skewed sources
  gated off in the run log; inbox has healthcare rows; keyless-skip badges
  present and honest.
- **SC3 — UK user, London (international).** Onboard w/ London; daily run;
  verify Adzuna /gb routing works through the web path (S35b's country-tail
  fix intact), US-only sources skipped AND surfaced in badges; local rows
  visible under default location mode.
- **SC4 — Remote-only marketer.** Remote-only preference; verify remote lanes
  populate, location filter modes behave, remote badges render in data.
- **SC5 — Returning user, two projects + concurrency.** Create 2nd project via
  engine (NOTE: if the web surface lacks a create-project flow, record as a
  finding — expected gap); switch via POST /api/project; verify no cross-bleed
  (S27 class: rows land in the right DB); start a daily run then immediately
  attempt a second (expect 409 same-project) and a run on the other project
  (expect 409 exclusive-mutex); backup download/restore round-trip on the tmp
  data dir; restore-during-run 409.

## Cross-cutting hunts (every agent)

- Response-envelope violations (non-JSON errors, HTML 500s).
- Latency outliers (>2s for reads, unexplained).
- Chatty patterns the UI would suffer (N+1 detail calls, missing batch ops).
- Parity gaps vs tk (features reachable in tk but absent on web) — LIST them.
- Copy/UX issues visible in API responses (badge text, error phrasing).
- Inclusion-over-precision violations (anything silently dropped).

## Deliverable

`brain/findings-2026-07-04-webui-scenarios.md`: consolidated findings ranked
by severity (errors → inefficiencies → improvements), each with evidence and
a suggested fix; plus a GO/NO-GO read on retiring the tk tabs. Confirmed
in-scope defects get a fix pass (suite green); larger items become the
next-session queue.
