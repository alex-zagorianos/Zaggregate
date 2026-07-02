"""In-app help: a scrollable Guide tab plus Help-menu dialogs (Quick Start,
What do the tabs do?, About) and an Open-data-folder action. Plain English,
written for someone who has never used a job-search tool before."""
import subprocess
import sys
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import config
from ui import theme

APP_NAME = "Job Search Tools"

# The Guide is a list of (tag, text). Tags map to Text styles set in GuideTab.
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
    ("h2", "The two keys that matter most"),
    ("bullet", "•  Adzuna — a broad aggregator covering millions of postings "
               "across ~19 countries. This is the single biggest unlock for "
               "local, on-site jobs in any field: office, trades, healthcare, "
               "retail, engineering. Free key, ~5 minutes."),
    ("bullet", "•  CareerOneStop — the U.S. Department of Labor's feed of the "
               "National Labor Exchange (~3.5 million active postings a day from "
               "all 50 state job banks). The best free source for teachers, "
               "nurses, government, trades, and every other job that never shows "
               "up on tech boards. Free key, ~5 minutes."),
    ("h2", "Worth adding when you want more"),
    ("bullet", "•  Jooble and Careerjet — two more free aggregators; each adds "
               "postings the others miss."),
    ("bullet", "•  USAJobs — every U.S. federal opening (free key)."),
    ("bullet", "•  SerpApi — powers the Inbox “reach” badge, which estimates "
               "what percentage of your local market the app is actually seeing "
               "instead of guessing. A small free quota is plenty."),
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

    ("h1", "Capture jobs from your browser (optional)"),
    ("body", "Some big boards (LinkedIn, Indeed, Glassdoor, ZipRecruiter, Dice) "
             "don't offer a search feed, but you can still pull jobs you're "
             "already looking at into your Inbox with the browser extension."),
    ("bullet", "1.  In the app, open Tools ▸ “Capture jobs from my browser”. "
               "It starts a small local listener (nothing leaves your computer)."),
    ("bullet", "2.  In Chrome or Edge, open the Extensions page "
               "(chrome://extensions), turn on “Developer mode” (top-right)."),
    ("bullet", "3.  Click “Load unpacked” and pick the browser_ext folder inside "
               "your install."),
    ("bullet", "4.  Browse a job board. When you see jobs you like, click the "
               "extension and choose “Send to Tool” — they land in your Inbox for "
               "triage, scored like everything else."),
    ("muted", "The listener runs only while the app is open and only accepts jobs "
              "from the extension on your own machine."),

    ("h2", "Capture this job on any site"),
    ("body", "The big boards above are handled automatically as you browse — but "
             "most jobs live somewhere else: a company's own careers page, or an "
             "applicant system like Workday, Greenhouse, or Lever. When you're "
             "looking at any single job posting, open the extension and click "
             "“Capture this job” to add the open posting to your collected list, "
             "then “Send to Tool” like usual."),
    ("body", "It reads the job's title, company, location, pay, and description "
             "straight from the page's own structured data when the site provides "
             "it (most do — it's what puts jobs in Google) and falls back to a "
             "best-effort read of the page when it doesn't. Either way, the job "
             "lands in your Inbox scored like everything else."),
    ("muted", "“Capture this job” only reads the one page you're on, only when you "
              "click it — it never reads other tabs or sites in the background."),

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


