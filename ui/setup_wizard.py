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


# ── connected-source detection (keys step) ──────────────────────────────────────
# Impact-ranked (Adzuna first, CareerOneStop second, then the rest) so the wizard
# keys step and its "Connected:" hint agree with the persona-measured coverage
# order. Each entry: (display label, list of required secret names). A source is
# "connected" only when EVERY one of its credentials resolves (env-then-secret),
# via the same config.resolve_secret path the source clients use.
_KEYED_SOURCES = [
    ("Adzuna", ["adzuna_app_id", "adzuna_app_key"]),
    ("CareerOneStop", ["careeronestop_user_id", "careeronestop_token"]),
    ("Jooble", ["jooble_api_key"]),
    ("Careerjet", ["careerjet_affid"]),
    ("USAJobs", ["usajobs_api_key", "usajobs_email"]),
]


def _credential_present(secret_name: str) -> bool:
    """True when a single credential resolves (env-then-secret), mirroring how the
    source clients read it. usajobs_email accepts the client's USAJOBS_USER_AGENT
    fallback so the hint matches the client's real resolution."""
    import os
    if secret_name == "usajobs_email":
        return bool(os.getenv("USAJOBS_EMAIL") or os.getenv("USAJOBS_USER_AGENT")
                    or config.read_secret("usajobs_email"))
    return bool(config.resolve_secret(secret_name.upper(), secret_name))


def connected_source_labels() -> list[str]:
    """Return the display labels of keyed sources whose credentials are all
    present, impact-ranked. Pure-ish (reads only credential state); never raises.
    Used by the wizard keys step to show progress without a live probe."""
    out: list[str] = []
    for label, secrets in _KEYED_SOURCES:
        try:
            ok = all(_credential_present(name) for name in secrets)
        except Exception:
            ok = False
        if ok:
            out.append(label)
    return out


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


# ── field presets (QW-1 / §6.2) ──────────────────────────────────────────────
# The free-text industry box silently mis-routed: a multi-word field ("mechanical
# engineering", "data analytics") tripped the P0-1 registry-tag bug and health
# synonym pollution. A validated preset picker fixes this AT THE SOURCE — each
# preset emits a CANONICAL industry token that (a) resolves to a non-generic
# industry_profile (source != 'generic', so Muse/Jobicy routing + query synonyms
# turn on) AND (b) matches the token-aware registry matcher for its own seeds.
#
# Every token here is a regression-tested contract (tests/ui/test_field_presets.py):
# each must resolve to a non-generic profile and self-match under the registry's
# _industry_tag_match. The tokens span the eight tested personas + the eng fields
# Alex uses. The last entry is an "Other" escape hatch that keeps the free-text
# box for anything unlisted (reach is never reduced — an unlisted field still
# searches broadly via the generic fallback).
_OTHER_PRESET = "Other (type your own)…"
_FIELD_PRESETS: list[tuple[str, str]] = [
    # (display label shown in the dropdown, canonical industry token emitted)
    ("Software engineering", "software engineering"),
    ("Mechanical engineering", "mechanical engineering"),
    ("Controls / automation engineering", "controls engineering"),
    ("Data analytics / data science", "data analytics"),
    ("Consulting", "consulting"),
    ("Marketing", "marketing"),
    ("Warehouse / logistics", "warehouse logistics"),
    ("Teaching / education (K-12)", "education"),
    ("Nursing / healthcare", "nursing"),
    ("Finance / accounting", "finance"),
    (_OTHER_PRESET, ""),
]
# display label -> canonical token, and the reverse (token -> label) for prefill.
_PRESET_TO_TOKEN: dict[str, str] = {label: tok for label, tok in _FIELD_PRESETS}
_PRESET_LABELS: list[str] = [label for label, _ in _FIELD_PRESETS]


def preset_tokens() -> list[str]:
    """The canonical industry tokens every non-'Other' preset emits (for tests
    and any caller that wants to enumerate the validated fields)."""
    return [tok for _label, tok in _FIELD_PRESETS if tok]


