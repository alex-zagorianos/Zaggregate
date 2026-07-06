"""Tk-free core of the in-app Guide + data backup/restore.

The static GUIDE content and the zip backup/restore logic both need to be
reachable from the web layer (a Guide page + a backup-download / restore-upload
flow) WITHOUT importing tkinter — ``ui/help.py`` pulls in ``tkinter`` at module
scope for its dialogs/GuideTab, which a headless server thread must not depend
on. So the display-independent surface lives here and ``ui/help.py`` re-exports
it (S36 *_core split precedent).

Public surface:
  * ``GUIDE``            — the (tag, text) content list (h1/h2/body/bullet/muted).
  * ``guide_sections()`` — GUIDE folded into ``[{heading, level, body}]`` for the
                           web Guide page (each h1/h2 starts a section; the body
                           text following it is joined).
  * ``make_backup(dest_base)``  — zip the data folder (excludes backups/, logs/).
  * ``restore_backup(zip_path)``— extract a backup zip over the data folder.
  * ``safe_extract_zip(...)``   — the zip-slip-safe extractor restore_backup uses.
  * ``backups_dir`` / ``auto_backup`` / ``_prune_backups`` — the rotating snapshot
                           helpers (headless daily path shares them).
"""
from __future__ import annotations

from pathlib import Path

import config

APP_NAME = "Zaggregate"

