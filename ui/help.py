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
    ("body", "This app finds engineering jobs for you, scores how well each one "
             "fits, and helps you apply faster. You never apply automatically — "
             "you stay in control and click submit yourself. There's nothing to "
             "install or configure beyond the quick setup; just follow the three "
             "steps below."),

    ("h1", "The 3 steps"),
    ("h2", "1.  Find jobs"),
    ("body", "Open the Search tab and click Search. Your Inbox also fills with "
             "fresh matches each day once daily updates are turned on, but on "
             "day one a Search is the fastest way to see jobs. Every job gets a "
             "Score from 0 to 100 for how well it fits what you're looking for."),
    ("h2", "2.  Keep the good ones"),
    ("body", "Select a job you like and click “Track ▸ Interested”. "
             "It moves to your Apply Queue. Not interested? Click Dismiss and "
             "you'll never see it again."),
    ("h2", "3.  Apply"),
    ("body", "Open the Apply Queue, pick a job, generate a tailored resume and "
             "cover letter, open the posting, and submit. When you've applied, "
             "click “Mark Applied ▸ Next” and it jumps to the next one."),

    ("h1", "What each tab does"),
    ("h2", "Inbox"),
    ("body", "Your daily shortlist of fresh matches. Triage it: Track the ones "
             "you like, Dismiss the rest. Tip: click a row and press T (track), "
             "D (dismiss), or O (open) to fly through it with the keyboard."),
    ("body", "New here? Your Inbox starts empty — run a Search first and it "
             "begins filling up. After that it refreshes on its own each day, "
             "once daily updates are turned on."),
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
    ("h2", "Resume Generator"),
    ("body", "Paste any job posting and generate a resume + cover letter tailored "
             "to it, even for a job that didn't come from this app."),

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
             "up (see the README for where to put it). Ranking your jobs with the "
             "round-trip above is separate and needs no key at all."),

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
              "included MCP server — see the claude-code folder in your install."),

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
    ("body", "No. The app works with several free job sources out of the box. "
             "Some optional sources need a free API key; you can add those later."),
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
    shutil.make_archive(base, "zip", root_dir=str(Path(config.USER_DATA_DIR)))
    return base + ".zip"


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
                            "Your data was restored. Please restart JobScout.",
                            parent=parent)
    except Exception as e:
        messagebox.showerror("Restore failed", str(e), parent=parent)


def show_quick_start(parent=None) -> None:
    """A short, friendly three-step popup."""
    messagebox.showinfo(
        "Quick Start",
        "Getting started takes three steps:\n\n"
        "1.  FIND JOBS\n"
        "     Open Search and click Search, or check your Inbox.\n"
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
        "     API key — see the README). Always review before you\n"
        "     send — you stay in control.\n\n"
        "Ranking your jobs is free and needs no key.\n\n"
        "Open the Guide tab for the full walkthrough.",
        parent=parent)


def show_privacy(parent=None) -> None:
    """Make the local-first promise concrete: exactly what does and doesn't leave
    this computer. The strongest differentiator, shown not just asserted."""
    messagebox.showinfo(
        "Privacy — what leaves this computer",
        "JobScout runs on your machine. The only things ever sent out are:\n\n"
        "JOB SEARCHES\n"
        "   When you Search (or the daily update runs), JobScout queries public\n"
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
        "   analytics or telemetry. JobScout never applies for you.",
        parent=parent)


def show_about(parent=None) -> None:
    messagebox.showinfo(
        "About " + APP_NAME,
        f"{APP_NAME}\n\n"
        "A private, on-your-computer job-search assistant: it finds and scores "
        "engineering jobs, helps you tailor a resume, and tracks your "
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
