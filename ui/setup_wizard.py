"""First-run Setup wizard: a friendly, multi-step form so a non-technical user
configures the app (what jobs, where, salary, resume) without ever editing a
JSON or Markdown file by hand.

The pure `build_preferences()` turns the collected answers into the on-disk
contract (preferences.json hard filters + preferences.md profile); `apply()`
writes that contract plus experience.md and seeds the search config; `maybe_run()`
shows the wizard only until the user finishes or skips (tracked by an .onboarded
marker in the data folder)."""
import json
import re
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import config
import workspace
from ui import theme

_MARKER_NAME = ".onboarded"


# -- resume auto-structuring (P0 #1) ---------------------------------------------
# The wizard invites a PLAIN-TEXT resume paste, but resume/experience_parser
# raises on any resume without '## ' markdown headings -- so a pasted nurse/welder/
# teacher resume crashed every subsequent search. structure_resume_text() turns
# a raw paste into a headed document the parser accepts, WITHOUT losing any text:
#   - already has '## '/'# ' headings  -> returned unchanged.
#   - has recognizable ALL-CAPS / alias heading lines (EXPERIENCE, EDUCATION,
#     LICENSES, SKILLS, ...) -> those lines are promoted to '## ' headings.
#   - otherwise -> leading contact-looking lines go under '## CONTACT' and the
#     rest under '## WORK EXPERIENCE'.
# Pure and side-effect-free so it is trivially unit-testable.

# Lines that look like contact info (email / phone / a short name or address at
# the very top), grouped under CONTACT when we have to wrap a bare paste.
_EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
_PHONE_RE = re.compile(r"(?:\+?\d[\d\-\.\s()]{7,}\d)")


# -- salary input parsing (P3 hourly-wage support) -------------------------------
# Annual-equivalent of a full-time hourly wage (40 h/wk x 52 wk). Matches
# match.scorer's 2080 annualization so a wizard-entered "18/hr" floor and a
# description-parsed hourly rate line up.
_FULLTIME_HOURS_PER_YEAR = 2080
_HOURLY_INPUT_RE = re.compile(r"/\s*h|\bhr\b|\bhour", re.I)


def _derive_industry(industry: str, roles: list) -> str:
    """When the optional industry box is blank, resolve the user's roles to an
    O*NET-SOC occupation and return a short field label IFF it lands on a
    NON-engineering occupation. Returns '' (keep today's behavior byte-identical)
    when the industry is already set, no role resolves, or the resolved role is
    engineering/tech-like. The first role that confidently resolves wins."""
    if (industry or "").strip():
        return ""
    try:
        import industry_profile
    except Exception:
        return ""
    for role in roles:
        role = (role or "").strip()
        if not role:
            continue
        try:
            soc = industry_profile.resolve_soc(role)  # None for eng-like/unresolved
        except Exception:
            soc = None
        if soc and soc.get("title"):
            return str(soc["title"]).strip()
    return ""


def parse_salary_input(text: str) -> int | None:
    """Parse a free-text salary floor into ANNUAL dollars, accepting both annual
    ('90000', '$90,000', '90k') and hourly ('18/hr', '$18.50 per hour', '25 hr')
    inputs. Hourly values are annualized at 2080 h/yr. Returns None for blank or
    unparseable input (never raises)."""
    s = (text or "").strip().lower()
    if not s:
        return None
    hourly = bool(_HOURLY_INPUT_RE.search(s))
    # Pull the first numeric token (allow a decimal point and 'k' suffix).
    m = re.search(r"(\d[\d,]*\.?\d*)\s*(k)?", s)
    if not m:
        return None
    num = m.group(1).replace(",", "")
    try:
        val = float(num)
    except ValueError:
        return None
    if m.group(2):            # explicit 'k' suffix -> thousands
        val *= 1000
    if hourly:
        val *= _FULLTIME_HOURS_PER_YEAR
    # A small bare number with no 'k' and no hourly marker (e.g. "18") is almost
    # certainly an hourly wage a user typed without the unit; annualize it so it
    # isn't stored as an $18 floor. 1000 is the cutoff (nobody means $18/yr).
    elif val < 1000:
        val *= _FULLTIME_HOURS_PER_YEAR
    val = int(round(val))
    return val if val > 0 else None


