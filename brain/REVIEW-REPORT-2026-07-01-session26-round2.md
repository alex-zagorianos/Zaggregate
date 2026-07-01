# Session 26 round-2 — free-reach: adversarial review (2026-07-01, Opus/ultracode)

Diff reviewed: `ce49c0e..24582b3` (WeWorkRemotely + WorkingNomads free feeds, Reach GUI badge,
BambooHR live-validation + location fix, Socrata guard). A focused 3-dimension review workflow
(6 agents, per-finding adversarial verification, Sonnet) found **3 confirmed findings (0
dismissed)** — 2 major, 1 minor. All fixed + regression-tested; full suite green.

## Findings + fixes

1. **WorkingNomads crashed the whole source on a non-string tag** (`search/workingnomads_client.py`)
   — `" ".join(tags)` raised `TypeError` if the public feed's `tags` array held a `null`/number,
   and because the single cached feed doc is re-parsed for every keyword, the source netted **zero
   results for the entire run** (not just the one bad job). **Fix:** `" ".join(str(t) for t in tags if t)`.
   Regression test added.

2. **BambooHR location regression I introduced** (`scrape/bamboohr_scraper.py`) — my round-2
   `_loc_from` added `country` to the scanned fields and `_location` returned the first non-empty
   result, so a `location:{"country":"United States"}` dict **shadowed a real city/state** living in
   `atsLocation` or the flat fields → degraded to a bare country → broke geo-filtering and risked
   dedup collisions (all such jobs collapse to the "united states" location token). **Fix:**
   restructured `_location` to resolve by specificity — explicit remote flag → city/state from ANY
   source → flat fields → bare country → remote signal. `_city_state()` no longer includes country.
   Regression test (country-only must not shadow a city).

3. **New remote jobs hidden under the default Inbox view** (minor, but it blunted the whole feature)
   — WeWorkRemotely/WorkingNomads emit region text like `"Anywhere in the World"` / `"Worldwide"` /
   `"USA Only"`, which `geo/filter` does **not** recognize as remote (it keys off the literal word
   "remote"), so ~all of these remote-only postings were classed `elsewhere` and hidden from the
   default "Local + remote" view. **Fix (surgical, client-side — no change to shared geo logic):**
   both clients now tag their location `"{region} (Remote)"` when it isn't already remote-literal, so
   geo recognizes them while preserving the region text. Regression tests assert `classify(...) ==
"remote"` for both.

## Note

Fix 3 was done client-side deliberately (rather than teaching `geo/filter` the global-remote
vocabulary) to avoid changing how existing sources (himalayas/jobicy, which share the latent gap)
are classified — keeping the blast radius to the two new sources. Teaching geo/filter the
"worldwide/anywhere" vocabulary is a reasonable future improvement but risks false positives
("International District") and changes existing users' views, so it's left for a deliberate call.

Suite after fixes: full green (see commit).
