"""First-run Setup wizard: a friendly, multi-step form so a non-technical user
configures the app (what jobs, where, salary, resume) without ever editing a
JSON or Markdown file by hand.

The pure `build_preferences()` turns the collected answers into the on-disk
contract (preferences.json hard filters + preferences.md profile); `apply()`
writes that contract plus experience.md and seeds the search config; `maybe_run()`
shows the wizard only until the user finishes or skips (tracked by an .onboarded
marker in the data folder)."""
import json
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import config
import workspace
from ui import theme

_MARKER_NAME = ".onboarded"


# ── onboarding marker ───────────────────────────────────────────────────────────
def _marker_path() -> Path:
    return Path(config.USER_DATA_DIR) / _MARKER_NAME


def is_onboarded() -> bool:
    return _marker_path().exists()


def mark_onboarded() -> None:
    p = _marker_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("ok\n", encoding="utf-8")
    except OSError:
        pass


# ── pure transform: answers -> on-disk preferences contract ─────────────────────
def build_preferences(answers: dict) -> dict:
    """Map wizard answers into {"hard": dict, "profile_md": str}. Pure (no I/O)
    so it is easy to test. Mirrors the shape preferences.load() expects.

    answers keys: roles (list[str]), location (str), remote_ok (bool),
    salary_min (int|None), about (str)."""
    roles = [r.strip() for r in answers.get("roles", []) if r and r.strip()]
    location = (answers.get("location") or "").strip()
    remote_ok = bool(answers.get("remote_ok", True))
    salary_min = answers.get("salary_min")
    about = (answers.get("about") or "").strip()

    hard = {
        "salary_min": salary_min if salary_min else None,
        "locations": [location] if location else [],
        "remote_ok": remote_ok,
        "work_auth": "",
        "dealbreakers": [],
        "seniority_exclude": [],
        "target_roles": list(roles),
    }

    lines = [
        "# My Job Preferences",
        "",
        "> Describe the roles you want in plain English. The AI reads this to rank",
        "> and sort jobs to your taste. Be specific about what you love and avoid.",
        "",
    ]
    if roles:
        lines += ["Target roles / keywords I care about: " + ", ".join(roles), ""]
    if location:
        where = location + (" (remote is fine too)" if remote_ok else "")
        lines += [f"Where I want to work: {where}", ""]
    if salary_min:
        lines += [f"Minimum salary I'll consider: ${salary_min:,}", ""]
    if about:
        lines += ["## About me / what I'm looking for", "", about, ""]
    return {"hard": hard, "profile_md": "\n".join(lines)}


def _search_config(answers: dict, existing: dict | None = None) -> dict:
    """Seed the search-tab config (keywords/location/salary) from answers so the
    Search tab pre-fills. Preserves any existing keys."""
    cfg = dict(existing or {})
    roles = [r.strip() for r in answers.get("roles", []) if r and r.strip()]
    if roles:
        cfg["keywords"] = roles
    if (answers.get("location") or "").strip():
        cfg["location"] = answers["location"].strip()
    if answers.get("salary_min"):
        cfg["salary_min"] = answers["salary_min"]
    return cfg


def apply(answers: dict) -> None:
    """Write the preferences contract, the search config, and (if the user
    supplied resume text) experience.md, then mark onboarding complete."""
    prefs = build_preferences(answers)
    pj, pm = workspace.preferences_paths()   # beside this project's config/resume
    pj.parent.mkdir(parents=True, exist_ok=True)
    pj.write_text(json.dumps(prefs["hard"], indent=2), encoding="utf-8")
    pm.write_text(prefs["profile_md"], encoding="utf-8")

    workspace.save_config(_search_config(answers, workspace.load_config()))

    resume = (answers.get("resume_text") or "").strip()
    if resume:
        exp = workspace.experience_file()
        exp.parent.mkdir(parents=True, exist_ok=True)
        exp.write_text(resume, encoding="utf-8")

    mark_onboarded()


