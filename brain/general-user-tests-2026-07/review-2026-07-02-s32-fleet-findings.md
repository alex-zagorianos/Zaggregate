# S32 Review-Fleet Findings — Adversarial Audit of the S32 Cumulative Diff

**Date:** 2026-07-02 · **Scope:** `414bb03..HEAD` (14 builder branches, 3 waves + registry migration)
**Method:** 20-agent fleet — 7 Opus dimension reviewers (Find) → per-finding Opus verifiers (Verify).
**Raw → deduped:** 22 → 22 findings; 13 crit/major verified adversarially, 9 minors passed through unverified.
**Verdict: 13 CONFIRMED · 0 REFUTED · 9 minors.** Every confirmed finding reproduced at HEAD; the
five S32d/S32e fix builders + the probe-verdict follow-up resolved all of them (mapped below).

This file **persists** the fleet's findings into the repo (they otherwise lived only in a temp
workflow output that vanishes). Condensed evidence — the verifiers' full reproductions are summarized,
not dumped. Fix lineage traced via `docs/handoffs/handoff_20260702_session32.md` + `git log`.

---

## Confirmed findings (13) — with fix commit

### 1. CRITICAL — daily_run's own rescore pass erases every S32 honesty lever it just applied

- **Dimension:** scoring/gate regressions for existing users
- **File:line:** `scripts/rescore_inbox.py:66-73` (caller) · `daily_run.py:488` (invoker) · `match/scorer.py:911-914` (levers)
- **Claim:** `rescore_inbox.rescore()`'s `score_jobs()` call passed only the OLD levers
  (exclude_keywords/exclude_titles/title_miss_penalty/seniority_exclude/remote_ok) and NONE of the four
  new S32 levers (`seniority_target` / `years_cap` / `title_context_required` / `remote_regions_ok`).
  `daily_run.py:488` calls `rescore(cfg=cfg)` at the END of every run, re-scoring the whole inbox and
  overwriting the lever-aware scores the daily insert just wrote (lines 409-419). The exact S24/P0#7 drift
  class the reference doc warns about — and the parity test was structurally blind (its EXEC_CFG sets none
  of the four keys), so the suite was green while the drift was live.
- **Key evidence:** verifier ran the offered repro on a temp DB — job "Senior Software Engineer" + body
  "8+ years", cfg `seniority_target='entry'`, `years_cap=3`: insert score **53** with `over-target(senior) -12`
  note → after `rescore()` score **65**, note gone. Real +12 ranking inflation, honesty demotion erased,
  every run, for the exact keyless wizard audience P0-3 targeted (`ui/setup_wizard.py:400-410` writes those
  cfg keys for an Entry-level user).
- **FIX:** `025b0ce` fix(rescore): thread the four S32 honesty levers into rescore_inbox
  (+ lever-tripping parity test) → merged `80ce359` (s32d/scoring).

### 2. MAJOR — Body-salary gate hard-drops legitimate roles when the JD body names a monthly bonus/commission figure

- **Dimension:** scoring/gate regressions
- **File:line:** `preferences.py:137-140` (hard-gate branch) · `preferences.py:158-176` (`_body_comp_below_floor`) · `match/scorer.py:444-446` (`_NON_SALARY_CTX`)
- **Claim:** the sub-floor-body branch fires when API salary fields are empty AND a floor is set; it calls
  `parse_comp` on the description, which parses a "bonus"/"commission"/"monthly" figure as if it were comp
  and annualizes it. `_NON_SALARY_CTX` skips stipend/401k/relocation/sign-on but NOT bonus/commission. So
  "Base salary competitive. Plus up to $2,500/month bonus" parses to $30k/yr and is HARD-DROPPED past an
  $85-90k floor — silent data loss, no per-job trace.
- **Key evidence:** verifier confirmed `_NON_SALARY_CTX.search('bonus')`/`('commission')`/`('signing bonus')`
  all False (only `'sign-on bonus'`=True). End-to-end through `hard_gate` at floor 85000, three legitimate
  sales/AE roles dropped via `continue`. Live-wired (`ranker.gate`→`hard_gate` runs before `score_jobs`;
  Adzuna sets `description` inline at gate time). Bounded to floor-setting users; common in sales/AE/hospitality.
  (One claim overstatement noted: active `preferences.json` has `salary_min=null` so currently a no-op until a floor is set.)
