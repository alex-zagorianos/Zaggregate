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

APP_NAME = "Job Search Tools"

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
    tracker DB, and settings."""
    import shutil
    base = dest_base[:-4] if dest_base.lower().endswith(".zip") else dest_base
    # Exclude the backups/ and logs/ trees so a backup never nests prior backups
    # (a self-including archive balloons on every run) or churns on the live log.
    src = Path(config.USER_DATA_DIR)

    def _ignore(dir_path, names):
        if Path(dir_path).resolve() == src.resolve():
            return [n for n in names if n in ("backups", "logs")]
        return []

    import tempfile
    with tempfile.TemporaryDirectory() as staging:
        mirror = Path(staging) / "data"
        shutil.copytree(src, mirror, ignore=_ignore)
        shutil.make_archive(base, "zip", root_dir=str(mirror))
    return base + ".zip"


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
    dest = backups_dir() / f"jobscout-backup-{stamp}"
    out = make_backup(str(dest))
    _prune_backups(keep)
    return out


def _prune_backups(keep: int) -> list[str]:
    """Delete all but the newest ``keep`` dated auto-backups. Returns the removed
    filenames. Only touches files matching the auto-backup name pattern so a
    user's manually-saved zip dropped in here is never removed."""
    d = backups_dir()
    archives = sorted(d.glob("jobscout-backup-*.zip"),
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
        # extractall, so the validation above is the single gate).
        dest.mkdir(parents=True, exist_ok=True)
        for info in infos:
            z.extract(info, str(dest))
    return [i.filename for i in infos]


def restore_backup(zip_path: str) -> list[str]:
    """Extract a backup zip over the data folder (created if missing), ZIP-SLIP
    SAFE. Returns the extracted member names. Raises :class:`UnsafeZipEntry` for a
    hostile archive (nothing written). NOTE: this OVERWRITES current data — the
    web caller requires an explicit confirm and (like the tk flow) may snapshot
    the current data first."""
    dest = Path(config.USER_DATA_DIR)
    dest.mkdir(parents=True, exist_ok=True)
    return safe_extract_zip(zip_path, dest)
