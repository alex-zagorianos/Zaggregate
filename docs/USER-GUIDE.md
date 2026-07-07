# Zaggregate User Guide

This is the full how-to for using Zaggregate — from first run through every tab,
the browser extension, daily automation, and backups. If you just want to try
it, [README.md](../README.md) is the shorter front door. If you want to
understand how it works under the hood, see
[ARCHITECTURE.md](ARCHITECTURE.md).

Everything here happens on your own computer. Nothing you type, no résumé, and no
search ever leaves your machine unless _you_ choose to paste a prompt into your
own AI chat.

---

## Contents

- [First run](#first-run)
- [The tabs, one by one](#the-tabs-one-by-one)
- [The browser extension](#the-browser-extension)
- [Daily automation](#daily-automation)
- [Backup and restore](#backup-and-restore)
- [Running multiple people or campaigns](#running-multiple-people-or-campaigns)
- [Troubleshooting](#troubleshooting)

---

## First run

### Starting the app

**Packaged app (a friend's download):** unzip the release, open the `JobProgram`
folder, and double-click `Zaggregate-Desktop.bat` (or `JobProgram.exe` — same
thing): the app opens in its own window. The first time, Windows may show an
"unknown publisher" warning because the app isn't code-signed yet —
`FIRST-RUN.txt` in the same folder walks you past it. `Zaggregate-Web.bat`
(= `--web`) runs the same app in your browser; the legacy Tk window is
`JobProgram.exe --classic`.

**From source:** with Python 3.12 on Windows,

```
py -3.12 -m pip install -r requirements.txt
py -3.12 src\gui.py                 # classic desktop app
cd src
py -3.12 -m webui                   # modern web UI at 127.0.0.1:5002/app
py -3.12 -m webui --desktop         # modern web UI in a native window
```

On first launch, with no `.onboarded` marker, the **Setup wizard** opens
automatically. You have two ways through it.

### The express lane: let your AI set it up

This is the fastest path — one round-trip with any AI chat (Claude, ChatGPT,
Gemini, Copilot; a free tier is fine):

1. On the wizard's first screen (or the Search tab), click **Set up with AI**.
   It copies one ready-made prompt to your clipboard.
2. Paste that prompt into your AI. Below it, add your résumé plus one sentence
   about the work you want — for example, _"I want mechanical design roles near
   Cincinnati."_ Send it, and copy the AI's whole reply.
3. Paste the reply back into the app.

**What the reply looks like.** The AI returns a structured block — typically a
short fenced section the app knows how to read — that names your target roles,
your location, a salary floor, your seniority, and a starter list of local
employers (as `Name | careers-page-link` lines). From that single paste,
Zaggregate fills in your roles, location, salary, and seniority, adds the
starter employers to your watch-list, **and kicks off your first search** — no
keys, no accounts, nothing uploaded. If the reply is slightly malformed (extra
prose, smart quotes, a stray comment), the parser is built to tolerate it and
extract the best object it can.

### The manual wizard

Prefer to do it yourself? Every step is available by hand. The wizard asks, in
plain forms:

- **What jobs are you looking for?** — target roles/keywords, and your
  **field / industry**. That field answer does more than label you: it routes
  which categories are fetched from each source, turns field-specific feeds
  (nursing, higher-education) on or off, tunes how titles are scored, and filters
  the company watch-list to your industry. If results feel off-field, re-run the
  wizard and sharpen it.
- **Where?** — a city and/or remote.
- **Salary floor** — a minimum you'd consider.
- **Your résumé** (optional) — used to score skill overlap and, later, to tailor
  documents.
- **Connect your best free sources** (optional, skippable) — the impact-ranked
  key-setup step (see the [Sources](#sources) tab below).
- **Anything else?** — a free-text box for must-haves and deal-breakers in plain
  English. This is high-leverage: it feeds every AI ranking and every tailored
  résumé.

You can re-run the whole wizard any time from **Help ▸ Run Setup Wizard**.

---

## The tabs, one by one

The modern web UI has eleven tabs, each a step in the search-to-apply loop. (The
classic Tk app has the same core tabs minus the newer Insights, Discover, and
Sources surfaces, which appear there as dialogs.)

### Inbox

Your daily matched feed, ranked best-first. Every job carries a **Score** (0–100,
computed instantly on your computer) and a **Fit** grade (blank until you ask an
AI to grade it — see [Working with AI](#top-picks-and-working-with-ai)).

**Triage keys.** Click a row and use the keyboard to fly through it:

- **T** — track (moves the job to your Apply Queue)
- **D** — dismiss (you never see it again)
- **O** — open the posting in your browser
- **Enter** — open the detail pane; **↑ / ↓** — move between rows

**Update my Inbox now.** The main button runs a fresh search across all your
sources; give it a few minutes. The chevron next to it picks a **Run depth**:

- **Quick run** — 1 page per source (fastest, fewest calls)
- **Standard run** — 2 pages per source (the default)
- **Deep run** — 3 pages per source (widest net, slowest)

If a run is already going, clicking again reattaches you to the live console
instead of starting a second run.

**Filters** narrow the _view_ only — nothing is ever deleted by a filter (the app
prefers to show you everything and let you drop it). You get a free-text search,
Source and Size selectors, a Location-mode selector, a Sort control, a min-score
slider, and toggle chips: **New only**, **Unscored only**, **Hide stale**, and
**Meets pay floor**. Bulk **Dismiss all shown** / **Dismiss selected** actions
come with an Undo toast.

**Badges** at the top show the last run's summary, a **reach** estimate for your
area, a "Sample data shown" pill on a brand-new inbox, and — importantly — a
**"N sources skipped (no key)"** chip. That chip is your cue that more local jobs
are one free key away; click it to jump to Sources.

> **New here?** Your Inbox first shows a short **SAMPLE** of example jobs so you
> can see what scored matches look like. Click **Update my Inbox now** to replace
> it with real jobs from your sources.

### Top Picks and working with AI

**Top Picks** is a read-only, AI-ranked shortlist derived from your inbox — the
strongest matches, sorted by rank, with a "Why" rationale. Use the **Show** limit
to see the top 10/15/20/25/50 or all. The same T/D/O triage keys work here.

Top Picks and the Fit column both come from the **ranking round-trip**, which is
free and needs no key:

1. Click **Ask AI to rank these** (or **Rank with AI**). It copies a ready-made
   prompt — your preferences plus the jobs — to your clipboard.
2. Paste it into any AI chat and copy the whole reply.
3. Click **Paste AI ranking**. Each job's Fit grade lands back on the right row.
4. Sort by Fit and work down from the top.

Prefer files to the clipboard? **Export for AI** writes a spreadsheet and
**Import results** reads the grades back. **Undo AI ranking** reverses the last
import. When Score and Fit disagree, trust Fit for nuance and Score for raw
skills overlap — a high Score next to a low Fit usually means "matches on paper,
wrong role for you."

### Search

Run a one-off search for any keywords in any location, on demand. Results are
scored 0–100 and you can Track, Dismiss, or add each (or **Add all to Inbox**).
The action buttons across the top:

- **Set up with AI** — the combined config-and-seed express lane (same one-paste
  flow as first run); its applied pane offers a **Run search now** button.
- **Add companies** — paste career-page links (one per line; plain links work,
  and `Name | link` works too) so those employers' jobs show up in future
  searches. The app verifies each board live before saving.
- **Build my list** — a guided flow for assembling a company watch-list.
- **Seed my area** — populate a starter list of local employers for your city
  and field. It has an AI-seed lane (no key needed — paste an AI's list) and a
  direct-seed lane.

**A note on adding companies safely:** the app probes each board live before
saving. Verified boards are added and scraped; anything that fails verification
(a wrong or guessed link) is either discarded or, if you keep it, saved marked
_unverified_ and left out of your searches until it checks out — so a bad guess
can't quietly break future runs.

**Don't know your area's employers?** Ask your AI: _"List the 25 largest
employers of [your kind of work] in [your city], with a link to each one's
careers page, one per line as Name | link."_ Paste the answer straight into
**Add companies**.

### Apply Queue

Every job you marked Interested, best match first. This is where you produce
tailored documents and mark jobs applied:

- **Copy resume prompt** → paste into your AI, then **Paste reply → DOCX**
  builds a tailored résumé and cover letter as Word documents.
- **Generate via API** produces both in one shot if you've connected an AI API
  key (Tools ▸ _Connect your AI_). Without a key it tells you to use the
  copy-prompt path instead.
- **Copy application pack** copies your contact info, work history, and résumé
  path to the clipboard for a manual application form.
- **Mark applied** sets the status and **auto-advances to the next job**, so you
  flow through the queue without re-clicking.

Always read and edit what the AI produces before sending — it gets you ~90% of
the way; the last 10% (truth, your voice, specifics) is yours. You always click
submit.

### Tracker

A record of every job you're tracking and where it stands. The lifecycle runs
**Interested → Applied → Phone screen → Interview → Offer → Accepted**, with
terminal states **Rejected**, **Withdrawn**, and **Ghosted**, plus an **Archive**
bucket. Filter chips across the top show a live count per status. Update a job's
status inline as you hear back, set follow-up reminders, and archive or restore
rows. When a follow-up date arrives, a "Draft it" link appears.

### Board

The exact same tracked applications as a drag-and-drop pipeline — one column per
stage. Drag a card forward as you progress, or use its **Move ▸** menu (handy for
keyboard use). The board only lets you drop a card on a valid next stage; an
illegal move snaps back with a note. It's the same data as Tracker, just laid out
as a pipeline so you can see your whole search at a glance. Double-click a card to
edit it.

### Insights

A read-only view of how your search is actually converting:

- **Funnel** — Tracked → Applied → Interview → Offer → Accepted, with the
  conversion percentage between each stage and a ghosted count.
- **Where your interviews come from** — a per-source table of applied count,
  interviews, and interview rate (thin rates flagged when there isn't enough
  data yet).
- **Application cadence** — a weekly bar chart with a streak counter and a
  gentle "steady 10–20/week" target band.

### Resume

Paste any job posting — even one that didn't come from this app — and generate a
résumé and cover letter tailored to it. Two steps: **Copy prompt** (paste into
your AI), then **Build résumé + cover letter** from the AI's reply, downloaded as
Word documents.

### Discover

An experimental BYO-AI helper that suggests role _directions_ (not job postings)
worth searching, grouped into **Ready today**, **Strong overlap**, and **Worth
stretching for**. Type your interests, click **Build my prompt**, paste it into
any AI, and **Paste AI reply**. Each suggested role has **Add to my searches**
(merges the keywords into your project) and **Search now** (hands them to the
Search tab). No API key needed.

### Guide

The full in-app how-to, the same editorial content this guide is built around —
from first run through the browser extension, working with AI, referrals, and
ghost-job shielding. Read-only, with an on-page section index.

### Sources

Connect optional free job-source keys and see which are active. **Keyless works
on day one** — the app searches a set of free, no-signup feeds and your built-in
company career pages out of the box. Adding a couple of free keys transforms the
net for your city and field. Each source card has **Save** and **Test** buttons
(Test confirms your key works with an inline status), and keys are masked with a
reveal toggle.

Which keys matter, and why:

- **Adzuna** — a broad aggregator across ~19 countries; the single biggest unlock
  for local, on-site jobs in any field (office, trades, healthcare, retail,
  engineering). Free key, ~5 minutes.
- **CareerOneStop** — the U.S. Department of Labor's feed of the National Labor
  Exchange (~3.5M active postings/day from all 50 state job banks); the best free
  source for teachers, nurses, government, and trades. Free key, ~5 minutes.
- **Jooble** and **Careerjet** — two more free aggregators; each adds postings the
  others miss.
- **USAJobs** — every U.S. federal opening (free key).
- **SerpApi** — powers the Inbox "reach" badge (how much of your local market the
  app is seeing). A small free quota is plenty.
- **JSearch (via RapidAPI)** — pulls the big walled boards (Indeed, LinkedIn,
  Glassdoor) through one free key.

If a source has no key, it simply contributes nothing — quietly — and the Inbox's
"N sources skipped (no key)" chip tells you what you're missing. This page also
hosts the optional **referrals** import (local LinkedIn/Google contact matching)
for flagging your network at a company.

---

## The browser extension

Some big boards (LinkedIn, Indeed, Glassdoor, ZipRecruiter, Dice) don't offer a
search feed, and many jobs live on a company's own careers page or an applicant
system like Workday, Greenhouse, or Lever. The extension lets you pull any job
you're already looking at into your Inbox, scored like everything else. It's a
one-time, two-minute setup.

**Install (unpacked):**

1. In the app, open **Tools ▸ Capture jobs from my browser**. This starts a
   small local listener on your own computer (nothing leaves your machine). Leave
   the app open while you browse — the listener runs only while it's open.
2. Note where the `browser_ext` folder is — it's inside your install folder.
3. In Chrome or Edge, go to `chrome://extensions`.
4. Turn on **Developer mode** (top-right).
5. Click **Load unpacked** and select the `browser_ext` folder. "Job Harvester"
   appears in your list.
6. Pin it (puzzle-piece icon → pin next to "Job Harvester").

**Capture flows** (from the extension popup, buttons vary by page):

- **Send to Tool** — sends the jobs the extension collected on the big boards
  into your Inbox for triage. (An **Auto-send** toggle can push every 25 new jobs
  automatically.)
- **Track All as Interested** — bulk-tracks all collected jobs at once.
- **Capture this job** — on ANY single posting (a company careers page, Workday,
  Greenhouse, Lever, anywhere), grabs the one job you're viewing; then **Send to
  Tool** delivers it. It reads the page's structured data when the site provides
  it (most do) and falls back to a best-effort page read otherwise.
- **Add this employer's board to my registry** — on a company's careers page,
  adds that employer so future searches watch its board.
- **Verify from this tab** — appears only when the server couldn't reach a walled
  or Cloudflare-protected board; re-clips using your logged-in browser.

The listener runs only while the app is open and only accepts jobs from the
extension on your own machine. "Capture this job" reads only the one page you're
on, only when you click it.

---

## Daily automation

**Tools ▸ Turn on daily updates** (classic desktop app) registers a **Windows
Task Scheduler** job that quietly tops up your Inbox once a day, so there's always
something fresh waiting. It runs the whole pipeline — every feed, every company
page, scoring, and freshness flags — each morning before you sit down, and the
Inbox header shows when it last ran and what it found.

Scheduling is **per project**: each project gets its own scheduled task
(`JobSearchDaily_<slug>`), so a multi-person or multi-campaign setup keeps its
lanes separate and staggered a few minutes apart. Under the hood the task invokes
`src\daily_run.py --project <slug>` (or the frozen exe's `--daily --project <slug>`).

> The modern web UI's **Update my Inbox now** is an on-demand trigger; the
> scheduled daily update is set up from the classic desktop app's Tools menu.

---

## Backup and restore

Your data — preferences, résumé, scores, and the application tracker — lives in
your local data folder, never in the app or the cloud. Open it any time from
**Help ▸ Open my data folder**.

Zaggregate keeps rotating automatic snapshots of that folder, and you can make or
restore a backup on demand from the Guide/Help surface. A backup is a single zip
of your data folder (excluding logs and the backups folder itself); restoring
extracts it back over your data folder. Restores use a zip-slip-safe extractor,
so a tampered archive can't write outside the data folder.

To move to a new machine, copy your data folder (or a backup zip) across and
restore it. The internal data-folder name stays `JobProgram` on purpose, so an
upgrade never orphans your existing data.

---

## Running multiple people or campaigns

Zaggregate is multi-campaign. Each **project** is an isolated search — its own
preferences, company watch-list, inbox, and tracker. One project is the **active**
project at a time; you switch between them in the app. This is how you run several
searches side by side: separate roles for yourself (say, "software" and "controls"
as different lanes), or a project per person you're helping, tagged by person.

Two things to know:

- **Only one project-touching process should run at a time.** The active project
  drives which data folder gets written, so running two searches at once could
  cross wires. The app pins the active project for the duration of a run to keep
  lanes from colliding.
- **Daily updates are per project** (see [Daily automation](#daily-automation)) —
  each project gets its own scheduled task, so every lane refreshes on its own
  without stepping on the others.

---

## Troubleshooting

- **A run seems stuck or slow.** A full run asks ~20 sources for several pages
  each; give it a few minutes. Use a **Quick run** (1 page/source) when you want
  speed over breadth.
- **Few or no local jobs.** The free no-key feeds lean toward remote tech. Add
  the two keys that matter most — **Adzuna** and **CareerOneStop** — on the
  Sources tab, and add your local employers with **Add companies** / **Seed my
  area**. The Inbox's "N sources skipped (no key)" chip shows what's still off.
- **Results feel off-field.** Re-run the Setup wizard and sharpen your
  **field / industry** answer and the **Anything else?** box; both steer scoring
  and source routing.
- **AI ranking or résumé generation needs a key.** The clipboard round-trips
  (Ask AI to rank, Copy resume prompt) need **no** key — any chatbot works.
  Only the hands-off **Generate via API** path needs an AI API key
  (Tools ▸ _Connect your AI_); any Anthropic-compatible endpoint works, including
  local Ollama.
- **The web UI won't load / port in use.** The web UI binds `127.0.0.1:5002`
  only. If something else already holds that port, close the other instance —
  only one server should own the port at a time.
- **Windows "unknown publisher" warning.** The exe isn't code-signed yet; it's
  safe. `FIRST-RUN.txt` has the two safe ways past it.
- **Reporting a problem.** **Help ▸ Report a problem** packages your logs and
  version into a small file for support — it never includes your API keys or
  résumé. Send it through the in-app feedback link.
