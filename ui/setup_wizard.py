"""First-run Setup wizard: a friendly, multi-step form so a non-technical user
configures the app (what jobs, where, salary, resume) without ever editing a
JSON or Markdown file by hand.

The pure `build_preferences()` turns the collected answers into the on-disk
contract (preferences.json hard filters + preferences.md profile); `apply()`
writes that contract plus experience.md and seeds the search config; `maybe_run()`
shows the wizard only until the user finishes or skips (tracked by an .onboarded
marker in the data folder).

The entire on-disk CONTRACT + pure transforms live in the Tk-free
``ui.setup_wizard_core`` so the web onboarding API and the AI-setup path can reuse
them without importing tkinter (S35b/S36 *_core split precedent). This module
re-exports every public name from the core and adds ONLY the Tk ``SetupWizard``
window on top — existing callers/tests that reach ``setup_wizard.build_preferences``
/ ``setup_wizard.parse_salary_input`` / ``setup_wizard.mark_onboarded`` (etc.) keep
working byte-for-byte."""
import json
import re
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import config
import workspace
from ui import theme

# Re-export the Tk-free core surface so every historical patch/call target on
# this module (setup_wizard.build_preferences, .parse_salary_input, .apply,
# .is_onboarded, .mark_onboarded, ._search_config, ._FIELD_PRESETS, ...) keeps
# resolving here. The SetupWizard class below uses these as module globals.
from ui.setup_wizard_core import (  # noqa: F401  (re-exported public surface)
    _MARKER_NAME,
    _EMAIL_RE, _PHONE_RE, _FULLTIME_HOURS_PER_YEAR, _HOURLY_INPUT_RE,
    _derive_industry, parse_salary_input, _alias_table, _normalize_heading_line,
    _looks_like_heading, _looks_like_contact, structure_resume_text,
    _KEYED_SOURCES, _credential_present, connected_source_labels,
    _marker_path, is_onboarded, mark_onboarded,
    build_preferences, prefill_from_existing,
    _OTHER_PRESET, _FIELD_PRESETS, _PRESET_TO_TOKEN, _PRESET_LABELS,
    preset_tokens, _token_to_preset_label, _LEVELS, _level_to_config,
    _config_to_level, _search_config, apply,
)


# The pure transforms (presets, level mapping, search-config apply) live in
# ui/setup_wizard_core.py and are imported above; this module keeps only the
# tkinter wizard window.


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
                  text="Let's set up your profile. It takes about a minute, and "
                       "every step is optional — you can skip anything now and "
                       "change it later from Help ▸ “Run Setup Wizard”.",
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
        # Point users at the browser-extension walkthrough — the way to pull jobs
        # from LinkedIn/Indeed and any careers page. The full numbered steps live
        # in the Guide ("Set up the browser extension — step by step").
        ttk.Label(
            self._body,
            text="Tip: to pull jobs straight from LinkedIn, Indeed, or any "
                 "company's careers page, set up the free browser extension. The "
                 "Guide has a short, numbered walkthrough — open it any time from "
                 "Help ▸ “Open the Guide”, section “Set up the browser extension”.",
            style="Muted.TLabel", wraplength=560, justify="left").pack(
                anchor="w", pady=(14, 0))

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
