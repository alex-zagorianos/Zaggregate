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
   `search_jobs` with the user's keywords/location, or no args for their config
   defaults. It hard-gates, scores, and adds new postings to the inbox.
3. **Pull the inbox** — call `list_inbox`. Each row carries its signal (title,
   company, location, salary, local `score`, current `fit`, your `rank`,
   `job_key`, a description snippet). You decide what's relevant — don't rely on a
   pre-filter. **PAGE for large inboxes:** a few hundred full rows can overflow a
   small local model's context. Keep `limit` at or below ~150 rows per call and
   pass `compact=true` (each row's long description becomes a one-line `facts`
   summary, ~15x smaller) so you can see far more jobs per call. Score a batch,
   then list the next batch of still-unscored rows and continue.
4. **Judge & rank** — score each posting 0–100 against `profile_md` AND the user's
   background (Guide: 90+ apply today · 70–89 strong · 50–69 stretch · <50 skip).
   Then choose the **top X** to recommend (default 10, or whatever the user asked
   for) and order them 1..X, 1 = best. Be honest; flag red flags (clearance,
   seniority mismatch, contract-only, misleading title).
5. **Persist** — call `set_fit_scores` with `[{"id", "fit", "rationale", "rank"}, ...]`.
   Give `rank` 1..X to your shortlist; omit `rank` for everything else. Ranked rows
   supersede the previous shortlist and appear in the app's **Top Picks** tab.
6. **Present** — show the top X best-first: `# · title · company · location · fit ·
one-line why`. Tell them these are now in the **Top Picks** tab. Offer to
   `track_job` the ones they like.

## Notes

- For a small inbox `list_inbox(limit=0, unscored_only=false)` returns everything
  in one pass; for a large one, page with `limit<=150` + `compact=true` (see step 3).
- `track_job(inbox_id)` promotes a posting to their tracker; `dismiss_job(inbox_id)`
  hides it from future searches.
- A fresh `set_fit_scores` run with new `rank`s replaces the old Top Picks shortlist.
- Never invent postings — only rank what `list_inbox` actually returns.

## Beyond ranking: the application cycle

Your help doesn't end when a job is tracked. These tools cover the whole cycle:

- **`skill_gap(inbox_id)`** — the JD's asked-for skills vs. what the candidate has
  ("matched"/"missing"); use it to explain a fit or steer a resume.
- **`get_resume_prompt(inbox_id=… | app_id=…)`** → answer its structured-JSON
  request → **`save_resume(data_json, company)`** writes the DOCX resume + cover.
  The prompt already folds the JD's `missing` skills in, so tailoring targets the
  posting's real asks.
- **Pipeline:** `list_applications(status?)`, `get_application(id)` (JD, resume,
  `days_in_stage`), `set_status(id, status)`, `set_follow_up(id, date)`, `funnel()`.
- **Follow-ups:** `followups_due()` finds what needs attention;
  `draft_followup_context(id)` gathers the job + JD snapshot + date_applied +
  contact so you can draft a follow-up email.