# ── the wizard window ───────────────────────────────────────────────────────────
class SetupWizard(tk.Toplevel):
    """A modal, 4-step first-run setup. Calls on_finish(applied: bool) when the
    user finishes (True) or skips/closes (False)."""

    def __init__(self, parent, on_finish=None):
        super().__init__(parent)
        self.title("Welcome — Quick Setup")
        self.on_finish = on_finish
        self._finished = False
        self.geometry("640x560")
        self.minsize(560, 520)
        self.configure(bg=theme.WINDOW)
        self.transient(parent)
        self.grab_set()

        self._step = 0
        self._vars = {
            "roles": tk.StringVar(),
            "location": tk.StringVar(),
            "remote_ok": tk.BooleanVar(value=True),
            "salary_min": tk.StringVar(),
        }
        self._build_chrome()
        self._steps = [self._step_welcome, self._step_roles,
                       self._step_where, self._step_resume]
        self._render()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # chrome: a title area, a swappable body, and a button bar
    def _build_chrome(self):
        theme.header_bar(self, "Quick Setup",
                         "A few quick questions and you're ready to go.")
        self._progress = ttk.Label(self, text="", style="Muted.TLabel")
        self._progress.pack(anchor="w", padx=18, pady=(8, 0))

        self._body = ttk.Frame(self)
        self._body.pack(fill="both", expand=True, padx=18, pady=10)

        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=18, pady=(0, 14))
        self._skip_btn = theme.btn(bar, "Skip for now", self._on_skip, "ghost")
        self._skip_btn.pack(side="left")
        self._next_btn = theme.btn(bar, "Next  \N{RIGHTWARDS ARROW}", self._next, "accent")
        self._next_btn.pack(side="right")
        self._back_btn = theme.btn(bar, "\N{LEFTWARDS ARROW}  Back", self._back, "ghost")
        self._back_btn.pack(side="right", padx=6)

    def _render(self):
        for w in self._body.winfo_children():
            w.destroy()
        # Welcome is an intro, not a data step; count only the data steps so the
        # progress label matches what the user actually fills in.
        if self._step == 0:
            self._progress.config(text="")
        else:
            self._progress.config(
                text=f"Step {self._step} of {len(self._steps) - 1}")
        self._steps[self._step]()
        self._back_btn.config(state=("normal" if self._step else "disabled"))
        last = self._step == len(self._steps) - 1
        self._next_btn.config(text=("Finish \N{HEAVY CHECK MARK}" if last
                                    else "Next  \N{RIGHTWARDS ARROW}"))

    # ── steps ───────────────────────────────────────────────────────────────────
    def _heading(self, text, sub=None):
        ttk.Label(self._body, text=text, style="H2.TLabel").pack(anchor="w")
        if sub:
            ttk.Label(self._body, text=sub, style="Muted.TLabel",
                      wraplength=560, justify="left").pack(anchor="w", pady=(2, 12))

    def _step_welcome(self):
        self._heading(
            "Welcome \N{WAVING HAND SIGN}",
            "This app finds engineering jobs for you, scores how well each fits, "
            "and helps you apply faster. You always click submit yourself — it "
            "never applies automatically, and your information stays on this "
            "computer.")
        for n, t in [
            ("1.  Find jobs", "Search job boards or check your daily Inbox."),
            ("2.  Keep the good ones", "Track the jobs you like; dismiss the rest."),
            ("3.  Apply", "Make a tailored resume, submit, and mark it applied."),
        ]:
            row = ttk.Frame(self._body)
            row.pack(fill="x", pady=4)
            ttk.Label(row, text=n, style="H2.TLabel").pack(anchor="w")
            ttk.Label(row, text=t, style="Muted.TLabel").pack(anchor="w")
        ttk.Label(self._body,
                  text="Let's set up your profile. It takes about a minute.",
                  wraplength=560, justify="left").pack(anchor="w", pady=(16, 0))

    def _step_roles(self):
        self._heading(
            "What jobs are you looking for?",
            "List the job titles or keywords you want, separated by commas. "
            "These drive every search.")
        ttk.Entry(self._body, textvariable=self._vars["roles"]).pack(
            fill="x", pady=(0, 6))
        ttk.Label(self._body,
                  text="Examples:  controls engineer, mechatronics engineer, "
                       "automation engineer",
                  style="Muted.TLabel", wraplength=560,
                  justify="left").pack(anchor="w")
        ttk.Label(self._body, text="Anything else the AI should know? (optional)",
                  style="H2.TLabel").pack(anchor="w", pady=(18, 2))
        ttk.Label(self._body,
                  text="What you love, what to avoid, must-haves — in plain "
                       "English. This is what makes the ranking personal to you.",
                  style="Muted.TLabel", wraplength=560,
                  justify="left").pack(anchor="w", pady=(0, 6))
        box = ttk.Frame(self._body)
        box.pack(fill="both", expand=True)
        self._about = tk.Text(box, wrap="word", height=6, relief="solid", bd=1,
                              font=theme.FONT, bg=theme.SURFACE, fg=theme.INK,
                              padx=8, pady=6, highlightthickness=1,
                              highlightcolor=theme.ACCENT,
                              highlightbackground=theme.BORDER)
        vsb = ttk.Scrollbar(box, orient="vertical", command=self._about.yview)
        self._about.configure(yscrollcommand=vsb.set)
        self._about.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        if getattr(self, "_about_cache", ""):
            self._about.insert("1.0", self._about_cache)

    def _step_where(self):
        self._heading(
            "Where do you want to work?",
            "A city or region. Leave salary blank if you'd rather not filter by it.")
        ttk.Label(self._body, text="Location").pack(anchor="w")
        ttk.Entry(self._body, textvariable=self._vars["location"]).pack(
            fill="x", pady=(0, 4))
        ttk.Label(self._body, text="Examples:  Cincinnati, OH   ·   Remote",
                  style="Muted.TLabel").pack(anchor="w", pady=(0, 10))
        ttk.Checkbutton(self._body, text="Remote jobs are fine too",
                        variable=self._vars["remote_ok"]).pack(anchor="w", pady=4)
        ttk.Label(self._body, text="Minimum salary (optional)").pack(
            anchor="w", pady=(10, 0))
        row = ttk.Frame(self._body)
        row.pack(anchor="w", pady=(0, 4))
        ttk.Label(row, text="$").pack(side="left")
        ttk.Entry(row, textvariable=self._vars["salary_min"], width=14).pack(side="left")
        ttk.Label(self._body, text="Example:  90000  (numbers only, no commas)",
                  style="Muted.TLabel").pack(anchor="w")

    def _step_resume(self):
        self._heading(
            "Your resume (optional)",
            "Paste your resume text below, or load it from a file. The app uses "
            "it to score jobs and tailor documents. You can skip this and add it "
            "later.")
        row = ttk.Frame(self._body)
        row.pack(fill="x", pady=(0, 6))
        theme.btn(row, "Load from file…", self._load_resume_file, "ghost").pack(
            side="left")
        ttk.Label(row, text="  .txt, .md, or paste below",
                  style="Muted.TLabel").pack(side="left")
        box = ttk.Frame(self._body)
        box.pack(fill="both", expand=True)
        self._resume = tk.Text(box, wrap="word", height=12, relief="solid",
                               bd=1, font=theme.FONT, bg=theme.SURFACE,
                               fg=theme.INK, padx=8, pady=6,
                               highlightthickness=1, highlightcolor=theme.ACCENT,
                               highlightbackground=theme.BORDER)
        vsb = ttk.Scrollbar(box, orient="vertical", command=self._resume.yview)
        self._resume.configure(yscrollcommand=vsb.set)
        self._resume.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        if getattr(self, "_resume_cache", ""):
            self._resume.insert("1.0", self._resume_cache)

    def _load_resume_file(self):
        path = filedialog.askopenfilename(
            title="Choose your resume",
            filetypes=[("Text or Markdown", "*.txt *.md"), ("All files", "*.*")],
            parent=self)
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            messagebox.showerror("Could not read file", str(e), parent=self)
            return
        self._resume.delete("1.0", "end")
        self._resume.insert("1.0", text)

    # ── navigation ──────────────────────────────────────────────────────────────
    def _cache_step(self):
        # Preserve free-text boxes across step changes (they're recreated each
        # render). Guard on winfo_exists so a destroyed widget keeps its cache.
        about = getattr(self, "_about", None)
        if about is not None and about.winfo_exists():
            self._about_cache = about.get("1.0", "end-1c")
        resume = getattr(self, "_resume", None)
        if resume is not None and resume.winfo_exists():
            self._resume_cache = resume.get("1.0", "end-1c")

    def _back(self):
        self._cache_step()
        if self._step:
            self._step -= 1
            self._render()

    def _next(self):
        self._cache_step()
        if self._step < len(self._steps) - 1:
            self._step += 1
            self._render()
        else:
            self._finish()

    def _collect(self) -> dict:
        roles = [r.strip() for r in self._vars["roles"].get().split(",")
                 if r.strip()]
        raw_salary = "".join(ch for ch in self._vars["salary_min"].get()
                             if ch.isdigit())
        salary = int(raw_salary) if raw_salary else None
        return {
            "roles": roles,
            "location": self._vars["location"].get().strip(),
            "remote_ok": bool(self._vars["remote_ok"].get()),
            "salary_min": salary,
            "resume_text": getattr(self, "_resume_cache", ""),
            "about": getattr(self, "_about_cache", ""),
        }

    def _finish(self):
        answers = self._collect()
        if not answers["roles"]:
            if not messagebox.askyesno(
                    "No roles yet",
                    "You haven't entered any job titles, so searches won't have "
                    "much to go on. Finish setup anyway?", parent=self):
                self._step = 1
                self._render()
                return
        try:
            apply(answers)
        except Exception as e:  # never trap the user in a broken wizard
            messagebox.showerror("Setup error", str(e), parent=self)
            return
        self._finished = True
        self._close(applied=True)

    def _on_skip(self):
        # Skipping leaves the app unconfigured — confirm so it isn't an accident.
        if not messagebox.askyesno(
                "Skip setup?",
                "Searches and job scoring won't be personalized until you run "
                "setup. You can do it any time from Help \N{RIGHTWARDS ARROW} "
                "Run Setup Wizard. Skip for now?", parent=self):
            return
        mark_onboarded()  # don't nag again; they can re-run from Help
        self._close(applied=False)

    def _on_close(self):
        # Closing the window counts as skipping (and marks onboarded).
        mark_onboarded()
        self._close(applied=False)

    def _close(self, applied: bool):
        cb = self.on_finish
        self.grab_release()
        self.destroy()
        if cb:
            cb(applied)


def maybe_run(root, on_finish=None) -> bool:
    """Show the wizard only if the user hasn't onboarded yet. Returns True if it
    was shown. `on_finish(applied: bool)` fires when it closes."""
    if is_onboarded():
        return False
    SetupWizard(root, on_finish=on_finish)
    return True


def run(root, on_finish=None) -> None:
    """Force the wizard (Help menu → Run Setup Wizard), ignoring the marker."""
    SetupWizard(root, on_finish=on_finish)
