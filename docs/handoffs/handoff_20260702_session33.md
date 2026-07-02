# Handoff — Session 33 (2026-07-02, Fable 5 orchestrating) — BROWSER-EXTENSION BREADTH WAVE

Alex: think about the extension; its goal is FILLING THE GAPS the main search
misses; make it easy, convenient, wide-format; assess how well it records from
Indeed/LinkedIn → "do that. We do want to be filling gaps and adding even more
breadth to our search." Assessment first (the extension covered only the 5
aggregator domains — the wrong territory for gap-filling: walled Workday
tenants, company careers pages and unprobeable ATS boards had ZERO capture),
then 3 Opus builders in worktrees + review fleet + fixes. **Suite 2195 → 2256
green. Master `058ae74`, ~207 ahead, PUSH HELD.**

## The wave (3 builders, all merged)

- **JSON-LD generic capture** (`7a44900`): "Capture this job" popup button
  works on ANY employer/ATS page via schema.org JobPosting JSON-LD (`@graph`
  walk, YEAR→numeric salary vs HOUR→composed text, HTML-stripped description
  via inert DOMParser, TELECOMMUTE→Remote, datePosted→`posted_iso` which now
  wins the `created` precedence) with a DOM fallback (h1/og:/main). NEW FILE
  `browser_ext/generic_capture.js`. Manifest v1.6: added ONLY `"scripting"`
  (activeTab-scoped injection — deliberately no new host permissions).
- **Browser-verified clip** (`238368d`): walled boards (FedEx/Banner 422 class)
  no longer dead-end — a failed clip reveals "Verify from this tab", which
  counts postings the user's logged-in browser can see (JSON-LD first,
  conservative DOM heuristic) and re-clips with evidence. Registry gains
  `BROWSER_ONLY_FLAG` (INVERTED default vs unverified: visible everywhere,
  ONLY `CareersClient` excludes it), `is_browser_only()`,
  `browser_only_count()`. Server probe always wins; evidence never overrides
  identity (resolve_board) and junk evidence sanitizes to absent.
- **Friction + selector health** (`f8b41b8`): receiver-down copy now points at
  the real GUI toggle (Tools ▸ "Capture jobs from my browser…"); Track-All
  goes through the receiver's new `/track` (port 5002, same origin gate,
  per-request project resolution) with 5001 tracker.app as fallback; opt-in
  auto-send every 25 jobs (background worker, `open_report:false` — /harvest
  honors it); selector-rot self-detection (amber `!` badge + popup warning) and
  a one-click Health-check button; selector registries deduped into shared
  `browser_ext/selectors.js` (single source for content.js + selector_check.js).

Merge conflicts: manifest/popup collided across all three builders as expected
— hand-resolved (both handlers/CSS kept), `node --check` clean, popup↔html id
cross-check done.

## Review fleet → fixes (`058ae74`)

4 Opus dimensions → adversarial verify: **3 confirmed / 1 refuted** (full
detail: `brain/review-2026-07-02-s33-ext-fleet-findings.md`):

1. Auto-send blanket-clear raced content.js (cross-context lost-update /
   duplicate-send / badge desync) → delta-clear by url/external_id identity +
   milestone re-baseline; residual overlap idempotent server-side.
2. Browser evidence was silently DISCARDED for boards stored unverified (the
   exact walled population the feature targets) → save_companies rescue
   branch: incoming browser-only upgrades stored UNVERIFIED (flag swap, never
   demotes verified).
3. apply_seed_lines stranded browser-only boards ("skipped") → they re-probe
   on re-seed; wall-down → upgraded into the scraped set; still-walled →
   honest verdict, no demotion.

+5 regression tests. Full suite 2256 passed.

## State

- Master `058ae74`, ~207 ahead of origin, **PUSH HELD**, tree clean.
- s33 worktrees/branches pruned (only pre-existing `ZAG0005-wt-12b-qat-t2f`
  remains). `graphify-out/` is now gitignored (hook artifact).
- No live runs this session; registry/projects untouched.

## Needs Alex

1. **Reload the unpacked extension** — now manifest v1.6 (new `scripting`
   permission + selectors.js). The v1.5 reload from S32 is superseded; one
   reload covers both.
2. **Live selector audit still pending** (task): needs Chrome with the Claude
   extension connected (no browser attached this session). LinkedIn was last
   live-verified 2026-06-14; Glassdoor/Zip/Dice selectors have NEVER been
   live-verified. The new in-popup Health-check button also works for this
   once the extension is reloaded — open a LinkedIn/Indeed search page and
   click it.
3. Carry-overs from S32: push decision (~207 now), gui eyeball, CareerOneStop
   key (daily source + Seed-My-Area Leg B), test-project cleanup.