# The Guide is a list of (tag, text). Tags: h1/h2 (headings), body/bullet (text),
# muted (a footnote). The web Guide page folds these into sections via
# guide_sections(); the tk GuideTab maps them to Text styles.
GUIDE = [
    ("h1", "Welcome \N{WAVING HAND SIGN}"),
    ("body", "This app finds jobs that match what you're looking for, scores how "
             "well each one fits, and helps you apply faster. You never apply automatically — "
             "you stay in control and click submit yourself. There's nothing to "
             "install or configure beyond the quick setup; just follow the three "
             "steps below."),

    ("h1", "Why Zaggregate"),
    ("body", "Two things make this app different from every job site and browser "
             "tool — and both are on your side:"),
    ("h2", "Your data stays yours"),
    ("body", "A 2025 study found 90% of job platforms sell their users' data. "
             "Zaggregate is the opposite: it runs on your computer with no "
             "account and no cloud, and nothing — your resume, preferences, "
             "scores, or application tracker — is ever uploaded or sold. That "
             "privacy is something no cloud service can match, because their "
             "business depends on your data."),
    ("h2", "Assisted, never auto-apply"),
    ("body", "Bots that blast out applications succeed about 0.01% of the time — "
             "1 in 10,000 — while a tailored application lands 4–6% of the time. "
             "Recruiters are now filtering out the AI spam, so mass-applying "
             "actively hurts. Zaggregate helps you find and tailor the right "
             "jobs, but you always click submit. Fewer, better applications — on "
             "purpose."),
    ("h2", "Honest about what it sees"),
    ("body", "Job sites bury you in stale and ghost listings and never say how "
             "much of the market you're actually seeing. Zaggregate shows you a "
             "reach estimate for your area and flags when top matches may be a "
             "poor fit, so you can trust the shortlist instead of guessing."),

    ("h1", "The 3 steps"),
    ("h2", "1.  Find jobs"),
    ("body", "Open your Inbox and click “Update my Inbox now” to pull in fresh "
             "matches, or use the Search tab to search on demand. To keep your "
             "Inbox filling on its own, turn on daily updates from Tools ▸ “Turn "
             "on daily updates”. Every job gets a Score from 0 to 100 for how "
             "well it fits what you're looking for."),
    ("h2", "2.  Keep the good ones"),
    ("body", "Select a job you like and click “Track ▸ Interested”. "
             "It moves to your Apply Queue. Not interested? Click Dismiss and "
             "you'll never see it again."),
    ("h2", "3.  Apply"),
    ("body", "Open the Apply Queue, pick a job, generate a tailored resume and "
             "cover letter, open the posting, and submit. When you've applied, "
             "click “Mark Applied ▸ Next” and it jumps to the next one."),

    ("h1", "What each tab does"),
    ("h2", "Inbox — “Jobs For You”"),
    ("body", "Your daily matched feed, ranked best-first: Score is our free match "
             "grade, Fit is your AI grade. Triage it: Track the ones you like, "
             "Dismiss the rest. Tip: click a row and press T (track), D (dismiss), "
             "or O (open) to fly through it with the keyboard."),
    ("body", "New here? Your Inbox first shows a short SAMPLE of example jobs so "
             "you can see what scored matches look like. Click “Update my Inbox "
             "now” to replace it with real jobs from your sources. Turn on daily "
             "updates (Tools ▸ “Turn on daily updates”) and it then refreshes on "
             "its own each morning."),
    ("h2", "Search"),
    ("body", "Search many job boards at once for keywords in a location. Results "
             "are scored and you can Track or Dismiss each one. “+ Add "
             "Companies” lets you paste a company's careers-page link so its "
             "jobs show up in future searches."),
    ("h2", "Apply Queue"),
    ("body", "Every job you've marked Interested, best match first. This is where "
             "you make tailored documents and mark jobs applied."),
    ("h2", "Job Tracker"),
    ("body", "A record of every job you're tracking and where it stands "
             "(Interested → Applied → Interview …). Update the "
             "status as you hear back, and set follow-up reminders."),
    ("h2", "Board"),
    ("body", "The same tracked applications as a visual board — one column per "
             "stage (Interested, Applied, Interview, Offer …). Use a card's "
             "“Move ▸” button to advance a job as you hear back, or double-click "
             "a card to edit it. It's the same data as the Job Tracker tab, just "
             "laid out as a pipeline so you can see your whole search at a glance."),
    ("h2", "Resume Generator"),
    ("body", "Paste any job posting and generate a resume + cover letter tailored "
             "to it, even for a job that didn't come from this app."),

    ("h1", "The fastest setup — let your AI do it"),
    ("body", "The quickest way to set up is one round-trip with any AI chat "
             "(Claude, ChatGPT, Gemini, Copilot — a free tier is fine). One paste "
             "of the reply configures your whole search AND starts your first one:"),
    ("bullet", "1.  Click “Set up with AI” (in the Setup Wizard's first screen, "
               "or the Search tab). It copies one ready-made prompt."),
    ("bullet", "2.  Paste that prompt into your AI, and below it add your résumé "
               "plus one sentence about the work you want (e.g. “I want mechanical "
               "design roles near Cincinnati”). Send it and copy the whole reply."),
    ("bullet", "3.  Paste the reply back. From that single paste the app fills in "
               "your roles, location, salary, and seniority, adds a starter list of "
               "local employers to watch, and kicks off your first search — no keys, "
               "no accounts, nothing uploaded."),
    ("body", "That's the whole setup. Everything below — connecting extra sources, "
             "free keys, and filling the wizard out by hand — is optional and only "
             "makes an already-working app reach wider. Prefer to do it yourself? "
             "Every step is still available manually."),

    ("h1", "Set up your sources — the 10 minutes that matters most"),
    ("body", "Out of the box the app searches a set of free, no-signup job feeds "
             "plus a built-in list of company career pages. That's a real start, "
             "but the free feeds lean toward remote tech jobs. Two free sign-ups "
             "transform the app into a wide net for YOUR city and YOUR field — "
             "in our live testing, they found the local jobs the built-in feeds "
             "missed entirely. The Setup Wizard now has a “Connect your best free "
             "sources” step that walks you through it (impact-ranked, and fully "
             "skippable); you can also open it any time from Tools ▸ “Connect job "
             "sources…”. Each source there links straight to its free-key page "
             "and has a Test button to confirm your key works."),
    ("body", "If a source has no key, it simply contributes nothing — quietly. So "
             "the Inbox header shows a “N sources skipped (no key)” note after a "
             "run; click it to connect them. That line is your cue that more local "
             "jobs are one free key away."),
    ("body", "Every source below has a one-click “Get a free key” button in "
             "Tools ▸ “Connect job sources…”, so you never have to hunt for the "
             "right page — but the signup links are listed here too."),
    ("h2", "The two keys that matter most"),
    ("bullet", "•  Adzuna — a broad aggregator covering millions of postings "
               "across ~19 countries. This is the single biggest unlock for "
               "local, on-site jobs in any field: office, trades, healthcare, "
               "retail, engineering. Free key, ~5 minutes. "
               "Get a free key: developer.adzuna.com"),
    ("bullet", "•  CareerOneStop — the U.S. Department of Labor's feed of the "
               "National Labor Exchange (~3.5 million active postings a day from "
               "all 50 state job banks). The best free source for teachers, "
               "nurses, government, trades, and every other job that never shows "
               "up on tech boards. Free key, ~5 minutes. Get a free key: "
               "careeronestop.org/Developers/WebAPI/registration.aspx"),
    ("h2", "Worth adding when you want more"),
    ("bullet", "•  Jooble and Careerjet — two more free aggregators; each adds "
               "postings the others miss. Get free keys: jooble.org/api/about "
               "and careerjet.com/partners/publishers/"),
    ("bullet", "•  USAJobs — every U.S. federal opening (free key). "
               "Get a free key: developer.usajobs.gov/apirequest/"),
    ("bullet", "•  SerpApi — powers the Inbox “reach” badge, which estimates "
               "what percentage of your local market the app is actually seeing "
               "instead of guessing. A small free quota is plenty. "
               "Get a free key: serpapi.com/users/sign_up"),
    ("bullet", "•  JSearch (via RapidAPI) — pulls the big walled boards "
               "(Indeed, LinkedIn, Glassdoor) through one free key. "
               "Get a free key: rapidapi.com — search “JSearch”."),
    ("h2", "Add your local employers — the biggest quality jump"),
    ("body", "Aggregators cast wide, but the app is at its best when it watches "
             "the career pages of the employers you actually want. That's how "
             "specific hospitals, manufacturers, school systems, and firms in "
             "your area end up in your Inbox on day one of a posting. Use "
             "“+ Add Companies” (Search tab) and paste career-page links, one "
             "per line — plain links work, and “Name | link” works too. The app "
             "verifies each one live and tells you what it could add."),
    ("body", "Don't know your area's employers offhand? Let an AI build the "
             "list. Ask your AI assistant (a free tier is fine): “List the 25 "
             "largest employers of [your kind of work] in [your city], with a "
             "link to each one's careers page, one per line as Name | link.” "
             "Paste its answer straight into “+ Add Companies”. The app probes "
             "each board live before saving: verified boards are added and "
             "scraped, and anything that fails verification (a wrong or guessed "
             "link) is either discarded or, if you choose to keep it, saved "
             "marked unverified and left out of your searches until it checks "
             "out — so a bad guess can't quietly break future runs. Ten minutes "
             "of this gives you a watch-list no job board offers."),
    ("h2", "Tell the app your field"),
    ("body", "In the Setup Wizard's “What jobs are you looking for?” step, the "
             "“Your field / industry” answer does more "
             "than fill a label: it routes which categories are fetched from "
             "each source, turns field-specific feeds on or off (nursing and "
             "higher-education feeds exist today), tunes how job titles are "
             "scored, and filters the company watch-list to your industry. If "
             "your results feel off-field, re-run the wizard and sharpen that "
             "answer first."),
    ("h2", "Make it automatic"),
    ("body", "Once sources are connected, turn on Tools ▸ “Turn on daily "
             "updates” and the whole pipeline — every feed, every company page, "
             "scoring, and freshness flags — runs each morning before you sit "
             "down. The Inbox header shows when it last ran and what it found."),

    ("h1", "Working with AI — the heart of this app"),
    ("body", "This app is built to be used *with* an AI assistant, and it pays "
             "off most when you lean on one. The instant Score is a fast "
             "keyword-and-skills match. An AI goes further: it reads your goals "
             "in plain English and the full job posting, and judges fit the way "
             "a sharp friend in your field would — weighing seniority, domain, "
             "must-haves and deal-breakers a keyword score can't see. Used well, "
             "the AI is what turns a long list into a short, ranked list of jobs "
             "actually worth your time."),

    ("h2", "Score vs. Fit — what the AI adds"),
    ("body", "Score (0–100) is computed instantly on your computer for every "
             "job. Fit is the AI's grade, and its column stays blank until you "
             "ask for it. When the two disagree, trust Fit for nuance and Score "
             "for raw skills overlap — a high Score next to a low Fit usually "
             "means “matches on paper, wrong role for you.”"),

    ("h2", "The ranking round-trip (free — no account or key needed)"),
    ("bullet", "1.  Click “Ask AI to rank these”. It copies a ready-made "
               "prompt — your preferences plus the jobs — to your clipboard."),
    ("bullet", "2.  Open any AI chat (Claude, ChatGPT, Gemini, Copilot — a "
               "free tier is fine) and paste it in."),
    ("bullet", "3.  Copy the AI's whole reply."),
    ("bullet", "4.  Click “Paste AI ranking”. Each job's Fit grade lands "
               "back on the right row automatically."),
    ("bullet", "5.  Sort by Fit and work down from the top."),
    ("body", "Prefer files to the clipboard? “Export for AI” writes a "
             "spreadsheet you can hand to any tool, and “Load AI results” reads "
             "the grades back. Changed your mind? “Undo AI ranking” reverses the "
             "last import."),

    ("h2", "Let the AI write your application"),
    ("body", "In the Apply Queue and the Resume Generator, the AI drafts a "
             "resume and cover letter tailored to the exact posting, using your "
             "experience. Always read and edit what it produces before sending: "
             "the AI gets you about 90% of the way; the last 10% — truth, your "
             "voice, the specifics — is yours. You always click submit."),
    ("body", "This step talks to an AI directly, so it needs an AI API key set "
             "up. Add it in Tools ▸ “Connect your AI (API key)…”. Ranking your "
             "jobs with the round-trip above is separate and needs no key at all."),

    ("h1", "Getting the most out of AI"),
    ("body", "The AI is only as good as what you tell it about yourself. A few "
             "minutes here changes every ranking and every tailored resume from "
             "then on — it's the highest-leverage thing you can do in this app."),
    ("h2", "Feed it a rich profile"),
    ("bullet", "•  In Setup (Help → “Run Setup Wizard”) fill in the "
               "“Anything else?” box in plain English: what you love, what to "
               "avoid, your must-haves and your deal-breakers."),
    ("bullet", "•  Be specific. “Hands-on controls work, PLC + robotics, no "
               "pure-IT or helpdesk, will relocate for the right team” ranks far "
               "better than “engineer”."),
    ("bullet", "•  Keep your resume current — the AI leans on it for both "
               "ranking and tailoring."),
    ("bullet", "•  Put your AI on setup duty too: have it build your local "
               "employer watch-list (see “Add your local employers” above), "
               "suggest search keywords people in your field actually use, and "
               "critique your “Anything else?” text. Setup is where an AI "
               "assistant pays off first."),
    ("h2", "Pick a capable model, and iterate"),
    ("bullet", "•  Any chat AI works, but a stronger model gives sharper "
               "judgment. Free tiers are plenty to start."),
    ("bullet", "•  If a ranking feels off, refine your “Anything else?” text "
               "and run “Ask AI to rank these” again. The AI mirrors what you "
               "tell it — treat it as a conversation, not a one-shot."),
    ("h2", "Trust, but verify"),
    ("bullet", "•  The AI is an assistant, not the decision-maker. Skim its "
               "reasoning and overrule it whenever you know better."),
    ("bullet", "•  Privacy: nothing leaves your computer except the prompt you "
               "choose to paste into your own AI (or, in hands-off mode, the job "
               "text and your profile sent to your own API key). The app never "
               "uploads anything on its own."),
    ("muted", "Power users: Claude Code can rank jobs directly through the "
              "included MCP server — see the claude-code folder in your install. "
              "The hands-off AI features can also point at a local or "
              "alternative Anthropic-compatible endpoint (e.g. Ollama) via a "
              "base URL instead of a paid key."),

    ("h1", "Set up the browser extension — step by step (optional)"),
    ("body", "Some big boards (LinkedIn, Indeed, Glassdoor, ZipRecruiter, Dice) "
             "don't offer a search feed, and many jobs live on a company's own "
             "careers page or an applicant system like Workday, Greenhouse, or "
             "Lever. The browser extension lets you pull any job you're already "
             "looking at into your Inbox, scored like everything else. It takes "
             "about two minutes to set up, once."),
    ("bullet", "1.  In the app, open Tools ▸ “Capture jobs from my browser”. "
               "This starts a small local listener on your own computer "
               "(nothing leaves your machine). Leave the app open while you "
               "browse — the listener runs only while it's open."),
    ("bullet", "2.  Find the extension folder. It's the browser_ext folder "
               "inside your install folder (the same folder the app runs from). "
               "You don't need to open it — just note where it is; you'll point "
               "Chrome at it in step 5."),
    ("bullet", "3.  In Chrome or Edge, open the Extensions page: type "
               "chrome://extensions in the address bar and press Enter."),
    ("bullet", "4.  Turn on “Developer mode” using the switch in the top-right "
               "corner of that page."),
    ("bullet", "5.  Click “Load unpacked” (top-left), then select the browser_ext "
               "folder from step 2. The “Job Harvester” extension appears in your "
               "list."),
    ("bullet", "6.  Pin it so it's one click away: click the puzzle-piece icon "
               "in the Chrome toolbar, then the pin next to “Job Harvester”. Its "
               "icon now sits in your toolbar."),
    ("bullet", "7.  Browse jobs. As you visit the big boards, the extension "
               "quietly collects the postings it sees — the little badge count "
               "on its toolbar icon goes up as it finds jobs on the page."),
    ("bullet", "8.  Click the extension icon to open its popup. You'll see up to "
               "three buttons, depending on the page:"),
    ("bullet", "     •  “Send to Tool” — sends the jobs the extension collected "
               "on the big boards straight into your Inbox for triage."),
    ("bullet", "     •  “Capture this job” — on ANY single job posting (a company "
               "careers page, Workday, Greenhouse, Lever, anywhere), grabs the "
               "one job you're looking at, then “Send to Tool” delivers it."),
    ("bullet", "     •  “Add this employer's board to my registry” — on a "
               "company's careers page, adds that employer so future searches "
               "watch its board for new postings."),
    ("body", "“Capture this job” reads the job's title, company, location, pay, "
             "and description from the page's own structured data when the site "
             "provides it (most do — it's what puts jobs in Google) and falls "
             "back to a best-effort read of the page when it doesn't. Either way "
             "the job lands in your Inbox, scored like everything else."),
    ("muted", "The listener runs only while the app is open and only accepts jobs "
              "from the extension on your own machine. “Capture this job” only "
              "reads the one page you're on, only when you click it — it never "
              "reads other tabs or sites in the background."),

    ("h2", "Capture this job on any site"),
    ("body", "This is the extension's most useful trick, so it's worth repeating: "
             "the five big boards are handled automatically as you browse, but "
             "most jobs live somewhere else — a company's own careers page, or an "
             "applicant system like Workday, Greenhouse, or Lever. On any single "
             "job posting, click the extension's “Capture this job” button and "
             "then “Send to Tool”. It reads the job's structured data when the "
             "site provides it and falls back to a best-effort page read when it "
             "doesn't, so the job lands in your Inbox scored like everything else."),

    ("h1", "Get referred — the numbers"),
    ("body", "The single biggest lever in a job search isn't a better resume — "
             "it's a warm introduction. The evidence is lopsided: a referred "
             "candidate reaches the interview stage about 40% of the time, while "
             "a cold application lands an interview only about 2–3% of the time. "
             "Referrals are a small slice of all applications but a large slice "
             "of actual hires. You don't need many warm paths — you need a few, "
             "used well."),
    ("h2", "How to find your warm path"),
    ("body", "For a job you like, look for a connection before you apply cold. "
             "In rough order of strength: someone you already know at the "
             "company; an alumnus from your school; a former colleague who "
             "landed there; then people in the same field through associations "
             "or meetups. Zaggregate is adding a “find my path in” helper that "
             "reads your own network export and past employers and drafts the "
             "outreach for you — but the play works today: check who you know, "
             "and ask."),
    ("h2", "Outreach etiquette — the two rules that matter"),
    ("bullet", "•  Send exactly ONE follow-up. If you don't hear back after "
               "your first message, wait about a week and send a single, short, "
               "friendly nudge — then stop. Most people never follow up at all, "
               "so one gentle reminder actually helps; a second or third does "
               "the opposite and reads as pushy."),
    ("bullet", "•  Always send a thank-you. After any conversation, call, or "
               "interview, send a brief thank-you (ideally within a day). It's "
               "welcomed almost universally and half of candidates skip it — an "
               "easy way to stand out for the right reason."),
    ("body", "Keep every message short and specific: who you are, why this role, "
             "one concrete thing you'd bring, and a small, easy ask (a quick "
             "chat, or whether they'd be comfortable referring you). Warm, "
             "honest, and human beats polished and generic. Ask your own AI to "
             "draft it in your voice, then edit it so it sounds like you."),

    ("h1", "Ghost jobs & how Zaggregate shields you"),
    ("body", "A “ghost job” is a posting that isn't really being filled — it's "
             "left up to build a resume pipeline, gauge the market, or was never "
             "taken down after the role closed. They're common: solid studies "
             "put roughly one in seven public listings in this bucket, and it "
             "runs higher in some industries and for senior roles. Ghost jobs "
             "waste your time and are a top reason job searches feel like "
             "shouting into a void."),
    ("h2", "What Zaggregate does about it"),
    ("bullet", "•  Freshness flags. Zaggregate watches how long a posting has "
               "been up and whether the same role keeps getting reposted, and "
               "marks the ones that look aged or repeatedly reposted so you can "
               "spend your energy on the live ones first."),
    ("bullet", "•  It flags, it never hides. A flagged job stays in your list — "
               "Zaggregate sorts and labels, it doesn't silently drop postings, "
               "because a “stale-looking” job is sometimes still real. You decide "
               "what to skip; the app just makes the signal visible."),
    ("bullet", "•  Company memory. If a company left you on read before (an "
               "application you marked “ghosted” in your tracker), Zaggregate "
               "reminds you the next time one of their jobs shows up — so a "
               "pattern of silence informs where you spend effort."),
    ("bullet", "•  Honest reach. Instead of pretending it sees everything, the "
               "Inbox shows a reach estimate of how much of your local market "
               "the app is actually pulling, so you know when to add a source or "
               "a company rather than assuming the well is dry."),
    ("body", "The point isn't to declare any single posting fake — nobody can do "
             "that reliably from the outside. It's to hand you the freshness and "
             "history signals boards hide, so you can trust your shortlist and "
             "aim your limited time at the jobs most likely to be real."),
    ("muted", "See also “Get referred — the numbers” above: the best shield "
              "against a ghost job is a warm path that gets you a real answer "
              "from a real person."),

    ("h1", "Tips & FAQ"),
    ("h2", "Where is my information stored?"),
    ("body", "Everything stays on your computer in your data folder. Open it any "
             "time from the Help menu → “Open my data folder”. "
             "Nothing is uploaded anywhere."),
    ("h2", "How do I change what jobs I'm looking for?"),
    ("body", "Run the setup again from the Help menu → “Run Setup "
             "Wizard…” to update your roles, location, salary, and "
             "resume with simple forms — no files to edit."),
    ("h2", "Do I need to pay for anything?"),
    ("body", "No. The app works with several free job sources out of the box, "
             "and every source in Tools ▸ “Connect job sources…” has a free "
             "tier — the keys cost time (a few minutes each), not money. See "
             "“Set up your sources” above for which ones matter most."),
    ("muted", "You can reopen this Guide any time from the Help menu."),
]

