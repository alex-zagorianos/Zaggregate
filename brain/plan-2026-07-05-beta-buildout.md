# Beta Buildout Plan (2026-07-05, overnight — BINDING for all builders)

Executes `brain/beta-roadmap-2026-07-05.md` Waves 1–3 plus the referral/ghost
designs agreed with Alex. Evidence: `brain/research-2026-07-05-beta-evidence.md`.
Orchestrator: Fable 5. Builders: Opus (sequential per phase). Reviewers: Sonnet.

## Global constraints (every builder)

- Python is ALWAYS `py -3.12`. Frontend: `npx tsc --noEmit` + `npx vitest run`
  from `webui/frontend` must pass; do NOT run `vite build` (orchestrator does).
- Knowledge graph: run `graphify query "<q>"` from repo root before broad
  source exploration; direct reads OK at contract-named anchors.
- PARITY-LOCKED, never touch: `match/scorer.py`, `ranker.py`,
  `preferences.py::hard_gate` semantics. `match/ghost.py` is NOT the scorer
  (advisory signal) but change it only where a contract says so.
- Inclusion over precision: new signals FLAG/SORT, never silently drop rows.
- webui package stays tk-free (`tests/webui/test_import_isolation.py`).
- Every new mutating route: `@require_local_origin` (route-audit meta-test
  enforces `__origin_gated__`). Envelope `{ok:true,...}/{ok:false,error}`.
- Frontend conventions: endpoints ONLY in `src/api/client.ts`; hooks in
  `src/api/queries.ts`; tabs via `src/tabs/registry.ts` + `TabRoutes.tsx`;
  Aegean tokens only (no raw hex / gray-*); serif headings `zg-serif`; mono
  numerals `zg-num`; shared components in `src/components/`; pure logic in
  `src/lib` with vitest tests.
- User data is gitignored (`projects/`, `tracker.db`, `preferences.*`,
  connections files) — NEVER commit user data; new user-data files go under
  the userdata dir (see `userdata.py`/`config.USER_DATA_DIR` patterns), and
  MUST be excluded by existing gitignore rules (verify).
- Tests REQUIRED for every behavior. Run the scoped suites you touch plus
  `py -3.12 -m pytest tests/webui/ -q` before committing.
- Commit at the end with `git commit --only <explicit paths you touched>`.
  NEVER `git add -A`/`.`. Do not push. Commit message ends with
  "Co-Authored-By: Claude Opus <noreply@anthropic.com>".
- If a contract assumption doesn't match the code you find, follow the CODE
  and note the deviation in your final report — do not invent parallel
  mechanisms.

## Phase 1 (sequential: B1 → B2 → B3)

### B1 — First-run success + update check + feedback

1. **Quick first run.** In `webui/api/runs.py::start_daily_run`: when the
   TARGET project has never completed a daily run (detect: no
   `last_run.json` in the project's output dir — reuse how
   `applog.last_run_info` resolves it) AND the request body does not set
   `max_pages`, default `max_pages=1` and emit a job log line via the
   handle: "First run: quick pass (1 page per source). Later runs go deeper
   automatically." Body-explicit values always win. Tests: first-run default
   applied; explicit body overrides; subsequent runs (last_run.json present)
   keep engine defaults.
2. **Expectation copy.** Frontend: Inbox empty state (when a run is active)
   and the run console header get one short line: first results land when
   the run finishes (a few minutes on a quick pass). Keep copy warm, no
   jargon.
