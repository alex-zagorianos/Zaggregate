# Deep Product Review — Zaggregate (JobScout) — 2026-07-01

**Scope:** full-app review against the product vision — (1) widest possible job net, (2) usable by anyone in any field, (3) bring-your-own-AI, (4) full application-cycle tracking, (5) style secondary to function.
**Method:** 8 parallel review agents (reach-internal, reach-external web research, generalization, BYO-AI, tracking, efficiency, UX, ranking quality) → adversarial verification of every critical/major claim (34 verified, ~90% CONFIRMED with citations) → completeness critic. 43 agents total. All findings below carry file:line evidence; verifier corrections are folded in.
**Baseline state:** master 28 ahead (push held), S27 uncommitted files intentional, 1222 tests green, aegean-restyle unmerged.

---

## Verdict

The engine is genuinely strong — layered dedup, honest reach math (refuses to fake a coverage %), explainable 0–100 scoring, a provider-agnostic clipboard AI round-trip with excellent import validation, WAL-mode DB with migrations, and craftsmanship well above typical tkinter. **But the product's core loop is broken for exactly the persona the vision names.** A non-technical user who installs the exe and follows the wizard hits three walls: their pasted resume crashes every subsequent search, their Inbox can never fill (no GUI trigger for daily_run; scheduler needs a Python install the exe user doesn't have), and their keyless daily net collapses to ~2 sources. Meanwhile the widest-net machinery silently erodes itself (self-inflicted 429s mark live boards dead), and the biggest free reach lever for non-tech users (CareerOneStop/NLx, ~3.5M jobs/day) isn't wired at all.

Priorities in one line: **fix the 3 novice dead-ends → stop the 429 self-erosion → unlock the aggregator tier + CareerOneStop → land job_key dedup BEFORE any overlap source → semantic + title-matcher precision fixes → cycle/AI/tracking depth.**

---

## P0 — Broken-product bugs (all CONFIRMED, fix before anything else)