- **FIX:** `a93ca54` fix(scorer): treat bonus/commission body figures as non-salary context → merged `80ce359`.

### 3. MAJOR — Adzuna location-label distrust false-positively caps genuinely-local roles whose body names the home city without its state abbrev

- **Dimension:** scoring/gate regressions
- **File:line:** `match/scorer.py:580-597` (`_location_contradicts`) · `:683-686` (application in `score_job`)
- **Claim:** `_location_contradicts` returns True (caps location to 0.34, flags `loc-unverified`) when the
  label's state isn't literally re-stated in the body but some OTHER "City, ST" is. Bodies routinely write
  the home city as bare prose ("based in Cincinnati") while naming other plants as "City, ST" — so a real
  Cincinnati role whose body mentions "Louisville, KY"/"Indianapolis, IN" is wrongly distrusted. Always-on;
  bare-city targets (the controls profile: location "Cincinnati", Adzuna enabled) are squarely in scope.
- **Key evidence:** identical local Controls Engineer labeled "Cincinnati, OH" scores **53** (loc 34%,
  `loc-unverified`) with bare-prose body vs **59** (loc 67%, no flag) when the body writes "Cincinnati, OH"
  explicitly. Bounded: Adzuna-only, ~6-pt nudge on a 15%-weight component, never hard-drops. Degrades the
  primary local-relevance signal for the flagship profile.
- **FIX:** `0adef93` fix(scorer): bare-city home in body confirms an Adzuna location label → merged `80ce359`.

### 4. MAJOR — REAP is silently inert for every GUI/MCP search (location never threaded into build_clients)

- **Dimension:** new-source plumbing
- **File:line:** `gui.py:3303` (build_clients call) · `mcp_server.py:60` · `search/reap_client.py:249-268` (portal resolved once in `__init__`)
- **Claim:** the GUI worker calls `build_clients(...)` with NO `location` arg → `ReapClient(location=None)`.
  ReapClient resolves its per-state portal ONCE in `__init__` via `portal_for_location`; with None that's
  None → `active=False`, `search()` returns `{'rows':[]}`, never re-resolved from `search()`'s location arg.
  An Ohio K-12 teacher searching from the GUI gets ZERO REAP rows even though the daily_run path (which
  passes `location=`) works — GUI/MCP diverge from daily_run for the exact persona REAP was added for.
- **Key evidence:** live repro of the GUI build path → reap client `active=False`, `portal=None`, "[reap]
  Inert" log line; the cli path with `location='Columbus, OH'` → `active=True`, `portal='ohreap.net'`.
  EdJoin unaffected (its gate depends on industry, not a location-resolved portal). Bounded to GUI/MCP
  education searches.
