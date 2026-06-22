---
name: find-jobs
description: Run a preference-tailored job search via the jobscout MCP server — search sources, rank the inbox against the user's written preferences, and surface the best matches. Use when the user asks to find jobs, run a job search, or rank/triage their job inbox.
---

# Find Jobs

You drive the **jobscout** MCP server — a thin data layer over a job-search engine.
**YOU are the ranker:** read the user's preferences and judge each posting's fit
yourself, then write the scores back. The server does no AI; that's your job.

## Workflow

1. **Read preferences** — call `get_preferences`. Note `profile_md` (what they want,
   in their own words) and `hard_filters` (already enforced by search).
2. **Search** (when asked to find new jobs, or the inbox is thin) — call
   `search_jobs` with the user's keywords/location, or no args to use their config
   defaults. It hard-gates, scores, and adds new postings to the inbox.
3. **Pull the inbox** — call `list_inbox(unscored_only=true)` for postings that still
   need YOUR ranking.
4. **Rank** — judge each posting 0–100 against `profile_md` AND the user's
   background. Guide: 90+ apply today · 70–89 strong · 50–69 stretch · <50 skip. Be
   honest — don't inflate. Flag red flags (clearance, seniority mismatch,
   contract-only, misleading title).
5. **Persist** — call `set_fit_scores` with `[{"id", "fit", "rationale"}, ...]`
   (rationale = ≤2 lines: why + any red flag).
6. **Present** — show the top matches best-first: `title · company · location · fit ·
one-line why`. Offer to `track_job` the ones they like.

## Notes

- Re-run from step 3 to rank more — `list_inbox` returns the next batch of unscored.
- `track_job(inbox_id)` promotes a posting to their tracker; `dismiss_job(inbox_id)`
  hides it from future searches.
- Never invent postings — only rank what `list_inbox` actually returns.
