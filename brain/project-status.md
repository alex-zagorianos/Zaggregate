# Project Status

#status #roadmap

---

## Session 43 (2026-07-06 evening, same conversation) — src/ LAYOUT RESTRUCTURE ★LIVE on the public repo ✅

Alex approved the full restructure (root = README/LICENSE/docs + src/; exes
stay in Releases). **`3abf007` (489 files: 480 pure git-mv renames + 244
content lines), private pushed, public fast-forwarded `22c2dc6..d56ca51`.**

1. **Keystone:** config.py dev anchors DIVERGED — `_get_data_dir()` stays
   `.parent` (= src/, bundle assets moved with code); `_get_user_data_dir()`
   → `.parent.parent` (= repo root; projects//output//.env/preferences/dbs
   did NOT move); dotenv anchored to repo-root .env. Consequence: tracked
   `src/companies.json` = SEED; user copy auto-seeds at root (now gitignored
   `/companies.json`) — ship registry changes via the src seed.
2. **Re-pointed:** build_package ROOT/SRC split (PyInstaller runs src/app.spec
   cwd=repo → dist//production/ unchanged; app.spec needed ZERO datas edits —
   spec-relative); **4 daily lanes re-registered `py src\daily_run.py`**
   (Task-Scheduler-verified + real-project db-path proof); receiver runs from
   src (live real-data check); run_servers/setup_schedule bats; claude-code
   .mcp.json → src/mcp_server.py + packaged-install clone note; conftest
   inserts src/; 6 path-reading tests re-anchored; docs sweep (README w/
   Download link, ARCHITECTURE map, BUILD, USER-GUIDE, CLAUDE.md).
3. **Review-fleet catches fixed pre-push:** ★.gitignore root-anchored patterns
   were silently stale after the move (legacy PII scratch incl. dad's config
   would have staged on `git add -A`; frontend node_modules; the *.pem +
   app.spec negation exceptions) — all re-pointed + `git check-ignore`
   verified. ★Packaged claude-code channel had no mcp_server.py source —
   README now routes packaged users to clone the repo (JOBPROGRAM_DATA points
   at their data).
4. **Verified:** pytest 3,248/2-skip · vitest 237 · exe rebuilt from
   src/app.spec + frozen-smoked · zip byte-identical (1,430 entries, PII
   clean) · graphify rebuilt. Recon = 3-lens census fleet (82 items) before
   touching anything; plan doc purged from public history (runbook list
   updated; public HEAD = private HEAD − 5 files).

Canonical: [[handoff_20260706_session43]] + [[plan-2026-07-06-src-layout]].