- **FIX:** `23af056` fix(k12): thread REAP location through GUI/MCP + de-spoof EdJoin, enforce robots
  → merged `b686f40` (s32d/feeds). (Also closes minor #2, EdJoin UA/robots — see below.)

### 5. MAJOR — National-feed (rnjobsite/higheredjobs) metro localization drops in-metro suburbs and keeps same-name out-of-state cities

- **Dimension:** new-source plumbing
- **File:line:** `search/rnjobsite_client.py:186-198` · `search/higheredjobs_client.py:208-213` (metro filter) · `search/remote_intent.py:83-98` / `coverage/geography.py:24-34` (`metro_variant_set`)
- **Claim:** for a metro-bound search both feeds HARD-DROP any row not in `metro_variant_set(location)`,
  which contains only the CBSA title + principal city + bare principal-city name (no constituent suburbs),
  via a naive substring match with no state check. Two wrong outcomes: (1) false-drop — a Cincinnati user
  loses "Edgewood, KY" (St. Elizabeth) and "Hamilton, OH"; (2) false-keep — a "Columbus, OH" user KEEPS
  "Columbus, GA" (700 mi) which then earns full local credit. Net coverage LOSS + cross-state false positives.
- **Key evidence:** repro — Cincinnati keeps ONLY `['Cincinnati, OH']` (two real suburbs discarded);
  Columbus OH keeps `['Columbus, GA','Columbus, OH']` and the GA row scores 2/3 local. Pre-change baseline
  had ZERO location filtering (all reached scoring). Asymmetry real: reap/edjoin fail-open on in-state rows;
  these two hard-`continue`. Bounded to two sector feeds on metro-bound searches.
- **FIX:** `4b4ba74` fix(feeds): state-aware, fail-open metro filter for national feeds → merged `b686f40`.

### 6. MAJOR — Adzuna remote-only rows lose their (Remote) tag on any cache hit

- **Dimension:** new-source plumbing
- **File:line:** `search/adzuna_client.py:92-100` (strip `_remote_intent` before caching; return cached at 64-66)
- **Claim:** on a remote-only search Adzuna sets `data['_remote_intent']=True` so `parse_results` tags
  fanned-out metro rows "City (Remote)". But the flag is stripped before caching and the cache-hit fast path
  returns the cached dict verbatim, so every cache-served remote response has `remote_intent=False` and the
  rows go untagged → score location=0 against a "Remote" search → demoted below min_score / out of Top Picks.
  First remote search of the day works; every subsequent GUI search + daily_run within the 24h TTL silently
  loses most remote Adzuna rows. Cache round-trip untested (tests use `cache_enabled=False`).
- **Key evidence:** live repro with temp cache — cold call: `_remote_intent=True`, row "Austin, TX (Remote)";
  cache hit: `_remote_intent=None`, bare "Austin, TX". Scoring: "Austin, TX"→0 vs "(Remote)"→2; a fan-out
  "Marketing Manager" row drops 78→67 on the cache hit. `CACHE_TTL_HOURS=24`.
- **FIX:** `23e3def` fix(adzuna): preserve (Remote) tag on cache-hit for remote-only searches → merged `b686f40`.

### 7. MAJOR — CareerOneStop userId leaks un-redacted into last_run.json + the "Report a problem" zip on any non-404 HTTP error

- **Dimension:** security / ToS / key hygiene
- **File:line:** `applog.py:71` (root cause) · `search/careeronestop_client.py:144` (leak source) · `search/search_engine.py:238`→`daily_run.py:579` (persist path)
- **Claim:** the CareerOneStop client puts the account userId in a bare URL PATH segment and calls
  `raise_for_status()`; on a 401/403/5xx the HTTPError string embeds `.../jobsearch/<USERID>/...`.
  `search_engine.py:238` stores `redact(str(e))` into `last_run.json['errors']`, which ships in the
  user-sendable diagnostic zip. `redact()`'s three regexes (query-param / jooble-path / user:pass@) don't
  match a bare path segment, and the value-substitution backstop that should scrub configured key values is
  dead (see #8), so the userId survives. The Jobs API is governance-gated since 2024-08-27 → the 401/403
  path is routine for a keyed-but-gated account.
- **Key evidence:** verifier confirmed `str(HTTPError)` on a 401 embeds the userId; `redact()` returns the
  string unchanged; `_known_secret_values()` returns `[]`. `ui/help.py:452-471` copies `last_run.json` into
  the zip. Bounded — only the account userId (an identifier) leaks, not the Bearer token (in the header,
  never in the raise_for_status URL).
- **FIX:** `8c90e89` fix(security): redact CareerOneStop userId at the source (client re-raise) +
  `a443e48` arm the value-substitution redaction backstop → merged `9f42df4` (s32d/secrets).

### 8. MAJOR — applog._known_secret_values() is entirely inert — value-based key scrubbing never runs for ANY credential (dead since S29)

- **Dimension:** security / ToS / key hygiene
- **File:line:** `applog.py:71`
- **Claim:** `_known_secret_values()` calls `config.resolve_secret(n)` with ONE positional arg but the
  signature requires TWO (`env_name, secret_name`). Every call raises TypeError, swallowed → returns `[]`.
  The `redact()` value-substitution loop therefore never scrubs a single configured key value. Any credential
  (adzuna/usajobs/jooble/careerjet/careeronestop/SERPAPI_KEY/ANTHROPIC_API_KEY/credential-bearing base_url)
  in a shape the three regexes don't match is NOT redacted. Green suite because the redaction tests only
  exercise query-param + jooble-path shapes and never assert the value list is non-empty.
- **Key evidence:** repro — `resolve_secret('adzuna_app_id')` raises the TypeError; `_known_secret_values()`
  returns `[]` even with real credentials set; an Adzuna key in `X-Api-Key: <key>` and an Anthropic key in a
  `token <key>` prose shape both survive `redact()`. A counterfactual two-arg call scrubs them. Defeated
  defense-in-depth backstop; the three regexes still catch the dominant full-URL query-param leak vector, so
  bounded (major, not critical).
- **FIX:** `a443e48` fix(security): arm the value-substitution redaction backstop + scrub CareerOneStop path
  userId → merged `9f42df4` (s32d/secrets). (Same builder that closes #7's backstop half.)

### 9. MAJOR — Re-verifying a previously-unverified board never clears the unverified flag; the board is permanently locked out of scraping

- **Dimension:** data integrity
- **File:line:** `scrape/company_registry.py:204-246` (`save_companies`) · docstring `:24-28` · `gui.py:2767-2810` · `ui/ai_setup.py:293-356`
- **Claim:** the documented P0-6 contract ("a later re-add with a live probe overwrites it and clears the
  flag") is NOT implemented. `save_companies` is strictly append-only (skips on `(ats_type,slug)`/name dup),
  so a board saved with `extra={'unverified':True}` after a transient probe failure, then re-added once live,
  returns `added=0` and stays flagged; `get_registry` excludes it from scraping forever. No code anywhere
  pops `UNVERIFIED_FLAG` (grep = 0 hits outside a test that hand-edits JSON). All three write paths affected
  (GUI `_do_gated_add`, `ai_setup.apply_seed_lines`/MCP `seed_companies`, `browser_receiver.clip_board`).
- **Key evidence:** live read-only repro against a tmp companies.json — verified re-add → `added=0`, record
  still `{'unverified':True}`, still excluded. Docstring at `:24-28` is false. Silent permanent coverage loss
  with misleading "Added 0 / duplicate" feedback for a transiently-down board.
- **FIX:** `c2c9589` fix(registry): clear unverified flag on a verified re-add (P0-6 re-verify) +
  `8249683` fix(seed): reject ToS-blocked hosts + wire re-verify in the AI/MCP seed path → merged `b5e3ba6`
  (s32d/registry). (Duplicate finding #13 below, from the cross-branch lens, is the same defect — closed here.)

### 10. MAJOR — New-person wizard silently discards the closing "Keep jobs coming" step

- **Dimension:** GUI/wizard coherence
- **File:line:** `gui.py:4907-4908` (callback) · `ui/setup_wizard.py:1099-1118` (`_close` arity dispatch)
- **Claim:** "New Person" launches the wizard with a 1-arg callback, so `_close`'s `takes_two` is False and
  the closing-step `_actions` dict (daily updates / Build-My-List / forced "Update your Inbox now") is never
  passed — every closing selection thrown away. First-run onboarding (2-arg `_after_setup`) honors all three.
  The wizard defaults `daily_updates` and `build_list` to True, so an additional profile accepting the
  defaults silently loses daily-update registration + Build-My-List + the forced first inbox update.
- **Key evidence:** confirmed via read-only `inspect.signature` repro (`takes_two`=False for the 1-arg lambda).
  Git history corroborates the drift — the `_new_person` lambda predates the closing-step actions (added in
  `9a3d1a9`, which updated only the first-run caller). Bounded to additional-profile onboarding; features
  reachable manually afterward.
- **FIX:** `c7de16a` fix(onboarding): honor closing wizard step for New Person + unstack first-run modals
  → merged `ad6a432` (s32d/guiflow). (Same builder also fixes minor #1, modal stacking.)

### 11. MINOR (reviewer said major; verifier downgraded) — First-run stacks the "Update your Inbox now?" prompt on the still-open Build-My-List modal

- **Dimension:** GUI/wizard coherence
- **File:line:** `gui.py:4144-4166` (`_after_setup`)
- **Claim:** on default first-run finish, `_after_setup` opens the modal `BuildCompanyListDialog` then
  IMMEDIATELY fires the "Update your Inbox now?" messagebox without awaiting the Build dialog — two competing
  modal grabs at once, breaking the intended sequential flow.
- **Key evidence:** mechanical claim reproduces exactly (dialog instance discarded, no `wait_window`;
  messagebox parented to the main window). Verifier headless Tk repro confirmed the grab transfers to the
  messagebox while the Build dialog stays open. **Downgraded to minor:** purely a stacked-modal UX papercut
  — no wrong results, data loss, leak, crash, or ToS; both dialogs stay functional.
- **FIX:** `c7de16a` (same builder as #10 — "unstack first-run modals") → merged `ad6a432`.

### 12. MAJOR — Demo sample-inbox rows leak into the "Export for AI" round-trip (no guard, no test)

- **Dimension:** test adequacy and drift
- **File:line:** `gui.py:2257` (`_export_for_ai`) → `:2249-2255` (`_export_rows`) → `:1643-1653` (`_filtered`) · demo activation `:1466-1474`
- **Claim:** the first-run demo inbox (`is_demo=True`, negative ids, source "Demo") is unguarded on export.
  Every other inbox action calls `_block_if_demo`, but `_export_for_ai` operates on `self._all`/`_filtered()`
  and never does. With the demo active, a first-run user who clicks the always-enabled "Export for AI" writes
  ~20 fictional jobs (Northwind Labs, etc.) into the AI round-trip CSV + prompt.md and asks their AI to rank
  jobs that don't exist — a misleading deliverable they act on. Import side is harmless (job_key never matches).
- **Key evidence:** read-only repro — `demo_inbox_rows()` → 20 rows; `export_inbox(...)` writes 21 CSV lines
  - a 4541-char prompt.md with demo companies. Test drift confirmed: `test_export_scope.py` fixture was
    modified in-scope to `retire_demo()`, so export tests never see the overlay. Bounded to first-run (demo
    auto-retires on the first real inbox).
- **FIX:** `1b08706` fix(demo): keep the sample inbox out of AI export + suppress its real-reach badge
  → merged `ad6a432` (s32d/guiflow). (Same builder also closes minor #5, the demo real-reach badge.)

### 13. MAJOR (duplicate of #9, from a different lens) — P0-6 unverified boards permanently excluded from scraping; docstring/test claim a clear that doesn't exist

- **Dimension:** cross-branch semantic conflicts git could not see
- **File:line:** `scrape/company_registry.py:24-27` (docstring) · `:204-247` (`save_companies`) · `gui.py:2767-2794` · `scrape/browser_receiver.py:129-160` · `ui/ai_setup.py:293-356` · `tests/test_discovery_persist.py:85-101`
- **Claim:** every transient-rescue write path (GUI gate, browser clip, AI seed-lines) funnels through the
  append-only `save_companies` with no upsert; a verified re-add returns `added=0` and leaves the flagged
  record untouched → `get_registry(include_unverified=False)` excludes it forever. The clip path compounds it
  (dedups via `get_registry(include_unverified=True)` → returns "duplicate" before the probe). This straddles
  the P0-6 gate branch + the clip/seed branches merged in different waves — each independently writes the flag,
  none can clear it. Docstring + test misrepresent that a clear exists.
- **Key evidence:** same repro as #9 (verified re-add `added=0`, record stays flagged, never listed). The only
  `pop` of the flag lives in `test_discovery_persist.py:99`, which hand-edits JSON and admits it "simulates"
  the clear. Green suite (2125 passed) didn't catch it.
- **FIX:** same as #9 — `c2c9589` + `8249683` → merged `b5e3ba6` (s32d/registry), plus `b5e3ba6`'s
  registry write-lock addressed minor #9 (the `/clip` lost-write race).

---

## Follow-up defect (not in the fleet's 13 — found by the live smoke, then fixed)

**workday_cxs 422-walled tenants saved as "verified-empty" instead of "unreachable."**
The post-fix smoke (`smoke-2026-07-02-post-fix.md` §1 + §Errors) observed that for `workday_cxs`,
`probe_count` returns `len(fetch(slug))`; a Cloudflare-walled 422 fails-soft to `[]` → `len([])==0`, an
integer, so the P0-6 gate marks it **"live (0 open jobs)" = verified** rather than `unreachable`. Not a
regression (still excluded from results because it yields 0 jobs), but the verify gate couldn't distinguish
"genuinely live, 0 open" from "Cloudflare-walled." A final builder resolved it:

- **FIX:** `b67a85e` fix(P0-6): surface workday_cxs reachability so a walled tenant isn't "verified" +
  `62f449e` fix(P0-6): route every verify consumer through the reachability verdict → merged `f3b07ee`
  (s32e/probeverdict). **This finding's lineage is the smoke test, not the review fleet.**

---

## Minors (9) — passed through unverified by the fleet; status per the fix-wave merge commits

The guiflow / registry / feeds / secrets fix builders verified-and-fixed most of these in passing. Status:

| #   | Minor                                                                                          | File:line                                                                      | Status                                                               | Where                           |
| --- | ---------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ | -------------------------------------------------------------------- | ------------------------------- |
| 1   | Demo rows flow into AI export (dup of confirmed #12, from scoring lens)                        | `gui.py:2249-2255`                                                             | **Real & FIXED**                                                     | `1b08706` → `ad6a432`           |
| 2   | EdJoin spoofs a browser UA + XHR header, no runtime robots enforcement (unlike REAP)           | `search/edjoin_client.py:130-145`                                              | **Real & FIXED** — honest UA, robots enforced                        | `23af056` → `b686f40`           |
| 3   | MCP `seed_companies`/`apply_seed_lines` save "direct" boards unprobed → arbitrary fetch target | `ui/ai_setup.py:327-332`; `scrape/direct_scraper.py:71-78`                     | **Real & FIXED** — ToS-blocked-host guard on programmatic seed paths | `8249683` → `b5e3ba6`           |
| 4   | AI-export includes read-only demo rows, reports them as real (dup of #12, data-integrity lens) | `gui.py:2249-2289`                                                             | **Real & FIXED**                                                     | `1b08706` → `ad6a432`           |
| 5   | Demo inbox shows a real-reach "mostly remote/tech" badge contradicting the balanced demo rows  | `gui.py:1490-1517`; `coverage/reach.py:229-248`                                | **Real & FIXED** — badge suppressed under demo                       | `1b08706` → `ad6a432`           |
| 6   | Kanban emits `<<KanbanChanged>>` that nothing binds; cross-tab sync only on tab-switch         | `ui/kanban.py:260,276` vs `gui.py`                                             | **Real & FIXED** — event wired for live cross-tab refresh            | `963ebd4` → `ad6a432`           |
| 7   | Kanban "days here" measures days-since-applied, not days in current stage                      | `ui/kanban.py:67-98,228`                                                       | **Real & FIXED** — stage-aware clock                                 | `963ebd4` → `ad6a432`           |
| 8   | Guide references a wizard step title that no longer exists + omits the new Board tab           | `ui/help.py:139-141,83`                                                        | **Real & FIXED** — copy synced                                       | `e8ef3f9` (guiflow) → `ad6a432` |
| 9   | `/clip` lost-write race on companies.json under Flask threaded server, no concurrency test     | `scrape/browser_receiver.py:166,579-596`; `scrape/company_registry.py:204-246` | **Real & FIXED** — registry write lock added                         | `b5e3ba6` (s32d/registry)       |

**Net:** all 9 minors were real; all 9 were fixed within the S32d fix wave (none left as pass-through debt).
Minors #1 and #4 are the same demo-export defect surfaced by the confirmed critical #12; minors #6/#7/#8 are
the Kanban/Guide papercuts folded into the guiflow builder.

---

## Summary

- **13 confirmed, 0 refuted, 9 minors — all real, all fixed.**
- The **critical** (rescore drift, #1) is the S24-class regression the whole S32 scoring effort was meant to
  land: it silently reverted the four honesty levers on every run for keyless wizard users. Fixed + a
  lever-tripping parity test that the original parity test was structurally blind to.
- Two **inert-since-S29** defects surfaced: the applog value-scrubber (#8) never ran for any credential, and
  the CareerOneStop userId (#7) rode that dead backstop into the diagnostic zip. Both armed.
- The registry re-verify lockout (#9/#13) is a cross-branch semantic conflict git could not see — two waves
  each wrote the unverified flag, neither could clear it. Fixed with an upsert/re-verify path + write lock.
- The **workday_cxs walled-vs-empty** follow-up came from the live smoke, not the fleet, and was closed by
  s32e/probeverdict — recorded here so the lineage is not lost.