# Which tags start a new section vs. contribute body text.
_HEADING_TAGS = ("h1", "h2")
_BODY_TAGS = ("body", "bullet", "muted")


def guide_sections() -> list[dict]:
    """Fold GUIDE into ``[{heading, level, body}]`` for the web Guide page.

    Each h1/h2 starts a new section; the body/bullet/muted lines that follow it
    are joined (blank-line separated) into that section's ``body``. ``level`` is
    1 for an h1, 2 for an h2, so the frontend can render the hierarchy. Any body
    text that appears BEFORE the first heading (there is none today, but be
    defensive) is emitted as a leading untitled section so no content is dropped
    (inclusion over precision)."""
    sections: list[dict] = []
    cur: dict | None = None
    for tag, text in GUIDE:
        if tag in _HEADING_TAGS:
            cur = {"heading": text, "level": 1 if tag == "h1" else 2, "body": ""}
            sections.append(cur)
        elif tag in _BODY_TAGS:
            if cur is None:  # body before any heading — keep it, untitled
                cur = {"heading": "", "level": 1, "body": ""}
                sections.append(cur)
            cur["body"] = (cur["body"] + "\n\n" + text).strip() if cur["body"] else text
    return sections


# ── data backup / restore ──────────────────────────────────────────────────────
def make_backup(dest_base: str) -> str:
    """Zip the whole data folder to dest_base (+'.zip' if absent). Returns the zip
    path. The single local root means one archive captures preferences, resume,
    tracker DB, and settings.

    WAL-safe (critical): before mirroring, run ``tracker.db.checkpoint()`` (a
    TRUNCATE-mode WAL checkpoint) so the on-disk ``tracker.db`` is complete on its
    own, and EXCLUDE the ``*-shm``/``*-wal`` SQLite runtime sidecars from the
    archive. Those sidecars are regenerable state, not durable data; shipping them
    is worse than useless — restoring a stale ``-wal`` over a fresh ``tracker.db``
    corrupts WAL state, and on Windows the live server (which services the backup
    through an open WAL connection) can't reliably snapshot them anyway. The
    checkpoint folds every committed page into the .db file, so dropping the
    sidecars loses nothing."""
    import shutil
    base = dest_base[:-4] if dest_base.lower().endswith(".zip") else dest_base
    # Fold the WAL into the main tracker.db so the zipped .db is self-contained.
    # Best-effort (checkpoint() never raises): a checkpoint hiccup must not fail a
    # backup, and the sidecar exclusion below is the belt to this suspenders.
    try:
        from tracker import db as _tracker_db
        _tracker_db.checkpoint()
    except Exception:  # noqa: BLE001 — backup must never fail on a checkpoint hiccup
        pass
    # Exclude the backups/ and logs/ trees so a backup never nests prior backups
    # (a self-including archive balloons on every run) or churns on the live log,
    # AND the SQLite -shm/-wal sidecars (regenerable runtime state — see above).
    src = Path(config.USER_DATA_DIR)

    def _ignore(dir_path, names):
        drop = [n for n in names if _is_sqlite_sidecar(n)]
        if Path(dir_path).resolve() == src.resolve():
            drop += [n for n in names if n in ("backups", "logs")]
        return drop

    import tempfile
    with tempfile.TemporaryDirectory() as staging:
        mirror = Path(staging) / "data"
        shutil.copytree(src, mirror, ignore=_ignore)
        shutil.make_archive(base, "zip", root_dir=str(mirror))
    return base + ".zip"