def _alias_table() -> dict:
    """The parser's normalized-heading -> canonical-heading map, reused so the
    wizard promotes exactly the headings the parser will recognize."""
    from resume.experience_parser import _HEADING_ALIASES, EXPERIENCE_SECTIONS
    table = dict(_HEADING_ALIASES)
    # The canonical names themselves are valid headings too.
    for canon in EXPERIENCE_SECTIONS.values():
        table.setdefault(canon, canon)
    return table


def _normalize_heading_line(line: str) -> str:
    return re.sub(r"\s+", " ", line.strip().upper()).rstrip(":").strip()


def _looks_like_heading(line: str, table: dict) -> str | None:
    """Return the canonical heading a bare line maps to, or None. A line is a
    heading candidate only if it is short and has no sentence punctuation (so a
    real experience sentence that happens to contain a keyword isn't promoted)."""
    raw = line.strip()
    if not raw or len(raw) > 40:
        return None
    if any(ch in raw for ch in ".!?,;:") and not raw.rstrip().endswith(":"):
        return None
    norm = _normalize_heading_line(raw)
    return table.get(norm)


def _looks_like_contact(line: str) -> bool:
    return bool(_EMAIL_RE.search(line) or _PHONE_RE.search(line))


def structure_resume_text(text: str) -> tuple[str, bool]:
    """Return (structured_markdown, was_restructured).

    was_restructured is True only when we actually inserted headings, so the
    wizard can show a gentle notice. Never raises; never drops text."""
    raw = (text or "").strip()
    if not raw:
        return raw, False
    # Already structured (any markdown H1/H2) -> leave it be.
    if re.search(r"(?m)^#{1,2}\s+\S", raw):
        return raw, False

    table = _alias_table()
    lines = raw.splitlines()

    # Path A: promote recognizable ALL-CAPS/alias heading lines in place.
    promoted: list[str] = []
    n_headings = 0
    for line in lines:
        canon = _looks_like_heading(line, table)
        if canon is not None:
            promoted.append(f"## {canon}")
            n_headings += 1
        else:
            promoted.append(line)
    if n_headings:
        return "\n".join(promoted).strip(), True

    # Path B: no recognizable headings at all -- wrap. Leading contact-looking
    # lines (name/email/phone/address at the top) go under CONTACT; the body
    # under WORK EXPERIENCE so the parser + scorer both have real content.
    contact: list[str] = []
    body_start = 0
    for i, line in enumerate(lines[:6]):  # only scan the top of the document
        if not line.strip():
            body_start = i + 1
            continue
        if _looks_like_contact(line) or (i == 0 and len(line.strip()) <= 60):
            contact.append(line.strip())
            body_start = i + 1
        else:
            break
    body = "\n".join(lines[body_start:]).strip()
    out: list[str] = []
    if contact:
        out.append("## CONTACT")
        out.append("")
        out.extend(f"- {c}" for c in contact)
        out.append("")
    out.append("## WORK EXPERIENCE")
    out.append("")
    out.append(body if body else raw)
    return "\n".join(out).strip(), True


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


