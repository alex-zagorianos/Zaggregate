# Zaggregate (JobScout)

A private, on-your-computer job search that casts the widest possible net across
many public job sources, ranks every posting to _your_ preferences, and tracks
your applications from "interested" through "applied" and beyond. Built to be
used **with** an AI assistant of your choice — bring your own.

Nothing is uploaded on its own: your resume, preferences, scores, and tracker
live in a local data folder. The app never applies for you — you always click
submit.

## Why Zaggregate — own your data, apply on purpose

Every other job tool is cloud SaaS that ingests your résumé. Zaggregate is
local-first by design, and that turns two industry-wide problems into features:

- **Own your data.** A 2025 study found **90% of job platforms sell user data**
  (8 of 9 investigated sell it under CCPA; ZipRecruiter, Monster, and LinkedIn
  ranked most invasive). Zaggregate has no account, no cloud, and no telemetry —
  your résumé, preferences, scores, and tracker never leave your machine. This is
  a moat no SaaS rival can answer.
  ([inc](https://www.inc.com/bruce-crumley/90-percent-of-job-platforms-sell-user-data-study-finds-here-are-the-biggest-offenders/91358104),
  [incogni](https://blog.incogni.com/are-job-search-platforms-exploiting-job-seekers-for-their-personal-data/))
- **Assisted, not auto-apply.** Bulk auto-apply bots succeed at roughly
  **0.01% per application (1 in 10,000)** versus **4–6% for a tailored
  application** — and recruiters are actively AI-filtering the spam (Greenhouse's
  CEO calls it a hiring "doom loop"; Wonsulting shut its bulk-send feature in
  Aug 2025). Zaggregate aggregates, de-dupes, scores, and helps you tailor — then
  **you** click submit. Tailored, not sprayed.
  ([forbes](https://www.forbes.com/sites/robinryan/2025/09/22/ai-auto-apply-job-tools-recruiters-warning/),
  [cnn](https://www.cnn.com/2025/12/21/economy/ai-hiring-complication))
- **Honest reach, not ghost-job opacity.** Zaggregate tells you what fraction of
  your local market it can actually see (a "reach" badge) and flags when top
  results may be poor fits — the opposite of the outdated/ghost postings and
  résumé hallucinations reviewers hit with the auto-apply "agents."
  ([flashfire](https://www.flashfirejobs.com/blog/is-jobright-ai-legit))

## What it does

- **Wide-net aggregation, any field.** Pulls postings from free public sources
  (Adzuna, USAJobs, CareerOneStop/NLx, The Muse, RemoteOK, Remotive, Jobicy,
  Himalayas, Hacker News "Who is hiring?", WeWorkRemotely, Working Nomads,
  Jooble, Careerjet) plus company career pages across many ATS platforms
  (Greenhouse, Lever, Ashby, Workday, SmartRecruiters, Workable, and more).
  Designed for any occupation — nurse, teacher, welder, driver, engineer — not
  just tech.
- **Explainable 0–100 scoring.** Every job gets an instant, on-device match Score
  from your keywords, skills, location, and salary. No black box.
- **AI-friendly ranking (bring your own AI).** Two channels, both provider-
  agnostic — see below.
- **Full application tracking.** Interested → Applied → Interview → Offer, with
  follow-up reminders, tailored resume/cover-letter generation, and a job
  Tracker.

## Quick start (run from source)

Requires Python 3.12 on Windows (`py -3.12`).

```
py -3.12 -m pip install -r requirements.txt
py -3.12 gui.py
```

A short Setup wizard on first run asks what jobs you want, where, your salary,
and your resume — no files to edit. Open your Inbox and click **Update my Inbox
now**, or use the Search tab.

### Build the distributable exe

```
py -3.12 -m pip install pyinstaller
py -3.12 build_package.py
```

This produces `dist/JobScout-v<version>.zip` — a folder a friend unzips and runs
with no Python install. See `build_package.py` for details.

## The two AI channels (bring your own AI)

1. **Clipboard round-trip (free, no key, any chatbot).** Click _Ask AI to rank
   these_ — it copies a ready-made prompt (your preferences + the jobs) to the
   clipboard. Paste it into any AI chat (Claude, ChatGPT, Gemini, Copilot — a
   free tier is fine), copy the reply, and click _Paste AI ranking_. Each job's
   Fit grade lands back on the right row.
2. **MCP server (Claude Code / MCP clients).** The `claude-code/` folder ships an
   MCP server so an agent can drive search, ranking, and the application cycle
   directly. See `claude-code/` for setup.

An optional API key (Tools ▸ _Connect your AI_) enables hands-off auto-ranking
and AI resume/cover-letter drafting. Any Anthropic-compatible endpoint works
(including local Ollama, GLM, DeepSeek, Kimi via a base-URL setting).

## Architecture

The high-level map lives in [`_index.md`](_index.md); design and review notes are
under [`brain/`](brain/) (e.g.
`brain/review-2026-07-01-deep-product-review.md`). Entry points: `gui.py`
(desktop app), `daily_run.py` (headless daily search → inbox), `search/cli.py`
(command line), `mcp_server.py` (MCP).

Application logs are written to `<data folder>/logs/app.log` (rotating). Use
Help ▸ _Report a problem_ to package logs + version for support — it never
includes your API keys or resume.

## License

License: not yet chosen — all rights reserved for now.