def _is_sqlite_sidecar(name: str) -> bool:
    """True for a SQLite WAL-mode runtime sidecar (``*-shm`` / ``*-wal``). These
    are regenerable — never durable data — so backups exclude them and restore
    ignores them inside uploaded zips + deletes any stale ones in the target."""
    n = str(name).lower()
    return n.endswith("-shm") or n.endswith("-wal")


BACKUP_DIR_NAME = "backups"


def backups_dir() -> Path:
    """The rotating auto-backup directory (<data>/backups), created on demand."""
    d = Path(config.USER_DATA_DIR) / BACKUP_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def auto_backup(keep: int = 7, when=None) -> str | None:
    """Take a dated snapshot of the data folder into <data>/backups/ and prune to
    the most recent ``keep`` archives. Reuses make_backup so the headless daily
    path and the Help menu share one backup implementation — friends' data
    survives corruption even if they never open Help. Returns the new zip path,
    or None if the data folder doesn't exist yet. Best-effort by contract; the
    daily-run caller wraps this so a backup hiccup never fails the run."""
    from datetime import datetime as _dt
    src = Path(config.USER_DATA_DIR)
    if not src.exists():
        return None
    stamp = (when or _dt.now()).strftime("%Y%m%d_%H%M%S")
    dest = backups_dir() / f"zaggregate-backup-{stamp}"
    out = make_backup(str(dest))
    _prune_backups(keep)
    return out


