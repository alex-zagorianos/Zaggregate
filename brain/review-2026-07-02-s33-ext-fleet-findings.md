# S33 review-fleet findings — browser-extension wave (2026-07-02)

Adversarial review of the cumulative S33 diff `e862b0b..f8b41b8` (three merged
branches: JSON-LD generic capture, browser-verified clip, friction/auto-send/
selector-health). Four Opus dimension reviewers (JS+MV3 correctness, receiver
security, registry/scraper integration, test adequacy + UX flows); every
crit/major finding independently adversarially verified (verifier instructed to
REFUTE). **3 confirmed / 1 refuted / 0 unresolved.** All three confirmed majors
fixed in commit `058ae74` (+5 regression tests; suite 2256 green).

## Confirmed (all major)

### 1. `browser_ext/background.js:65` — auto-send blanket clear raced content.js (js-mv3)

`doAutoSend` cleared `chrome.storage.local` `jobs` to `[]` after a successful
/harvest POST. content.js keeps harvesting in a SEPARATE JS context during the
fetch round-trip (~100–500 ms): its `busy` lock only serializes within the
content script, so a MutationObserver tick could read the pre-send array, add
card #26, and either (a) have its 26-job write clobbered by the background's
`[]` (silent job loss + badge desync), or (b) land after it and resurrect the
just-sent 25 for a duplicate send at the next milestone (background also reset
`autoSendLastAt` to 0). The verifier traced all four preconditions as reachable
under documented usage (auto-send ON, infinite-scroll past 25, receiver up).

**Fix:** delta-clear — re-read storage after the fetch resolves and remove
exactly the sent jobs by identity (url / external_id); re-baseline the
milestone from what actually remains. The race window shrinks from
fetch-duration to the get→set gap, and the residual overlap is harmless
because the receiver inboxes by url-derived `job_id` (duplicate send is
idempotent server-side). No JS harness — fix verified by trace + `node --check`.

### 2. `scrape/browser_receiver.py:247` / registry — evidence discarded for stored-unverified boards (security)

The exact walled-board population S33 targets was silently unrescuable if the
board had ever been added before: a walled Workday tenant added via
'+ Add Companies'/AI-seed is stored UNVERIFIED; a later re-clip with browser
evidence set `BROWSER_ONLY_FLAG` on the incoming entry, but
`_save_companies_locked`'s upgrade guard required the incoming entry to be
server-verified (`not is_browser_only(e)`), so the upgrade was skipped, the
name/slug collision blocked insertion, `added=0`, and clip_board reported
"duplicate". The board stayed permanently dark (unverified: out of scraping AND
invisible to browser-only surfacing) and the user's "Verify from this tab"
click was silently thrown away. Verifier reproduced end-to-end.

**Fix:** new rescue branch in `_save_companies_locked` — an incoming
browser-only entry upgrades a stored UNVERIFIED record in place (swap
UNVERIFIED→BROWSER_ONLY, merge industries). Gated on the stored record being
unverified, so it can never demote a server-verified record; browser-only on
browser-only stays a no-op skip. clip_board needed no change — the evidence
path now returns `added/browser_verified` naturally.

### 3. `ui/ai_setup.py:323` — browser-only boards stranded by the seed dedup (integration)

`apply_seed_lines`' `known` short-circuit excluded only unverified entries, so
a browser-only board re-seeded after its wall came down was skipped as
"already in registry" and never re-probed — stranded on extension-only refresh
forever.

**Fix:** browser-only names are excluded from `known` (they flow through to the
probe; a live verdict reaches save_companies' upgrade and the board re-enters
the scraped set), and a still-walled re-seed now reports honestly ("still
walled — kept browser-only") with nothing saved instead of a misleading
"saved unverified" — no demotion, no duplicate row.

## Refuted (1)

- `popup.js` `countJobPostingsInPage` "always-truthy evidence saves ANY page as
  browser-verified" — REFUTED: the scenario dies at two server gates it can't
  pass. A login/error/About page is not `resolvable` (resolve_board only
  resolves recognized-ATS URLs with a real slug → `failed/unresolvable`), and
  `_valid_browser_evidence` sanitizes the `job_count:null`-with-no-postings
  shape. Evidence can only ever upgrade reachability of a board whose identity
  came from resolve_board.

## Scope notes

- Minor-severity findings were not adversarially verified this wave (fleet
  filtered to crit/major); none were flagged critical-adjacent by the finders.
- The extension still has no JS test harness; JS fixes are verified by trace,
  `node --check`, and the popup↔html id cross-check the friction builder ran.
