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
- **tkinter ceiling**: the UI is at ttkbootstrap's limits. Roadmap decision
  (S35b): engine stays Python permanently; the eventual UI successor is a
  local web UI served by the Flask receiver (tab-by-tab migration — the gui.py
  split made each tab an independently replaceable unit), optionally wrapped
  in Tauri later for single-exe distribution.

## Fixed since first written (S35b, 2026-07-04 — kept for history)

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