def prefill_from_existing(prefs: dict | None = None, cfg: dict | None = None) -> dict:
    """Return {roles, location, remote_ok, salary_min, about} loaded from the
    current preferences + search config for wizard pre-population.  Pure: when
    prefs and cfg are supplied no I/O happens, making this easy to unit-test.
    Reads from disk when either argument is None."""
    if prefs is None:
        try:
            import preferences as _prefs_mod
            prefs = _prefs_mod.load()
        except Exception:
            prefs = {}
    if cfg is None:
        try:
            cfg = workspace.load_config()
        except Exception:
            cfg = {}
    hard = (prefs or {}).get("hard", {})

    # Roles: prefer hard.target_roles, fall back to cfg.keywords
    roles_list = hard.get("target_roles") or cfg.get("keywords") or []
    roles_str = ", ".join(roles_list)

    # Location: prefer hard.locations[0], fall back to cfg.location
    locations = hard.get("locations") or []
    location = (locations[0] if locations else None) or cfg.get("location") or ""

    remote_ok = bool(hard.get("remote_ok", True))

    salary_min = hard.get("salary_min")

    # About: extract the section after "## About me" in the profile_md
    md = (prefs or {}).get("profile_md", "")
    about = ""
    _marker = "## About me / what I'm looking for"
    if _marker in md:
        about = md.split(_marker, 1)[1].strip()

    return {
        "roles": roles_str,
        "location": str(location),
        "remote_ok": remote_ok,
        "salary_min": str(salary_min) if salary_min else "",
        "about": about,
        "industry": str(cfg.get("industry") or ""),
        "level": _config_to_level(cfg or {}),
    }


# Career-level → rubric config (match.rubric reads these off the search config).
# Only emitted when a level is chosen, so an unset level leaves defaults intact.
_LEVELS = ("", "Entry", "Mid", "Senior", "Manager/Exec")


def _level_to_config(level: str) -> dict:
    lvl = (level or "").strip().lower()
    if lvl in ("entry", "entry-level", "junior"):
        return {"seniority_target": "entry", "allow_intern": True, "years_cap": 3}
    if lvl in ("mid", "mid-level"):
        return {"seniority_target": "mid", "years_cap": 8}
    if lvl == "senior":
        return {"seniority_target": "senior", "years_cap": 12}
    if lvl in ("manager/exec", "manager", "exec", "executive", "management"):
        return {"seniority_target": "senior-exec", "allow_management": True, "years_cap": 25}
    return {}


def _config_to_level(cfg: dict) -> str:
    if cfg.get("allow_management"):
        return "Manager/Exec"
    return {"entry": "Entry", "mid": "Mid", "senior": "Senior",
            "senior-exec": "Manager/Exec"}.get(
        (cfg.get("seniority_target") or "").lower(), "")


def _search_config(answers: dict, existing: dict | None = None) -> dict:
    """Seed the search-tab config (keywords/location/salary/industry/level) from
    answers so the Search tab pre-fills. Preserves any existing keys."""
    cfg = dict(existing or {})
    roles = [r.strip() for r in answers.get("roles", []) if r and r.strip()]
    if roles:
        cfg["keywords"] = roles
    if (answers.get("location") or "").strip():
        cfg["location"] = answers["location"].strip()
    if answers.get("salary_min"):
        cfg["salary_min"] = answers["salary_min"]
    if (answers.get("industry") or "").strip():
        cfg["industry"] = answers["industry"].strip()
    if (answers.get("level") or "").strip():
        cfg.update(_level_to_config(answers["level"]))  # rubric-read keys
    return cfg


