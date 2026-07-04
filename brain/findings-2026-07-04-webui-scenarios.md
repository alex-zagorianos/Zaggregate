# Web-UI Scenario-Testing Findings (S36, 2026-07-04)

Consolidated from the S36 journey-level scenario tests (plan:
`brain/test-plan-2026-07-04-webui-scenarios.md`). Each agent drove a realistic
user start-to-finish through the WEB HTTP surface (the same `webui/api/*`
routes the React app calls), against a throwaway Flask server on its own port
(>=5090) with an isolated `JOBPROGRAM_DATA` tmp dir. Real `projects/` and the
`:5002` preview server were confirmed untouched throughout; every test port was
confirmed freed on teardown.

**Journeys landed:** SC1 (fresh engineer, Cincinnati -- flagship), SC2 (nurse,
Columbus -- non-tech routing), SC3 (UK user, London -- international). SC4
(remote-only marketer) and SC5 (two-project concurrency) reports did NOT
arrive in the synthesis payload and produced no scratchpad artifact -- their
findings are NOT represented here (see Coverage Gap at the end; the
GO/NO-GO is scoped accordingly).

Findings are ranked severity-first, then deduped across scenarios. Every claim
carries the reporting scenario(s) + evidence.

---

## 1. Defects (ranked)

### MAJOR-1 -- Resume work-history silently dropped on a bare "Experience" heading, while onboarding reports success (SC1)

- **Where:** `ui/setup_wizard_core.py` (`structure_resume_text` / `_looks_like_heading`); `resume/experience_parser.py` (`_HEADING_ALIASES`, which intentionally excludes bare `EXPERIENCE`).
- **What happens:** Onboarding POST with a pasted resume whose work section is headed by a bare `Experience` line (an extremely common convention) returns `{"resume_restructured": true}`, but `structure_resume_text()` promotes only `## EDUCATION`; the name/title and the entire Experience block stay as unheaded orphan text, which `load_experience()` then silently drops. `GET /api/resume/prompt` for that candidate then renders EMPTY Contact/Summary/Skills/Work Experience/Projects -- the tailoring AI receives only the education line. The preview route `/api/onboarding/resume-structure` reproduces the identical drop with no warning.
- **Evidence (SC1):** resume_text with a bare `Experience` heading followed by `Manufacturing Engineer, Acme Corp, 2022-2026` + bullets -> saved `experience.md` shows only `## EDUCATION` promoted; built prompt CANDIDATE EXPERIENCE section empty except Education. `resume_restructured:true` returned despite the loss.
- **Why it matters:** Silent data loss on the highest-value input, on a very common resume format, reported as success -- directly degrades the core resume-tailoring feature with no user-visible signal. Also an "inclusion over precision" adjacency: content dropped, not surfaced.
- **Suggested fix (any of):** (a) alias a bare `Experience` line to `WORK EXPERIENCE` when the following lines look like a job entry (date range / bullet list) rather than excluding it unconditionally; or (b) when Path A promotes >=1 heading but leaves orphan non-blank lines before the first promoted heading, fold them into a `WORK EXPERIENCE` (or generic `OTHER`) section instead of dropping; or (c) minimum bar -- return a `resume_restructured_warning` / `unrecognized_lines` count whenever any non-blank line survives outside every recognized section, so the wizard can prompt the user to review the preview.

### MAJOR-2 -- Nursing daily source (RNJobSite) never fires for the exact industry string the wizard itself derives (SC2)

- **Where:** `search/rnjobsite_client.py` (`_should_poll`, `_NURSING_TOKENS` at :41-45); root also touches `industry_profile.py` (`resolve_soc` returns the verbatim O*NET title, :364).
- **What happens:** Onboarding a nurse (blank industry, nurse role text) persists `industry='Registered Nurses'` -- the PLURAL O*NET SOC title for 29-1141.00. `RNJobSiteClient._should_poll()` intersects tokens `{"registered","nurses"}` against `_NURSING_TOKENS`, which contains singular `"nurse"` but NOT `"nurses"` -> no overlap -> `active=False`. The one source built specifically for nurses contributes zero postings for a user who onboarded exactly as the wizard intends.
- **Evidence (SC2):** run log line `[rnjobsite] Inert for industry 'Registered Nurses' -- not a nursing field.` Inbox still populated (4 VA rows via USAJobs), but RNJobSite silently absent every run, no user-visible way to notice.
- **Why it matters:** Auto-derivation and source-gate disagree on plural vs singular, so a whole sector source is dark for its own target persona. `resolve_soc` can emit many plural titles (`Licensed Practical and Licensed Vocational Nurses`, etc.) -- a class bug, not a one-off.
- **Suggested fix:** Normalize tokens (strip trailing `s` / stem) before the set-intersection, ideally via a SHARED singularize/stem helper used by every industry-token gate (`_NURSING_TOKENS`, `_HANDSON_TEXT_SIGNALS`, `_KNOWLEDGE_TEXT_SIGNALS`, and sibling sector sources) rather than per-source plural patches.

