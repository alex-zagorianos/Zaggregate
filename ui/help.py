"""In-app help: a scrollable Guide tab plus Help-menu dialogs (Quick Start,
What do the tabs do?, About) and an Open-data-folder action. Plain English,
written for someone who has never used a job-search tool before."""
import subprocess
import sys
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

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

    ("h1", "How the AI ranking works"),
    ("body", "Two numbers, two purposes. The Score (0–100) is the app's own "
             "instant match, shown for every job. The Fit grade is a separate, "
             "smarter opinion from an AI — its column stays blank until you ask "
             "for it. Here's how to fill it in:"),
    ("body", "The Score is calculated instantly on your computer. For that "
             "second opinion you can ask an AI (like Claude or ChatGPT) to rank "
             "your jobs:"),
    ("bullet", "•  Click “Ask AI to rank these” — it copies a "
               "ready-made prompt to your clipboard."),
    ("bullet", "•  Paste it into the AI chat, then copy the AI's reply."),
    ("bullet", "•  Click “Paste AI ranking” and the Fit grades land "
               "back on the right jobs."),
    ("body", "Prefer files? “Export for AI” writes a spreadsheet you can "
             "hand to any tool, and “Load AI results” reads the scores "
             "back. “Undo AI ranking” reverses the last import."),

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
