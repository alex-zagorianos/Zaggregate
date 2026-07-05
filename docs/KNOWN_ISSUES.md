# Known Issues & Design Trade-offs

Living document. Each entry is a deliberate trade-off or an accepted gap — not a
forgotten bug. Fix candidates reference the S35 fleet finding numbers in
`brain/review-2026-07-03-s35-weakness-sweep.md`.

## Design philosophy — inclusion over precision (Alex, S35, 2026-07-03)

**Get as many potential jobs in front of the user as possible and let the USER
do the final dropping.** Filters exist only to cut what is _clearly_ stated as
unwanted (an explicit dealbreaker token, a hard salary floor, a ToS-blocked
source) or _completely_ unrelated. When a gate/scorer choice is ambiguous, keep
the job. Corollary for contributors (and future Claude sessions): never add a
filter that can silently over-drop; prefer down-ranking to dropping, and prefer
showing to down-ranking.

### Accepted trade-off

Because the net is wide, users WILL see some loosely-related jobs (adjacent
titles, near-metro rows, generalist postings). That is by design — the Inbox
triage flow (dismiss / statuses / location view-modes) is the intended dropping
mechanism, not the fetch pipeline.

## Known issues (accepted for now)

- **Blue-collar starter registry gap (#4)**: the shipped companies.json is
  tech/health/defense-shaped; warehouse/trades/retail users lean on Adzuna +
  the extension until the registry buildout session happens (planned; Alex:
  "wait on blue collar, keep building the seeded company list in a different
  session").
- **jobs.ac.uk PROVISIONAL endpoint 404s** (caught by the S35b live UK run):
  `feeds/subject-areas/{area}` returned 404 for at least one slug — the feed
  URL pattern needs re-deriving from the live site. The failure is properly
  SURFACED now (last_run.json errors[]), never cached-empty. Also by design: a
  UK-activated run with a non-academic field polls the broad academic net
  (inclusion philosophy; the scorer filters).
- **Sector-feed breadth (#16/#17)**: discovery's LLM-enumeration angle biases
  toward ATS-having employers; sector RSS feeds only cover education. Both are
  new-source builds, not bugs.
- **Non-US metro scoring beyond substring (#27)**: the S35 bare-city fallback
  makes international local-matching work; a proper non-US metro table (à la
  the US CBSA data) would still improve suburb/variant matching.
- **Zero-key regression floor (from #8)**: a standing CI test pinning "N
  keyless sources / companies.json ≥ 400" is a suggested follow-up so breadth
  can't silently shrink.
- **Web-UI era (S36, 2026-07-04 — the tkinter-ceiling roadmap item is BUILT).**
  The web UI (React/shadcn served by the receiver at 127.0.0.1:5002/app,
  launcher `py -m webui` / exe `--web`) now twins every tk surface. Accepted
  gaps carried as the next-session queue (full detail + evidence in
  `brain/findings-2026-07-04-webui-scenarios.md`):
  - ~~No web create-project / new-person flow~~ — **SHIPPED S37 (B2)**:
    topbar "New project…" dialog + POST /api/project/create.
  - Filter state not URL-synced (back/refresh resets the Inbox view).
  - **Pending Alex decisions**: tk-tab retirement (GO/NO-GO read in the
    findings report §6), deletion of the deprecated `tracker/app.py` (:5001
    retired; file kept), and whether the exe DEFAULT becomes `--desktop`
    (native window shipped in S36c; tk remains the no-flag default).
- **Discover tab (S36c, EXPERIMENTAL — may be removed)**: BYO-AI role
  recommendations (prompt from experience/preferences/tracked signal ->
  paste reply -> lane-grouped cards -> additive keyword apply). Web-only, no
  tk twin, no DB schema. Removal = delete `recommend.py`,
  `webui/api/recommend.py`, `src/tabs/discover/` + the three marked one-line
  registrations (api/__init__.py, registry.ts, TabRoutes.tsx).
- **Recall (S36c, 2026-07-04)** — full program in
  `brain/findings-2026-07-04-search-optimization.md`:
  - **Free keys unclaimed** (CareerOneStop, Brave Search, Jooble, Careerjet,
    SerpApi): all fully wired and auto-on once keyed; the single biggest
    untapped jobs-found lever (~15 min of signups, needs Alex).
  - No sector source for mech/industrial/manufacturing (IEEE/ASME/SAE-style
    boards) — research + build queued, following the self-gating
    `_higheredjobs` pattern.
  - `get_conn()` opens a fresh SQLite connection per call — reuse redesign
    deferred (highest perf win, biggest blast radius; S27 pin interactions).
  - "Minneapolis, MN"-style inputs never match their own hyphenated
    multi-city CBSA title (pre-existing metro_variants gap; bare city works).

## Fixed since first written (kept for history)

- ~~S36 scenario minors + P1 parity gap~~ — **FIXED in the S36 continuation
  (2026-07-04)**: MINOR-1 garbage `location_mode` now fails OPEN to All
  locations (shared `location_visible` predicate, web + tk); MINOR-2 blanket
  `{ok,error}` JSON envelope on routing-layer /api errors (unknown routes,
  405s, literal `../`); MINOR-3 `.ics` SUMMARY humanized ("Phone Screen");
  MINOR-4 reach-badge copy branches on `is_knowledge_work` (nurses no longer
  read "mostly remote/tech jobs"); MINOR-5 rubric/grade-scale stoplist in the
  ATS gap list ("iv" deliberately kept — intravenous); **P1: `POST
/api/runs/daily` accepts `{max_pages, min_score}`** + Inbox split-button
  run-depth menu (Quick 1 / Standard 2 / Deep 3 pages).
- ~~tkinter ceiling (S35b roadmap)~~ — **BUILT in S36 (2026-07-04)**: full web
  UI shipped (all tabs + wizard + dialogs), deep-tested (scoring parity
  proven) + 5 scenario journeys (2 criticals + 7 majors found and fixed, incl.
  the `get_conn()` WAL-connection leak and the resume bare-"Experience"
  work-history drop).

- ~~Ranking refinements #28/#37/#38~~ — fixed (exec-intent split, SOC-11
  exemption, honest skills chip); eng-profile parity proven byte-identical.
- ~~Silent source failures #5/#6/#22/#23~~ — fixed (no cache-on-error,
  careers/Brave failure surfacing, per-source constructor guard).
- ~~Zero-key transparency #18/#19/#32~~ — fixed (all three entry points).
- ~~US-only sources for non-US #12~~ — fixed (skip + log for non-US).
- ~~Efficiency #24/#25/#26/#36~~ — fixed (per-run fetch memo, discovery
  TTL/dedup, harvest negative-cache, GC-in-finally).
- ~~Adzuna where-string country tail~~ (found by the live UK validation, not
  the fleet): /gb/ + "London, United Kingdom" returned 0; tail now stripped
  when it names the routed country → 295 live gb results.