3. **Update check.** New `webui/api/meta.py` blueprint: GET `/api/meta/version`
   -> {ok, version: config.APP_VERSION}; POST `/api/meta/update-check`
   (origin-gated) -> queries
   `https://api.github.com/repos/<config.UPDATE_REPO>/releases/latest`
   (stdlib urllib, 5s timeout), compares semver-ish tags to APP_VERSION,
   returns {ok, current, latest, url, newer:bool}; latest=null gracefully on
   ANY failure (offline, 404 private repo, no releases) — never an error
   envelope for network failure. Add `UPDATE_REPO = "alex-zagorianos/Job-Program"`
   to config.py. Cache result to a file under the userdata cache dir for 24h.
   Frontend: Settings menu gains "Check for updates" -> toast ("You're up to
   date" / "vX available — open releases page" w/ link). Tests: monkeypatched
   urlopen (newer/same/failure), cache honored, route gated.
4. **Feedback.** Add `FEEDBACK_EMAIL = "alexzagorianos@gmail.com"` to
   config.py; GET `/api/meta/feedback-target` -> {ok, email, subject}
   (subject includes version). Settings menu gains "Send feedback" ->
   `mailto:` built client-side from that endpoint (opens default mail app)
   with a short prefilled body template. Also mention where the
   report-a-problem zip lives if such a helper exists (check `applog` /
   help_core; if the zip builder is tk-only, just link the mailto — do NOT
   port it).

### B2 — Web create-project / new-person flow (biggest parity gap)

1. Read the existing project surface first: `webui/api/system.py` (or
   wherever GET `/api/project` and the project-switch route live) and
   `workspace.py` (`create_project`, registry shape, `registry_active_slug`,
   pin semantics, S27 rules). tk's App chrome (gui.py project menu) is the
   behavioral reference; web must NOT import tk.
2. API: POST `/api/project` (origin-gated) {name, person?} -> validates
   (non-empty name; slug derived the same way workspace does; duplicate ->
   409 {ok:false,error:"a project with that name already exists"}), creates
   via `workspace.create_project`, does NOT auto-switch unless
   {switch:true} passed; returns {ok, slug, projects:[...]}. Switching uses
   the EXISTING switch route (extend only if none exists; respect the
   exclusive-engine-job 409 guard that scenario testing added).
3. Frontend: the topbar project dropdown gains a separator + "New project…"
   -> dialog (Name, Person (optional, "who is this search for?"), checkbox
   "Switch to it now" default on). On success w/ switch: navigate to /inbox;
   the onboarding gate will appear naturally for the empty project (that IS
   the wizard flow). Person display: reuse how GET /api/project renders
   name/person today.
4. Tests: create + duplicate + validation + gating + switch integration
   (runner exclusive 409 respected); frontend lib logic (slug/name
   validation helper) vitest if any pure logic added.

### B3 — Trust docs + packaging

1. `PRIVACY.md` at repo root: the 5-line core ("Zaggregate runs entirely on
   your computer. Your resume, applications, and job data never leave your
   machine. No account, no telemetry, no data sale — nothing to sell. The
   only network calls are the job-source fetches you configure and an
   optional update check against GitHub. AI features work by you copying a
   prompt into the AI you already use.") + short details sections (what data
   lives where on disk; the browser extension talks only to 127.0.0.1; the
   optional update check; contact email). Plain language.
2. `EULA.txt`: short as-is beta disclaimer (no warranty; user responsible
   for complying with each job source's terms — they query sources on their
   own behalf; no affiliation with any job board). Do NOT add an open-source
   LICENSE (Alex's pending decision — note that in your report).
3. README.md: rewrite the top for the wedge (finds jobs for you across ~20
   sources; 100% local + private; free, no account; ghost-job shielding;
   BYO-AI; assisted-never-auto apply) + quickstart (exe modes: default tk,
   --desktop, --web) + link PRIVACY/EULA. Keep honest, no hype numbers.
4. Guide (`guide` content source — find where the in-app Guide sections come
   from, likely a markdown/py structure served by /api/guide): add a "Get
   referred — the numbers" section (referred candidates ~40% reach interview
   vs 2–3% cold; how to use the (upcoming) network import + warm-path
   prompts; outreach etiquette: one follow-up + thank-you) and a "Ghost jobs
   & how Zaggregate shields you" section. Follow the existing section
   format/tests exactly.
5. `build_package.py`: also emit `SHA256SUMS.txt` for the produced zip(s) +
   include PRIVACY.md/EULA.txt in the production folder layout. `packaging/
winget/` gets a manifest TEMPLATE (yaml, placeholders for version/url/
   sha256) + README-winget.md instructions — template only, no live PR.
6. QUICKSTART.md (repo copy that build_package ships): add the desktop-mode
   note if missing + privacy one-liner.

## Phase 2 (sequential: B4 → B5 → B6)

### B4 — Referral engine + warm-path prompt

1. New top-level module `network.py` (tk-free, import-safe):
   - `parse_connections_csv(text) -> list[dict]` — LinkedIn Connections.csv
     (handles the "Notes:" preamble LinkedIn prepends; columns First Name,
     Last Name, URL, Email Address, Company, Position, Connected On; be
     tolerant of column order/case) and Google Contacts CSV (Name,
     Organization 1 - Name / Organization Name variants). Rows without a
     company are kept but unmatchable.
   - Storage: `network.json` under the USER DATA dir (config.USER_DATA_DIR
     based, NOT per-project — connections are user-level; verify gitignore
     covers it; the file must never land in the repo).
   - `company_key(name)` — conservative normalize (lowercase, strip
     punctuation + legal suffixes via the same approach existing code uses —
     check `cleanco` usage in the codebase and reuse).
   - `matches_for(company) -> list[contact]` and
     `match_counts(companies) -> dict` (bulk, for list annotation).
   - `import_text(text, source:"linkedin"|"google") -> {added, total}` —
     MERGE by (name, company) dedup, never destructive; `clear()`.
2. API `webui/api/network.py`: POST `/api/network/import` (origin-gated;
   accepts {text, source} JSON — the frontend reads the file client-side and
   posts text; enforce a sane size cap ~5MB), GET `/api/network/summary`
   -> {ok, total, companies, last_import}, DELETE/POST clear (gated),
   GET `/api/network/company/<name>` -> {ok, contacts:[...]}. Register in
   api/**init** (marked line).
3. Surfacing: inbox DETAIL response (`/api/inbox/<id>/detail`) and the
   application detail (JobDialog data source) gain
   `network: {count, contacts:[{name, position}]}` (top 5) when matches
   exist — compute via network.matches_for(company), cheap. Frontend: a
   "Your network" block in the Inbox detail pane + JobDialog: "N people in
   your network work at {company}" + names/positions + a hint to reach out.
4. Import UI: Sources tab gains a "Your network (local)" card: choose file
   (.csv, parsed client-side via FileReader → POST text), shows summary
   (N contacts, M companies, last import), clear button, one-line privacy
   note ("stays on this computer"), and a "How to export from LinkedIn"
   help link/copy (Settings → Data privacy → Get a copy of your data →
   Connections).
5. **Warm-path prompt** (BYO-AI, prompt-only, no paste-back): new function in
   `network.py` (or `outreach.py` if B5 landed it — coordinate: B4 runs
   FIRST, so create `outreach.py` here with `build_warm_path_prompt(job,
contacts, experience_text, cfg)`): includes job title/company/description
   snippet, the user's matched contacts (if any), schools + past employers
   parsed from experience.md (reuse resume/experience_parser.load_experience
   or raw text), and asks the AI for: likely warm paths ranked (direct
   contacts, alumni, past-colleague diaspora, associations/meetups), exact
   LinkedIn search strings the user can run in their own browser, and 2
   outreach drafts (informational-interview ask + referral ask) in the
   user's voice, ≤120 words each, plus the one-follow-up rule. API: GET
   `/api/inbox/<id>/warm-path-prompt` + `/api/applications/<id>/warm-path-
prompt` -> {ok, prompt}. Frontend: "Find my path in" button (detail pane
   - JobDialog) -> PromptDialog (reuse `components/prompt-dialog.tsx`).
6. Tests: parsers (both formats, preamble, weird columns, dedup-merge),
   matching (suffix/case variants; no false positives across distinct
   companies), storage isolation (tmp dir), routes (gating, size cap,
   summary), detail enrichment, prompt content.

### B5 — Outreach drafts + interview prep (BYO-AI, prompt-only)

1. Extend `outreach.py`: `build_followup_prompt(app_row, stage)` (post-apply
   follow-up OR post-interview thank-you — pick wording by the application's
   status/rounds; embed the evidence rules: exactly one follow-up, always
   thank-you within 24h, ≤120 words, no groveling),
   `build_interview_prep_prompt(app_row, experience_text)` (role+company+JD
   -> likely interview areas, 10 practice questions incl. behavioral +
   role-specific, strong-answer sketches from the USER'S actual experience,
   questions to ask the interviewer, red flags to listen for).
2. API: GET `/api/applications/<id>/followup-prompt`,
   `/api/applications/<id>/interview-prep-prompt` -> {ok, prompt} (404
   unknown id). Frontend: JobDialog gains "Draft follow-up" /
   "Interview prep" buttons -> PromptDialog; the follow-up nudge surface
   (wherever follow-ups-due show — check Tracker) links "Draft it".
3. Tests: prompt builders (content varies by status; thank-you vs follow-up
   selection; experience folded in), routes.

### B6 — Insights tab (channel conversion + cadence)

1. FIRST inspect what the tracker actually stores: does `applications` carry
   `source`? (inbox rows do; check `inbox_track` copy behavior + columns.)
   Build with what EXISTS: per-source stats computed over applications
   joined with their statuses/status_history; if source is missing on
   applications, fall back to matching the application's original inbox row
   (job_key/url) — and if genuinely unavailable for old rows, bucket as
   "unknown" honestly.
2. New module `insights.py` (tk-free, top-level): `funnel()` (counts+rates:
   tracked→applied→interview(any round or status)→offer/accepted; plus
   ghosted count), `by_source()` (per source: applied, interviews,
   interview_rate; ONLY display sources with ≥1 applied; no benchmarks
   hardcoded beyond a one-line static context note), `cadence(weeks=8)`
   (applications/week from date_applied; current week; streak; the 10–20/wk
   guidance band as constants). All read-only over tracker db.
3. API `webui/api/insights.py`: GET `/api/insights` -> {ok, funnel,
   by_source, cadence}. Register (marked line).
4. Frontend: new tab "Insights" (registry between Board and Resume; Compass
   is taken — use a chart icon (BarChart3)). Sections: funnel row (big
   zg-num numbers + conversion %), "Where your interviews come from" table
   (source, applied, interviews, rate — with an honest empty state before
   enough data: "Track a few applications and this fills in"), cadence bar
   chart (pure CSS/divs — NO new chart dependency), weekly target band copy
   ("steady 10–20 quality applications/week beats bursts — the data says
   consistency wins"). All read-only.
5. Tests: insights.py units (fixture db: multi-source apps w/ statuses +
   rounds; rate math; unknown-source bucketing; empty db), route test,
   vitest for any pure lib helpers (week bucketing done server-side is fine
   — prefer server-side).

## Phase 3 (B7)

### B7 — Ghost shielding surfaced + speed signals + copy pack

1. **Ghost badge on rows.** `webui/serializers.py::inbox_row_list` gains
   `ghost: {level, reasons[]}` from `match/ghost.py::ghost_score` (already
   cached day-bucketed; verify cheapness). Frontend Inbox: subtle badge for
   level=="stale"/"aging" (tooltip lists reasons; e.g. "Reposted 3×",
   "Posted 45+ days"). NEVER hides rows (the existing opt-in filter stays
   the only hiding mechanism).
2. **Longevity.** If ghost.py's signals don't already include "seen across
   multiple runs / first_seen age", check what job_key/repost history
   provides (S29 job_key coalescing + repost decay) and surface what EXISTS
   in the reasons list — do not build new engine history mechanisms.
3. **Company ghost memory.** `insights.py` (from B6) or `tracker/service.py`
   read-only helper: companies where the user has ≥1 application with
   status "ghosted" → inbox detail + JobDialog show "⚠ This company ghosted
   you before (N times)". Tests included.
4. **Posting-age urgency + new-since-last-visit.** Inbox rows already carry
   created/first-seen data (check what the list serializer sends; postedLabel
   exists in lib/relative-time). Add: age >30d gets the muted "aging" tint
   via the ghost badge (no separate mechanism); "new since last visit" =
   frontend-only: localStorage stamp per project of last Inbox visit; on
   load, count rows whose new-batch stamp/created is newer → banner chip
   "N new since your last visit" (clears on view). Pure lib logic +
   vitest.
5. **Copy pack.** Apply Queue detail gains "Copy application pack" → builds
   plaintext block server-side: GET `/api/queue/<id>/copy-pack` -> {ok,
   text} with contact fields from config/experience (name, email, phone,
   location, links if present in experience.md contact section), work
   history one-liners, education, and the job-specific tailored-resume file
   path if one was generated. Frontend copies to clipboard (reuse
   lib/clipboard). Tests: pack content, missing-fields grace, route.

## Review protocol (orchestrator runs after each phase)

3 Sonnet reviewers over the phase diff (correctness+contracts / security+
privacy (origin gating, user-data paths, no telemetry) / UX+conventions) with
structured findings → adversarial verify → fix wave → suite+vitest+build
green → phase commit(s) already in place.

## Final (orchestrator)

Full pytest + vitest + tsc + vite build; static commit; PyInstaller rebuild +
production/ mirror + desktop smoke; KNOWN_ISSUES/project-status/_index/
handoff/vault-HANDOFF/memory updates; graph mtime check. PUSH HELD.