### MAJOR-3 -- Country-gated US-only source skips (usajobs, careeronestop) are never surfaced in structured badges (SC3)

- **Where:** `webui/api/inbox.py` (`_badges` reads `applog.last_run_info -> keyless_skipped`); `search/source_registry.py` (`_usajobs`/`_careeronestop` call `ctx.slog.info(...)` on a country skip, never `ctx.note_keyless(...)`); `search/cli.py` (`skipped_keyless` out-param scoped to missing-FREE-key skips by design).
- **What happens:** For a London/`gb` project, USAJobs and CareerOneStop are correctly skipped by country gate, but `GET /api/inbox` -> `badges.last_run.keyless_skipped == ["jooble","careerjet"]` only (the two missing-API-key sources). Country skips exist only as free-text lines in the SSE/run log; no UI-consumable field reports them.
- **Evidence (SC3):** SSE log has `[usajobs] US-only source - skipped for 'London, United Kingdom' (country=gb).` and the careeronestop equivalent; badge array omits both. Scenario expectation ("US-only sources skipped AND surfaced in badges") only half met: skip=yes, badge-surfaced=no.
- **Why it matters:** The web UI cannot render an honest "US-only sources skipped for your country" badge -- a UK/international user has no in-app signal for why US sources contributed nothing. Related in spirit to SC2's keyless-badge honesty, but a DISTINCT root cause (country gate vs missing-key gate).
- **Suggested fix:** Fold country self-skips into `keyless_skipped` with a reason tag (`{"name":"usajobs","reason":"country"}`), or add a parallel `badges.last_run.country_skipped` list populated like `note_keyless` (a second `BuildContext` callback, e.g. `ctx.note_country_skip`, wired through `build_clients` `skipped_country` out-param).

### MINOR-1 -- Unknown/garbage `location_mode` fails CLOSED to "Local only" instead of OPEN to "All locations" (SC1)

- **Where:** `geo/filter.py` (`location_visible`); `webui/inbox_filters.py` (`filter_rows`).
- **What happens:** `GET /api/inbox?location_mode=NotARealMode` -> `shown=10` (identical to `Local only`), not `shown=19` (the `All locations` baseline). Mode strings matched against exact literals with no else-branch, so any typo / outdated frontend enum / API misuse silently narrows to the strictest local view.
- **Evidence (SC1):** `location_mode=NotARealMode` shown=10 == verified `Local only` shown=10; baseline (unset) shown=19.
- **Why it matters:** Direct inclusion-over-precision violation (CLAUDE.md: never silently over-drop; when ambiguous, keep the job).
- **Suggested fix:** Allow-list check in `location_visible`/`filter_rows`: any `location_mode` not in the known set behaves as `All locations` (fail-open), not the strictest mode.

### MINOR-2 -- Unknown `/api/*` routes (and literal `../` on download routes) return Flask's default HTML 404 instead of the `{ok:false,error}` JSON envelope (SC1, SC2, SC3)