def _prune_backups(keep: int) -> list[str]:
    """Delete all but the newest ``keep`` dated auto-backups. Returns the removed
    filenames. Only touches files matching the auto-backup name pattern so a
    user's manually-saved zip dropped in here is never removed."""
    d = backups_dir()
    archives = sorted(d.glob("zaggregate-backup-*.zip"),
                      key=lambda p: p.name, reverse=True)
    removed = []
    for old in archives[max(keep, 0):]:
        try:
            old.unlink()
            removed.append(old.name)
        except OSError:
            pass
    return removed


class UnsafeZipEntry(ValueError):
    """A backup zip contained a member whose path would escape the extraction
    root (zip-slip: an absolute path, a ``..`` traversal, or — on extraction — a
    symlink pointing out of the tree). Raised BEFORE any file is written, so a
    hostile archive can never land a byte outside the data folder."""


def _is_within(base: Path, target: Path) -> bool:
    """True iff ``target`` (already resolved) is ``base`` or a descendant of it."""
    try:
        target.relative_to(base)
        return True
    except ValueError:
        return False


def safe_extract_zip(zip_path: str, dest: Path) -> list[str]:
    """Extract ``zip_path`` into ``dest`` with ZIP-SLIP DEFENSE, then return the
    list of member names extracted.

    Every member's final on-disk path is resolved against the (resolved) dest
    root and REQUIRED to stay inside it — a member with an absolute path
    (``/etc/x``, ``C:\\x``) or a ``..`` traversal (``../../x``) resolves outside
    the root and raises :class:`UnsafeZipEntry` before ANY file is written (the
    whole archive is validated first, so a hostile entry can't leave a partial
    write behind). Directory entries are honored; symlink members are refused
    outright (a symlink whose target escapes the tree is the second zip-slip
    vector) — a backup never legitimately contains one.

    This replaces ``ZipFile.extractall`` (which blindly trusts member names) for
    the web restore path, where the zip comes from an upload we do not control.
    """
    import zipfile

    dest = dest.resolve()
    with zipfile.ZipFile(zip_path) as z:
        infos = z.infolist()
        # Phase 1 — validate EVERY member before writing anything.
        for info in infos:
            name = info.filename
            # A symlink member (unix external-attr high bits 0xA000) is refused:
            # extracting it could plant a link out of the tree that a later member
            # then writes through. Backups never contain symlinks.
            mode = (info.external_attr >> 16) & 0o170000
            if mode == 0o120000:
                raise UnsafeZipEntry(f"symlink member refused: {name!r}")
            target = (dest / name).resolve()
            if not _is_within(dest, target) and target != dest:
                raise UnsafeZipEntry(f"path escapes backup root: {name!r}")
        # Phase 2 — all members are safe; extract each explicitly (never
        # extractall, so the validation above is the single gate). SKIP any
        # SQLite -shm/-wal sidecar members: older backups may still contain them,
        # but restoring a stale -wal over a fresh tracker.db corrupts WAL state,
        # and on Windows overwriting the live sidecars while the server holds an
        # open WAL connection is a sharing violation. The .db file is complete on
        # its own (make_backup checkpoints before zipping); the caller deletes any
        # stale on-disk sidecars after extraction so the next connection rebuilds
        # them from the restored .db.
        dest.mkdir(parents=True, exist_ok=True)
        extracted = []
        for info in infos:
            if _is_sqlite_sidecar(info.filename):
                continue
            z.extract(info, str(dest))
            extracted.append(info.filename)
    return extracted