1. **Wizard resume paste crashes all scoring.** Wizard invites plain-text paste (ui/setup_wizard.py:383-392), writes it verbatim; experience_parser raises ValueError on any resume without `## ` markdown headings (resume/experience_parser.py:80-86); scorer/daily_run/gui call it unguarded → every search errors with markdown jargon. Reproduced live with a plain-text nurse resume. Fix: auto-structure the paste (promote ALL-CAPS/alias lines to headings, else wrap as `## WORK EXPERIENCE`) + lenient parser mode + ValueError → neutral in scorer.
2. **Inbox can never fill from GUI or exe.** Only daily_run/mcp/browser_receiver write the inbox; gui.py has no trigger; setup_schedule needs system Python; the exe ships neither (app.spec builds gui.py only). The empty-state copy is factually wrong — "click Search — matches land here" but GUI Search never writes the inbox (gui.py:1156-1160 vs 2280-2292). Fix: "Update my Inbox now" button (worker thread + pin_active + log-sink progress), `--daily` headless mode in the frozen exe, Tools → "Turn on daily updates" registering schtasks against the exe, fix the copy, and a wizard closing step offering both.
3. **429s poison live boards + 5 scrapers uncached.** conditional_get_json treats ANY 4xx as permanent (scrape/cache_helpers.py:178-186) → mark_failed; verifier correction: greenhouse/lever poison = 24h, **workday/direct = 168h**; workable (the top 429 source) just silently returns []. No per-host rate limiter anywhere in the ATS path (pattern exists in stealth_fetch.py:157-164, unused); workable/recruitee/rippling/personio/bamboohr have **no cache**, so N keywords × 47 workable boards = N live fetches each (careers_client.py:174-183). The 241-429 S27 incident = silent under-coverage. Fix: 429/5xx → serve stale + never mark_failed (or 1h TTL); per-host limiter in careers_client; wire cache/conditional-GET into the 5 scrapers; respect Retry-After (http_util's Retry already does).
4. **Keyless non-tech user's daily net ≈ careers + themuse.** Adzuna/USAJobs keys are .env-only (no Settings/wizard path — ui/settings.py:72 holds only anthropic+serpapi); Jooble/Careerjet aren't in DAILY_SOURCES at all (config.py:209-215); gate_tech_sources strips the 7 remote boards for non-knowledge-work fields. Fix: "Connect job sources" Settings panel (adzuna/usajobs/jooble/careerjet keys + signup links, env-then-secret resolution), append jooble+careerjet to DAILY_SOURCES (they already self-skip keyless — zero risk), wizard step for keys.
5. **S27 concurrency class only half-closed.** pin_active exists only in daily_run. **mcp_server.py never pins** (mcp_server.py:175-178) — a live MCP session + GUI project switch reproduces the S27 corruption; GUI `_api_rank_worker` writes from a background thread resolving per-call; scripts/ likewise; **projects.json is written non-atomically** (workspace.py:77-79 bare write_text; repo already has tmp+os.replace helpers) and corruption **silently falls back to the root workspace** (cross-project bleed, no error). Fix: pin in mcp_server.main(), atomic registry writes, loud corruption path, explicit slug/db_path through GUI worker threads, optional lockfile.
6. **PII on GitHub: experience.md is git-tracked and already pushed** — home address + phone under `## CONTACT`, in origin/master history (github.com/alex-zagorianos/Job-Program). The exe build correctly ships only the template; dev never got the same treatment. Fix: `git rm --cached experience.md` + .gitignore + **Alex decision on history rewrite / repo visibility**. Also relocate tracker.db.bak (3.6MB user data at root).
7. **Nightly rescore erases the good scores.** daily_run scores with target_level/semantic_profile/remote_ok, then calls scripts/rescore_inbox.py which re-scores EVERY row without them (rescore_inbox.py:44-50) — the exec ±15/16 adjustment is applied at insert and stripped minutes later; it would also silently strip semantic if ever enabled. Likely the direct cause of S27's "exec-fit too weak" observation. Fix: pass the three kwargs (or refactor to one scoring path). Cheapest precision win in the codebase.
8. **hard_gate kills good jobs pre-inbox.** Salary test uses the range FLOOR: a $70k–$120k job dies against a $90k floor (preferences.py:74-77), contradicting comp.meets_floor (max-or-min); location gate is whole-string substring, so prefs "Cincinnati, OH" fails job "Greater Cincinnati Area" (metro_variants exists, unused here). Invisible false negatives. Fix: floor test on max-or-min; tokenized/metro-variant location match; log per-reason drop counts.

## P1 — Reach roadmap (vision #1, the main ask)

**Ordering rule from the critic (important):** every overlap-adding source below double-lists the inbox unless job_key coalescing lands first — dedup is URL-only today (search_engine.py:185-207; inbox UNIQUE norm_url), safe only while free families are disjoint (f2=0). **Land `job_key` inbox coalescing + repost detection (freshness → {job_key: first_seen}) BEFORE or WITH the first overlap source**, plus an inflow governor (per-source daily caps, auto-dismiss-below-X into a reviewable bucket) so the widened net stays triageable at human+AI capacity.

**Tier A — free, small, multiplicative:**

- **CareerOneStop (US DOL) client — the #1 non-tech reach win.** Free-key REST API backed by NLx: ~3.5M active US jobs/day from all 50 state job banks + ~300k employers — nurses, teachers, trades, retail, state/local gov (partially recovers the NEOGOV block). Clone usajobs_client.py; attribution required. Endpoint verified live 2026.
- Aggregator-tier unlock (P0 #4) + daily --max-pages 2 for paginated clients once keys flow.
- **Sparse Google-Jobs overlap probe:** 1–2 serpapi queries/run (~30-60/mo, inside the 250/mo free tier, key already GUI-manageable) merged into last_raw_results → f2>0 → the reach badge finally shows "seeing ~X%". Alternatives for $0 measurement: TheirStack 200 credits/mo or Techmap jobdatafeeds 1k jobs/mo as an independent overlap sample (measurement-only module).
- **Auto-run build_company_list at wizard finish** for the user's field+metro (machinery exists; today a new nurse starts with a 556-company tech registry). Expose `--jobhive` in the GUI dialog (biggest measured raw-reach lever, currently CLI-only).
- Registry facts: 87% greenhouse/lever/ashby (485/556), software+applied_ai = 472 tags, health = 44 → the careers leg structurally can't serve non-tech fields yet regardless of registry size.

**Tier B — ATS scraper wave 2 (where hospitals/universities/Fortune-1000 non-tech live):**
verified public JSON surfaces, each a clone of an existing scraper + ats_detect rule:

1. **Paylocity** — _officially documented_ public feed API (easiest, sanctioned — do first).
2. **ADP Workforce Now** — no-auth careers JSON (`workforcenow.adp.com/...(v1)/job-requisitions?cid=...`), huge SMB non-tech long tail.
3. **Eightfold** — `{co}.eightfold.ai/api/apply/v2/jobs` (Eaton already in registry as 'direct').
4. **Oracle Recruiting Cloud** — `hcmRestApi/.../recruitingCEJobRequisitions` (+siteNumber from page, 2 headers) — unblocks **UC Health**.
5. **Phenom** — POST `/widgets` ddoKey=refineSearch (+refNum from page; sitemap fallback) — unblocks **TriHealth/Christ**.
   Long tail (~1-file each): Breezy (`/json?verbose=true`), Pinpoint (`/postings.json` + XRW header), Teamtailor (public jobs.rss), JazzHR (applytojob XML), Gem. iCIMS: no public JSON exists (partner-gated) — sitemap enumeration + HTML parse is the only upgrade; mark rows description-less.
   Sector RSS clients (persona-targeted, sanctioned): HigherEdJobs per-category RSS, RNJobSite per-specialty RSS, jobs.ac.uk feeds. Confirmed dead ends — do not build: EURES (ToS), hiring.cafe (bot-wall), UK Find-a-Job direct (WAF; use Adzuna/gb — it powers the site), jobdataapi/Coresignal/JobsPikr (no real free tier).

- **Adzuna country parameterization** — config.py:110 hardcodes /us/; same free key serves ~19 countries. One config change = international breadth. (Gate on the critic's language guard: detect non-English postings and mark unscored rather than confidently mis-scoring.)

**Tier C — recover reach already paid for:**

- tiered_scrape default-on above ~200 companies (module built+tested, off by default — daily O(626) scrape is both the speed problem and the 429 contributor).
- Extend conditional-GET to the other 7 JSON scrapers; on 304 use os.utime instead of rewriting multi-MB bodies; drop indent=2; add cache GC (cache/ is 262MB, never evicted).
- Per-company cap overflow visibility ("Cincinnati Children's: 12 more matches capped — raise?") — silent discard loses exactly the single-dominant-employer jobs a nurse wants. URL-less jobs: persist with keyless identity instead of silent drop at inbox door (tracker/db.py:697-699).
- linkedin_guest: honor the documented opt-in (currently on-by-default in GUI/CLI despite the config comment).
- **Browser extension = the only compliant LinkedIn/Indeed/Glassdoor/ZipRecruiter/Dice path and it's already built but invisible** (critic finding): receiver is `py -m` only (dead in exe), zero GUI mention, unpinned (S27 class). Promote: receiver as daemon thread behind a Settings toggle (pinned), Help walkthrough, bundle browser_ext/ into the zip, surface capture counts + selector-rot status.

## P2 — Ranking precision (vision: "the perfect job for them")

- **Title matcher root-cause fix (S27 false positives):** query leaves are boundary-less raw substring, and any full boolean match returns 1.0 + title_hit → "Senior QA Automation Engineer" gets title-100% for "automation engineer"; "RN" matches inteRNship. Fix: word-boundary lookarounds in query._Leaf.matches (pattern already exists in scorer for skills).
- **Semantic enablement, done right:** it's OFF because config.py never defines SEMANTIC_RANKING and no UI toggle exists — but honest math says SEM_WEIGHT=12 moves scores only ~3 pts vs the 8-11-pt S27 inversions. Enable (config flag + Settings checkbox + bundle potion-base-8M in the exe) **and add semantic modulation of title credit** (sem < ~0.35 caps title at 0.6) so it vetoes the generic-token failure mode. Validate against the S27 corpus.
- **Symmetric seniority fit:** IC seekers get zero penalty for manager/director titles (scorer.py:86-98 — deliberate tradeoff, now worth revisiting): add the mirror branch (~-10/-14) and/or wizard-seed seniority_exclude for IC profiles.
- Confidence shrinkage: 2-of-5-component jobs can post 100 (renormalization); damp distance-from-50 by data-presence so data-poor title-only 100s stop outranking data-rich 92s.
- Auto-hide publisher-expired postings (validThrough in the past — near-zero false-positive) + staleness as a list column, not detail-pane-only.
- Comp parsing gaps: $30k annual floor makes sub-$14.43/hr wages invisible (min-wage tier retail/food-service); monthly/weekly periods missed; USD-only. (Overlaps generalization below.)
- Gate: years_cap=8 drops "10+ years" postings for every non-exec seeker — a 15-yr senior IC's own tier never reaches AI ranking (rows stay in inbox, so quality loss not data loss). Read tenure from experience or raise cap for "senior" keywords.

## P3 — Any-user / any-field (vision #2)

- Resume paste fix (P0 #1) + **LICENSES & CERTIFICATIONS / SUMMARY as first-class sections** (currently silently dropped — the load-bearing section for nurses/welders/teachers/drivers; feed certs into skill terms).
- **Derive industry from roles when the "(optional)" field is blank** — blank currently keeps ENGINEERING routing (Muse eng categories → ~0 nurse hits); resolve_soc('registered nurse') already works, just never applied.
- **Hourly-wage pay model:** lower/context-aware money floor, accept "/hr" values, carry a period through to display "$14.50/hr", wizard hourly example.
- **Employment-type dimension** (full/part-time, contract, PRN/per-diem, shift) in facts + hard prefs + Inbox chip + wizard row — the top missing fit dimension for clinical/retail/trades; the facts/gate seams already exist.
- Ship the full ~935-CBSA delineation table (currently 15 metros; everyone else gets substring luck and "Local + remote" hides their local jobs). Non-US groundwork = Adzuna country + currency-aware comp.
- Field-aware penalty_roles (a maintenance tech's/salesperson's exact target work is downranked by default); knowledge-work gate loosening (health informatics/education lose all remote boards via the jobicy-slug proxy — Dad's own field); deseniorize guard ("Shift Supervisor"→"shift" junk queries); kill DEFAULT_LOCATION='Cincinnati' leakage (Search prefill, Inbox home metro for skip-wizard users, browser_receiver falling back to engineering DEFAULT_KEYWORDS); About dialog still says "engineering jobs".

## P4 — BYO-AI (vision #3)

- **Provider-agnostic API route — the single biggest BYO-AI unlock:** all five AI call sites are hardcoded `anthropic` with no base_url (ranker.py:174, gui.py:82, resume/generator.py, discover/enumerate.py, industry_profile.py — the last also hardcodes a haiku model id). Step 1 (~20 lines): ANTHROPIC_BASE_URL config + Settings field + pass base_url → instantly enables Ollama v0.14+ (native Anthropic endpoint), GLM, DeepSeek, Kimi. Step 2: provider enum + OpenAI-compat fallback for ChatGPT/Gemini/LM-Studio. This is the deferred spec §7/§11b work — it matters.
- **Chunked + compact file export:** the 660-row export measures ~215K tokens (verified against the live DB) — fits no free chatbot; the file route never got the S21 compact facts spine. chunk_size=100 files + facts_summary mode → ~15-30K tokens. Import already handles subsets by job_key.
- **Undo parity:** bridge/API/MCP score writes are per-row singleton batches with source="manual" — the Undo button (file_import-scoped) silently does nothing after a paste/MCP rank. Thread one shared batch through; make Undo batch-atomic on any source. Biggest trust hazard of letting arbitrary AIs write scores.
- MCP: pin project (P0 #5); add compact/paged list_inbox (fix the "pull the WHOLE inbox" SKILL.md guidance — 165K+ tokens at 660 rows, fatal for 32K local backends); **expose resume tailoring + application cycle** (get_resume_prompt/save_resume, set_status, followups_due, funnel, draft_followup_context) — today any AI's help ends the moment a job is tracked; feed skillgap['missing'] into the resume prompt (computed, never consumed).
- De-Alex the prompts: DEFAULT_FIT_PREFERENCE bakes "prefers smaller companies" into every user's ranking on all routes — make it a per-profile fit_preference (param already exists).
- Surface bridge partial-coverage ("Scored 17/20 — 3 not scored") in the GUI instead of stdout; fix MCP set_fit_scores counting nonexistent ids as applied. Opt-in auto-rank of new jobs in daily_run when a key/local model is configured (compact prompt ≈ trivial cost) = "wake up to a ranked inbox".
- Fix packaged README's Claude-only framing (bridge is provider-agnostic; help.py already names ChatGPT/Gemini/Copilot).

## P5 — Application cycle (vision #4)

- **Centralize entered-applied side-effects in db.update_job** — today only Apply Queue's Mark Applied stamps date_applied + follow_up(+7d); Tracker quick-status, Flask, API/extension paths silently disarm the whole follow-up engine.
- **Add 'accepted' and 'ghosted' states** (enum ends at 'offer' — you literally cannot record getting the job; ghosting, the most common outcome, is unrepresentable) + auto-ghost nudge (status='applied', no history movement in 21d → Due dialog: "Mark ghosted / follow up").
- Interview rounds table + stdlib .ics export (largest Teal/Huntr parity gap); offer fields (amount/deadline/notes); timestamped per-stage notes via status_history note column.
- Surface contacts in job context ("You know 2 people at Acme") — table+query built and tested, zero surfaces call it; referrals are the highest-conversion channel.
- Proactive due nudges: startup banner when count_followups_due()>0, due line in daily_run summary, tab badge. Bulk ops (trees are single-select). Snooze bypasses db_guard (crash path).
- Data safety: PRAGMA quick_check at launch, rotating auto-backup reusing ui/help make_backup (manual zip backup/restore EXISTS — critic corrected the fleet here), applications CSV export, OneDrive/Dropbox path warning (WAL SQLite under a syncer = corruption vector). Rename by_source's 'response_rate' → 'interview_rate' (two metrics, one name, same dialog).

## P6 — UX (function-first)

- Close the daily loop in-GUI (P0 #2) — the headline UX fix.
- **Search-run feedback:** per-source determinate progress, Cancel (threading.Event), end-of-run source-health summary ("11 ok, 2 skipped (no key), 1 throttled") — today every source failure is print()-to-nowhere (console=False exe discards it; an expired key is indistinguishable from a thin market). Pass industry_filter + tiered=True to the GUI search (currently full unfiltered 627-board scrape behind an indeterminate bar with no cancel).
- Bulk triage: Ctrl+A + "Dismiss all shown" over the filtered view (undo infra already batch-capable); optionally "add Search results to Inbox" to unify the two find surfaces.
- Copy hygiene: empty-state lie, "secrets folder"/"see the README" → point at the existing Connect-your-AI dialog, Cincinnati default, Build-My-List paste-back path (file-picker flow is the most technical step a novice faces).
- _*aegean-restyle: verified ui-only (12 commits, ui/* + gui.py + tests + build_package.py, zero app logic, conflict-free with S27 dirty files), right direction (palette, score chips, rebrand), BUT human-unverified visuals_* — merge after Alex eyeballs `py gui.py` both modes; do not let it queue-jump the workflow fixes. Do the gui.py mechanical split into ui/tabs/ AFTER the merge (11 classes, zero raw SQL — file-organization debt, not architecture debt).

## P7 — Product lifecycle (critic — whole missed dimension)

- **Versioning/updates: none.** No **version** anywhere, unversioned zips, no upgrade path — every reach/quality fix never reaches already-shipped copies; friend bug reports un-triageable. APP_VERSION + versioned zip + CHANGES.txt + data-dir separation (%LOCALAPPDATA%) + optional GitHub-Releases update check.
- **No logging framework** — only the Tk-exception log. RotatingFileHandler under data/logs, last_run.json rendered as "Last updated: … — N new jobs" in the Inbox header, Help → "Report a problem" (zip logs+version, redact keys). Makes the 429-erosion class visible and friend-support real.
- Repo readiness: README is 13 bytes; no LICENSE (all-rights-reserved ambiguity even for friends' zips), no CI (1222 tests run only on this machine while 28 commits sit unpushed). One-day pass: real README, deliberate license, pytest workflow, move 24 root handoffs → docs/history, 9 root one-off scripts → scripts/. Prereq: untrack experience.md first (P0 #6).
- Legal posture notes: linkedin_guest should be a documented informed opt-in; stealth_fetch's guards are good (registry-allowlist, never LinkedIn/Indeed) but shipping bot-evasion inside friends' exes transfers that judgment call — consider excluding stealth from the distributable or gating it.

## Efficiency extras (not already covered)

- **normalize_title: memoize + hoist the key list + score_cutoff** — every fuzzy-path call rebuilds a 51k-element list and full-scans O*NET titles; job_key calls it for every result every run. Likely the dominant CPU cost of a daily run. 3-line fix.
- get_conn() re-reads projects.json + 5 PRAGMAs per call; sqlite3 `with` doesn't close connections (refcount-reliant). Low urgency; cache registry by mtime.
- tests: add a socket guard (autouse fixture / pytest-socket) — 1222 tests with no network fence.

---

## Suggested build order

1. **Hotfix wave (small, huge):** resume-paste fix · rescore parity · hard_gate salary/location · 429-safe transport + per-host limiter · mcp pin + atomic projects.json · untrack experience.md · empty-state copy.
2. **Core-loop wave:** Update-Inbox-now + exe --daily + scheduler toggle · source keys in GUI + jooble/careerjet in DAILY_SOURCES · wizard closing step (daily updates + Build My List) · search progress/cancel/health.
3. **Dedup-then-reach wave:** job_key inbox coalescing + repost history → CareerOneStop client → serpapi overlap probe (reach % goes live) → tiered default-on + conditional-GET extension.
4. **Precision wave:** word-boundary titles · semantic on + title modulation · symmetric seniority · confidence shrink · expired-hidden.
5. **ATS wave 2:** Paylocity → ADP → Eightfold → Oracle → Phenom (+ long-tail quartet, sector RSS).
6. **BYO-AI wave:** base_url provider setting · chunked/compact export · undo batches · MCP cycle tools.
7. **Cycle wave:** applied side-effects · accepted/ghosted · rounds+.ics · contacts surfacing · proactive due.
8. **Lifecycle wave:** version+logging+README/LICENSE/CI · extension promotion · aegean merge (after eyeball) → gui split.

## Needs Alex (decisions only he can make)

- **experience.md PII already in pushed GitHub history** — rewrite history / make repo private / accept? (untrack+ignore happens regardless).
- Merge aegean-restyle after live `py gui.py` eyeball (both modes, chip gutter widths).
- Push the 28+ held commits (CI would make this safer — see P7).
- License choice for the repo / distribution posture (friends-only zips vs public).
- CareerOneStop + Adzuna/Jooble/Careerjet key signups (all free) when the Settings panel lands.
- Whether stealth_fetch ships in friend builds.

_Full agent output: session workflow wb911bevd (43 agents, 3.2M tokens). Companion docs: brain/eval-2026-07-01-dad-vs-controls-runs.md (S27 live eval), handoff_20260701_session27.md._