- **Where:** app factory / blueprint registration -- `webui/__init__.py` (no `errorhandler(404)`); `scrape/browser_receiver.py`; download path `webui/downloads.py` (`send_locked`) + `webui/api/resume.py`.
- **What happens:** `GET /api/does-not-exist` -> HTTP 404, `Content-Type: text/html`, `<!doctype html>...404 Not Found` body. Same for a literal `../` traversal on a download route (`/api/resume/download/../../../../windows/win.ini`) -- Werkzeug path-normalizes and 404s at the routing layer before the view runs, so the app's own JSON containment check never fires. The frontend `client.ts` parses JSON only on a content-type match, so these surface as a generic `Request failed (404 Not Found)` with no real error string.
- **Evidence:** SC2 `GET /api/does-not-exist` -> HTML 404. SC1 `.../resume/download/../../../../windows/win.ini` -> Werkzeug HTML 404, whereas the URL-encoded `%2e%2e%2f...` variant -> correct JSON `{ok:false,error:"not found"}`. Security boundary holds both ways (no traversal ever succeeds); this is a response-SHAPE inconsistency, not a vuln.
- **Why it matters:** Response-envelope violation (a named cross-cutting hunt); a stale/typo'd route leaks a non-JSON page to an API consumer that contractually expects `{ok,error}` everywhere.
- **Suggested fix:** Register a Flask `errorhandler(404)` (and ideally 405/500) scoped to `/api/` (`request.path.startswith('/api/')`) returning `jsonify({ok:False, error:'not found'}), 404`. Normalizes routing-layer 404s too, closing both the unknown-route and literal-`../` cases in one place.

### MINOR-3 -- `.ics` event SUMMARY leaks raw snake_case round kind ("Phone_Screen interview") (SC1)

- **Where:** `tracker/service.py` (`write_round_ics` -- interpolates `kind` without humanizing).
- **Evidence (SC1):** downloaded `.ics` for a `phone_screen` round -> `SUMMARY:Phone_Screen interview - eightsleep` (underscore kept, only first letter capitalized).
- **Suggested fix:** Route the round `kind` through the existing `STATUS_LABELS`-style humanizer (`tracker/db.py`) -> `Phone Screen interview - eightsleep`. Generalize: humanize any snake_case internal enum before it hits user-facing copy (ICS SUMMARY, board labels, badges).

### MINOR-4 -- Reach badge "reason" hardcodes "mostly remote/tech jobs" even for non-tech fields where tech sources were already gated off (SC2)

- **Where:** `coverage/reach.py` (`badge_reason`, ~:247).
- **What happens:** `badge_reason()` unconditionally emits `mostly remote/tech jobs because {missing} {is/are} not connected` when a headline key (CareerOneStop/Adzuna) is missing and coverage isn't certifiable -- no branch for industry/field.
- **Evidence (SC2):** inbox was 100% VA nursing jobs in Columbus and all tech-skewed sources were gated OFF, yet `badges.reach.reason` returned the "mostly remote/tech jobs" string -- actively misleading copy for a nurse.
- **Suggested fix:** Parameterize `badge_reason()` by `is_knowledge_work(industry)`: for non-knowledge-work fields drop the "remote/tech jobs" clause (e.g. "coverage is uncertain because {missing} {is/are} not connected").

### MINOR-5 -- ATS "missing skills" surfaces rubric boilerplate as if it were required skills (SC2)

- **Where:** `webui/api/inbox.py` detail path -> engine `extract_skill_terms` in `match/scorer.py` (pre-existing engine-level extraction issue, not web-specific).
- **Evidence (SC2):** `GET /api/inbox/1/detail` `ats.missing` for a VA Nurse Practitioner posting -> `["nurse","practitioner","apn","np","education","practice","ii","dimension"]`; `ii`/`education`/`practice`/`dimension` are federal grade-scale/rubric boilerplate, not listable skills.
- **Why it matters:** Undermines perceived detail-pane quality on any long-form government/clinical posting (common across personas).
- **Suggested fix:** Stoplist for structural/rubric words (grade-level roman numerals, `education`, `experience`, `requirement`, `dimension`, `scope`, ...) in `extract_skill_terms`, or require minimum term specificity (drop short single-word matches not in a curated skills vocabulary).

---

## 2. Inefficiencies