def _release_db_before_restore() -> None:
    """Flush + FULLY RELEASE the live tracker.db lock before a restore overwrites
    the data folder. On Windows an open WAL connection (get_conn()'s ``with`` block
    manages the transaction but leaks the connection until GC) keeps tracker.db +
    its -shm/-wal sidecars LOCKED, so extracting a fresh tracker.db over them fails
    with [WinError 32]/[Errno 22]. ``release_for_restore()`` GC-closes the leaked
    connections and switches the db out of WAL (deleting + unlocking the sidecars).
    Best-effort; never raises (matches checkpoint())."""
    try:
        from tracker import db as _tracker_db
        _tracker_db.release_for_restore()
    except Exception:  # noqa: BLE001 — a restore must not fail on a release hiccup
        pass


def _purge_sqlite_sidecars(folder: Path) -> list[str]:
    """Delete any ``*-shm``/``*-wal`` sidecars directly under ``folder`` (and its
    project subfolders' tracker.db sidecars). Called AFTER a restore extracts but
    BEFORE any new connection opens, so a stale sidecar left over from the pre-
    restore db can't corrupt the freshly-restored tracker.db — the next
    get_conn() rebuilds them from the .db. Returns the removed relative names;
    best-effort per file."""
    removed: list[str] = []
    try:
        for p in folder.rglob("*"):
            if p.is_file() and _is_sqlite_sidecar(p.name):
                try:
                    p.unlink()
                    removed.append(p.name)
                except OSError:
                    pass
    except OSError:
        pass
    return removed


def restore_backup(zip_path: str) -> list[str]:
    """Extract a backup zip over the data folder (created if missing), ZIP-SLIP
    SAFE. Returns the extracted member names. Raises :class:`UnsafeZipEntry` for a
    hostile archive (nothing written). NOTE: this OVERWRITES current data — the
    web caller requires an explicit confirm and (like the tk flow) may snapshot
    the current data first.

    WAL-safe (critical): checkpoints + releases the live tracker.db connection
    state first (so the open WAL connection doesn't block overwriting the .db on
    Windows), skips any -shm/-wal members inside the uploaded zip, and deletes any
    stale on-disk sidecars after extraction — the next get_conn() rebuilds them
    from the restored .db."""
    dest = Path(config.USER_DATA_DIR)
    dest.mkdir(parents=True, exist_ok=True)
    _release_db_before_restore()
    members = safe_extract_zip(zip_path, dest)
    _purge_sqlite_sidecars(dest)
    return members