def _open_path(path: Path) -> None:
    """Open a folder in the OS file browser (Windows/macOS/Linux)."""
    try:
        if sys.platform.startswith("win"):
            subprocess.Popen(["explorer", str(path)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception:
        webbrowser.open(path.as_uri())


def open_data_folder() -> None:
    """Reveal the user's data folder (preferences, resume, database live here)."""
    folder = Path(config.USER_DATA_DIR)
    folder.mkdir(parents=True, exist_ok=True)
    _open_path(folder)


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


def _providers_configured() -> dict:
    """A redacted snapshot of which API keys/credentials are set — NAMES and a
    set/unset flag ONLY, never a value. So a bug report shows "anthropic key: set,
    adzuna: unset" without ever leaking the secret itself."""
    snapshot = {}
    try:
        from ui import settings as ui_settings
        for provider in sorted(ui_settings._KEY_FILES):
            try:
                snapshot[provider] = "set" if ui_settings.has_api_key(provider) else "unset"
            except Exception:
                snapshot[provider] = "unknown"
    except Exception:
        pass
    return snapshot


def _report_meta() -> dict:
    """The redaction-safe metadata blob for a problem report: version, platform,
    timestamp, a sync-folder warning if any, and which providers have keys set
    (values redacted). No secret values, resume text, or personal data."""
    import platform
    from datetime import datetime as _dt
    meta = {
        "app_version": config.APP_VERSION,
        "generated": _dt.now().isoformat(timespec="seconds"),
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "providers_configured": _providers_configured(),
    }
    try:
        import userdata
        warn = userdata.sync_folder_warning()
        if warn:
            meta["sync_folder_warning"] = warn
    except Exception:
        pass
    # A quick registry of known projects so support knows which last_run.json's to
    # look at. Names only — no config contents.
    try:
        import workspace
        meta["projects"] = [p.get("slug") for p in workspace.list_projects()]
    except Exception:
        pass
    return meta


def build_report_zip(dest_dir=None) -> str:
    """Assemble a timestamped diagnostic zip for "Report a problem" and return its
    path. ALLOWLIST by construction — it copies ONLY non-secret diagnostics:

      * report_meta.json  (version, platform, redacted provider flags, sync warn)
      * logs/             (the rotating app.log family)
      * last_run.json     (per project: root + each project dir)

    It deliberately never touches secrets/, experience.md, preferences, or the
    tracker DB, so a friend can send it without leaking their API keys or resume.
    Written to ``dest_dir`` (default: the data folder), so the caller can reveal
    the containing folder."""
    import json as _json
    import shutil
    import tempfile
    from datetime import datetime as _dt

    src = Path(config.USER_DATA_DIR)
    stamp = _dt.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(dest_dir) if dest_dir else src
    out_dir.mkdir(parents=True, exist_ok=True)
    base = out_dir / f"jobscout-report-{stamp}"

    with tempfile.TemporaryDirectory() as staging:
        stage = Path(staging) / "report"
        stage.mkdir(parents=True, exist_ok=True)
        # 1. redaction-safe metadata
        (stage / "report_meta.json").write_text(
            _json.dumps(_report_meta(), indent=2), encoding="utf-8")
        # 2. logs/ (rotating app.log family) — support's primary evidence.
        # CONTENT-SCRUBBED on copy: the live logger already redacts, but lines
        # written before the redaction filter existed (or by older versions)
        # may carry URL-borne credentials — never ship them verbatim.
        from applog import redact as _redact

        def _copy_scrubbed(fsrc: Path, fdst: Path):
            try:
                fdst.write_text(
                    _redact(fsrc.read_text(encoding="utf-8", errors="replace")),
                    encoding="utf-8")
            except OSError:
                pass

        logs_src = src / config.LOG_DIR_NAME
        if logs_src.is_dir():
            (stage / "logs").mkdir(parents=True, exist_ok=True)
            for f in sorted(logs_src.iterdir()):
                if f.is_file():
                    _copy_scrubbed(f, stage / "logs" / f.name)
        # 3. every last_run.json (root + per project). Machine-readable run summary
        # (scrubbed on copy, same rationale) — added by daily_run.
        seen = set()
        candidates = [src]
        try:
            import workspace
            for p in workspace.list_projects():
                try:
                    candidates.append(Path(workspace.project_dir(p.get("slug"))))
                except Exception:
                    pass
        except Exception:
            pass
        for i, proj_dir in enumerate(candidates):
            lr = Path(proj_dir) / "last_run.json"
            if lr.is_file() and lr.resolve() not in seen:
                seen.add(lr.resolve())
                # Flatten to a unique name so multiple projects don't collide.
                name = "last_run.json" if i == 0 else f"last_run.{i}.json"
                _copy_scrubbed(lr, stage / name)
        out = shutil.make_archive(str(base), "zip", root_dir=str(stage))
    return out


def report_problem(parent=None) -> None:
    """Help -> "Report a problem...": build a redaction-safe diagnostic zip
    (logs + version + last-run status, NO keys/resume) and open the folder so the
    user can attach it to a message. The menu wiring for this lives in gui.py; if
    the other builder hasn't added the Help item yet, this function is ready to
    call (recorded as a deviation for the orchestrator)."""
    try:
        out = build_report_zip()
    except Exception as e:
        messagebox.showerror("Report a problem", f"Could not build the report:\n{e}",
                             parent=parent)
        return
    messagebox.showinfo(
        "Report a problem",
        "A diagnostic report was saved to:\n" + out + "\n\n"
        "It contains app logs, your version, and the last-run summary — but NOT "
        "your API keys, resume, or job data. Attach it to your message so the "
        "problem can be diagnosed.",
        parent=parent)
    _open_path(Path(out).parent)


def restore_backup(zip_path: str) -> None:
    """Extract a backup zip over the data folder (created if missing)."""
    import zipfile
    dest = Path(config.USER_DATA_DIR)
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(str(dest))


def backup_data(parent=None) -> None:
    """Pick a destination and snapshot the data folder — so 'local-first' isn't
    'lose-everything-if-the-laptop-dies'."""
    dest = filedialog.asksaveasfilename(
        parent=parent, title="Back up my data", defaultextension=".zip",
        initialfile="jobscout-backup.zip", filetypes=[("Zip archive", "*.zip")])
    if not dest:
        return
    try:
        out = make_backup(dest)
        messagebox.showinfo(
            "Backup complete",
            f"Your data was backed up to:\n{out}\n\nNote: this archive includes any "
            "saved API key — don't share it.", parent=parent)
    except Exception as e:
        messagebox.showerror("Backup failed", str(e), parent=parent)


def restore_data(parent=None) -> None:
    """Restore the data folder from a backup zip (overwrites current data)."""
    path = filedialog.askopenfilename(
        parent=parent, title="Restore from backup",
        filetypes=[("Zip archive", "*.zip"), ("All files", "*.*")])
    if not path:
        return
    if not messagebox.askyesno(
            "Restore from backup",
            "This overwrites your current data (preferences, tracker, settings) "
            "with the backup. Continue?", parent=parent):
        return
    try:
        restore_backup(path)
        messagebox.showinfo("Restore complete",
                            "Your data was restored. Please restart Zaggregate.",
                            parent=parent)
    except Exception as e:
        messagebox.showerror("Restore failed", str(e), parent=parent)


def show_quick_start(parent=None) -> None:
    """A short, friendly three-step popup."""
    messagebox.showinfo(
        "Quick Start",
        "Getting started takes three steps:\n\n"
        "1.  FIND JOBS\n"
        "     Open your Inbox and click “Update my Inbox now”, or\n"
        "     use the Search tab to search on demand.\n"
        "     Every job is scored 0–100 for how well it fits you.\n\n"
        "2.  KEEP THE GOOD ONES\n"
        "     Select a job and click “Track ▸ Interested”.\n"
        "     It moves to your Apply Queue. Dismiss the rest.\n\n"
        "3.  APPLY\n"
        "     In Apply Queue, make a tailored resume, open the\n"
        "     posting, submit, then “Mark Applied ▸ Next”.\n\n"
        "Open the Guide tab any time for the full walkthrough.",
        parent=parent)


def show_tabs_help(parent=None) -> None:
    """Explain each tab in one popup."""
    messagebox.showinfo(
        "What do the tabs do?",
        "Inbox — your daily shortlist of fresh matches to triage.\n\n"
        "Search — search many job boards at once for keywords + location.\n\n"
        "Apply Queue — jobs you liked; make documents and mark applied.\n\n"
        "Job Tracker — every tracked job and its status, with follow-ups.\n\n"
        "Resume Generator — paste any posting to tailor a resume + cover letter.\n\n"
        "Guide — the full, plain-English walkthrough.",
        parent=parent)


def show_ai_help(parent=None) -> None:
    """A focused popup on using AI well — the app's core workflow."""
    messagebox.showinfo(
        "Getting the most from AI",
        "This app works best WITH an AI assistant.\n\n"
        "RANK YOUR JOBS  (free — no key needed)\n"
        "   1. Click “Ask AI to rank these” — copies a prompt.\n"
        "   2. Paste it into any AI chat (Claude, ChatGPT, …).\n"
        "   3. Copy the reply, then click “Paste AI ranking”.\n"
        "   4. Sort by Fit and work down from the top.\n\n"
        "GET BETTER RANKINGS\n"
        "   • In Setup, fill the “Anything else?” box with what you\n"
        "     love, what to avoid, and your deal-breakers.\n"
        "   • Be specific, keep your resume current, and re-rank if\n"
        "     a result feels off — the AI mirrors what you tell it.\n\n"
        "WRITE APPLICATIONS\n"
        "   • The Apply Queue & Resume Generator use AI to tailor a\n"
        "     resume + cover letter to each posting (this needs an\n"
        "     API key — add it in Tools ▸ Connect your AI). Always\n"
        "     review before you send — you stay in control.\n\n"
        "Ranking your jobs is free and needs no key.\n\n"
        "Open the Guide tab for the full walkthrough.",
        parent=parent)


def show_privacy(parent=None) -> None:
    """Make the local-first promise concrete: exactly what does and doesn't leave
    this computer. The strongest differentiator, shown not just asserted."""
    messagebox.showinfo(
        "Privacy — what leaves this computer",
        "Zaggregate runs on your machine. The only things ever sent out are:\n\n"
        "JOB SEARCHES\n"
        "   When you Search (or the daily update runs), Zaggregate queries public\n"
        "   job boards and company career pages — Greenhouse, Lever, Ashby,\n"
        "   Workday, Adzuna, USAJobs, The Muse, RemoteOK, Hacker News and the\n"
        "   like. It sends only your search KEYWORDS and LOCATION to look up\n"
        "   matching public postings. Never your resume, profile, or tracker.\n\n"
        "AI RANKING  (only if you use it)\n"
        "   “Ask AI to rank these” copies a prompt to YOUR clipboard. Nothing is\n"
        "   sent until YOU paste it into the AI chat you chose. If you add an\n"
        "   optional API key, the job text + a profile summary go to YOUR key's\n"
        "   provider — and nowhere else.\n\n"
        "CHECKING LINKS\n"
        "   “Clean dead links” visits each job's URL to see if it still exists.\n\n"
        "WHAT NEVER LEAVES\n"
        "   Your resume, experience, preferences, scores, notes, and application\n"
        "   tracker stay in your local data folder. No account, no cloud, no\n"
        "   analytics or telemetry. Zaggregate never applies for you.",
        parent=parent)


def show_about(parent=None) -> None:
    messagebox.showinfo(
        "About " + APP_NAME,
        f"{APP_NAME}\n"
        f"Version {config.APP_VERSION}\n\n"
        "A private, on-your-computer job-search assistant: it finds and scores "
        "jobs in your field, helps you tailor a resume, and tracks your "
        "applications.\n\n"
        "It never applies for you and never uploads your data — everything "
        "stays on this machine.",
        parent=parent)


class GuideTab(ttk.Frame):
    """A scrollable, read-only in-app guide rendered from GUIDE."""

    def __init__(self, parent, app=None):
        super().__init__(parent)
        self._app = app
        self._build()

    def _build(self):
        theme.header_bar(
            self, "Guide",
            "Everything you need to use this app — no tech skills required.")

        wrap = ttk.Frame(self)
        wrap.pack(fill="both", expand=True)
        txt = tk.Text(wrap, wrap="word", bg=theme.SURFACE, fg=theme.INK,
                      relief="flat", padx=24, pady=18, font=theme.FONT,
                      cursor="arrow", borderwidth=0, highlightthickness=0)
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=vsb.set)
        txt.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        txt.tag_configure("h1", font=("Segoe UI", 16, "bold"),
                          foreground=theme.INK, spacing1=18, spacing3=8)
        txt.tag_configure("h2", font=("Segoe UI", 12, "bold"),
                          foreground=theme.ACCENT, spacing1=12, spacing3=4)
        txt.tag_configure("body", font=theme.FONT, foreground=theme.INK,
                          spacing3=8, lmargin1=2, lmargin2=2)
        txt.tag_configure("bullet", font=theme.FONT, foreground=theme.INK,
                          spacing3=4, lmargin1=18, lmargin2=34)
        txt.tag_configure("muted", font=theme.FONT_SM, foreground=theme.MUTED,
                          spacing1=18)

        for tag, text in GUIDE:
            txt.insert("end", text + "\n", tag)
        txt.configure(state="disabled")
        self._text = txt