def apply(answers: dict) -> dict:
    """Write the preferences contract, the search config, and (if the user
    supplied resume text) experience.md, then mark onboarding complete.

    Returns a small info dict {"resume_restructured": bool} so the caller can
    show a gentle notice when a plain-text paste had to be auto-structured. A
    pasted resume is ALWAYS run through structure_resume_text() first so it can
    never crash later scoring/generation (P0 #1)."""
    prefs = build_preferences(answers)
    pj, pm = workspace.preferences_paths()   # beside this project's config/resume
    pj.parent.mkdir(parents=True, exist_ok=True)
    pj.write_text(json.dumps(prefs["hard"], indent=2), encoding="utf-8")
    pm.write_text(prefs["profile_md"], encoding="utf-8")

    workspace.save_config(_search_config(answers, workspace.load_config()))

    info = {"resume_restructured": False}
    resume = (answers.get("resume_text") or "").strip()
    if resume:
        structured, restructured = structure_resume_text(resume)
        info["resume_restructured"] = restructured
        exp = workspace.experience_file()
        exp.parent.mkdir(parents=True, exist_ok=True)
        exp.write_text(structured, encoding="utf-8")

    mark_onboarded()
    return info


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
            "industry": tk.StringVar(),
            "level": tk.StringVar(),
            # Closing "Keep jobs coming" step (default ON — the whole point of the
            # app is a self-refilling inbox). Read by the caller after finish.
            "daily_updates": tk.BooleanVar(value=True),
            "build_list": tk.BooleanVar(value=True),
        }
        # Pre-populate from existing preferences/config so re-running the wizard
        # to edit one field does not blank-overwrite the rest.
        try:
            _existing = prefill_from_existing()
            self._vars["roles"].set(_existing["roles"])
            self._vars["location"].set(_existing["location"])
            self._vars["remote_ok"].set(_existing["remote_ok"])
            self._vars["salary_min"].set(_existing["salary_min"])
            self._vars["industry"].set(_existing.get("industry", ""))
            self._vars["level"].set(_existing.get("level", ""))
            self._about_cache = _existing["about"]
        except Exception:
            self._about_cache = ""
        self._build_chrome()
        self._steps = [self._step_welcome, self._step_roles,
                       self._step_where, self._step_resume, self._step_keep_going]
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
            "This app finds jobs that match what you're looking for, scores how "
            "well each one fits, and helps you apply faster. You always click "
            "submit yourself — it never applies automatically, and your "
            "information stays on this computer.")
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
                  text="Examples:  registered nurse, controls engineer, staff "
                       "accountant, HVAC technician, UX designer",
                  style="Muted.TLabel", wraplength=560,
                  justify="left").pack(anchor="w")
        ttk.Label(self._body,
                  text="Tip: use broad field terms (e.g. “clinical "
                       "informatics”) rather than a full senior title (e.g. "
                       "“VP of Clinical Informatics”) — narrow "
                       "titles return almost nothing. Set seniority with Career "
                       "level below, not in the search terms.",
                  style="Muted.TLabel", wraplength=560,
                  justify="left").pack(anchor="w", pady=(4, 0))
        # Optional field + career level — tune enumeration + the ranking rubric to
        # any field, not just engineering. Both blank = today's behavior.
        fl = ttk.Frame(self._body)
        fl.pack(fill="x", pady=(12, 0))
        ttk.Label(fl, text="Your field / industry (optional)").grid(
            row=0, column=0, sticky="w")
        ttk.Label(fl, text="Career level (optional)").grid(
            row=0, column=1, sticky="w", padx=(12, 0))
        ttk.Entry(fl, textvariable=self._vars["industry"]).grid(
            row=1, column=0, sticky="ew", pady=(2, 0))
        ttk.Combobox(fl, textvariable=self._vars["level"], values=list(_LEVELS),
                     state="readonly", width=16).grid(
            row=1, column=1, sticky="w", padx=(12, 0), pady=(2, 0))
        fl.columnconfigure(0, weight=1)
        ttk.Label(self._body,
                  text="Field examples:  health informatics · nursing · finance · "
                       "controls engineering",
                  style="Muted.TLabel", wraplength=560,
                  justify="left").pack(anchor="w", pady=(4, 0))
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
                              highlightbackground=theme.BORDER,
                              insertbackground=theme.INK)
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
        ttk.Label(self._body,
                  text="Examples:  90000  (per year)   or   18/hr  (per hour, "
                       "we convert it for you)",
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
                               highlightbackground=theme.BORDER,
                               insertbackground=theme.INK)
        vsb = ttk.Scrollbar(box, orient="vertical", command=self._resume.yview)
        self._resume.configure(yscrollcommand=vsb.set)
        self._resume.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        if getattr(self, "_resume_cache", ""):
            self._resume.insert("1.0", self._resume_cache)

    def _step_keep_going(self):
        self._heading(
            "Keep jobs coming",
            "Two quick options so your Inbox stays full. Both are optional and "
            "free — you can change them any time.")
        ttk.Checkbutton(
            self._body,
            text="Update my inbox automatically every morning",
            variable=self._vars["daily_updates"]).pack(anchor="w", pady=(6, 2))
        ttk.Label(
            self._body,
            text="Adds a small Windows task (just for you — no administrator "
                 "needed) that searches your sources each morning and adds fresh "
                 "matches to your Inbox.",
            style="Muted.TLabel", wraplength=560, justify="left").pack(
                anchor="w", padx=(24, 0), pady=(0, 10))
        ttk.Checkbutton(
            self._body,
            text="Build my employer list now",
            variable=self._vars["build_list"]).pack(anchor="w", pady=(6, 2))
        ttk.Label(
            self._body,
            text="Opens a one-click tool that finds employers in your field and "
                 "area so “careers” searches cover them. Runs after setup.",
            style="Muted.TLabel", wraplength=560, justify="left").pack(
                anchor="w", padx=(24, 0), pady=(0, 6))

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
        # Accept annual ('90000', '$90k') OR hourly ('18/hr') input; store annual.
        salary = parse_salary_input(self._vars["salary_min"].get())
        return {
            "roles": roles,
            "location": self._vars["location"].get().strip(),
            "remote_ok": bool(self._vars["remote_ok"].get()),
            "salary_min": salary,
            "industry": self._vars["industry"].get().strip(),
            "level": self._vars["level"].get().strip(),
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
        # Derive the field from the roles when the optional industry box is blank,
        # so a non-engineering user isn't silently routed as an engineer.
        detected = _derive_industry(answers.get("industry", ""), answers["roles"])
        if detected:
            answers["industry"] = detected
            self._vars["industry"].set(detected)  # reflect it if the wizard reopens
        try:
            info = apply(answers)
        except Exception as e:  # never trap the user in a broken wizard
            messagebox.showerror("Setup error", str(e), parent=self)
            return
        if detected:
            messagebox.showinfo(
                "Field detected",
                f"Field detected: {detected} - edit if wrong (Help -> Run Setup "
                "Wizard). This tunes company discovery and job ranking to your "
                "field instead of engineering.", parent=self)
        if info.get("resume_restructured"):
            messagebox.showinfo(
                "Resume saved",
                "We tidied your pasted resume into sections (Contact, Work "
                "Experience, and any headings we recognized) so the app can read "
                "it. You can refine it any time.", parent=self)
        # Closing-step "Keep jobs coming" choices ride back to the caller (gui),
        # which owns the daily-updates registration + Build-My-List dialog.
        self._actions = {
            "daily_updates": bool(self._vars["daily_updates"].get()),
            "build_list": bool(self._vars["build_list"].get()),
            "industry": answers.get("industry", ""),
            "location": answers.get("location", ""),
        }
        self._maybe_offer_discovery(answers.get("industry", ""))
        self._finished = True
        self._close(applied=True)

    def _maybe_offer_discovery(self, industry: str) -> None:
        """A non-engineering first run starts with an empty, eng-only starter
        registry. Point the user at the free company-discovery paths so they don't
        get an empty Inbox (plan 1D). Best-effort; never blocks finishing."""
        industry = (industry or "").strip()
        if not industry:
            return
        try:
            from scrape.company_registry import has_industry
            if has_industry(industry):
                return
            messagebox.showinfo(
                "Build your employer list",
                f"There aren't any {industry} employers in the starter list yet. "
                "Open Search \N{RIGHTWARDS ARROW} \N{SPARKLES} Build My List to "
                "auto-build one for your field (it harvests your Inbox, AI-suggests "
                "employers, and verifies live jobs) — or use + Add Companies to "
                "paste a few careers-page links. Both are free.", parent=self)
        except Exception:
            pass

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
        actions = getattr(self, "_actions", None)
        self.grab_release()
        self.destroy()
        if not cb:
            return
        # Back-compat: call cb(applied) for a 1-arg callback, cb(applied, actions)
        # for a 2-arg one (so the caller can act on the "Keep jobs coming" step).
        try:
            import inspect
            params = [p for p in inspect.signature(cb).parameters.values()
                      if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
            takes_two = len(params) >= 2
        except (TypeError, ValueError):
            takes_two = False
        if takes_two:
            cb(applied, actions)
        else:
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