1. **No web way to cap a daily run (`--max-pages`) -- every web run uses the CLI default `max-pages=2` (SC1, SC2, SC3).** `POST /api/runs/daily` -> `daily_run_core.run_ingest` hardcodes `sys.argv` = `['daily_run.py','--project',slug]` with no page/source knob. This is 2x the request volume the plan's "smallest realistic setting" called for and doubles outbound calls to paginated sources (Adzuna) on every web-triggered run. (Also why the plan's "max-pages 1" target was un-honorable via the web surface in all three journeys -- see Parity Gaps.)
2. **First-run wall time dominated by direct-career-page scraping (~700 s) (SC1).** SSE log: `[CareersClient] 1080 results in ~701.5s` on page 1, then `~0.2s` on page 2 (in-run memo). SC1 total daily run ~11m44s; SC3 ~12.5 min. The first pass over ~150+ company career pages is unavoidably slow and is the bulk of the wait before a first-time web user sees any inbox -- a real UX cliff for an onboarding flow (vs the CLI, where a batch wait is expected).
3. **Full `description` text retransmitted repeatedly across list/detail/board/applications (SC2).** For the same 2 tracked jobs, a multi-KB VA description was resent across `GET /api/inbox`, `/api/inbox/{id}/detail`, `/api/applications`, `/api/board` -- at least 4x in one session. List endpoints already have a `description_preview` pattern on the detail endpoint; applying preview-only to list/board would cut most of the duplication. (Related: per-row detail is an N+1 fan-out if a user opens several detail panes; may be a deliberate lazy-load tradeoff given payload size.)
4. **Testing-harness lesson, not a product defect (SC1, SC3):** a fixed-timeout SSE client (`curl --max-time 600` / a 5-min bash ceiling) misses the terminal `done` frame because real daily runs take ~11-12 min. A browser `EventSource` has no such cap and is fine; a fresh re-subscribe to a finished job replays all lines + `done` in ~130 ms. Any automated web-journey test on this endpoint needs a generous/unbounded timeout (or the poll-`GET /api/jobs/<id>` pattern SC3 fell back to).

---

## 3. Improvement ideas

1. **Surface "text fell outside a recognized heading" from the resume-structure preview** (`unrecognized_lines` count or `warning` string) so the wizard can prompt a review before finishing onboarding -- catches MAJOR-1 at input time. (Directly resolves MAJOR-1 option (c).)
2. **Add an optional `max_pages` / `fast` / "quick run vs deep run" field to `POST /api/runs/daily`**, threaded to `run_ingest -> run_main`, defaulting to current behavior for parity -- closes the top inefficiency and the top parity gap, and makes the S36 plan's own "max-pages 1" achievable over the documented HTTP surface.
3. **Expose sector-source inert/active status in the API** (e.g. `/api/settings/keys` or a new `/api/settings/sources`) so a nurse/teacher/trades user can see which free sector sources (RNJobSite, HigherEdJobs, REAP, Edjoin) are or aren't contributing -- today that lives only in the transient SSE log. (Would have made MAJOR-2 user-visible.)
4. **Shared humanize-label helper** for any snake_case internal enum before it reaches copy surfaces (ICS SUMMARY, board labels, badge text). (Generalizes MINOR-3.)
5. **Branch reach-badge copy on `is_knowledge_work(industry)`** so non-tech personas never see "mostly remote/tech jobs". (Resolves MINOR-4.)
6. **Blanket JSON error-envelope handler** for 404/405/500 scoped to the `/api` blueprint. (Resolves MINOR-2 across all leak paths.)
7. **ATS extractor stoplist / minimum-specificity filter** centrally in `extract_skill_terms`. (Resolves MINOR-5.)

---

## 4. Parity gaps (web vs tk / CLI)

| # | Gap | Reachable in tk/CLI | On web | Scenario |
|---|-----|---------------------|--------|----------|
| P1 | Run-shaping knobs (`daily_run.py --max-pages`, `--min-score`, source list, keyword scope) | Yes (CLI flags) | NONE -- `/api/runs/daily` takes no body/query params; always CLI defaults | SC1, SC2, SC3 |
| P2 | Per-source "why is this source inert for my industry" visibility | Visible in run log | Only in transient SSE log; `/api/settings/keys` covers keyed sources only, not free/gated sector sources (RNJobSite/HigherEdJobs/REAP/Edjoin) | SC2 |
| P3 | Multi-project registry / project switch | tk multi-project | `/api/project` shows `active:null, projects:[]` even after full onboarding + run + tracked apps; no web path observed that registers a project into `projects.json` | SC2 (noted; SC5 owns this and did not report -- treat as unverified) |

P1 is the load-bearing parity gap: it recurs in all three journeys and blocks a deliberately-cheap web run. P3 is only partially observed (SC5, which owned the concurrency/project-switch verification, is missing) -- do not treat P3 as confirmed.

---

## 5. Step-timing table (server-side, representative)

Reads are single-digit-to-low-hundreds ms; the only outlier is the daily run itself (a batch job, expected). No unexplained >2 s reads were found. SC1 timings are raw Flask view time (sub-ms possible on an isolated dir); SC2/SC3 include client round-trip.