def _token_to_preset_label(industry: str) -> str:
    """The dropdown label whose canonical token matches `industry` (case/space-
    insensitive), or the 'Other' label when it's a custom/unlisted field. Blank
    industry -> '' (nothing selected). Used to pre-select the picker when the
    wizard reopens on an already-configured field."""
    ind = (industry or "").strip().lower()
    if not ind:
        return ""
    for label, tok in _FIELD_PRESETS:
        if tok and tok.lower() == ind:
            return label
    return _OTHER_PRESET


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
    # Write the contract through the shared scaffold helper (the same one
    # create_project + the AI-assisted-setup path use) so all three paths agree
    # on the preferences shape. Supplying hard/profile_md overwrites both files.
    workspace.scaffold_preferences(hard=prefs["hard"],
                                   profile_md=prefs["profile_md"])

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
            # The dropdown selection (a display label); the canonical token lands
            # in "industry" when a preset is picked, or the free-text box feeds it
            # when "Other" is chosen. Kept separate so reopening the wizard can
            # re-select the right row.
            "field_preset": tk.StringVar(),
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
            self._vars["field_preset"].set(
                _token_to_preset_label(_existing.get("industry", "")))
            self._vars["level"].set(_existing.get("level", ""))
            self._about_cache = _existing["about"]
        except Exception:
            self._about_cache = ""
        self._build_chrome()
        # The optional AI express-lane sits right after Welcome (before the manual
        # data steps) so a user with an AI can prefill everything in one paste and
        # then just review — while a user without one clicks straight past it. The
        # keys step sits AFTER roles/where/resume (value-first) and BEFORE the
        # closing step: the user has felt what they're setting up before the one
        # moment of real friction (research-onboarding-ux motivated-friction /
        # value-first sequencing). Every step here is fully skippable — the wizard
        # completes with zero AI and zero keys.
        self._steps = [self._step_welcome, self._step_ai, self._step_roles,
                       self._step_where, self._step_resume, self._step_keys,
                       self._step_keep_going]
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

    def _step_ai(self):
        # Optional BYO-AI express lane (§6.3): the user pastes a prompt into THEIR
        # own AI (with their résumé + one sentence of intent), pastes the reply
        # back, and we prefill the SUBSEQUENT steps from it. The following steps are
        # NOT skipped — the user still reviews/adjusts every prefilled field. This
        # step is entirely optional: Next advances with nothing pasted, and the
        # whole wizard remains completable with zero AI.
        from ui import ai_setup
        self._heading(
            "Have an AI assistant? Let it set you up (optional)",
            "If you use Claude, ChatGPT, Gemini, or Copilot (a free tier is fine), "
            "it can fill in the next few steps for you. Copy the prompt below, "
            "paste it into your AI along with your résumé and one sentence about "
            "the job you want, then paste its reply back here. You'll still review "
            "every field. Prefer to do it by hand? Just click Next.")
        ttk.Label(self._body, text="1.  Copy this prompt into your AI:",
                  style="H2.TLabel").pack(anchor="w", pady=(4, 2))
        pbox = ttk.Frame(self._body)
        pbox.pack(fill="x")
        self._ai_prompt = theme.text_widget(pbox, height=5, wrap="word")
        self._ai_prompt.insert("1.0", ai_setup.build_setup_prompt())
        self._ai_prompt.configure(state="disabled")
        self._ai_prompt.pack(side="left", fill="both", expand=True)
        pvsb = ttk.Scrollbar(pbox, orient="vertical", command=self._ai_prompt.yview)
        self._ai_prompt.configure(yscrollcommand=pvsb.set)
        pvsb.pack(side="right", fill="y")
        theme.btn(self._body, "Copy prompt", self._copy_ai_prompt, "ghost").pack(
            anchor="w", pady=(4, 10))
        ttk.Label(self._body, text="2.  Paste your AI's reply here:",
                  style="H2.TLabel").pack(anchor="w", pady=(0, 2))
        rbox = ttk.Frame(self._body)
        rbox.pack(fill="both", expand=True)
        self._ai_reply = theme.text_widget(rbox, height=6, wrap="word")
        self._ai_reply.pack(side="left", fill="both", expand=True)
        rvsb = ttk.Scrollbar(rbox, orient="vertical", command=self._ai_reply.yview)
        self._ai_reply.configure(yscrollcommand=rvsb.set)
        rvsb.pack(side="right", fill="y")
        theme.btn(self._body, "Fill in my answers from this", self._prefill_from_ai,
                  "accent").pack(anchor="w", pady=(6, 2))
        self._ai_status = ttk.Label(self._body, text="", style="Muted.TLabel",
                                    wraplength=560, justify="left")
        self._ai_status.pack(anchor="w", pady=(2, 0))

    def _copy_ai_prompt(self):
        """Copy the setup prompt to the clipboard (classic tk clipboard, like
        source_keys). Best-effort; never raises out of the wizard."""
        from ui import ai_setup
        try:
            self.clipboard_clear()
            self.clipboard_append(ai_setup.build_setup_prompt())
            if getattr(self, "_ai_status", None) is not None and \
                    self._ai_status.winfo_exists():
                self._ai_status.config(text="Prompt copied — paste it into your AI.")
        except Exception:
            pass

    def _prefill_from_ai(self):
        """Parse the pasted config block and prefill the wizard's answers so the
        subsequent steps open pre-populated (the user still reviews/edits them).
        On any parse/validation problem, show the actionable message and leave the
        manual path completely untouched — nothing is applied here (apply happens
        on Finish like any other run)."""
        from ui import ai_setup
        reply = getattr(self, "_ai_reply", None)
        text = reply.get("1.0", "end-1c").strip() if (
            reply is not None and reply.winfo_exists()) else ""
        if not text:
            if getattr(self, "_ai_status", None) is not None:
                self._ai_status.config(
                    text="Paste your AI's reply above first, or click Next to fill "
                         "everything in by hand.")
            return
        try:
            parsed = ai_setup.parse_setup_block(text)
        except ai_setup.SetupBlockError as e:
            messagebox.showwarning("Couldn't read that reply", str(e), parent=self)
            if getattr(self, "_ai_status", None) is not None:
                self._ai_status.config(text=str(e))
            return
        answers = parsed["answers"]
        extras = parsed["extras"]
        # Prefill the wizard vars from the parsed answers. roles/keywords are a
        # comma-joined string in the wizard; the industry token drives the field
        # preset picker (falling back to the free-text 'Other' box for a custom
        # token); level maps 1:1 to the wizard's level labels.
        self._vars["roles"].set(", ".join(answers.get("roles", [])))
        self._vars["location"].set(answers.get("location", ""))
        self._vars["remote_ok"].set(bool(answers.get("remote_ok", True)))
        salary = answers.get("salary_min")
        self._vars["salary_min"].set(str(salary) if salary else "")
        industry = answers.get("industry", "")
        self._vars["industry"].set(industry)
        self._vars["field_preset"].set(_token_to_preset_label(industry))
        self._vars["level"].set(answers.get("level", ""))
        self._about_cache = answers.get("about", "") or self._about_cache
        # Report what landed so the user knows the next steps are pre-filled.
        titles = ", ".join(answers.get("roles", [])[:4])
        where = "Remote" if extras.get("remote_only") else (answers.get("location")
                                                            or "—")
        if getattr(self, "_ai_status", None) is not None:
            self._ai_status.config(
                text=f"Filled in — Field: {extras.get('field_token') or 'general'} "
                     f"· Titles: {titles or '—'} · Where: {where}. Click Next to "
                     "review and adjust each step.")

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
        # Field PICKER (validated presets) + career level — tune enumeration + the
        # ranking rubric to any field, not just engineering. A preset emits a
        # canonical token that routes sources & rankings correctly (QW-1 / §6.2);
        # "Other" reveals a free-text box for an unlisted field. Both blank =
        # today's behavior.
        fl = ttk.Frame(self._body)
        fl.pack(fill="x", pady=(12, 0))
        ttk.Label(fl, text="Your field / industry (optional)").grid(
            row=0, column=0, sticky="w")
        ttk.Label(fl, text="Career level (optional)").grid(
            row=0, column=1, sticky="w", padx=(12, 0))
        self._field_cb = ttk.Combobox(
            fl, textvariable=self._vars["field_preset"], values=_PRESET_LABELS,
            state="readonly")
        self._field_cb.grid(row=1, column=0, sticky="ew", pady=(2, 0))
        self._field_cb.bind("<<ComboboxSelected>>",
                            lambda _e: self._on_field_preset())
        ttk.Combobox(fl, textvariable=self._vars["level"], values=list(_LEVELS),
                     state="readonly", width=16).grid(
            row=1, column=1, sticky="w", padx=(12, 0), pady=(2, 0))
        fl.columnconfigure(0, weight=1)
        # Free-text box, only shown for "Other". Packed/forgotten by _sync_field_ui.
        self._field_other_frame = ttk.Frame(self._body)
        ttk.Label(self._field_other_frame,
                  text="Type your field (e.g. legal, hospitality, HR):",
                  style="Muted.TLabel").pack(anchor="w")
        ttk.Entry(self._field_other_frame,
                  textvariable=self._vars["industry"]).pack(fill="x", pady=(2, 0))
        # The one-line "this is load-bearing" note the research + plan call for.
        self._field_note = ttk.Label(
            self._body,
            text="This drives which job sources you search and how jobs are "
                 "ranked for you — picking your field turns on the right local "
                 "sources and tunes scoring. Leave blank and we search broadly.",
            style="Muted.TLabel", wraplength=560, justify="left")
        self._field_note.pack(anchor="w", pady=(4, 0))
        self._sync_field_ui()
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

    def _on_field_preset(self):
        """A dropdown selection: map the chosen preset to its canonical industry
        token (so routing is always correct) and show/hide the free-text 'Other'
        box. The canonical token is written straight into the 'industry' var; the
        'Other' path leaves 'industry' driven by the free-text entry."""
        label = self._vars["field_preset"].get()
        if label and label != _OTHER_PRESET:
            self._vars["industry"].set(_PRESET_TO_TOKEN.get(label, ""))
        elif label == _OTHER_PRESET:
            # Switching TO Other: don't clobber a token the user might re-pick, but
            # if the current industry is a known preset token, clear it so the box
            # starts empty for a genuinely custom field.
            if _token_to_preset_label(self._vars["industry"].get()) != _OTHER_PRESET:
                self._vars["industry"].set("")
        self._sync_field_ui()

    def _sync_field_ui(self):
        """Show the free-text field box only when 'Other' is selected; keep it
        packed just above the explanatory note. Guarded so it is a no-op if the
        step's widgets aren't currently built."""
        frame = getattr(self, "_field_other_frame", None)
        note = getattr(self, "_field_note", None)
        if frame is None or not frame.winfo_exists():
            return
        show = self._vars["field_preset"].get() == _OTHER_PRESET
        if show:
            if note is not None and note.winfo_exists():
                frame.pack(fill="x", pady=(6, 0), before=note)
            else:
                frame.pack(fill="x", pady=(6, 0))
        else:
            frame.pack_forget()

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

    def _step_keys(self):
        self._heading(
            "Connect your best free sources (optional)",
            "The app already searches free no-signup feeds, but those lean toward "
            "remote tech jobs. Two free keys unlock local, on-site jobs in YOUR "
            "field — in our tests these keys supplied most local results. You can "
            "skip this and add keys any time from Tools \N{RIGHTWARDS ARROW} "
            "Connect job sources.")
        # Impact-ranked pitch (Adzuna first, CareerOneStop second, then the rest)
        # — the same order the persona tests measured as the coverage unlock.
        for name, why in [
            ("1.  Adzuna",
             "the single biggest unlock for local, on-site jobs in any field "
             "(office, trades, healthcare, retail, engineering). ~5 min, free."),
            ("2.  CareerOneStop",
             "the U.S. Dept. of Labor feed — the best free source for teachers, "
             "nurses, government, and trades that never show up on tech boards. "
             "~5 min, free."),
            ("3.  Jooble · Careerjet · USAJobs",
             "more free aggregators (and every U.S. federal opening) — each adds "
             "postings the others miss."),
        ]:
            row = ttk.Frame(self._body)
            row.pack(fill="x", pady=3)
            ttk.Label(row, text=name, style="H2.TLabel").pack(anchor="w")
            ttk.Label(row, text=why, style="Muted.TLabel", wraplength=560,
                      justify="left").pack(anchor="w")
        btn_row = ttk.Frame(self._body)
        btn_row.pack(fill="x", pady=(14, 4))
        theme.btn(btn_row, "Connect job sources\N{HORIZONTAL ELLIPSIS}",
                  self._open_source_keys, "accent").pack(side="left")
        self._keys_status = ttk.Label(
            self._body, text="", style="Muted.TLabel", wraplength=560,
            justify="left")
        self._keys_status.pack(anchor="w", pady=(2, 0))
        self._refresh_keys_status()

    def _open_source_keys(self):
        """Open the EXISTING 'Connect job sources' dialog (ui.source_keys) — the
        one with per-source live Test buttons + free-key deep links. Reuse, not
        new machinery. Guarded so a headless/degraded build never breaks the
        wizard; on return, refresh the connected-sources hint."""
        try:
            from ui import source_keys
            win = source_keys.open_dialog(self)
            if win is not None:
                # Modal-ish: wait for the dialog so the hint reflects new keys.
                self.wait_window(win)
        except Exception:
            pass
        self._refresh_keys_status()

    def _refresh_keys_status(self):
        """Show which of the free keys are now present so the user sees progress
        without leaving the wizard. Best-effort; never raises."""
        lbl = getattr(self, "_keys_status", None)
        if lbl is None or not lbl.winfo_exists():
            return
        try:
            connected = connected_source_labels()
        except Exception:
            connected = []
        if connected:
            lbl.config(text="Connected: " + ", ".join(connected))
        else:
            lbl.config(text="No keys connected yet — that's fine, you can add "
                            "them later.")

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
                # Jump back to the roles step (index is not hard-coded, so it stays
                # correct as steps are added/reordered — e.g. the AI express-lane).
                try:
                    self._step = self._steps.index(self._step_roles)
                except ValueError:
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
