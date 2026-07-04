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

- **Ranking refinements held** (change scoring, need explicit approval + a
  parity check against Alex's daily run): `_EXEC_RE` can flip an IC title
  containing "manager" to the senior rubric (#28); SOC penalty-role exemption
  only covers sales/maintenance (#37); skill-overlap abstains to neutral on a
  thin résumé, diluting title signal (#38). All are _ranking_ accuracy, not
  drops — jobs still appear.
- **Blue-collar starter registry gap (#4)**: the shipped companies.json is
  tech/health/defense-shaped; warehouse/trades/retail users lean on Adzuna +
  the extension until the registry buildout session happens (planned; Alex:
  "wait on blue collar, keep building the seeded company list in a different
  session").
- **Silent source failures (#5/#6/#22/#23)**: a failing feed/scraper can lose
  its jobs for a run without a surfaced signal (swallowed RSS errors can cache
  empty; per-company scraper failures don't reach the health summary; one
  client constructor crash can abort a run). Surfacing/guarding is queued.
- **Zero-key transparency (#18)**: "source skipped — needs a free key" is only
  surfaced on one of three entry points; a zero-key user can't distinguish
  "no key" from "ran, found nothing" everywhere.
- **US-only sources for non-US users (#12)**: USAJobs/CareerOneStop/REAP/EdJoin
  still register and spend time for international users (they return zero).
- **Efficiency (#24/#25/#26/#36)**: careers registry re-walked per keyword;
  discovery queries re-fire daily; no negative-cache on inbox-company harvest;
  cache GC only runs after a clean daily_run.