**S43b — in-repo `Executables/` download folder ★LIVE (`2bc4af4` → public
`2cba1ec`):** repo root gained `Executables/` = the single ready-to-run zip
(46.5MB, under GitHub's 100MB blob limit) + SHA256SUMS + plain-English README
(3 steps, launcher names, SmartScreen note). Rationale: a GitHub FOLDER can't
be downloaded by itself, so the folder carries the one-click zip; also fixes
that the README's Releases link 404s until the release exists.
`build_package.zip_package()` now calls `refresh_executables()` — zip + sums +
version-stamped README regenerate every build, stale-version zips dropped (a
new kit test pins it). Root README download links point at the folder. Raw
download URL live-verified (HTTP 206 stream). Trade-off on record: ~46MB per
version lands in git history; when the Releases/Velopack pipeline is live,
consider slimming the folder to a pointer README (drop the blob via the
republish rewrite). Suite 3,250/1-skip.

## Session 42 (2026-07-06 PM, same conversation) — ★PUBLISHED to github.com/alex-zagorianos/Zaggregate ✅

Alex: "change what is needed to turn the repo public" → executed the runbook
end-to-end; he created the repo (public) and the verified mirror is LIVE
(master `707581d`, 628 commits). Old `Job-Program` stays private forever.

1. **History rewrite (3 passes on fresh mirrors):** git-filter-repo, master
   only (delegate/* + remote refs dropped), 8 purged paths (résumé, 2 user
   configs, session-24 handoff root AND docs/handoffs copies, both dad
   evaluation notes, the runbook itself) + replacements.txt redactions
   (address/phone all formats + bare fragments, family first name all case
   variants, personal resume filename). Public HEAD tree = private HEAD minus
   4 files, verified by diff.
2. **Verification:** direct greps (every pattern → 0 across all 628 commits,
   messages/authors/refs/notes clean) + TWO 4-lens sonnet scan fleets w/
   completeness critic. Fleet 1 was invalidated by my own broken grep recipe
   (see gotcha) — fleet 2 (fixed recipe + mandatory sanity-check) returned
   NO-GO with 3 upheld blockers, all fixed: session-24 docs/ copy survived the
   root-path purge (S31 reorg had moved it); the redacted resume filename
   variant survived case-sensitively in ~424 historical blobs; dad evaluation
   notes = career dossier beyond the accepted "Dad" framing (employer, resume
   metrics, fit-scored real postings) → purged both.
3. **Repo-ref fixes `f0f37fb`:** config.py UPDATE_REPO default + EULA URL →
   `alex-zagorianos/zaggregate`; scrape health-probe UAs → zaggregate.
   **`6124cb2`:** runbook de-fragmented (never quote redaction patterns in
   tracked files — v1 of the runbook was itself a carrier) + expanded purge
   list; brain/README private-notes note; coverage-research links → relative.
   Suite 3,247/2-skipped. Both pushed to private origin.
4. **★GOTCHAS (verification-critical):** (a) `git rev-list --all | xargs git
grep -l <pat> -- ` — the trailing `--` shifts SHAs into pathspec position;
   in a bare repo that errors, and with stderr suppressed it reads as "0
   hits". Always sanity-check history greps against a known-hit pattern
   first. (b) filter-repo --replace-text literals are case-sensitive — carry
   all case variants. (c) GitHub CLI installed via winget but unauthenticated
   (`gh auth login` = Alex); repo was created by Alex in the web UI instead.

Accepted residuals (Alex's S41 framing): "Dad" label + aggregate search-story
mentions in the journal; author email; local E:\ folder-path prose in old
notes. Staging record: `%USERPROFILE%\job-program-public-release\PUBLISH.md`.
Open: repo About/topics (needs gh auth or web), auto-update pipeline build,
re-publish flow = runbook + `push --mirror`.

**S42b (same day) — v1.0.0 RELEASE STAGED + REPUBLISH:** fresh
`build_package.py` → `dist/Zaggregate-v1.0.0.zip` (46.5MB) + SHA256SUMS;
zip PII-scanned (experience.md = blank template; only accepted contact email
in EULA/PRIVACY); frozen smoke passed (exe alone on 5002 verified — killed dev
receiver first, restored after; port co-bind trap respected). README quick
start now links `/releases/latest` (`d060fd3`); mirror re-run → public master
**`c9a33f1`** (★rewrite is DETERMINISTIC — identical prefix SHAs, push was a
fast-forward, no churn for cloners). Release creation = Alex:
`gh auth login` then `%USERPROFILE%\job-program-public-release\release.ps1`
(release + About/topics in one go), or web-UI draft w/ the 2 dist/ files.

## Session 41 (2026-07-06 early AM, same conversation) — AGPL + PUBLIC-PREP DEEP CLEAN ✅

Alex: license adopted → deep-clean audit before going public. **★PUSHED
`969770b..6db3f8d`** (4 commits). Suite **3,249/0**, vitest 237.

1. **AGPL-3.0 adopted** `0890217` (LICENSE + README section w/ DCO note + EULA
   §6 grant reference) — reversible while sole-author, keeps institutional
   dual-license door open. Repo still PRIVATE.
2. **4-Opus-auditor fleet** (history PII / backend / frontend+docs /
   structure): ★history verdict **NO-GO as-is** — résumé in ~280 commits,
   dad-config + phone-in-prompt history; secrets/DBs clean across all 624
   commits. Remediation = `brain/public-release-runbook.md` (filter-repo on a
   fresh mirror → publish to a NEW repo; replacements.txt lives OUTSIDE the
   repo at %USERPROFILE%\job-program-public-release\). Alex flips visibility
   himself. Structure: nothing improper tracked; zero safe root moves (all 24
   root modules imported/entry points — src-layout stays registered debt).
3. **Fix wave (3 Opus builders):** `196e71b` product name unified to
   **Zaggregate** everywhere user-visible (title bar was "Job Search Tools",
   exe properties/claude-docs/backups were "JobScout") + ~48-site
   depersonalization sweep + dead-code deletions (scorer `_parse_money`/
   `_HOURLY_CTX`, schema `_LazyPromptTemplate`/`PROMPT_TEMPLATE`, wizard
   scaffolding) + silent-failure surfacing (ranker profile-summary, gui
   rolling_backup) + scorer/facts/network docstring truth-fixes + tracked-PII
   scrub (family name → "Dad", salary figures dropped); `2bbb77a` 73 scraper
   print()→applog via scrape/_log.py diag() (console byte-identical,
   capsys-safe); `7e89961` docs set — README rewritten (pins intact, 2 real
   screenshots) + **docs/ARCHITECTURE.md** (concepts+codebase lenses, 3
   mermaid) + **docs/USER-GUIDE.md** + BETA-WALKTHROUGH de-personalized+tracked
   - brain/README.md journal framing; `6db3f8d` screenshots + runbook.
4. Dead-code sweep verdict across ui/webui/tracker/match/search/discover:
   only the 4 deleted symbols — codebase unusually disciplined.

Production exe rebuilt post-clean (Zaggregate file properties). Needs Alex:
run the public-release runbook when ready to flip; auto-update pipeline calls.

---

## Session 40 (2026-07-06 overnight, same night as S39) — AI-FIRST SETUP shipped + review fleet + searches + cleanup ✅

Alex approved the design then slept; Opus builders implemented everything.
Suite **3,247 / 0** (2 headless-tk skips), vitest **237**, bundle current.
**S40b (morning): ★PUSHED `e298bd2..aeed3fe` + production exe REBUILT +
frozen-smoked (serves `index-mlVew1_R.js`; production now carries S39+S40).**
**LICENSE DECIDED (S40b, Alex): AGPL-3.0 adopted + pushed `0890217`** (LICENSE

- README section w/ DCO note + EULA §6 grant reference; dual-license door for
  institutions kept open). Repo still PRIVATE — going public needs the
  PII-in-old-history sweep first (S34 note stands).
  GOTCHA: Claude desktop's chrome-native-host.exe had the production
  VCRUNTIME140.dll mapped → rmtree Access-denied; kill the native host (respawns)
  to release. Canonical:
  `docs/handoffs/handoff_20260706_session40.md` + `brain/plan-2026-07-06-ai-first-setup.md`.

1. **"Paste one reply, start searching"** = THE setup path now: combined
   config+seeds prompt (`build_full_setup_prompt`/`split_full_reply`),
   `POST /api/ai-setup/apply-full` → sync config apply + ONE exclusive job
   (seed-probe → quick first run via shared knobs helper); wizard landing step
   = inline AI panes (manual = quiet link); Search tab "Set up with AI";
   Guide re-led. Live-verified 3× in a real browser: one paste → config +
   starter companies + first search streaming in the Inbox console →
   auto-refetch on done.
2. **Two live-test bugs found by clicking, both fixed same night**: handoff
   consumed only on InboxTab mount (takeover overlays a mounted Inbox) →
   location.key-keyed consume `4e4a2b0`; shared SSE reconcile silently
   detached at the finish boundary + failed path never invalidated →
   resubscribe + onFailed invalidation `91b8697` (benefits all consoles).
3. **Review fleet** (12 Opus agents, 4 dims → adversarial verify): 6 confirmed
   / 2 refuted → ALL fixed `23c7efd` (seed-leak span pin, ★job-thread WAL
   release, ★harvest silent-drop surfacing w/ ext-compatible `inbox_error`,
   stale console handlers, inbox row memoization, prompt-fetch abort).
   Findings: `brain/review-2026-07-06-s40-fleet-findings.json`.
4. **Searches + picks**: all 5 projects ran (log `logs/s40_runs.log`); 2 Opus
   curators → `output/job-picks-2026-07-06.md` (11 Alex / 8 dad). Scoring
   tune-ups surfaced: title-seniority-blind ranking, offshore-remote loc
   over-credit, cross-board dupes (need Alex's parity approval).
5. **Cleanup**: 19 test profiles deleted (8 real projects remain; mecheng/eng2/
   proj-x flagged for Alex); ClaudeWork strays → `_archive/zag0005-cleanup-2026-07-06/`.

New debt: residual DB-lock class (live request threads cache other-project
conns — matters for a future delete-project feature). Needs Alex: production
exe repackage, scoring tune-up GOs, mecheng/eng2/proj-x ruling, wave-3 GOs.

---

## Session 39 (2026-07-06 overnight) — dead project switcher fixed + Alex's 4-lane session ✅

Suite **3,221 / 0**, vitest 217, bundle rebuilt. Committed locally, PUSH HELD.
Canonical: `docs/handoffs/handoff_20260706_session39.md`.

1. **Switcher bug (Alex report)**: the webui launch pin ate every in-app
   project switch — persisted to registry, never went live, UI snapped back
   mute. Fix: `webui/api/system._go_live_or_pending` MOVES an idle pin (no
   exclusive engine job) on switch/create+switch; `pending_pinned` only for a
   real in-flight run. Frontend: `SwitchProjectResponse` type + toasts on
   pending/error. Tests split idle-pin vs running-engine (TDD, red→green).
2. **Ops**: dev receiver AND the S38 production JobProgram.exe (--desktop,
   EMPTY `production\JobProgram\data` root) were BOTH bound to 5002
   (SO_REUSEADDR) — the exe answered `project:null` intermittently. Both
   killed; one clean dev receiver runs the fix (live-verified round-trip).
   Production exe still has OLD code — repackage before next swap. New debt:
   port-conflict guard; run-finally unpin destroys the launch pin
   (save/restore semantics).
3. **Alex's session**: active=applied-ai; daily lanes EXCLUSIVELY applied-ai /
   software / controls / mechdesign (controls-cincinnati OFF); per-project
   schtasks 07:30–07:45; legacy bare `\JobSearchDaily` deleted (restore cmd in
   handoff). No data wiped.

Needs Alex: production repackage GO · wave-3 GOs (IMAP status, ATS autofill).

---

## Session 38 (2026-07-05 evening) — desktop chrome + full queue buildout + tech-debt sweep ✅

Alex testing live. Three directives, all landed same night (suite **3,218 / 0
failed**, vitest 217, exe **91.8MB** was ~141MB, frozen smoke green;
**★PUSHED origin/master `d6d385a..dce252a` — 37 commits, pre-push scan
clean**). Canonical: `docs/handoffs/handoff_20260705_session38.md`.

1. **Title bar/icon**: `webui/native_win.py` (ctypes, tk-free) — Z mark
   (`scripts/make_icon.py` → committed .ico + favicon.svg, app.spec icon=),
   WM_SETICON + AppUserModelID, DWM caption painted Aegean Paper/Night, live
   theme sync via pywebview js_api ThemeBridge. Verified on the real window.
2. **Previous-session queue ALL BUILT**: get_conn() thread-cache redesign
   (53x/call, deterministic close-all, S27-pin safe, nested-txn semantics
   preserved) · URL-synced Inbox filters · metro CBSA multi-city fix ·
   breadth-floor tests (18 keyless/558 companies) · jobs.ac.uk retired
   (upstream deleted ALL feeds — verified) · opt-in Windows toast on high-fit
   matches (ctypes; live-smoked, Win64 WNDPROC bug caught+fixed) · **NSPE
   mech/mfg sector source** (keyless RSS, self-gating, 31 live items) ·
   IMAP-status-detection + ATS-autofill **design briefs awaiting Alex GO**.
3. **US-first** (Alex): non-US metro table + intl source work dropped from
   backlog; existing intl support stays (self-gating); language guard now
   arms from the ACTIVE project's country.
4. **Tech-debt sweep**: 16-agent fleet → `brain/techdebt-register-2026-07-05.md`
   (39 findings; orchestrator hand-verified — finder errors on
   test_application_cycle + gitignored-personal legacy/ caught). Fixed waves
   D1–D4: retired :5001 tracker DELETED + report links now deep-link the web
   Inbox · frontend lazy per-tab chunks (821→495KB main) + useQueryGuard +
   dead dep/directives · shared parity-proofed HTML stripper (13 files) +
   dateparse dedup + salary-classification reuse + error guards + zero real
   test sleeps · exe excludes unreachable numpy/HF chain (−49MB) + packaging
   hygiene. Deferred (registered): pyproject root-fix, db.py split,
   search→ui layering, tab_inbox split, gui.py lazy-tk, conftest tmp_db.

Needs Alex: swap the running window to the final build · wave-3 GOs ·
push (~38 commits) · LICENSE · free keys (Jooble = 500-request starter
bucket, not load-bearing) · tk-retirement/exe-default/Discover decisions.

---

## Session 37b (2026-07-05 OVERNIGHT) — BETA BUILDOUT: all 3 waves shipped ✅

Alex slept; 7 Opus builders + 3 Sonnet review fleets executed
`brain/plan-2026-07-05-beta-buildout.md` end-to-end. **Read-first:
`docs/handoffs/handoff_20260705_session37.md`.** Shipped: first-run quick pass

- update check + feedback (B1) · **web create-project/new-person flow** (B2 —
  the last parity gap) · PRIVACY/EULA/README-wedge/Guide/SHA256SUMS/winget
  template (B3) · **referral engine** (LinkedIn/Google contacts import → local
  matching → "your network at this company" + find-my-path-in prompts, B4) ·
  follow-up/thank-you + interview-prep prompts (B5) · **Insights tab** (funnel,
  per-source interview rates, cadence chart, B6) · **ghost badges on rows +
  company ghost memory + new-since-visit + copy pack** (B7). Review fleets
  confirmed 5 findings (1 CRITICAL: fresh-registry create silently overrode
  switch:false — `017c0d9`; 1 major ghost-banner level mismatch — `8f3f84c`;
  plus README positioning pins restored `cc4ae26`) — ALL fixed same night.
  **Suite 2,968 → 3,104 / 0 failed; vitest 199; exe rebuilt + production/
  mirrored + frozen web smoke; verified live on dad's project (Insights funnel,
  real Aging/Stale badges). ~14 commits PUSH HELD.** Morning list in the
  handoff: eyeball app, push call, LICENSE choice, beta-cohort go.

---

## Session 37 (2026-07-05) — beta-stage research program + Discover tab ✅

Alex: "what's needed for beta… research what the data says… compare to our
app… what are we missing." 9-thread research fleet (funnel evidence, market
pains, 6 competitor deep-dives, privacy landscape, dark patterns, LinkedIn
ToS enforcement, US legal, beta-ops) → **`brain/beta-roadmap-2026-07-05.md`**
(synthesis + 3-wave build order) + **`brain/research-2026-07-05-beta-evidence.md`**
(persisted evidence digest). Headline: "most jobs possible" is the wrong
objective — the levers are discovery+freshness (we excel), referral-path
surfacing (biggest gap, 40%-vs-2-3% interview rates), channel-conversion
intelligence (nobody has it; our tracker data enables it), tailoring (1.6x),
cadence; never-auto-apply now data-validated (bots: 0.4–6% response, bans).
Beta blockers: first-run quick-run, MS Store (individual reg FREE since
9/2025, no SmartScreen) or Trusted Signing $9.99/mo, update check, in-app
feedback, web create-project, 5-line privacy page. Earlier same conversation:
**EXPERIMENTAL Discover tab shipped** (`afbcf66`, BYO-AI role recommendations,
1-commit removable — recipe in KNOWN_ISSUES). Commits held unpushed.

---

## Session 36c (2026-07-04 afternoon, same conversation) — search optimization + full UX/perf review + DESKTOP APP ✅

Alex (away, full autonomy): maximize jobs found across all his roles + dad,
full frontend UI/UX + backend efficiency review, "will this run as a desktop
app? that is what we want." All delivered — read
`docs/handoffs/handoff_20260704_session36c.md` first. Highlights: **live
6-project test → Alex's five role inboxes 2,964→6,603 rows**; fetch-side
widening (metro satellites CSV + curated eng query synonyms — measured +19%
raw pull, 17 query keywords vs 10 on mechdesign re-run); **`--desktop` native
window (pywebview/WebView2) shipped + frozen-exe smoke PASSED**; frontend
dedup/polish batch (row-actions/kbd/status/relative-time/friendly-error +
Toaster dark-mode); backend perf batch (list payloads -description, board N+1
batched, ghost cache + day-bucket, JobRunner eviction, asset cache headers);
onboarding legacy-config inference (dad no longer re-gated every load) +
mid-wizard sentinel; **adversarial review wave confirmed 5 findings — all
fixed same-session** (worst: bare hyphen-split city variants cross-matching
other metros; ghost cache freezing staleness). **Suite 2,968/0, vitest 176,
exe rebuilt + production/ mirrored. ★PUSHED origin/master `b0cff80..22b4b61` (63 commits, 2026-07-04; pre-push scan clean). NEEDS ALEX: free
API keys (CareerOneStop/Brave/Jooble/Careerjet/SerpApi — biggest untapped
recall lever), push decision, tk-vs-desktop default.** Full data:
`brain/findings-2026-07-04-search-optimization.md`.

---

## Session 36b (2026-07-04, same conversation) — scenario minors + P1 knobs FIXED ✅

Morning continuation: Alex said "start working on the changes that surfaced
that need fixing" → the findings-report queue executed inline, one commit per
fix, test-first. **MINOR-1** garbage `location_mode` fails OPEN to All
locations (`geo/filter.py location_visible`, covers web+tk) `701ccba`.
**MINOR-2** blanket `{ok,error}` JSON envelope on routing-layer /api errors
(HTTPException handler scoped by `request.path`; literal `../` + 405 + unknown
routes; non-API paths untouched) `fb2f91f`. **MINOR-3** `.ics` SUMMARY
humanized `6b6f7ca`. **MINOR-4** reach-badge copy branches on
`is_knowledge_work(industry)` (auto-resolves active config per call)
`8c16f0e`. **MINOR-5** rubric/grade-scale stoplist in `match/skillgap.py`
(display/tailoring only — NOT the scoring path; "iv" kept for intravenous)
`e731cae`. **P1 parity gap**: `POST /api/runs/daily` accepts
`{max_pages:1-10, min_score:0-100}` → threaded to `--max-pages/--min-score`
argv; absent = byte-identical legacy argv; bad values 400 never clamped; Inbox
"Update my Inbox now" is now a split button w/ Quick/Standard/Deep run-depth
menu (verified live in preview) `fbcfc1a`. **Suite 2903 → 2927 / 0 failed;
vitest 151; PUSH STILL HELD (now ~51 commits).** §6 GO/NO-GO blockers all
cleared; remaining queue: web create-project flow (P3), filter URL sync,
sector-source status API (improvement #3), inefficiencies #2/#3. Details in
`brain/findings-2026-07-04-webui-scenarios.md` Addendum 2.

---

## Session 36 (2026-07-04 overnight) — WEB-UI MIGRATION: all phases + deep + scenario testing ✅

Alex approved the tkinter→web roadmap item and slept; fleet executed the whole
program overnight. _*Stack: Vite+React19+TS+Tailwind4+shadcn served by the
receiver at 127.0.0.1:5002/app; /api/* mirrors the MCP seam; SSE job console;
Aegean tokens generated from ui/theme.py._* All 8 tabs + wizard + dialogs +
Guide have web twins; tk GUI untouched and green; launcher `py -m webui` /
exe `--web`; :5001 legacy tracker retired; frozen exe proven serving /app.
Every phase gated builder→reviewers→fix→verify. ★Catches worth remembering:
key-test probe leaked raw secrets via HTTPError str() (fixed via applog.redact
chokepoint); fresh-install inbox-table 500; resume bare-"Experience" heading
dropped all work history; **get_conn() leaks open WAL connections (context
manager = transaction-scoped) → tracker.db.release_for_restore() for backup
restore**; industry auto-derivation was tk-only until parity-fixed; remote-only
home treated as metro. Deep testing (D1–D7, results in
`brain/test-plan-2026-07-04-webui-deep.md`): scoring parity PROVEN
(d25247d..HEAD zero diff on match/ranker/preferences), route-audit meta-test
(every mutating route origin-gated), frozen functional pass. Scenario testing
(5 live journeys → `brain/findings-2026-07-04-webui-scenarios.md` + addendum):
21 defects, ALL 2 criticals + 7 majors fixed; minors + parity gaps (no web
create-project flow = biggest) queued. **Suite 2478 → 2903 / 0 failed; vitest
151; PUSH HELD (~40 commits).** Read-first: `docs/handoffs/handoff_20260704_session36.md`.

---

## Session 35b (2026-07-04) — FIX-ALL + modularize + full-scale validation ✅

Same conversation as S35. Alex: "fix all other findings that need it", "multiple
files instead of one monolith", "full scale test of multiple profiles… make sure
the refactoring didn't break anything", language question. **Wave 1 (3 Sonnet
builders, worktrees):** ranking (#28 exec-intent split / #37 SOC-11 / #31 SOC 33+51
routing / #38 honest skills chip — **eng parity byte-identical**), sources (keyless-
skip on ALL 3 entry points, US-only skip for non-US, jobsacuk activation, careerjet/
jooble country, adzuna cache versioning), resilience (no cache-on-error, careers/
Brave failure surfacing, per-source ctor guard, careers fetch memo N-not-3N,
discovery TTL+memo, GC-in-finally, icims/taleo/SF discovery hosts, harvest negative-
cache). 4-region cli.py merge conflict hand-resolved. **Wave 2 (modularize):**
gui.py **5,303→1,834** (10 ui/ modules, pure moves, compat re-exports); cli.py
816→610 via `search/source_registry.py` (one function per source). **Review fleet
over cumulative diff: 0 findings in merge/pure-move/interaction dims; 1 confirmed
test-hygiene** — applog `_WARNED_ONCE` cross-test pollution → autouse conftest
reset (`979397d`). **Full-scale validation ALL PASS:** 5 blank-slate profiles
through real daily_run (eng 2255/280, nurse 507/136, warehouse 282/53, **London-UK
555/304**, remote 784/125); live catch: Adzuna /gb/ + "London, United Kingdom"
where-string = 0 results (geocoder chokes on country tails) → strip-when-tail-names-
routed-country fix (`config.location_country_tail`) → **Adzuna gb 295 rows = UK
lane's top source**; GUI compat 29/29; parity byte-identical through refactors;
receiver live 200/403/**413**; **production exe rebuilt + clean launch** post-split.
Language decision: engine stays Python; UI successor = local web UI over Flask
(roadmap, KNOWN_ISSUES). Suite **2478 green** (S35 open = 2311). **★PUSHED to
origin/master 2026-07-04 (S35+S35b era, ~43 commits).** See [[handoff_20260704_session35b]].

---

## Session 35 (2026-07-03) — Weakness sweep: cheap-AI onboarding + international + receiver ✅

Alex: "keep testing… find flaws/inefficiencies… make sure cheap AIs can onboard
with ease… help as many people as possible." **Empirically tested cheap-AI
onboarding** (fed the REAL setup prompt + 8 diverse personas — SWE/nurse/warehouse/
career-changer/UK/India/HVAC-trade/fresh-grad — to granite:micro 2B + gemma-12b,
then ran each raw reply through the ACTUAL `parse_setup_block`; +19/9 deterministic
adversarial-format cases) and ran a **39-finding fleet audit** (8-dimension find →
adversarial-refuter verify, 51 Sonnet agents; 43 raised → 39 confirmed / 3 refuted).
Empirical verdict: parser is robust (8/8 parse on a 2B model) but had model-INDEPENDENT
**hard-blocks** on plausible AI output. **Fixed 5 commits / ~50 tests (suite 2311→2360,
0 failed):** (1) onboarding parser — salary "140k"/"$120k per year"/ranges, radius
"25 miles", seniority director/C-level/intern aliases, comma-string titles split, smart
quotes + `//` comments, two-fence best-object, **O\*NET trades (machinist/barista/welder)
accepted as fields** (`65454d0`); (2) **Adzuna routes to user's country** (London→/gb/,
Bangalore→/in/; US byte-identical, Indianapolis IN≠India) + **metro_variants non-US city
fallback** so international local jobs aren't hidden (`4aaf9d5`); (3) receiver — **/track
dedup** (`url_is_tracked`, 'Track All'×2 no longer dupes), /clip non-string 500 fix,
8 MB body cap (`d19c9f6`); (4) generic_capture JSON-LD scan bounded (`24605fb`).
**DEFERRED for Alex's approval (byte-identical scoring/filter rule):** #7 hard_gate
title substring over-drop ("sales"→drops Salesforce), #28 _EXEC_RE IC-title false-positive,
#37/#38 SOC/skill scoring gaps. **DEFERRED design/data (biggest lever = #4 zero
blue-collar starter registry; #15 non-tech ATS hosts; silent-failure surfacing #5/#6/#22/#23;
zero-key transparency #18).** Full disposition of all 39: `brain/review-2026-07-03-s35-weakness-sweep.md`.
PUSH HELD. See [[handoff_20260703_session35]].
**→ ALEX DECIDED (same day): DESIGN PHILOSOPHY = inclusion over precision** — "get as
many potential jobs in front of the users as possible, let the users drop, never
over-drop; but don't show completely unrelated jobs." **#7 APPLIED** (`78fbc67`
word-boundary blockers; +3 tests); philosophy baked into repo CLAUDE.md + new
**`docs/KNOWN_ISSUES.md`** (living trade-offs doc); #28/#37/#38 held as known issues
(ranking, not drops); **#4 blue-collar waits; seeded-company-list buildout = a planned
FUTURE session.** Bonus: pre-existing wall-clock time-bomb test fixed (`3ac80fa` —
hardcoded created-date crossed a recency-rounding boundary; repro'd on clean tree).
Suite **2363 green**; 8 commits ahead, PUSH HELD.

---

## Session 34 (2026-07-02 evening) — Live-test fixes + onboarding + production + FIRST PUSH ✅

Alex live-tested the extension in his real Chrome (first true end-to-end run) →
found: extension couldn't even LOAD (manifest referenced never-created icons —
since v1.5), auto-send double-fired (delta-clear resurrect race), degenerate
"T"/"C" captures, edisonsmart clip dead-end, plus a test that leaked fixture
rows into his real project DB. **5 Opus builders**: (1) sentKeys ledger +
capture sanitation; (2) **Vincere ATS** (`ajax/search-jobs` + Laravel token
dance; edisonsmart = verified_live 214 jobs) + browser-verified `direct`
fallback for still-unrecognized boards; (3) onboarding — verified "Get a free
key →" links everywhere, Tools ▾ top-bar button, numbered extension walkthrough
in Guide, **DWM-themed title bar** (ui/titlebar.py), typography tokens; (4)
`build_package.py --production` → production/ folder w/ 18MB onedir exe
(smoke-launched clean); (5) **semantic 4-test flake root-caused + fixed** (not
skipped): model2vec from_pretrained phones home even when cached → conftest
socket guard → swallowed exception latched available()=False; offline-first
`_resolve_source(local_files_only=True)` + no transient latching. Review fleet:
0 confirmed / 1 refuted (SSRF dies on BROWSER_ONLY gating); its verifier
exposed prune_companies deleting browser-only boards → fixed + tested. Suite
**2258 → 2312 green (0 failed, flake included)**. Pre-push scan clean →
**PUSHED to origin/master (~225 commits)**. NEEDS ALEX: reload extension
(again — sentKeys landed after his session), re-clip edisonsmart, relaunch app
for the new chrome, delete junk tracker rows from the pre-fix test.

## Session 33 (2026-07-02) — Browser-extension breadth wave: any-site capture + browser-verified boards ✅

Alex: the extension's job is FILLING GAPS the main search misses; "do that. We
do want to be filling gaps and adding even more breadth." Assessment found it
covered only the 5 aggregator domains — zero capture on the actual gap
territory (walled Workday, careers pages, unprobeable ATS). **3 Opus builders**
(worktrees, all merged): (1) **JSON-LD "Capture this job"** on ANY employer/ATS
page (schema.org JobPosting + DOM fallback, `posted_iso` created-precedence,
manifest v1.6 adds only `scripting` — no new host permissions); (2)
**browser-verified clip** — failed clips reveal "Verify from this tab", walled
boards save as `BROWSER_ONLY_FLAG` (visible everywhere, only CareersClient
skips; server probe wins; evidence never overrides identity); (3) **friction +
health** — GUI-toggle receiver copy, `/track` single-port tracking (5001
fallback), opt-in auto-send per 25 jobs (`open_report:false`), selector-rot
self-detection (amber badge) + in-popup Health-check, shared
`browser_ext/selectors.js` registry. **Review fleet** (4 dims, adversarial
verify): 3 confirmed majors / 1 refuted → all fixed `058ae74` (auto-send
delta-clear vs cross-context race; browser-only RESCUE of stored-unverified
boards; seed-path re-probe of browser-only boards). Suite **2195 → 2256
green**; ~207 ahead, PUSH HELD. Docs: `handoff_20260702_session33.md` +
`brain/review-2026-07-02-s33-ext-fleet-findings.md`. NEEDS ALEX: reload
unpacked extension (v1.6 supersedes the S32 v1.5 reload); live selector audit
still pending a connected Chrome (LinkedIn last verified 06-14;
Glassdoor/Zip/Dice never).

## Session 32 (2026-07-02) — Full improvement-plan rollout: 19 builders + review fleet + live smoke ✅

Alex: "roll out fixes/changes/improvements with Opus subagents; breadth/quality =
yes; keep sending waves until all changes are made and reviewed." Built the ENTIRE
S31 plan. **Wave 1** (7 builders): all P0s — token-aware industry matching +
probe-gated seeding, seniority/country/salary/label scoring honesty, Adzuna/USAJobs
remote queries + remote_intent, Workday `wday/cxs` fetcher (live-validated;
Cloudflare tenants still walled), taxonomy rules, set_active/UnknownFieldError/
Top-Picks/warn_once lifecycle fixes, wizard keys step + keyless-skip badge.
**Wave 2** (6): wizard v2 (presets, DEMO inbox, update-now terminal action, keys
UX, actionable reach badge, Jobs-For-You), ui/ai_setup.py BYO-AI setup + MCP
seed_companies + SOC aliases, Seed-My-Area Leg B (Business Finder, key-gated),
REAP/EdJoin + Himalayas country=US, Kanban Board tab + ATS match hint + QW-7
positioning, browser clip-to-seed (/clip + ext v1.5 — **needs unpacked reload**).
**Wave 3**: wizard AI express-lane + workday migration script → **APPLIED: CCH
(479 jobs) + Bon Secours (96) now live via cxs**. **Review fleet** (20 agents,
7 dims): 13 CONFIRMED / 0 refuted — CRITICAL rescore-drift (end-of-run rescore
erased the new scoring levers; parity test was blind), applog secret-scrubber
INERT since S29 (wrong-arity call), REAP inert from GUI, unverified-flag permanent
lockout, demo rows in AI export, + 8 more → 5 fix builders, ALL merged. **Live
smoke** (3 blank slates): marketing-remote **8→36 inboxed (Adzuna remote 0→114
raw)**; warehouse/teacher machinery proven (P0-1 15 seeds matched, 15/15 cxs
probes, REAP 13 OH rows), P0-4 verified live; + final builder fixed cxs
walled-vs-empty probe verdicts. Suite **1744 → 2195 green**;
**~196 ahead, PUSH HELD**. Needs Alex: eyeball `py gui.py`, reload extension,
CareerOneStop key, push decision. Detail:
`docs/handoffs/handoff_20260702_session32.md` + smoke report in
`brain/general-user-tests-2026-07/`.

---

## Session 31 (2026-07-02 overnight) — Repo reorg + 8-persona general-user tests → improvement plan ✅

Fable 5 orchestrating an Opus fleet while Alex slept. (1) Repo-root reorg
(`ecddfa7`): 27 handoffs → `docs/handoffs/`, one-off scripts → `scripts/`
(bootstraps fixed), legacy quarantined; suite exactly 1744/1. (2) **8 blank-slate
general-user personas** (SWE new-grad Austin, RN Boise, teacher Columbus,
consultant Chicago, warehouse Memphis, remote-only marketer, mecheng Seattle,
data career-changer Phoenix) each ran the FULL journey — wizard-equivalent setup,
ask-your-AI seeding via the real + Add Companies pipeline, live `daily_run`,
BYO-AI top-10, tracked apply→interview→offer/rejected/ghosted — zero crashes,
verdicts 6-7/10, 7/8 beats-manual (remote-only marketer the exception: 8 rows).
(3) 4 code-verifying review lenses + 3 web research agents → synthesized
**`brain/improvement-plan-2026-07-02-general-user.md`**. Headline confirmed P0s:
`_industry_tag_match` space/underscore one-liner zeroes the careers path for ALL
multi-word industries (warehouse 17 seeds→0 searched); Adzuna is 48-100% of every
metro inbox with CareerOneStop unkeyed+silently dark; Adzuna/USAJobs return 0 for
location="Remote"; raw Score is seniority-/country-blind (facts.py logic never
wired into scorer/hard-gate); probe-advisory seeding + Workday/CSRF walls (fix:
public `wday/cxs` JSON API — top strategic bet); `daily_run --project` flips the
global active project. Corpus: `brain/general-user-tests-2026-07/` (commit
`ba0482d`). **No app code changed — fix wave held.** ~118 ahead, push HELD.
Detail: `docs/handoffs/handoff_20260702_session31.md`.

---

## Session 30 (2026-07-01, same day) — Live blank-canvas test runs + setup depth ✅

Proved the S29 overhaul live: cloned both profiles into fresh test projects
(kept, active = `test-controls`), ran the full pipeline, delivered top-10s
(controls 685-row inbox; Dad 19 = supply-bound, seeds delivered). Measured the
reliance answer: careers registry 85%/58% of the two inboxes, Adzuna carried all
non-seeded local wins, keyless tier ~1%/0 top-10 slots. Runs caught + fixed 3
bugs (FileCache `:`-filename → jobicy never cached on Windows; Oracle tenant-slug
company names; freshness log counts). Guide gained a deep source-setup/seeding
section (incl. ask-your-own-AI employer-list flow that works today); Seed-My-Area
plan written + **HELD** (`brain/plan-2026-07-01-ai-assisted-setup-seeding.md`);
Opus subagent added the consulting taxonomy entry + live-validated/hardened the
(already-existing) SmartRecruiters fetcher. Suite **1744 green**; **~115 ahead,
push HELD**. OPEN: company-name canonicalization for cross-board dedup (design
pass first). Detail: `handoff_20260701_session30.md`. Output mode: terse.

---

## Session 29 (2026-07-01) — Deep review → full remediation buildout + Aegean merge ✅

The whole review roadmap (`brain/review-2026-07-01-deep-product-review.md`, P0–P7)
built in one session: 5 Opus builder waves + post-build adversarial review fleet
(all confirmed defects fixed) + aegean-restyle merged (Zaggregate branding).
Suite 1223 → **1731 green**; master **110 ahead, push HELD**; one folder again
(branches/worktrees pruned). Detail + Needs-Alex: `handoff_20260701_session29.md`.
Output mode this session: default terse (verbose for the review deliverable).

---

## Phase 1 — Job Scraper ✅ COMPLETE (2026-05-27)

### API Sources

- [x] Adzuna API client — working, tested
- [x] JSearch (RapidAPI) — working, key in .env
- [x] USAJobs — working, key in .env
- [x] Multi-source architecture (base class, dedup, HTML report with source badges)
- [x] CLI: `py -m search.cli` with full flag set (see below)

### Career Page Scraper

- [x] Greenhouse scraper — public JSON API
- [x] Lever scraper — public JSON API
- [x] Workday scraper — slug format `tenant:N:site`; Caterpillar confirmed working; most others CSRF-protected (kept as `direct` type)
- [x] Direct scraper — BeautifulSoup best-effort for custom portals
- [x] Company registry — `REGISTRIES` dict, 2 industries (controls_engineering, health_informatics); 40+ entries
- [x] `CareersClient` — slots into pipeline via `search_and_parse()` override (no dict roundtrip)
- [x] User-editable `companies.json` — merges with hardcoded registry, user wins on name collision
- [x] Company discovery — **Brave Search API** (replaced DDG); requires `BRAVE_SEARCH_API_KEY` in `.env`; skips gracefully if key absent; free 2,000 req/month

### CLI Features

- [x] `--keywords` / `--add-keyword` / `--user-config` — 3-tier resolution: CLI > user_config.json > defaults
- [x] `--location` — default falls through to user_config.json then hardcoded DEFAULT_LOCATION
- [x] `--salary-min` — same resolution chain
- [x] `--sources` — comma-separated; respects `sources` dict in user_config.json
- [x] `--sort-by date|location` — location uses `_location_score()` in search_engine.py
- [x] `--industry` — filters company registry
- [x] `--top-n`, `--max-pages`, `--no-cache`, `--no-discover`, `--companies-file`
- [x] `--edit-csv` — opens output CSV in default app after search (Windows)

### User Config Files

- [x] `user_config.json` — Alex's personal defaults (10 ME keywords, Cincinnati, $85K)
- [x] `config_dad.json` — Dad's health informatics config
- [x] `run_dad.bat` — double-click launcher for Dad
- [x] `run_servers.bat` — starts all three Flask servers in separate windows

### Output

- [x] HTML report — dynamic source filter dropdown (built from actual cards), Track button per job
- [x] CSV report — opens automatically with `--edit-csv`

---

## Phase 2 — Resume & Cover Letter Generator ✅ COMPLETE (code) (2026-05-27)

- [x] `resume/experience_parser.py` — parses experience.md by `## ` headings
- [x] `resume/generator.py` — Claude API call, structured JSON response, fence-stripping
- [x] `resume/docx_builder.py` — resume DOCX + cover letter DOCX, dark navy theme
- [x] `resume/app.py` — Flask on port 5000, returns .zip of both DOCXs
- [x] `resume/templates/index.html` — paste job posting, loading state, error display
- [ ] **`ANTHROPIC_API_KEY` not yet added to `.env`** — required to use
- [ ] **ERP tech stack gap in experience.md** (line 109 placeholder) — affects output quality

**Run:** `py -m resume.app` → `http://localhost:5000`

---

## Browser Extension — Job Harvester ✅ COMPLETE (2026-05-27)

- [x] Chrome MV3 extension — `browser_ext/`
- [x] SITES registry pattern — 5 sites: LinkedIn, Indeed, Glassdoor, ZipRecruiter, Dice
- [x] Adding a new site: one object in SITES array + one URL pattern in manifest.json
- [x] Debounced MutationObserver (600ms) + SPA URL change detection (1s)
- [x] Dedup by URL in chrome.storage.local
- [x] Popup: count badge, **Send to Tool** (→ report via browser_receiver), **Track All as Interested** (→ tracker direct), Clear
- [x] `scrape/browser_receiver.py` — Flask on port 5002, converts to JobResult, generates HTML+CSV report

**Send to Tool:** requires `py -m scrape.browser_receiver`
**Track All:** requires `py -m tracker.app`

---

## Job Application Tracker ✅ COMPLETE (2026-05-27)

- [x] `tracker/db.py` — SQLite (`tracker.db`, gitignored), full CRUD, 7 statuses
- [x] `tracker/app.py` — Flask on port 5001
- [x] `tracker/templates/tracker.html` — status tabs with counts, add form (collapsible, pre-fill from URL params), inline status dropdown (auto-submits), expandable notes, delete
- [x] Status flow: interested → applied → phone_screen → interview → offer / rejected / withdrawn
- [x] JSON API: `POST /api/add` (CORS enabled) — used by browser extension Track All
- [x] Pre-fill path: `http://localhost:5001/add?title=...&company=...&url=...&salary=...`
- [x] "Track" button on every job card in search HTML reports

**Run:** `py -m tracker.app` → `http://localhost:5001`

---

## Desktop GUI ✅ COMPLETE (2026-05-28) — consolidates Tracker + Resume

- [x] `gui.py` — single tkinter window, two tabs, replaces the two Flask UIs for day-to-day use
- [x] **Job Tracker tab** — Treeview with sortable columns, status filter bar with counts, add/edit modal (`JobDialog`), inline quick-status combobox, delete-with-confirm, open-URL; talks to `tracker/db.py` directly (no HTTP)
- [x] **Resume Generator tab** — paste posting → generates in a daemon worker thread → writes `output/resume_DATE.docx` + `output/cover_letter_DATE.docx`, clickable output path opens the folder
- Shares the navy `#1a1a2e` palette and `STATUS_FG` colors with the web UIs

**Run:** `py gui.py` (no servers needed for tracker + resume)

> The Flask apps still exist: `browser_receiver.py` (:5002) is required for the browser
> extension's "Send to Tool", and the web tracker/resume remain as browser-based alternatives.

⚠️ **Not yet committed** — `gui.py` is untracked in git as of this writing.

---

## Code Quality — Reviewed & Fixed (2026-05-27)

- [x] Port constants centralized in config.py (`PORT_RESUME=5000`, `PORT_TRACKER=5001`, `PORT_RECEIVER=5002`)
- [x] `CareersClient.search_and_parse()` — eliminates JobResult→dict→JobResult roundtrip
- [x] Registry loaded once in `CareersClient.__init__()`, not per keyword
- [x] `base_client.py` — added default `search_and_parse()` wrapping search+parse
- [x] `_parse_salary` regex requires `$` prefix (matches content.js behavior)
- [x] `datetime.utcnow()` → `datetime.now(timezone.utc)` (Python 3.12 deprecation)
- [x] All print statements ASCII-safe (Windows cp1252)
- [x] `debug=False` on all Flask apps

---

## Persistent discovery watchlist — 2026-06-02

`--save-discovered` (CLI): auto-discovered Greenhouse/Lever companies that returned ≥1 matching job that run ("winners") are appended to `companies.json` — tagged with the run's `--industry` (fallback `discovered`) — so they become a permanent, growing watchlist scraped on every future run. Opt-in only; dedups by slug+name; preserves file comments; atomic write. `CareersClient._record_winner`/`persist_discovered` + `company_registry.save_companies`. 5 tests in `test_discovery_persist.py`.

`--prune-companies` (CLI maintenance mode, `--prune-threshold` N default 2): probes every `companies.json` entry and removes those that 404 or have an empty board for N **consecutive** runs (streak tracked in `cache/company_health.json`; transient timeouts/connection errors are "unknown" and don't penalize). Greenhouse/Lever probed for empty-board; direct probed for 404; workday slugs skipped. Hardcoded registry is never touched. `scrape/company_health.py`; 4 tests in `test_company_health.py`. Pairs with `--save-discovered` to keep the watchlist self-cleaning.

## Hardening pass — 2026-06-02

Full review ([[review-2026-06]]) + phased remediation ([[plan-2026-06]]) executed. **76 unit tests** added (the repo had none); deps were missing from the env and reinstalled. Highlights: XSS/CORS fixed; rate-limiter rewritten + JSearch monthly cap; collision-free cache keys; resume generator on tool-use + prompt caching; engine parallelized; tracker gained follow-up/deadline/contact/JD-snapshot + cross-run dedup (`--show-tracked`); new **GUI Search tab**. New modules: `search/http_util.py`, `resume/service.py`, `tests/`. Deferred items tracked in the plan. **No git operations performed** — all changes in working tree.

## Throughput overhaul — 2026-06-09 (Session 7) ✅ SMOKE-TESTED

Pipeline rebuilt around apply-throughput ([[../handoff_20260609_session7]]): scheduled daily search → local 0–100 scoring → deduped **Inbox** → optional Claude fit-ranking via **copy-paste bridge (no API key)** → **Apply Queue** with resume prompts + "Mark Applied ▸ Next".

- [x] `match/scorer.py` — 0–100: title 35/skills 25/salary 15/location 15/recency 10, −30 per exclude keyword; skills auto-parsed from experience.md; `JobResult.score`/`score_notes`
- [x] `claude_bridge.py` — fit + resume prompts via clipboard; strict-JSON parsers tolerant of fences/prose; `clip` UTF-16; works with zero API keys
- [x] `inbox` table in tracker.db (`norm_url UNIQUE` dedup vs tracked ∪ dismissed); applications gained `score`/`fit_score`/`fit_rationale`
- [x] `daily_run.py` + `setup_schedule.bat` — headless 07:30 Task Scheduler run; free sources only (jsearch excluded to protect 200/mo quota); ≥40 score → inbox; logs `output\daily_run.log`
- [x] New free sources: `search/themuse_client.py` (keyword-blind cached fetch + client-side filter), `search/remoteok_client.py` (single cached feed)
- [x] GUI now 5 tabs: **Inbox (n)** / Search (scored, prefilled, multi-select) / **Apply Queue** / Job Tracker / Resume Generator; `PasteDialog` for bridge replies
- [x] CLI: `--sort-by score` default, `--min-score`; CSV score column; HTML score badges + "Best match" sort
- [x] `resume/service.py` — bridge-first; API optional (lazy anthropic import); company-slug DOCX filenames
- [x] **SMOKE TEST PASSED** (2026-06-09): py_compile all 13 modules, imports, scorer (70 vs 0+penalty), bridge parsers (fenced + prose JSON), DB inbox migration/dedup/track/dismiss, gui import. Live `daily_run --max-pages 1`: 3564 raw → 649 deduped → 419 ≥40 → **399 new in inbox**. 2 self-review bugs fixed (badge-before-tabs TclError; missing salary in inbox fit prompt).
- [ ] No unit tests yet for scorer / bridge parsers (only manual smoke)
- [ ] `setup_schedule.bat` not yet executed (needs Alex, possibly as admin)
- [x] **Careers-noise root cause fixed** (2026-06-09, post-smoke review). Three bugs:
  1. `careers_client.py` truncated `companies[:top_n]` — REGISTRY lists 26 health-IT entries first, so with `industry: null` the 18 controls companies were **never scraped**. Now: curated registry always scraped in full; `top_n` caps only auto-discovered additions (CLI `--top-n` help updated).
  2. `daily_run.py` never passed `industry` to `build_clients` — user_config `industry` was ignored on scheduled runs. Now passed through.
  3. Scraper keyword fallback was `any(token)` — bare "engineer" matched everything (Veeva: 208 "matches"/keyword). New shared `scrape/text_match.py::keyword_matches`: exact phrase, else **all** tokens ≥3 chars (trailing-s stripped, so "controls engineer" still hits "Control Systems Engineer"). Used by greenhouse/lever/direct `_matches`.
  - `user_config.json`: `"industry": "controls_engineering"` (Dad's config_dad.json already had health_informatics).
  4. `search/remoteok_client.py`: `_STOPWORDS` strips "engineer", so keyword "R&D engineer" reduced to `[]` and the `if toks and ...` guard let the **entire 168-job feed** through (CEO, "Farmer REMOTO", etc.). Now: empty toks → return []; match on **title+tags only** (dropped the over-loose `all(t in desc)` branch).
- [x] **VERIFIED end-to-end on Opus 4.8** (2026-06-09): all modules py_compile; `text_match.keyword_matches` unit assertions pass (matches "Control Systems Engineer", rejects "Software Engineer"). Re-ran `daily_run --max-pages 1` twice. Result: careers 0 (controls registry is all CSRF Workday "direct" portals — correct to yield 0 vs 2989 health-IT spam); **inbox 233**, sources adzuna 186 / themuse 14 / usajobs 13 / remoteok 20 (was 168). Top matches all on-target (CNC Field Service, Mechanical Design, Automation, Industrial Eng); junk tail gone. Score min/median/max 40/57/78.
  - NOTE: careers source now contributes ~0 for controls until real Greenhouse/Lever controls boards are added or Workday CSRF is solved — the API sources (Adzuna/USAJobs/TheMuse/RemoteOK) carry the pipeline.
- [x] **10 scrapeable hardware/robotics boards added to controls registry** (2026-06-09, slugs verified live via boards-api.greenhouse.io / api.lever.co): GH — spacex, andurilindustries, **pathrobotics (Columbus OH)**, formlabs, flyzipline, nuro, redwoodmaterials, relativity (Relativity Space); Lever — zoox, brightmachines. Rejected (404): shieldai, skydio, stokespace, hadrian, agilityrobotics, relativityspace.
- [x] **Verified live + 2 more bugs fixed** (2026-06-09, Opus 4.8). Re-ran `daily_run --max-pages 1`; careers jumped 0 → **~1016 results** (SpaceX, Anduril, Relativity, Zoox, Caterpillar, etc.). Two issues found and fixed: 5. `cache_helpers.slug_safe` didn't strip `:` → every Caterpillar (Workday slug `cat:5:CaterpillarCareers`) cache write threw `[Errno 22] Invalid argument` on Windows. Now regex-sanitizes all Windows-reserved chars `[<>:"/\|?*,\s]` → `_` (alphanumeric slugs unchanged, so no cache invalidation; `&` kept — filename-legal). Caterpillar now returns 20/keyword. 6. greenhouse/lever scrapers hard-coded `description=""` → all 580+ careers jobs scored identically (~52), since the scorer's 25-pt skill component had nothing to read. Now: greenhouse populates from `job["content"]` (`_clean_content`: html.unescape + strip tags + collapse ws, cap 3000); lever from `descriptionPlain`. **Score spread 52→59 median, top now genuinely Alex-shaped** (Mechatronics Engineer, Mfg Engineer Analytics, Machine Vision/Automation, SpaceX Mfg Tool & Die all 76–78). Matching still uses title+departments only (tight); description used for scoring only.
  - Final inbox: **959 jobs**, careers 726 / adzuna 186 / remoteok 20 / themuse 14 / usajobs 13. Big-board volume (Anduril 311, SpaceX 188) is fine — best matches sort to top, generic ones sink; no per-company cap needed.

- [x] **Session 8 (2026-06-09): 4-agent improvement analysis + Phase 1 + Ashby implemented & VERIFIED on Opus 4.8.** All 11 modules py_compile; `_smoke_phase1.py` all-pass (salary regex, recency neutral+decay, word-boundary skills, size modifier small84/unknown76/mega70, round-robin+migration on temp DB, fit-prompt size context); `_smoke_user_companies.py` all-pass (companies.json merge 49 entries/filters correct, user-added "User Test Robotics Co"/pathrobotics scraped 2 jobs w/ 3000-char desc — flow works end-to-end). Live `daily_run --max-pages 1`: per-company cap trimmed **977→394 (−583 Anduril/SpaceX flood)**; 44 new→inbox 1003. Round-robin inbox: first 10 rows = 10 different companies; **Gecko Robotics (bc=16, +8 boost) now tops the inbox at 82, above Anduril/SpaceX** — exactly the intended skew fix. Smoke files deleted. NOTE: the 959 pre-existing inbox rows predate board_count capture (show bc=-1/neutral) and were inserted before the cap, so Anduril 311/SpaceX 188 still physically present — round-robin handles them at display layer; a one-time cache-bypass re-run or inbox trim would backfill/cap them if wanted. Agent reports synthesized: ranking (scores cluster: title=35 pre-matched, salary constant-neutral, recency biased), sources (Common Crawl CDX slug enumeration = biggest find lever; Ashby/SmartRecruiters/HN-Algolia/Remotive/Jobicy/Himalayas endpoint-verified; Brave free tier dead since Feb 2026, now $5/mo), apply (~10–15 min/app → ~5–7 with batch resume prompts + canned ATS answers), skew (cap + round-robin beats supply alone).
      **Implemented (all uncommitted):**
  1. `models.py`: `JobResult.board_count` — total postings on the company board, free size proxy (−1 unknown).
  2. `greenhouse_scraper.py`: captures `meta.total`; `created` prefers `first_published` over `updated_at` (kills big-board "always fresh" bias). `lever_scraper.py` + new `ashby_scraper.py` set `board_count=len(postings)`.
  3. `tracker/db.py`: inbox `board_count` column + ALTER migration; `inbox_all(order="roundrobin")` default via `ROW_NUMBER() OVER (PARTITION BY company …)` — first screen = best job per company (`order="score"` = old).
  4. `daily_run.py`: per-company insert cap (`max_per_company`, default 15, 0 disables; in user_config.json).
  5. `match/scorer.py`: word-boundary skill matching (kills 'pid'⊂'rapid'); `salary_from_text` recovers pay ranges from descriptions (annualizes hourly, 30k–500k bounds, fills salary_min/max); recency unknown → 0.5 neutral (was 0), exponential 10-day half-life; size modifier ≤30→+8, ≤100→+4, >250→−6 (in score_notes).
  6. `company_registry.py`: **18 verified small/mid boards added** (5/5 spot-checked live): GH formic(31) agilityrobotics(43) apptronik(90) locusrobotics(19) carbonrobotics(24) tulip(60) paperlessparts(14, CNC shops) fictiv(70) divergent(56) ursamajor(38) stokespacetechnologies(54) seurat(3) outrider(6); Lever dexterity(8) osaro(10) copia(9, Git-for-PLC) ambirobotics(8); **Ashby gecko-robotics(10, Pittsburgh)**. Dead-slug list in comments. Earlier "agilityrobotics 404" was transient — live.
  7. New `scrape/ashby_scraper.py` (api.ashbyhq.com, verified; salary from compensation tiers, fail-soft) + `ats_type="ashby"` dispatch + companies.json instructions.
  8. `gui.py`: Inbox Size column (S/M/L/XL); `_copy_fit_prompt` no-selection default = unscored, max 2/company; `claude_bridge.py`: "Board openings: N" per job + small-company preference instruction in fit prompt.
  9. Smoke tests written, NOT run: `_smoke_phase1.py`, `_smoke_user_companies.py` (companies.json merge + live user-entry scrape). Delete after passing.
     **companies.json gotcha (traced):** with `industry` set, user entries with a non-empty `industries` list lacking the tag are silently filtered; empty list always passes.
     **Phase 2 remaining:** HN Algolia client, Remotive/Jobicy/Himalayas, SmartRecruiters, Common Crawl enumeration. **Phase 3:** batch resume prompts, cover-letter persistence (gui.py discards `_cover`), canned ATS answers, follow-up reminders, status-history analytics.

- [x] **Session 8 cont. (2026-06-09): Phase 2 sources + Phase 3 quick wins + browser→inbox — WRITTEN then VERIFIED LIVE on Opus 4.8.**
  1. New feed clients (RemoteOK pattern — single cached feed, client-side `keyword_matches` filter): `search/remotive_client.py` (≤4 fetches/day courtesy; salary text prepended to desc for `salary_from_text`), `search/jobicy_client.py` (50 jobs/engineering category; no salary fields), `search/himalayas_client.py` (paginated to 500; **pubDate unix→ISO**; min/maxSalary annualized via salaryPeriod yearly/monthly×12/weekly×52/hourly×2080, 30k–500k bounds; location from locationRestrictions).
  2. `search/hn_client.py` — 2-step Algolia: latest `author_whoishiring` "Who is hiring" story (cached) → per-keyword comment search; parses first-line `Company | Role | Location`; skips comments without pipes (replies); url=news.ycombinator.com/item?id=…; source_api="hn". Startup-heavy = small-company lever.
  3. `scrape/smartrecruiters_scraper.py` — list endpoint has NO descriptions; per-MATCH detail fetch (jobAd sections, cached per posting, capped 15/board/keyword); board_count from `totalFound`; url jobs.smartrecruiters.com/{slug}/{id}. Wired as `ats_type="smartrecruiters"` in careers_client dispatch + companies.json instructions + CompanyEntry docstring. No SmartRecruiters companies in registry yet — add when found.
  4. Wiring: config.py constants (REMOTIVE/JOBICY/HIMALAYAS/HN blocks) + DAILY_SOURCES += remotive,jobicy,himalayas,hn; cli.py ALL_SOURCES + build_clients deferred imports; user_config.json sources +4 true. daily_run/GUI pick up automatically.
     **VERIFIED LIVE (Opus 4.8, 2026-06-09):** (a) all 13 touched modules py_compile ✓. (b) Per-client smoke: Remotive 27-feed→8 SWE matches, fields/salary-prepend/dates ✓ (0 controls — remote board, software-skewed, expected); Jobicy 50-feed→44 matches, ISO dates ✓; **Himalayas BUG FOUND+FIXED** — API hard-caps 20/page & ignores `limit`, so the `len(batch)<PAGE_SIZE` break stopped after 1 page (20 jobs); now pages by `offset += len(batch)` to MAX_JOBS, PAGE_SIZE→20, MAX_JOBS→200 (10 reqs/cold-cache); re-test 200-deep→46 matches/16 w/salary; unix→ISO + annualization confirmed (added `annual`/`daily` to factor map — API returns "annual" not "annually"); HN thread 48357725 found→78–80 postings, `Company|Role|Location` parse ✓. (c) Full pipeline via cli.py: 191 raw→172 dedup, all 4 scored ✓. (d) `daily_run --max-pages 1`: integrated, cap 1028→445, **7 new→inbox (1010)**, exit 0 ✓ — niche hardware keywords yield few remote-board hits (Himalayas 2, HN 80; remote boards are bonus coverage, HN is the small-co lever). (e) DB migrations cover_path/follow_up_date/board_count all present; follow-up auto-set +7=2026-06-16 ✓; browser-receiver route parse→score(70, skills 0% as documented)→inbox ✓.
  5. **Phase 3 quick wins (same session, VERIFIED):** `tracker/db.py` +`cover_path` column (migration + \_EDITABLE); `gui.py` Apply tab persists cover letter path on both bridge-paste and API paths (was discarded); Mark Applied auto-sets `follow_up_date = today+7` when empty; Tracker header shows amber "N follow-up(s) due" count (statuses applied/phone_screen/interview, date ≤ today).
     **Phase 3 remaining:** batch resume prompts (~5 jobs/paste), canned ATS answers panel (apply/canned.py), status-history table + response-rate analytics, resume A/B variant column + filename collision fix (resume/service.py:61). **Phase 4:** Common Crawl CDX slug enumeration script (biggest find lever; ~95k slugs via Feashliaa/job-board-aggregator + index.commoncrawl.org CC-MAIN-2026-21).
  6. **Browser extension → inbox integration (same session, routing VERIFIED):** `browser_receiver.py /harvest` now also routes harvested jobs through `score_jobs` → `inbox_add_many` (no min-score floor — hand-picked; fail-soft so report still saves on DB error; response gains `inboxed` count); popup.js shows "N new to inbox". Route tested: fake LinkedIn card → salary recovered (120k–140k) → scored 70 → inboxed 1 ✓. Extension code intact & JobResult-compatible; **remaining risk = content.js selector rot (selectors from 2026-05-27, LinkedIn churns DOM) — only verifiable by ALEX browsing with extension loaded + `py -m scrape.browser_receiver` running.** Harvested jobs have empty descriptions (card scrape) → skill component 0; Claude fit prompt is the ranking signal for them.

- [ ] **Session 8 cont. 2 (2026-06-10, fable, shell blocked): post-review improvement pass — WRITTEN, NOT yet compiled/tested.**
      From the 7-point review Alex approved with "Start doing those". All code-only items done; shell items queued below.
  1. `match/scorer.py`: empty description → skill component **0.5 neutral** (was 0 — buried HN/browser-harvest/direct jobs 25 pts under described jobs for a data gap, not a signal). Docstring updated.
  2. `resume/service.py`: filename collision fixed — two roles at the same company on the same day now get `_2`, `_3` numeric suffixes instead of overwriting (checks both resume* and cover_letter* names).
  3. **Negative-failure caching** (`scrape/cache_helpers.py` `mark_failed`/`is_failed`): dead slugs (404/timeout) were retried for every keyword every run (~15 dead registry entries × 10 keywords ≈ 150 doomed requests/run). Now one attempt per TTL window. Wired into all 6 ATS scrapers: greenhouse/lever/ashby/smartrecruiters use `{"_failed": true}` JSON markers in both except blocks; `direct_scraper.py` uses string sentinel `"<!--fetch-failed-->"` (its cache is raw HTML text); `workday_scraper.py` uses a separate company-level `workday_{slug}_FAILED.json` (its results cache is per-keyword).
  4. `gui.py` **InboxTab UX overhaul**: (a) sortable column headers — click to sort (numeric cols score/fit/size start desc), click again to flip, third click returns to round-robin default; client-side over cached snapshot; ▲/▼ arrows in headings. (b) Filter bar: min score, source dropdown (auto-populated), size (S/M/L/XL/?), unscored-only checkbox, title/company text find, Clear button — all client-side, count label shows "N of M awaiting triage". (c) **Keyboard triage**: `t`=track, `d`=dismiss, `o`=open URL bound on the tree; selection auto-advances to the next row after track/dismiss (`_focus_index`/`_restore_focus`), so a screen can be cleared without the mouse. (d) Detail line → 4-line read-only Text pane: fit*why/score_notes + 600-char description preview. (e) **Dismiss Company** button: bulk-dismisses every \_visible* (filtered) row from the selected row's company, with confirm — the fast way to clear one mega-board's flood.
  5. **Batch resume prompts (~5 jobs/paste)**: `claude_bridge.py` — `_experience_corpus` factored out; `_BATCH_RESUME_INSTRUCTIONS` (JSON array, per-object `"i"` + the standard resume keys, "tailor each individually"); `build_batch_resume_prompt(postings, experience)`; `parse_batch_resume_response` → `{i: resume_data}`, skips malformed/incomplete objects (falls back to array position when `"i"` missing), raises only if nothing usable. `resume/service.py` — `build_batch_prompt(postings)` wrapper. `gui.py` ApplyQueueTab — `_BATCH_LIMIT = 5`; "Batch Prompt (5)" picks selected rows else walks the queue top-down, taking jobs that **still need docs AND have a saved description** (no per-job paste stop in batch mode), headers `Title/Company/Location` prepended, ids in `_batch_order`; "Paste Batch ▸ DOCX" saves each via `save_bundle_from_data(company=…)` (collision-safe now), updates `resume_path`/`cover_path`, fail-soft per item with an error rollup + "N missing from the reply" notice. Cuts the per-app prompt round-trips ~5×.
     **Queued for shell (Opus or recovered fable):** py_compile of the 12 touched files (gui.py, claude_bridge.py, match/scorer.py, resume/service.py, scrape/cache_helpers.py + 6 scrapers); GUI launch smoke (filter/sort/keys, batch buttons); negative-cache smoke (`*_FAILED.json` markers appear, second run skips); `py daily_run.py --prune-companies` to clean dead registry entries; **git commit (4 sessions uncommitted — Alex must approve)**.
     **Awaiting Alex's approval:** one-time trim/backfill of the 959 legacy inbox rows (bc=−1, pre-cap Anduril 311/SpaceX 188). **Still open from review:** canned ATS answers panel (apply/canned.py) — last unstarted item.

## Outstanding — Needs Alex

- [ ] `ANTHROPIC_API_KEY` in `.env` — get from console.anthropic.com
- [x] ~~ERP tech stack in `experience.md`~~ — resolved; placeholder filled, no placeholders remain (`experience.md` has uncommitted edits)
- [ ] `BRAVE_SEARCH_API_KEY` in `.env` — optional, free at api.search.brave.com; enables company auto-discovery
- [ ] **Commit `gui.py`** — currently untracked; also stage `experience.md` working-copy edits

## Session 9 — 2026-06-14 (Opus 4.8) ✅ ALL COMMITTED + PUSHED through 1493571

Caught up the repo and shipped four features + a bug fix. Spec: [[spec-2026-06-14-archive-search-projects]]. All verified; full suite **127 passing**.

- **Committed the 4-session backlog** (`627bce6`) and pushed — repo was stuck at `8fa925b`. The 2026-06-10 uncompiled pass was py_compile'd + smoke-verified first.
- **Fix: Workday/Caterpillar links** (`53e9469`). CXS `externalPath` is site-relative (`/job/...`) → `host+path` 404'd. `workday_scraper._job_url()` inserts the site (`/CaterpillarCareers/job/...`); `scripts/fix_workday_urls.py` backfilled **107/107** existing inbox links. Live-verified 200.
- **Archive** (soft-delete) (`df6aa52`). `applications.archived` col; `archive_job`/`unarchive_job`; `get_all`/`get_counts` exclude archived + `"archived"` filter. Tracker tab: Delete→**Archive**, Archive(n) chip, archive view = Restore + Delete-permanently. Archived stays in `tracked_urls()` (no resurface).
- **Search tightening** (`b74d696`). `search/query.py` boolean keywords (`"phrase"`, OR, NOT/-, ()) — back-compat; wired into `text_match` + scorer. Scorer downranks (never hides): `title_miss_penalty` (35), `exclude_titles` blocklist (profile-specific, **default empty** so Dad's data roles aren't hit; Alex's list in `user_config.json`), `seniority_exclude`. `scripts/rescore_inbox.py` ran → AI/ML/Data titles → 0, on-target kept (Mechatronics 79). `--list`/threaded through cli/daily/gui.
- **Job-Search Projects** Phases 0–3 (`54200ca`, `1375889`). `workspace.py` = call-time per-project path resolution (root fallback pre-migration). `scripts/migrate_to_projects.py` ran: 1098 inbox → `projects/controls-cincinnati/` (active), `dad-health-informatics` empty; `.bak` + row-parity OK. Repointed db/experience/output/config seams. GUI **project switcher** header (dropdown + New) rebuilds tabs live (controls 1098 ↔ dad 0). `--project` on cli/daily. `projects/` + `*.bak` gitignored (local data). **Phase 4 (per-project scheduler) DEFERRED** — the only remaining Projects work.
- **Add Companies via GUI** (`5457594`). `scrape/ats_detect.py`: `detect_ats` (greenhouse/lever/ashby/smartrecruiters/workday + direct), `parse_line`, `probe_count` (live count). Search tab **"+ Add Companies"** dialog: paste URLs → auto-detect → Validate → save to companies.json tagged with the project's industry. Live-verified counts.

**Open / next:**

- Projects **Phase 4** (per-project scheduler: `daily_run --project` is done; need per-project `setup_schedule.bat` + `daily` flag wiring).
- `setup_schedule.bat` still never run (07:30 task unregistered).
- Tooling could add: company **remove/edit** UI (currently hand-edit companies.json), Projects "Manage" (rename/delete).
- `tracker.db.bak` left in root (safety; gitignored) — delete after a release.

### Session 9 cont. — browser-extension verification (2026-06-14) ✅

Verified the LinkedIn/Indeed "collect while scrolling" pipeline end-to-end via Claude-in-Chrome live audit. Commits `64ff8ea`, `14bdd31` (pushed).

- **Receiver** (`browser_receiver` /harvest → score → inbox): verified live (POST → scored → inbox, cleanup); **fixed** it to thread `exclude_titles`/`title_miss_penalty`/`seniority_exclude` (was missing the search-tightening; harvested AI Engineer now → 0).
- **Indeed selectors: healthy** — 18/18 cards, title/company/location 100% (via the existing `data-jk`/`data-testid` fallbacks; primary `h2.jobTitle a` dead but chain holds). No change.
- **LinkedIn selectors: had silently rotted** (LinkedIn moved to `artdeco-entity-lockup`). Fixed in `content.js`: promoted the working lockup selectors to primary for company/location; **salary** now reads `.artdeco-entity-lockup__content` (was uncaptured — sits in the 2nd of two metadata wrappers w/ randomized class) and server `_parse_salary` pulls the $ (verified 5/5 salaried cards); **title de-dup** (LinkedIn repeats title in a hidden span → "T\nT", now first-line only). manifest 1.1→1.2.
- New `browser_ext/selector_check.js` = paste-in DevTools console self-audit for future rot.
- **NOTE for next use:** Alex must **reload the unpacked extension** (chrome://extensions → reload Job Harvester) to pick up v1.2; LinkedIn collection needs him logged in; `py -m scrape.browser_receiver` must run for "Send to Tool". The Claude-in-Chrome MCP tab is NOT logged into LinkedIn — selector re-audits need either his login in the controlled window or the console snippet in his own tab.

## Session 10 — 2026-06-15 (Opus 4.8) — Full review + first Hermes test slice

Full multi-agent code+product review of the whole app. **Complete findings → [[review-2026-06-15]]** (50 subsystem findings + 26 feature ideas + GUI audit + product roadmap + architecture recs + adversarial verdicts). **No code changed this session** — review + planning only.

**Headlines:**

- 🔴 **C1 (LIVE data bug):** `projects/dad-health-informatics/experience.md` is Alex's master file byte-for-byte (the migration copied it) → Dad's resumes/scoring use the wrong person's career.
- 🔴 C2 `daily_run` has no top-level error trap (silent dead 07:30 runs); 🔴 C3 `.exe` would crash on first use (no `.spec`, templates/quota under `_MEIPASS`); 🔴 C4 no global Tk exception handler (windowed `.exe` swallows errors); 🔴 C5 no WAL/`busy_timeout` on the shared `tracker.db`.
- Prior [[review-2026-06]] items are **mostly fixed**; the scorer is genuinely strong. The GUI is a **god-FILE not a god-object** — the fix is splitting `gui.py` into a package in Python, not a rewrite.
- Adversarial pass: score-compression (SCORE-1) and `norm_url` query-strip (TRACK-4) were **overstated** — real but smaller than first claimed; everything else confirmed; 6 cross-cutting items the readers **missed** (incl. C1 and inbox-score-staleness MISSED-3).

**Hermes test harness built** — `E:\ClaudeWork\hermes-test-01-jobapp\`: the first "Claude plans → Hermes executes" E2E test (the canonical job-search test from `MASTER-local-ai-stack` §P6). A high-value, unit-testable **8-fix slice** (query parser ×3, HN cache, salary parse, `_extract_json`, CSV injection, DB WAL, `daily_run` guard, dad-data + new-project seed) is written two ways: `plan.md` (Nemotron — **Windows-native**: one self-verifying `py` script per task in `staging\`, validated end-to-end → suite 140) and `claude-fallback-plan.md` (Claude). **Not yet run by Hermes.** 13 new tests; commits at end (no push); dad file backed up to `.bak`.

**Open / next (full list in [[review-2026-06-15]] §Recommended sequencing):**

- [ ] Run the Hermes test (or the Claude fallback) to apply the 8-fix slice → see `hermes-test-01-jobapp\START-HERE.md`.
- [ ] Then: C3 (`.exe`) + C4 (Tk handler) → Wave 2 `.exe` readiness → Wave 3 status-history analytics spine → Wave 4 `gui/` decomposition + service layer → Wave 5 ranking/apply polish.
- Output mode this session: **TERSE**.

## Session 11 — 2026-06-15 (Opus 4.8) — Hermes RAN the test + editing experiment staged

- **Test #01 EXECUTED by Hermes (Nemotron 30B) and PASSED.** It applied all 9 review-slice fixes via the Windows-native plan and **committed** them: **`e0ec05e`**, tree clean, **140 passing**. The "doom loop" Alex saw was only the `progress.md` free-form append (botched newline → retry loop) — the real work was done + committed. **Fixed:** staging scripts now self-log; `plan.md`/`START-HERE`/`SKILL` updated so the model never touches `progress.md`, + an anti-loop rule. Harness: `E:\ClaudeWork\hermes-test-01-jobapp\` (Windows-native, 11 `py` commands).
- **Test #02 BUILT (not yet run)** — `E:\ClaudeWork\hermes-test-02-edit\`: the real cost/capability experiment where **Claude writes only test + spec and Hermes writes the code.** 3 open fixes (SEARCH-5, SCORE-7, SEARCH-6), gradient edit→add→write-method. Validated achievable (Claude impl → 147 passing; reverted to clean 140). Run via its `START-HERE.md`; measure **how** Nemotron edits.
- **Learning:** the script approach saved ~no Claude tokens (Claude did the engineering); real savings = the test-02 division of labor. File-editing is the goal; the discipline is _verified_ editing (a test gate), not avoiding edits. Full detail: [[handoff_20260615_session11]].

> **HEAD is now `e0ec05e`, clean, 140 passing** (supersedes the stale `## Git` block below).

## Session 12 — 2026-06-22 (Opus 4.8, ultracode) — hardened + rebuilt as a distributable AI-native product

Largest build session to date. Brainstormed → spec → **5 phases**, all landed. **ALL LOCAL — push HELD** (Alex chose "keep local" pending confirming GitHub `alex-zagorianos/Job-Program` is PRIVATE; `experience.md` PII already on origin). master `e0ec05e` → **`6e1ac37`, 19 commits ahead of origin, 140 → 322 tests**, tree clean, only `master` remains (all delegate/allfixes feature branches + worktrees pruned).

**Approved design (the product):** two channels on ONE engine + data folder — (1) **EXE** with hybrid AI (clipboard bridge default + optional API auto), (2) **MCP server + Claude Code skill** where Claude Code itself is the ranker. Wide-net fetch → JSON hard-gate → cheap local scorer → AI fine-rank to `preferences.md`. Spec `brain/spec-2026-06-22-distributable-product-design.md`; plans `brain/plan-2026-06-22-phase{0,1,2}-*.md` (P3/P4 inline).

- **P0 Harden:** committed the 2026-06-19 relaunch work; **merged `claude-allfixes`** (290-test backlog; resolved 3 resume conflicts — kept relaunch ATS docx base + allfixes SSOT parser/generator + re-added Projects section); folded delegate **T4 `status_history`** (SCHEMA_VERSION 1→2); **C1 recurrence guard** (new-project resume copy now opt-in, default NO); untracked personal config (`config_dad.json`/`user_config.json`); deleted dead `resume/app.py`; pruned 8 worktrees.
- **P1 Data folder + prefs contract:** `config.USER_DATA_DIR` (external editable folder: `JOBPROGRAM_DATA` env › `./data` when frozen › repo-root in dev = unchanged); `workspace.BASE_DIR` roots there (fixes frozen `_MEIPASS` write); new **`preferences.py`** (`preferences.md` NL profile + `preferences.json` hard-gate {salary_min/locations/remote_ok/work_auth/dealbreakers/seniority_exclude} + legacy migration); **`userdata.scaffold()`/`bootstrap()`** + `data_templates/` neutral seeds.
- **P2 AI ranking:** new **`ranker.py`** anchors the existing fit prompt to `preferences.md` + experience summary; `rank_via_api` runs the same prompt+parser via API (key from env or `secrets/anthropic_key`); `gate` = hard-filter. Wired into the service so InboxTab + ApplyQueueTab both rank to preferences and `daily_run` hard-gates. **Fixed a LATENT post-merge bug:** ApplyQueueTab called the new list-returning `parse_fit_response` with the old `.items()` dict API (would crash) — rerouted through `tracker_service`.
- **P3 Packaging (buildable):** `userdata.bootstrap()` self-seed wired into gui + daily_run startup; `app.spec` PII-clean (drops `experience.md`/`user_config.json`; bundles `data_templates/` + `companies.json`); **`build_package.py`** → `dist/JobScout.zip` (app + seeded `data/` next to exe + README); `preferences.{md,json}` gitignored at root.
- **P4 Claude Code channel:** **`mcp_server.py`** — 6 stdio tools via the official `mcp` SDK's `FastMCP` (`get_preferences`/`search_jobs`/`list_inbox`/`set_fit_scores`/`track_job`/`dismiss_job`; CC is the ranker, no AI in the server) + `claude-code/` (`.mcp.json` + `find-jobs` skill + README) + `requirements-mcp.txt` (kept out of the exe build).

**🟡 REMAINING — Alex's machine/decision only:** (1) confirm repo PRIVATE → **push the 19 commits**; (2) `py build_package.py` → exe build + manual GUI test (the pyinstaller run was NOT executed here; GUI is windowed → needs a live launch; watch for an `ImportError` on a lazily-imported scraper/feed client → add it to `app.spec` `hiddenimports`, currently `anthropic, docx, bs4`); (3) docx title-line decision (kept relaunch bold-concat `Company — Title`; flip to allfixes ATS-split on request); (4) optional first-run setup wizard. Full record: HANDOFF `E:\ClaudeWork\HANDOFF.md` (2026-06-22) + memory `project-job-search`.

## Session 13 — 2026-06-22 (Opus 4.8, ultracode) — measure coverage, raise it with proof, AI re-rank round-trip

Three workstreams, sequenced **measure → improve-with-proof → tailor**. All merged + **pushed** (repo confirmed private). master `6e1ac37`/`7a7dad4` → **`228b013`**, **322 → 490 tests**, tree clean, only `master` remains. Specs `brain/spec-2026-06-22-ws{1,2,3}-*.md`; plans `brain/plan-2026-06-22-ws{1,2,3}-*.md`.

- **WS-1 Coverage foundations** (merged earlier this session, `7a7dad4`): entity resolution (cleanco/rapidfuzz/datasketch, all optional behind `try/except ImportError`) + a stable **`job_key`** (`models.JobResult.job_key` cached_property → `coverage.entity.job_key_for`, `sha1` of company_canon∣soc∣loc∣title_core, 16 hex) + a **3-leg coverage benchmark** (reference-proxy ∪ capture-recapture {chapman/chao1/good_turing/loglinear} ∪ JOLTS sanity gate → weighted composite). New `_deduplicate` (URL fast-path + keyless entity key). Regression anchor `tests/fixtures/coverage/baseline.json` (synthetic Cincinnati/15-1252 pin, composite 38.2 — **not** a live area number).
- **WS-2 Coverage engine** (merged `228b013`, 17 modules / 75 tests): generic **discovery funnel** (`discover/` — Common Crawl CDX slug harvest, careers-link finder via robots/sitemap/anchors, ATS detect, user-wins `registry.merge_discovered`) replacing registry-as-seed; **Tier-1 scrapers** (`scrape/` — workable/recruitee/rippling/personio + JSON-LD schema.org extractor + XXE/billion-laughs-safe `xml_safe`); **Workday CSRF prime + offset paging** fix; **free aggregators** (`search/` — Arbeitnow/Jooble/Careerjet/LinkedIn-guest) + BYO **SerpApi** (key-gated); **geo** metro/remote filter (`geo/filter.py`); deep **title+body** matching (`scrape/text_match.keyword_matches_deep`); per-source **freshness** deltas (`search/freshness.py`); `preferences.target_roles`. **Every source gated by a coverage-lift test** proving it does not lower the WS-1 score (`test_*_lift.py`, `test_depth_lift.py` — 6 gates green). `defusedxml` added to requirements (optional).
- **WS-3 AI re-rank round-trip** (merged `14c59d7`, 20 files / 45 tests, **stdlib-only**): pluggable **`Ranker`** protocol (`ranker.py` — Bridge/Api/File rankers); inbox **export** to csv/md with a versioned prompt anchored to `preferences.md` (`rerank/export.py`); validated CSV/JSON **import** with `job_key` join (`rerank/import_.py`, `rerank/schema.py`); **`score_history`** snapshots + **undo-last-rerank** (`tracker/db.py` **SCHEMA_VERSION 2→3**, mirrors the `status_history` precedent); GUI Export/Import/Undo + MCP `export_inbox`/`import_scores`.

**Build mechanics:** authored as 3 delegate-style plans. GLM executor hit the **z.ai 5-hour usage cap** (false-green no-op — recorded as a cc-delegate reliability bug in memory `delegate-buildout`); the harness `builder` worktree-isolation also based off the wrong commit. Worked around both by building WS-2/WS-3 as **`general-purpose` Sonnet agents in manually-created worktrees off master** (`__build/ws2`, `__build/ws3`), verifying each independently (full suite + import + lift-gates), then merging `--no-ff` (disjoint file sets → zero conflicts) and re-running the suite on master. Builders found + fixed 2 WS-3 plan bugs (broken test lambda; `inbox_set_fit` second-precision ts truncation so undo reverts the whole batch) and a WS-2 Workday monkeypatch-compat regression. Worktrees + branches + 9 stale delegate job-dirs GC'd (`delegate-clean -Apply`).

**🟡 REMAINING:** (1) **live coverage baseline** — the lift-gates prove improvement on fixtures; a real area number needs a live measurement run (network/sources), best done interactively. (2) WS-3 undo's second-precision batch grouping is fine for the manual round-trip but would only partially undo a batch straddling a wall-clock second — a `batch_id` is the clean follow-up. (3) carry-over from Session 12: `py build_package.py` exe build + manual GUI launch; docx title-line decision.

## Session 14 — 2026-06-22 (Opus 4.8, ultracode) — UI/UX pass: crisp look + non-technical onboarding

A look-and-feel + usability pass so a total non-technical user can run the app unaided. Built **inline** (concentrated in `gui.py` + a new `ui/` package; visual/taste work needing a rendered eyeball; prior delegate runs hit the z.ai cap). Four confirmed decisions: **clean light & modern** theme, **all four** help surfaces, **relabel** (not hide) the AI controls, build a **first-run Setup wizard**. **Committed locally, NOT pushed** (awaiting Alex's go).

- **New `ui/` package** (keeps `gui.py` focused; fully unit-tested): `theme.py` (real ttk `clam` theme — one accent `#3b5bdb`, white surfaces, zebra tables, flat notebook tabs; widget factories `btn`/`header_bar`/`tip_strip`/`zebra`/`Tooltip`), `help.py` (scrollable **Guide** tab rendered from a `GUIDE` list + Help-menu dialogs + `open_data_folder`), `setup_wizard.py` (pure `build_preferences`/`_search_config`, `apply`, `SetupWizard`, `.onboarded` marker).
- **`gui.py`:** theme applied app-wide; **menu bar** (File/Help); 6th **❓ Guide** tab; per-tab tip strips; every `tk.Button`→`theme.btn`; zebra-striped tables; dialogs recolored; AI controls **relabeled in plain English** ("Ask AI to rank these"/"Paste AI ranking"/"Load AI results"/"Undo AI ranking"; merge dropdown "Replace it / Keep the old one / Only fill blanks"); first-run wizard auto-launches.
- **Adversarial self-review** (5-dimension Workflow → per-finding verify → synthesis): 9 findings, all verified real (1 major, 8 minor), **all fixed**:
  - **MAJOR** — wizard never collected the free-text "about" narrative (the single highest-value AI-ranking input; the generated `preferences.md` literally instructed the user to provide it) → added an optional multi-line box on the roles step, cached across re-renders, returned by `_collect()`.
  - **Project-aware preferences** (the one architectural fix) — `apply()` wrote prefs to the root while config/resume went per-project, so re-running the wizard after creating a project desynced them; `ranker`/`rerank` call `preferences.load()` bare and had the same latent **read-side** desync. Added `workspace.preferences_paths(slug)`; routed both `apply()` **and** `preferences.load()` through it. No-project common case is byte-identical (root).
  - Wizard counter "of 4" vs "three steps" copy → counter excludes the welcome intro ("Step 1–3 of 3"); **Skip now confirms**; skip/close lands the user on the **Guide** (was stranded on an empty Search tab); merge label "already scored"→"already has a Fit grade"; Guide now **defines Score-vs-Fit** and that the Inbox **starts empty** day-one; README defers to Help→Open my data folder and fixes the stale "Copy fit prompt" button name.
- **Tests:** +20 since Session 13 (14 `tests/ui/` + 6 project-aware-prefs/help) → **510** (`py -m pytest -q`, ~7s, 1 display-guarded skip headless). Live wizard-walk + full-App construct smokes pass. `app.spec` unchanged (the `ui` package is imported at `gui.py` top level → PyInstaller bundles it).

### Session 14 cont. — dark mode + deepened "use it with AI" guide (2026-06-22) ✅

Two follow-on asks, same inline approach + an adversarial review pass. **Local commit on top of the first; push still held.**

- **Light/Dark theme switch.** `theme.py` now holds `_LIGHT`/`_DARK` palettes; `set_mode()`/`current_mode()`/`toggle_mode()` rewrite the module-level color names so every `theme.X` reference picks up the active mode the next time a widget is built; `apply_theme(root, mode=None)` restyles ttk live. New `ui/settings.py` persists the choice to `USER_DATA_DIR/ui_settings.json` (best-effort; gitignored). gui.py: a **View → Dark mode** checkbutton → `_set_theme()` which persists + restyles ttk + re-syncs the legacy color aliases (`_sync_palette_aliases`) + reconfigures the root + rebuilds the project bar (grouped under `self._projbar`, packed `before=self._nb`) and the tabs (`_rebuild_tabs(select_index=…)` keeps the user's tab). Tracker status badges are now theme-aware (`theme.STATUS_BADGE`, brightened on dark). Tooltips use `TOOLTIP_BG/FG`. Saved mode applied at startup.
- **Deepened AI guidance.** `help.py` GUIDE gained "Working with AI — the heart of this app" + "Getting the most out of AI" (Score-vs-Fit, the free clipboard round-trip step-by-step, file Export/Load, feed-it-a-rich-profile, pick-a-capable-model/iterate, trust-but-verify/privacy) + a new Help → "Getting the most from AI" dialog (`show_ai_help`).
- **Adversarial review (Workflow) — partial (hit the z.ai/Anthropic session cap mid-run) but returned 4 verified findings, all fixed**, then I finished the sweep by hand: themed every un-themed `tk.Text` (PasteDialog/ResumeTab/JobDialog-notes/AddCompanies) with `bg=SURFACE/fg=INK/insertbackground=INK`; added `fg`+`selectcolor`/active colors to the InboxTab filter Source/Size/Find labels + "Unscored only" checkbutton (were black-on-dark); repointed transient status-label hex (`#e65100`/`#2e7d32`/`#666`/`#888`) to `theme.WARN/SUCCESS/MUTED`. **Accuracy fix:** the AI help had claimed an API key "ranks the inbox automatically, including the daily update" — but `rank_via_api` is only reached via `ranker.rank()`, which neither the GUI nor `daily_run` calls (daily_run only `ranker.gate`s; the GUI uses the clipboard/file bridge). Reworded so the key is correctly tied to AI **resume/cover generation**, and ranking is described as free/no-key.
- **Tests:** +13 (`test_settings.py` ×5, theme modes/badges ×6, help AI-content/accuracy ×2) → **522** (`py -m pytest -q`; 1 display-skip headless). Live dark-switch smoke: root + rebuilt tk widgets recolor, aliases re-sync, selected tab preserved, choice persists; resume/paste boxes go dark, filter labels readable, badges brightened.

## Session 15 — 2026-06-22 (Opus 4.8) — Top Picks: full-inbox AI snapshot → ranked top-X

Make the **whole relevant set trivially consumable by an AI**, let the AI judge relevance itself, and write back a **ranked top-X shortlist** that surfaces in a new GUI **Top Picks** tab. Built **inline**, TDD (brainstorm→spec→plan→approve). **Committed local, push HELD.** Handoff [[handoff_20260622_session15]]; spec `brain/spec-2026-06-22-top-picks-recommendation-design.md`; plan `brain/plan-2026-06-22-top-picks-recommendation.md`.

**Locked decisions (AskUserQuestion):** both channels (AI-consumable set **and** GUI Top Picks view) · relevant set = the **full inbox, AI judges relevance itself** · one full snapshot then rank. **Approach A** (reuse `extras` JSON + the rerank `new_rank` column) over B — top-X with **zero new DB surface**.

- **No DB migration.** Rank rides in each inbox row's existing **`extras` JSON** (`rank` + `rec_batch`); `SCHEMA_VERSION` unchanged. **Latest `rec_batch` wins** so a fresh AI run supersedes the prior shortlist. One place owns the shape: `service.rank_patch(rank, batch, tags=None)`.
- **`tracker/db.py`** `inbox_merge_extras` (key-preserving merge, tolerant of missing/non-dict blob). **`tracker/service.py`** `new_rec_batch`/`rank_patch`/`read_rank`/`top_picks(limit=10)` (latest-batch, `rank>=1`, best-first, cap). `apply_rerank_scores` untouched.
- **`rerank/`** import maps CSV `new_rank`→`extras` rank + a per-call `rec_batch`; `build_prompt` explains `new_rank` as the Top Picks signal (`RERANK_CSV_COLUMNS` frozen).
- **`mcp_server.py`** `list_inbox(limit=0)` returns the WHOLE inbox + `rank` + `job_key`; `set_fit_scores` accepts an optional `rank` (→ `inbox_merge_extras`). **`find-jobs` skill** rewritten to one-snapshot→rank.
- **`gui.py`** new **`TopPicksTab`** (rank/fit/title/company/location/why/score/source; Show-top-N 10..50/All; empty-state; Track/Dismiss/Open; themed) wired between Inbox and Search across `_build_tabs`/`_rebuild_tabs`/`_on_tab_changed`. InboxTab Export-for-AI scope toggle (default **Entire inbox**).
- **Tests:** +16 (`tests/test_top_picks.py`, `tests/ui/test_export_scope.py`, `tests/ui/test_top_picks_tab.py`, + rerank/mcp/schema extensions). Back-compat (list_inbox defaults, apply_rerank, export, existing mcp/schema) all green.

## Session 16 — 2026-06-24 (Opus 4.8, ultracode) — wire the latent gaps + mechanical-debt sweep

A familiarize → fix pass on findings from a fresh subsystem audit (9 parallel readers + a live-suite verify). All built this session; **committed local, push still HELD** (rides the Session 14/15 hold). master `6bf3722` → **+4 commits**, **553 → 572 tests** (`py -m pytest -q`, ~7s). Three behavior-changing wire-ups (all confirmed in via AskUserQuestion) + two cleanups, five clusters:

- **JSON-LD wired** (was orphaned dead code): `direct_scraper` now folds same-page schema.org/JobPosting JSON-LD into its results (deduped by `identity_key` — strictly additive, can't lower coverage); new `jsonld` ats_type; shared `_fetch_html` keeps the negative-failure cache. (`00f97f0`)
- **Discovery funnel unified** (was built-but-unreachable): new `discover/funnel.run_funnel` combines Common-Crawl-CDX harvest + per-domain careers-link finding → `registry.merge_discovered` (user-wins, additive-only), behind `py -m search.cli --discover [--discover-domains …]`. (`db82cb2`)
- **Freshness deltas surfaced** (was unintegrated): `daily_run` marks jobs new vs a project-scoped baseline (`search/freshness`, `daily:<slug>`; manual searches don't move it), stamps new inbox rows' `extras.new_batch` (schema-free, latest-batch-wins like Top Picks), GUI gains a **"New only"** Inbox filter. `JobResult.is_new` is transient; `inbox_add_many(new_batch=…)` is opt-in. (`5350056`)
- **normalize_url deduped**: `tracker/db.normalize_url` was a parity copy of `models.normalize_url` → now imported from `models` (verified byte-identical for all inputs, so the inbox `norm_url` UNIQUE key is unchanged). (`5350056`)
- **GLM-delegated mechanical bundle** (`b328f00`, via cc-delegate → glm-5.2, green/$0.65, Opus-planned+verified): `exclude_keywords` now match on **word boundaries** (was substring — "ai"⊂"maintain", "remote"⊂"remotely"); `claude_bridge.to_clipboard` **cross-platform** (clip/pbcopy/xclip/xsel) for the off-Windows distributable; `config.ANTHROPIC_MODEL` **env-overridable**; dropped the **vestigial `datasketch`** dep (never imported); `app.spec` hardened via **`collect_submodules`** (frozen-exe ImportError guard for lazily-imported app modules); scorer size-modifier docstring → its 4 bands.

Build mechanics: 9-reader audit Workflow → `AskUserQuestion` locked all 3 wire-ups in → 5 clusters built inline (TDD, each additive/lift-safe), 1 mechanical cluster delegated to GLM (fully-inlined weak-model-proof plan, file-disjoint, transferred into master after a confirming verify). +19 tests. **Doc-undercount note (now corrected here):** MCP exposes **8** tools — get_preferences/search_jobs/list_inbox/set_fit_scores/track_job/dismiss_job + **export_inbox/import_scores**; the company-size modifier has **4** bands (≤30 +8, ≤100 +4, ≤250 −2, >250 −6), not 3.

## Session 17 — 2026-06-24 (cheap-backend, autonomous) — dead-link fix + competitive Tier 1–3 buildout

Beta-test session → big autonomous build. (1) Diagnosed the AI-lane "dead links": Greenhouse
`absolute_url` is often a company JS careers SPA that never renders the job; **build the
server-rendered hosted URL** `job-boards.greenhouse.io/embed/job_app?for=slug&token=id` from slug+id
(`scrape/greenhouse_url.py`), add an inbox **liveness prune** (`scrape/inbox_health.py`,
`--prune-inbox` + GUI button, 404-only), and a repair script that fixed 914 existing rows
(browser-verified). (2) Ran a 12-agent **market-research workflow** (no product ships JobScout's
6-leg combo; closest = OSS Swiss Job Hunter 4/6) → 41 mined features (`E:\ClaudeWork\_jobscout_
features_digest.md`). (3) **Built the Tier 1–3 roadmap.** Full record: `handoff_20260624_session17`,
plan `brain/plan-2026-06-24-all-tiers-buildout.md`, decisions/questions `brain/buildout-log-2026-06-24.md`.

**Shipped:** all of **Tier 1** (T1.1 clean-dead-links + daily prune · T1.2 structured scorecard in
the detail pane via `scorer.score_breakdown` · T1.3 colored score cells · T1.4 empty states · T1.5
Tools▸Due via `db.followups_due` · T1.6 Tools▸Connect-AI key box via `config.read/write_secret` +
`ui.settings` · T1.7 Help▸Privacy) · **Tier 2** T2.8 Tools▸Funnel (`tracker/analytics.py`) · T2.9
ghost staleness + Hide-stale (`match/ghost.py`) · T2.10 skill-gap (`match/skillgap.py`) · T2.11
SmartScreen kit in `build_package.py` · T2.12 first-search on Setup finish · **Tier 3** T3.14 comp
normalizer + pay-floor filter (`match/comp.py`) · T3.18 contacts CRM (`contacts` table,
SCHEMA_VERSION **3→4**) + Tools▸Contacts · T3.22 opt-in daily discovery refresh · T3.23 T/D/O hints
· T3.24 File▸Backup/Restore. New engine modules built **in parallel via delegated worktree agents**
(Workflow), reviewed + merged; gui.py wiring done inline (single delicate file). Every new
liveness/ghost/comp/location signal is **view-level — the 0-100 score is untouched** (the
location-filter precedent).

**Not built (remaining roadmap, specced in the plan):** T2.13 browser-ext capture-on-submit; T3.15
age/repost display; T3.16 size facets; T3.17 `job_key` dedup (held — subtle); T3.19 filter presets;
T3.20 review-mode card; T3.21 onboarding checklist; T3.27 tunable weights (**Q2 — Alex's call**);
T3.28 auto-update. **Deferred (D2):** web/Tauri reskin, Gmail-OAuth email status.

**Open questions:** Q1 docx title-line; Q2 expose tunable weights?; Q3 daily auto-prune on by
default? (all default-handled, logged in the buildout log).

## Session 18 — 2026-06-25 (cheap-backend, ultracode) — modern UI (ttkbootstrap) + extension data buildout

Two requests: make the GUI modern + fix the jarring dark-mode white outlines, and build the
browser extension out to pull in as much job data as possible. Full record:
`handoff_20260625_session18`. master `1c80295`… → **+5 commits**, **683 → 696 tests**, push HELD.

**Task 1 — modern UI on ttkbootstrap.** Adopted **ttkbootstrap** as the ttk Style engine (Alex
picked "evaluate ttkbootstrap"; it passed eval — runs on 3.13, Pillow already present, no gui.py
rewrite). `ui/theme.py` stays the facade — every color name / helper / style name preserved. The
**white outlines are gone at both sources**: ttkbootstrap's element layouts are flat (the old
`clam` lightcolor/darkcolor bevel is what drew the light edge on every input), and the 5 `tk.Text`
panes now route through a new `theme.text_widget()` (themed 1px border, not the default ~white
focus ring). Modernized both palettes (indigo accent, real dark-mode surface elevation), bigger
rowheight/padding, accent-underline tabs. **Two non-obvious integration hacks** (documented in
theme.py): (a) **restore the vanilla classic-tk constructors right after importing ttkbootstrap** —
ttkbootstrap monkeypatches `tk.Frame/Label/Text` to force-recolor every classic widget to its own
palette, which would obliterate the app's hand-painted chrome (accent rules, colored status badges,
surface elevation); we want only its _ttk_ theming. (b) **build the Style singleton once and
_rebind_ it (master/tk) per root** rather than rebuilding — re-running `Style.__init__` re-triggers
a localization/msgcat init that races with pytest's many short-lived Tk roots and flakes. EXE:
`ttkbootstrap` (+submodules +localization data) + `PIL` added to `requirements.txt` + `app.spec`.

**Task 2 — extension pulls full job data.** Was card-only (title/company/location/salary), so
harvested jobs had **no description → the scorer's 25-pt skill component was always 0**. content.js
now has a **passive detail layer**: when you OPEN a job (LinkedIn/Indeed right pane or `/jobs/view`)
it reads the full **description** + a raw details blob and **upgrades that job's stored card in
place**, matched by a stable external id (LinkedIn job id / Indeed `jk`). No auto-clicking — only
jobs you open get the full record (stays "assisted, never automate"); LinkedIn + Indeed only. One
**server-side parser** owns field extraction (same DRY trick as salary, so the JS can't diverge):
`parse_details()` pulls **work mode / employment type / seniority / applicants / posted age /
easy-apply**. `_to_job_result` now threads the real **description** (honest scoring + skill-gap /
comp / ghost finally work for browsed jobs), derives `created` from the **posting age** (accurate
recency/staleness), and attaches rich metadata to the inbox row's **`extras["browse"]`** —
schema-free, **view-level, never folded into the 0-100 score**. The Inbox detail pane surfaces
"Captured while browsing: Remote · Full-time · Mid-Senior level · 47 applicants · Easy Apply"; the
popup shows "Y of N with full details" (silent detail-rot visible); `selector_check.js` now audits
the detail-pane selectors; manifest → **1.3**.

**Pre-push adversarial review** (Workflow `jobscout-session-review`, 7 agents over 5 dimensions —
theme integration, receiver parsing, extension JS, privacy/security, GUI+tests — each finding
independently verified). 2 raw findings → **1 confirmed, fixed**: an id-less detail pane (Indeed's
bare search auto-opens the first result before `vjk` is in the URL) hit the standalone-record push
with no dedup → a fresh duplicate every ~600ms observer tick (client-side only — `inbox_add_many`
dedups by `norm_url`, so the inbox never saw them). Fix: `extractDetail` now requires a
URL-identified job + the standalone push is idempotent; verified by node simulation. No
privacy/security/packaging regressions found.

**Live-verify owed (Alex, can't be done headless):** the LinkedIn/Indeed detail selectors are
best-known + generously-fallback'd but unverified against the live DOM — paste `selector_check.js`
with a job open and send the output to patch any rot.

## Session 19 — 2026-06-25 (cheap-backend, ultracode) — company-acquisition pipeline + remote-first-class

Research → plan → build. A 6-angle web-research workflow (+ adversarial fact-check of the
load-bearing stats) on **how LinkedIn/Indeed data is acquired and how jobs are actually found**
concluded: there's **no read API** for either (LinkedIn's is write-only/closed; Indeed's died ~2020),
all that's left is fragile/legally-hazardous scraping (Proxycurl, the biggest, was sued + shut down
2025), and the **safest way to touch them is the user's own browser session — exactly the existing
extension**. Structurally, LinkedIn/Indeed are **syndication layers on top of the ATS** (Greenhouse
Limited Listings + Indeed XML feeds are fed FROM the ATS), so a comprehensive **company-careers/ATS
registry captures the canonical posting, often earlier** — and **the registry (which companies to
poll) is the binding coverage constraint**, not extraction. The "80% hidden / 85% networking" stats
are debunked folklore; measured ATS data (Ashby, 38M apps) says inbound/posted applications dominate
tech hires. Residual gap of skipping the boards = the no-ATS SMB/industrial/agency tail (Indeed-only)
→ that's the extension's job. Full record: `handoff_20260625_session19`; plan
`~/.claude/plans/shimmering-moseying-wadler.md`. master → **+5 commits**, **696 → 725 tests**, push HELD.

**Built (4 phases, plan-mode approved):** **(1) Remote first-class** (`dbcc793`): `_location_score(…,
remote_ok)` credits an acceptable-remote role with full location points (was 0 — capping remote at
85/100 and burying it below local); `remote_ok` threaded through `score_job`/`score_jobs`, sourced
from `preferences.json` at daily_run/browser_receiver/GUI. **(2) Metro enumeration** (`67cd176`): the
core "add companies" engine — `discover/enumerate.py` (an LLM proposes {name,domain} for a metro +
industries; **Bridge/Api duality** like `ranker` — API if key, else clipboard-bridge) +
`enumerate_companies.py` (enumerate → resolve via `career_link`+`detect_ats` → **probe-verify gate**
→ `save_companies`). The probe gate makes LLM enumeration safe: hallucinated/dead companies resolve
to no live board and are dropped. **(3) Enterprise-ATS** (`c520849`): Workday public-URL →
`tenant:N:site` (already worked; tested); **iCIMS/Taleo/SuccessFactors** detected by host + routed to
the existing `jsonld_scraper` (their pages carry schema.org/JobPosting LD — the data Google for Jobs
reads), with a `probe_count` JSON-LD branch so enumeration can vet them. Lightweight — no bespoke
fragile API scrapers. **(4) Tiered scheduling** (`e5375d6`+`111bd84`): `scrape/tiering.py` (pure;
hot=daily/warm=weekly/cold=monthly; an active board is **never starved** so coverage can't regress)

- opt-in `CareersClient(tiered=…)` (default OFF → byte-identical) + `daily_run` `tiered_scrape` flag,
  so a 1–2k-company registry keeps the daily run fast.

**Reused ~70%:** discover/funnel + career*link + detect_ats, verify_and_add probe pattern,
company_registry.save_companies (user-wins, append-only), coverage/ benchmark + lift-gate,
geo/filter + metro_variants, ranker key/SDK + claude_bridge.\_extract_json, FileCache/RateLimiter/
ThreadPool. **Deviations (justified):** no hardcoded seed list of guessed Workday/iCIMS slugs (risks
dead entries — enumeration discovers them properly); skipped `arbeitnow` (EU-noise). **Pre-push
adversarial review** (1 agent over the diff): **no real bugs**; refined one minor wart (the cold tier
was dead in the live path → now an errored board is correctly marked cold). **Open minor:** the CLI
location-\_sort* tiebreak hardcodes remote_ok=True (inbox **scoring** honors prefs correctly).

## Git

- Sessions 14–19 = **37 local commits on `master`, NOT pushed** — awaiting Alex's `py gui.py`
  eyeball then `git push`. Now includes, on top of the S14–17 surface (colored score cells, scorecard
  detail pane, Hide-stale / Meets-pay-floor / New filters, Clean-dead-links, empty states, **Tools**
  menu [Due/Funnel/Contacts/Connect-AI], **Help▸Privacy**, **File▸Backup/Restore**): the **S18 modern
  ttkbootstrap theme + dark-mode white-outline fix** (eyeball in both light & dark), the **browser
  extension's full-detail capture** (S18), and the **S19 company-acquisition pipeline + remote-
  first-class** (metro enumeration CLI, enterprise-ATS, tiered scheduling — all opt-in/additive).
  master `fe96b71` + 37.
- **New dependency (S18):** `ttkbootstrap==1.20.4` (+ Pillow, already present) — in `requirements.txt`
  and `app.spec`. First `py build_package.py` after this needs the EXE re-tested (ttkbootstrap data +
  PIL now bundled). S19 added **no new deps** (anthropic SDK already present).
- Remote: `git@github.com:alex-zagorianos/Job-Program.git` (private).
- Full suite: **725 passed** (`py -m pytest -q`, ~9–17s; display-guarded Tk tests skip headless,
  shows as 724 + 1 skip). Python command: `py`. GUI constructs + live light↔dark toggle verified.
- Active project: `applied-ai` (672-row inbox after the S17 dead-link prune). DB schema **unchanged
  at v4** — S18 browse metadata + S19 tier state ride JSON (extras / registry_state.json; no migration).
- **S19 new entry points:** `py enumerate_companies.py` (grow the registry; API or clipboard-bridge),
  `"tiered_scrape": true` project-config flag (tiered daily run).

## Session 20 — 2026-06-30 (Opus 4.8 + GLM + Sonnet) — deep review + remediation buildout

Reviewed the whole app (41 verified findings via a multi-agent workflow), ran a **live new-user
test of the built `.exe`**, then fixed **every** finding via a plan-mode-approved remediation
delegated across **GLM** (cheap engine fixes, `cc-delegate`) and **Sonnet** (the Scrapling seam +
the delicate gui.py UX cluster), with Opus doing build-judgment/delicate bits inline. **ALL LOCAL
on `master`, push HELD.** Full record: [[../handoff_20260630_session20]]; plan
`brain/plan-2026-06-30-review-remediation.md` (coverage map). Suite **725 → 841**.

- 🔴 **CRITICAL found + fixed + re-verified on the rebuilt exe:** the distributable crashed on
  first real use — `app.spec` never bundled `data_static/`, so the inbox's default "Local + remote"
  filter hit a missing `cbsa_delineation.csv` → windowed exe died ("Unhandled exception in script").
  Only surfaces with a _populated_ inbox in the _frozen_ build (empty-inbox launch passes). Fixed
  (bundle + graceful `geography._rows`); rebuilt exe boots on the populated inbox.
- **Schema v4 → v5** (`score_history.batch`, additive ALTER; undo now reverts the whole rerank
  batch + clears Top-Picks rank).
- **Scrapling integrated (lean-exe variant — Alex's call):** lazy stealth/JS fetch fallback in
  `direct_scraper` (config-gated, graceful no-op); **Tools ▸ Enable stealth fetching** downloads
  Chromium (~300 MB) on demand; app.spec bundles scrapling/playwright python+driver, NOT the 1.4 GB
  browsers. New dep `scrapling` in requirements.txt.
- **Top Picks now fills from the FREE clipboard pass** (was empty for the taught workflow); **New
  Project** registers a "Default" project so the root inbox isn't orphaned; **tracker CSRF/Origin
  guard**; `safe_url` on all URL-open sinks; Indeed `?jk=` preserved (extension manifest **1.4**);
  Ashby prune via board-API; many parser/gate accuracy fixes.
- **Deferred (1):** F25 (job_key-collision on import scores only the first row) — `inbox_rows_by_key`
  has ~15 dependents; a collision means two canonically-identical postings (first-row-wins is
  acceptable, the other keeps its local score, not dropped). Revisit with a batch_id 1:1 join if needed.
- **Needs Alex:** eyeball `py gui.py` → **push the 79 local commits**; reload extension (manifest 1.4).

## Session 21 — 2026-06-30 (cheap-backend) — controls smoke test + AI-pipeline optimization (decompose ranking for cheap/local models)

Built in this session, committed under the Session-20 push (now **pushed**, origin even). Full record: `handoff_20260630_session21.md`; spec `brain/spec-2026-06-29-ai-pipeline-optimization.md`. The AI-pipeline spine was committed (`7d9a721`) then **Session 20's review hardened its heuristics** (`02471d7` = S20 findings F4/F5/F10 on `match/facts.py`).

**Part 1 — controls smoke test.** Registry was already broad (~98 controls entries); a 3-pass direct-slug **probe-verify** added **8 net-new live boards** (Samsara, PsiQuantum, Neuralink, Epirus, Noah Medical, Tenstorrent, Shield AI, Crusoe). Wrote `projects/controls-cincinnati/preferences.md` (was the blank template) from `experience.md` JOB-SEARCH-CRITERIA. Careers-only scrape → **1514 jobs in ~84s** → local `score_jobs` (median 44, max 87, 35≥70) → AI-ranked top 18 (real `ranker` round-trip) → fit + Top Picks into the controls-cincinnati inbox. **Finding:** `enumerate_companies.py`'s discovery path (`find_career_url` domain→ATS) yields only ~1/10 — modern ATS boards are JS-SPAs invisible to robots/sitemap/anchor scraping; the LLM step is fine, the resolver is the weak link → direct-slug+probe is far higher-yield.

**Part 2 — AI-pipeline optimization (model-agnostic spine).** Insight: the recurring AI cost is small (18 jobs); the expense was a frontier agent doing/supervising deterministic work + hand-enumerating companies. Decomposed into narrow, cached, specified steps; **same `parse_response` contract** so consumers are unchanged. New: `match/facts.py` (deterministic extraction, cached by job_key), `match/rubric.py`, `match/gate.py` (drops intern/clearance/foreign-visa/people-management/excluded-title/over-senior **before** any AI — drop = excluded from the AI batch, keeps local score), `claude_bridge.build_fit_prompt_compact`, `ranker.build_compact_request`/`prepare_compact`, `tracker/service.compact_fit_prompt_for_rows`+`mark_inbox_gated`. **Wired live:** both "Ask AI to rank these" buttons (Inbox + Apply Queue) use the compact, gated path; gated jobs get a low fit + "Auto-filtered: \<reason\>" so they don't re-surface. **Effect:** live smoke 20→18, prompt **71% smaller** (~8.5k→2.4k tok), no AI spent on structural non-fits, fully offline/deterministic. **+29 tests** (725→754, folded into the 841 suite).

**DEFERRED (Alex's call): local-model integration** (spec §11b) — `LocalRanker`→Ollama, the granite-vs-gemma-vs-frontier Spearman eval to pick the SCORE model, endpoint choice. Recommended cascade: **frontier (cached) for extract+rubric** (comprehension; errors propagate), **small/fast model (granite) for score** on pre-extracted facts, deterministic for gates/harvest.

**Repo/Needs Alex:** master **pushed** (origin even), **841 passing**. **1 uncommitted file** `tests/test_scorer_compress.py` — made `test_confidence_marker_data_rich` hermetic (explicit `skill_terms`); was red because the active project drifted to **dad-health-informatics** (0 skills → `conf 4/5`, correct behavior, fragile test) — commit+push it with these doc edits. **Active project is `dad-health-informatics`** — switch back to `controls-cincinnati` for controls work (that's where the Top Picks / 18 ranked jobs live).

## Session 22 — 2026-06-30 (cheap-backend) — search-perf + parallelization + coverage measurement + 3 build plans

Full record: `handoff_20260630_session22.md`. **859 tests, push held.** Shipped: parallelized fetch to (client[,keyword]) units (~5× cold), tiered timeouts, 7-day dead-URL TTL, GUI source toggles honored; Himalayas depth cap 200→100 (killed a 61s cold sweep); `coverage/registry_coverage.py` Chapman capture-recapture + `company_coverage.py` CLI; exec/management-seeker gate fix (`match/rubric._EXEC_RE` infers management intent from target roles). **PLANNED but did not build 3 plans** (`brain/plan-2026-06-30-{company-coverage-100,board-expansion,agnostic-multiprofile}.md`) → built in Session 23.

## Session 23 — 2026-06-30 (cheap-backend) — BUILT all 3 Session-22 plans

Full record: `handoff_20260630_session23.md`. **859 → 925 tests (+66), push HELD.** 8 commits `56e5366`→`fdf0483`. TDD, each phase committed + full-suite-green, everything config-gated so Alex's controls flow is byte-identical.

- **Plan 1 (coverage→100%, P1–P6):** `discover/dataset_seed.py`+`seed_companies.py` (bulk MIT ATS-slug import through the live probe-verify gate, dataset-agnostic stdlib parse, $0, no new deps); `angles_for_industry` + `config.DEFAULT_INDUSTRY` (eng/empty = `DEFAULT_ANGLES` byte-identical; other field = neutral named angles; `scope='national'`); `discover/classify.py` relevance gate (deterministic-first, AI-on-ambiguous, cached, never drops no-sample); `estimate_coverage_industry` + `loop_signal` + `coverage/registry_history.py` (per-industry `.jsonl`, `--record/--loop-signal`); nationwide/remote-first 2nd enumeration pass gated by `hard.remote_ok`; `cc_harvest.harvest_host_index` (registered-domain CDX, paginated) + enterprise ATS domains (Workday/iCIMS/Taleo/SF) via `run_funnel(host_level/enterprise)` + `--discover-host-level/-enterprise/-max-pages`.
- **Plan 2 (board-expansion):** `config.SERPAPI_ENGINE` (google_jobs|indeed) + engine-select/defensive-parse in `serpapi_client`; `models.normalize_url` unwraps Google/generic redirects + collapses Indeed→`jk` so click-redirects dedup to one row. No standalone Indeed scraper (ToS).
- **Plan 3 (agnostic + multi-person):** wizard Field/industry + Career-level (→ rubric keys), `has_industry` discover-hint; **`match.facts` industry-gated** — tech/empty keeps eng role map + skill vocab byte-identical, other fields merge universal role buckets (care/admin/finance/trade) + profile-derived skills, `facts_for` caches under a **profile signature** (no cross-person/-industry leak — the job_key-only cache trap); `ranker` threads `(industry, skill_terms)`. **Person = project:** `workspace.create_project(person=)` + `people()`/`projects_for_person()`/`person_of()`, GUI **+ Person** button + "Person — Campaign" labels; ranking follows active person for free.

**Autonomous defaults used** (Alex away): dataset importer built **dataset-agnostic** (real bulk import = Alex's data-op: `py seed_companies.py --dataset f.csv --industry …`; recommend OpenJobs); loop_signal <2%/2-rounds/≥85% (overridable); SerpApi free default kept; P5 national = **explicit `--national` opt-in** (changed from remote_ok-default after review). **Needs Alex:** eyeball `py gui.py` (wizard fields, + Person); **push 10 commits**; run a real dataset seed + `company_coverage --record --loop-signal` to actually raise coverage.

**Adversarial review at close (`2dc1a82`) — 9 confirmed defects, ALL fixed (925→931 tests, `tests/test_review_fixes_s23.py`):** `normalize_url` generic redirect-unwrap over-collapsed direct/apply URLs (real inbox data-loss) → host/path-gated; **`ranker._facts_profile` didn't fall back to active config when cfg=None → the 1E agnostic feature never fired through the live GUI "Ask AI to rank" path + collapsed the facts cache to the shared job_key-only file** → now falls back like build_rubric (tech byte-identical); `harvest_host_index` lost earlier pages on a later-page failure → first-page reachability; `dataset_seed` ignored the real name column → same-slug boards collided → threads real name; national pass now explicit opt-in; `_new_person`/`_new_project` duplicate-slug guard; project switcher index-based; `classify` symbol-keyword regex (C++/.NET).

**Post-session — real-data test setup (2026-06-30):** Dad's real resume (healthcare analytics/BI leadership, 20+ yrs, Epic Clarity/Power BI/SQL/HIPAA) saved to `projects/dad-health-informatics/dad-resume-2025-v2.docx` + extracted → that project's `experience.md` (canonical `## ` headings; verified: 6 sections, 44 skill terms). Then a **dedicated isolated TEST project** `projects/health-informatics-test/` was created dogfooding GOAL 2 (`workspace.create_project(person="Dad", copy_resume_from="dad-health-informatics", make_active=True)` + manual `preferences.{json,md}` copy), so test runs don't touch the real dad project. `people()` → `[None, 'Dad']`; **active project is now `health-informatics-test`.** Verified `ranker._facts_profile(None)` → `health_informatics` + 44 skill_terms (the review-fixed 1E path fires through the live GUI route). `projects/` is gitignored (local data) — no repo change. Staged to run a real-data health-informatics search. ⚠️ resume is BI/analytics-leadership vs the clinical-informatics/CMIO keyword lean → may want "Director Analytics / VP Business Intelligence" keyword variants. **Active-project note: `controls-cincinnati` for Alex's controls work, `health-informatics-test` for dad testing, `dad-health-informatics` for the real (non-test) dad search.**