| Step | SC1 (ms) | SC2 (ms) | SC3 (ms) |
|------|---------:|---------:|---------:|
| Bootstrap / status | 100 (up) | 124 | 2 |
| GET /api/onboarding | 2 | 159 | 1.6 |
| Onboarding POST (wizard) | 6 | 197 | 76.6 |
| GET /api/settings/keys | 1.4 | 124 | 1.6 |
| POST /api/runs/daily (start) | 134 | 161 | 123 |
| Daily run to completion (SSE) | ~704,000 (~11m44s) | ~5,000 shown* | ~754,000 (~12.5m) |
| GET /api/inbox (baseline) | 2 | 151 | 133 |
| Inbox filters (min_score/q/location_mode) | 2 | 159 | 80 |
| GET /api/inbox/{id}/detail | 2 | 148 | 11 |
| Track / dismiss | 11 / 16 | 220 / 139 | 12 |
| Bulk-dismiss + undo | 5 | 183 / 126 | -- |
| Export-for-AI | 6 | 129 | -- |
| Import synthesized scores | 243 | 152 | -- |
| Top picks | fast | 132 | -- |
| Board valid move | 14 | 135 | -- |
| Board invalid move (400/404) | fast | 127 | -- |
| Add round + `.ics` | 12 | 134 | -- |
| Resume prompt build | 75 | 218 | -- |
| Resume paste -> DOCX | 56 | 164 | -- |

\* SC2's SSE figure is stream-read time on a small (4-row) run, not the full ingest wall time; SC1/SC3 report true end-to-end ingest duration. Takeaway is consistent: all reads/mutations are fast; the daily ingest is the only long pole (~11-12 min, career-scrape-dominated).

---

## 6. GO / NO-GO -- retiring the tk tabs

**Verdict: CONDITIONAL GO for the journeys tested (SC1/SC2/SC3), NO-GO to retire tk wholesale yet.**

What the web surface proved it can carry end-to-end (all three journeys): onboarding + industry derivation, masked key handling + strict-origin security gate, daily run via SSE, inbox list/filter/detail, track/dismiss/bulk/undo, export -> AI-synthesize -> import round-trip, top picks, tracker + board (valid + invalid moves with correct 400/404 envelopes), interview rounds + `.ics`, resume prompt/paste -> DOCX, and funnel coherence (zero cross-bleed, arithmetic reconciled in SC1). International routing (Adzuna `/gb`) works through the web path. A complete flagship journey with no PASS->FAIL wall.

**Blockers before retiring the corresponding tk tabs:**

1. MAJOR-1 (resume drop) must be fixed or at least warned -- silent data loss on the resume tab is not acceptable to make web the only path.
2. MAJOR-2 (RNJobSite plural gate) -- a sector user loses a source silently; fix the token normalization (cheap) before non-tech users are web-only.
3. P1 parity gap (no run knobs) -- either accept the always-default run as intended web behavior OR ship `max_pages`; today the web user genuinely cannot do something the CLI user can.

**Explicitly unverified -- do NOT green-light on this evidence:**

- SC4 (remote-only marketer) and SC5 (two-project concurrency: cross-bleed, 409 same-project / exclusive-mutex, backup/restore round-trip, restore-during-run 409) were NOT reported. The S27-class cross-bleed guarantee and the concurrency-mutex behavior on the WEB surface are untested here. Retiring the multi-project / concurrency-sensitive tk paths must wait for SC4/SC5 to actually run.

**Recommended sequence:** fix MAJOR-1 + MAJOR-2 (both small, suite-greenable) and the MINOR JSON-envelope handler this session -> re-run SC4 + SC5 -> then reassess retiring the multi-project and remote tabs. The single-project engineer/nurse/UK journeys are close to web-only-ready; the multi-project story is unproven.

---

## Coverage gap (methodological, for the record)

Only 3 of 5 journey reports reached synthesis (SC1/SC2/SC3). SC4 and SC5 produced no payload and no scratchpad artifact; their scenarios -- remote-lane population + remote-badge rendering (SC4) and the entire two-project/concurrency/backup-restore suite (SC5) -- are absent from this report. Findings above are complete and load-bearing for what was tested; the GO/NO-GO is deliberately scoped to exclude the untested surface. Re-running SC4/SC5 is the top follow-up.
