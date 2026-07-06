"""
gui.py — Local desktop GUI replacing the Flask browser apps.
Run: py gui.py

Tabs:
  Inbox            — scored matches from the daily headless run (daily_run.py)
  Search           — multi-source search with match scoring
  Apply Queue      — ranked 'interested' jobs; docs + mark-applied workflow
  Job Tracker      — application pipeline (the :5001 Flask tracker it
                     replaced was deleted in the S38 debt sweep)
  Resume Generator — tailored resume/cover generation (ex resume/app.py :5000)
"""
import io
import json
import queue
import re
import sys
import sqlite3
import threading
import subprocess
import webbrowser
import contextlib
from datetime import date
from pathlib import Path
from urllib.parse import urlparse
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog

sys.path.insert(0, str(Path(__file__).resolve().parent))

import applog
import ranker as _ranker_mod
import workspace
from tracker import service as tracker_service
from tracker.db import (
    init_db, add_job, get_all, get_counts, count_followups_due, followups_due,
    stale_applications, update_job, delete_job, get_job,
    archive_job, unarchive_job,
    add_status_note, status_timeline,
    add_interview_round, list_interview_rounds, delete_interview_round,
    quick_check, rolling_backup, export_applications_csv,
    seen_urls, normalize_url, dismiss_url,
    inbox_all, inbox_count, inbox_track, inbox_dismiss, inbox_set_fit,
    inbox_delete_urls,
    add_contact, list_contacts, delete_contact,
    STATUSES, STATUS_LABELS,
)
from config import DEFAULT_LOCATION, OUTPUT_DIR
from geo.filter import location_visible, LOCATION_MODES, DEFAULT_LOCATION_MODE
from claude_bridge import (
    BridgeParseError, to_clipboard,
    build_fit_prompt, parse_fit_response, profile_summary,
)
from match import ghost as ghostmod
from match import comp as compmod
from match import ats_hint as atshintmod
from match.scorer import score_breakdown, extract_skill_terms
from tracker import analytics as analyticsmod
from scrape.inbox_health import prune_inbox
from ui import theme
from ui import chrome
from ui import help as uihelp
from ui import setup_wizard
from ui import settings as uisettings
from ui.kanban import KanbanTab

# ── COMPAT RE-EXPORT (S35 gui-split): shared GUI infra moved to ui/common.py.
# Re-imported here so existing `gui.set_status` / `gui.db_guard` / etc. call
# sites and test monkeypatch targets keep working unchanged.
from ui.common import (
    safe_url, _call_prompt_via_api, _scored_status, _LineSink,
    _DATE_RE, db_guard, copy_or_warn, set_status, _sync_palette_aliases,
)
from ui import common as _ui_common


def run_daily_ingest(slug, *, on_line=None) -> int:
    """Run the daily search->score->inbox pipeline for ONE project, pinned so a
    concurrent second run or a GUI project switch can't redirect its inbox/output
    writes mid-run (the S27 corruption class). Pins BEFORE any db write and unpins
    in `finally`; never mutates the global active pointer. `on_line` (optional) is
    a line sink fed the pipeline's stdout. Returns daily_run's exit code (0 = ok).

    Shared by the in-GUI 'Update my Inbox now' button and the frozen exe's
    `--daily` headless mode so both take the identical, S27-safe path.

    S36 web migration: the implementation moved to the Tk-free ``daily_run_core``
    module so the web backend can run the same ingest without importing
    gui/tkinter. This stays a thin re-export wrapper — existing test monkeypatch
    targets (``gui.run_daily_ingest``, and swapping ``daily_run`` in ``sys.modules``
    then calling this) are unchanged, and the pin/argv/sink/finally path is
    identical (it lives in ``daily_run_core.run_ingest`` now)."""
    import daily_run_core
    return daily_run_core.run_ingest(slug, on_line=on_line)


# ── COMPAT RE-EXPORT (S35 gui-split): JobDialog/_RoundDialog moved to
# ui/job_dialog.py, PasteDialog moved to ui/paste_dialog.py.
from ui.job_dialog import JobDialog, _RoundDialog, _ROUND_KINDS
from ui.paste_dialog import PasteDialog


# ── COMPAT RE-EXPORT (S35 gui-split): TrackerTab moved to ui/tab_tracker.py.
from ui.tab_tracker import TrackerTab


# ── COMPAT RE-EXPORT (S35 gui-split): ResumeTab moved to ui/tab_resume.py.
from ui.tab_resume import ResumeTab


# ── COMPAT RE-EXPORT (S35 gui-split): InboxTab + its module helpers moved
# to ui/tab_inbox.py.
from ui.tab_inbox import (
    InboxTab,
    _row_new_batch, _row_browse, _browse_summary, _latest_new_batch, _is_new_row,
)


# ── COMPAT RE-EXPORT (S35 gui-split): TopPicksTab moved to ui/tab_toppicks.py.
from ui.tab_toppicks import TopPicksTab


# ── COMPAT RE-EXPORT (S35 gui-split): AiSetupDialog moved to ui/ai_setup_dialog.py.
from ui.ai_setup_dialog import AiSetupDialog


# ── COMPAT RE-EXPORT (S35 gui-split): AddCompaniesDialog + BuildCompanyListDialog
# + partition_add_entries moved to ui/companies_dialogs.py.
from ui.companies_dialogs import (
    AddCompaniesDialog, BuildCompanyListDialog, partition_add_entries,
)


# ── COMPAT RE-EXPORT (S35 gui-split): SearchTab moved to ui/tab_search.py.
from ui.tab_search import SearchTab


# ── COMPAT RE-EXPORT (S36 gui-split): ApplyQueueTab moved to ui/tab_queue.py.
from ui.tab_queue import ApplyQueueTab


# ── App root ──────────────────────────────────────────────────────────────────
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        import userdata
        userdata.bootstrap()  # first-run: seed the data folder + runtime dirs
        theme.apply_theme(self, mode=uisettings.get_theme())   # light/dark, before any widgets
        _sync_palette_aliases()
        self.geometry("1280x780")
        self.minsize(980, 620)

        # Theme the native Windows title bar (caption) to the app palette, and
        # install the class hook so every Toplevel dialog gets the same treatment.
        # Hard no-op off Windows / on unsupported builds / headless.
        try:
            from ui import titlebar
            titlebar.install(self)
        except Exception:
            pass

        # Global Tk callback exception handler: in a windowed .exe an unguarded
        # error inside a button/after callback otherwise vanishes silently (dead
        # button, no feedback). Log the traceback and show the user something.
        self.report_callback_exception = self._on_tk_exception

        self._build_menu()

        self._proj_var = None
        self._build_topbar()           # branded hero, above the project bar
        self._build_projectbar()       # shown only when projects exist

        self._nb = ttk.Notebook(self)
        self._nb.pack(fill="both", expand=True)
        self._build_tabs()

        # Tracker/queue contents change from other tabs; refresh on focus.
        self._nb.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        self._update_title()
        self.bind_all("<Control-k>", self._open_palette)   # command palette

        # Open where the work is: inbox if the daily run found anything.
        if inbox_count() == 0:
            self._nb.select(self._search)

        # Data safety (D1 P5): integrity check + rolling daily backup, once per
        # launch. Both are fully guarded and never crash the app.
        self.after(60, self._data_safety_check)

        # Proactive due nudge: a dismissible banner (NOT a modal) when there's
        # follow-up / no-response work waiting, linking to the Due dialog.
        self.after(200, self._maybe_show_due_banner)

        # First launch (no .onboarded marker): walk the user through Setup.
        self.after(120, lambda: setup_wizard.maybe_run(self, on_finish=self._after_setup))

    # ── menu bar ────────────────────────────────────────────────────────────────
    def _build_menu(self):
        menubar = theme.style_menu(tk.Menu(self))

        filem = theme.style_menu(tk.Menu(menubar, tearoff=0))
        filem.add_command(label="New Project…", command=self._new_project)
        filem.add_command(label="Open my data folder",
                          command=uihelp.open_data_folder)
        filem.add_separator()
        filem.add_command(label="Back up my data…",
                          command=lambda: uihelp.backup_data(self))
        filem.add_command(label="Restore from backup…",
                          command=lambda: uihelp.restore_data(self))
        filem.add_command(label="Export applications (CSV)…",
                          command=self._export_applications_csv)
        filem.add_separator()
        filem.add_command(label="Exit", command=self.destroy)
        menubar.add_cascade(label="File", menu=filem)

        viewm = theme.style_menu(tk.Menu(menubar, tearoff=0))
        self._dark_var = tk.BooleanVar(value=(theme.current_mode() == "dark"))
        viewm.add_checkbutton(label="Dark mode", variable=self._dark_var,
                              command=self._toggle_dark)
        menubar.add_cascade(label="View", menu=viewm)

        menubar.add_cascade(label="Tools", menu=self._make_tools_menu(menubar))

        helpm = theme.style_menu(tk.Menu(menubar, tearoff=0))
        helpm.add_command(label="Quick Start",
                          command=lambda: uihelp.show_quick_start(self))
        helpm.add_command(label="Open the Guide", command=self._open_guide)
        helpm.add_command(label="What do the tabs do?",
                          command=lambda: uihelp.show_tabs_help(self))
        helpm.add_command(label="Getting the most from AI",
                          command=lambda: uihelp.show_ai_help(self))
        helpm.add_separator()
        helpm.add_command(label="Run Setup Wizard…",
                          command=lambda: setup_wizard.run(self, on_finish=self._after_setup))
        helpm.add_command(label="Open my data folder",
                          command=uihelp.open_data_folder)
        helpm.add_separator()
        helpm.add_command(label="Privacy: what leaves this computer",
                          command=lambda: uihelp.show_privacy(self))
        helpm.add_command(label="Report a problem…",
                          command=lambda: uihelp.report_problem(self))
        helpm.add_command(label="About", command=lambda: uihelp.show_about(self))
        menubar.add_cascade(label="Help", menu=helpm)

        self.config(menu=menubar)

    def _make_tools_menu(self, parent):
        """Build the Tools menu once so BOTH the menubar cascade and the branded
        top-bar 'Tools ▾' button post the identical actions (surface
        Tools as a top button while keeping the menubar entry for muscle memory).
        Kept on self so the topbar can reuse it and a theme rebuild re-creates it."""
        toolsm = theme.style_menu(tk.Menu(parent, tearoff=0))
        toolsm.add_command(label="Due — follow-ups & deadlines…",
                           command=self._show_due)
        toolsm.add_command(label="Application funnel…", command=self._show_funnel)
        toolsm.add_command(label="Contacts / referrals…", command=self._show_contacts)
        toolsm.add_separator()
        toolsm.add_command(label="Turn on daily updates…",
                           command=self._show_daily_updates)
        toolsm.add_command(label="Capture jobs from my browser…",
                           command=self._toggle_browser_capture)
        toolsm.add_separator()
        toolsm.add_command(label="Set up with your AI…",
                           command=self._show_ai_setup)
        toolsm.add_command(label="Connect your AI (API key)…",
                           command=self._show_settings)
        toolsm.add_command(label="Connect job sources…",
                           command=self._show_source_keys)
        toolsm.add_command(label="Seed my area (find local employers)…",
                           command=self._show_seed_area)
        toolsm.add_separator()
        toolsm.add_command(label="Enable stealth fetching (downloads browser)…",
                           command=self._enable_stealth)
        self._tools_menu = toolsm
        return toolsm

    def _open_guide(self):
        if getattr(self, "_guide", None) is not None:
            self._nb.select(self._guide)

    def _open_palette(self, _event=None):
        from ui import palette
        palette.open_palette(self)

    def _after_setup(self, applied: bool, actions: dict | None = None):
        """Called when the Setup wizard closes. On apply, refresh tabs so the
        seeded preferences/config show up, then honor the closing 'Keep jobs
        coming' step (register daily updates / open Build-My-List). Either way
        land on the Guide so a brand-new user (including one who skipped) has an
        obvious next step instead of an empty Search tab."""
        if applied:
            self._rebuild_tabs()
            actions = actions or {}
            # Closing-step: register daily updates if the user opted in.
            if actions.get("daily_updates"):
                self._register_daily_updates()
            # Closing-step: open Build-My-List unconditionally when opted in, so a
            # fresh user's 'careers' searches have employers to scrape. Block on
            # it (wait_window) so the "Update your Inbox now?" prompt below is
            # offered AFTER the user finishes Build-My-List, not stacked on top of
            # its still-open modal (both grab_set() otherwise — a two-modal
            # collision). BuildCompanyListDialog does its work on threads, so
            # waiting only holds until the user closes it.
            if actions.get("build_list"):
                try:
                    dlg = BuildCompanyListDialog(
                        self, default_industry=actions.get("industry", ""),
                        default_metro=actions.get("location", ""))
                    self.wait_window(dlg)
                except Exception:
                    pass
            # Forced first action (§6.5): the terminal action is "Update my Inbox
            # now" — the SAME S29 in-GUI pipeline the Inbox button + scheduled task
            # run — so a fresh user's very first result is a populated, scored
            # Inbox (not a Search tab they have to drive). We land on the Inbox and
            # kick the existing update-now machinery; its own progress/empty-state
            # takes over from there. No second run mechanism is introduced.
            if messagebox.askyesno(
                    "You're all set",
                    "Your preferences are saved.\n\nUpdate your Inbox now to pull "
                    "in your first real jobs?", parent=self):
                self._nb.select(self._inbox)
                self.update_idletasks()
                try:
                    self._inbox._update_inbox_now()   # threaded; existing machinery
                except Exception:
                    pass
                return
        self._open_guide()

    # ── Tools dialogs ───────────────────────────────────────────────────────────
    def _enable_stealth(self):
        """One-time browser download so the Scrapling JS/anti-bot fetch fallback
        can run. The exe ships lean (no bundled browser); this enables it on
        demand. Runs off the UI thread."""
        from scrape import stealth_fetch
        if not stealth_fetch.available():
            messagebox.showinfo(
                "Stealth fetching",
                "The stealth fetch library isn't available in this build.")
            return
        if stealth_fetch.browsers_ready():
            messagebox.showinfo("Stealth fetching",
                                "Stealth fetching is already enabled.")
            return
        if not messagebox.askyesno(
                "Enable stealth fetching",
                "This downloads a browser (about 300 MB, one-time) so the app can "
                "read JavaScript-heavy or anti-bot career pages. It can take a few "
                "minutes. Continue?"):
            return

        def _work():
            ok, msg = stealth_fetch.install()
            self.after(0, lambda: (messagebox.showinfo if ok else messagebox.showwarning)(
                "Stealth fetching", msg))

        threading.Thread(target=_work, daemon=True).start()
        messagebox.showinfo(
            "Stealth fetching",
            "Downloading in the background — you can keep using the app. "
            "You'll get a message when it's ready.")

    def _show_settings(self):
        """Optional 'Connect your AI' key box. The free clipboard bridge stays the
        default — a key only powers auto-rank + AI resume/cover generation."""
        dlg = tk.Toplevel(self)
        dlg.title("Settings — Connect your AI")
        dlg.transient(self)
        dlg.configure(bg=theme.WINDOW)
        dlg.resizable(False, False)
        tk.Label(dlg, text="Connect your AI (optional)", bg=theme.WINDOW,
                 fg=theme.INK, font=theme.FONT_H2).pack(anchor="w", padx=14, pady=(12, 2))
        tk.Label(dlg, justify='left', bg=theme.WINDOW, fg=theme.MUTED,
                 font=theme.FONT_SM,
                 text='Without a key: click "Ask AI to rank" to copy a prompt,\n'
                      'paste it into claude.ai, then paste the reply back.\n'
                      'With a key saved here: "Ask AI to rank" calls the API\n'
                      'automatically -- no copy/paste step needed.\n'
                      'A key also enables AI resume/cover writing.\n'
                      'Your key is stored only on this computer.').pack(anchor='w', padx=14)
        row = tk.Frame(dlg, bg=theme.WINDOW)
        row.pack(fill="x", padx=14, pady=(10, 2))
        tk.Label(row, text="Anthropic API key:", bg=theme.WINDOW, fg=theme.INK,
                 font=theme.FONT_SM, width=16, anchor="w").pack(side="left")
        akey = tk.StringVar(value=uisettings.get_api_key("anthropic"))
        ttk.Entry(row, textvariable=akey, width=44, show="*").pack(side="left")
        # Base URL: point the SAME key box at any Anthropic-compatible endpoint
        # (Ollama v0.14+ native, GLM, DeepSeek, Kimi) instead of Anthropic's own.
        # Stored to secrets/base_url via config.write_secret; blank = Anthropic.
        import config as _cfg
        row2 = tk.Frame(dlg, bg=theme.WINDOW)
        row2.pack(fill="x", padx=14, pady=(4, 2))
        tk.Label(row2, text="Base URL (optional):", bg=theme.WINDOW, fg=theme.INK,
                 font=theme.FONT_SM, width=16, anchor="w").pack(side="left")
        aurl = tk.StringVar(value=(_cfg.read_secret("base_url") or ""))
        ttk.Entry(row2, textvariable=aurl, width=44).pack(side="left")
        tk.Label(dlg, justify='left', bg=theme.WINDOW, fg=theme.MUTED,
                 font=theme.FONT_SM,
                 text='Leave Base URL blank to use Claude. Or point it at any\n'
                      'Anthropic-compatible endpoint -- a local Ollama\n'
                      '(http://localhost:11434), GLM, DeepSeek, or Kimi -- to\n'
                      'run BYO-AI ranking through your own model.').pack(anchor='w', padx=14, pady=(2, 0))
        status = tk.Label(dlg, text="", bg=theme.WINDOW, fg=theme.MUTED,
                          font=theme.FONT_SM)
        status.pack(anchor="w", padx=14, pady=(4, 0))

        def save():
            v = akey.get().strip()
            uisettings.set_api_key("anthropic", v)
            _cfg.write_secret("base_url", aurl.get().strip())
            ok = (not v) or uisettings.looks_like_key("anthropic", v)
            status.config(text="Saved." if ok else
                          "Saved — but that doesn't look like an Anthropic key (sk-ant-…).",
                          fg=theme.SUCCESS if ok else theme.WARN)

        def test():
            v = akey.get().strip()
            if not v:
                status.config(text="No key entered.", fg=theme.MUTED)
                return
            ok = uisettings.looks_like_key("anthropic", v)
            status.config(text="Looks valid (format only — not a live check)." if ok
                          else "Doesn't look like an Anthropic key (should start sk-ant-).",
                          fg=theme.SUCCESS if ok else theme.WARN)

        bb = tk.Frame(dlg, bg=theme.WINDOW)
        bb.pack(fill="x", padx=14, pady=12)
        theme.btn(bb, "Save", save, "accent").pack(side="left", padx=2)
        theme.btn(bb, "Test key", test, "ghost").pack(side="left", padx=2)
        theme.btn(bb, "Where do I get a key?",
                  lambda: webbrowser.open("https://console.anthropic.com/settings/keys"),
                  "ghost").pack(side="left", padx=2)
        theme.btn(bb, "Close", dlg.destroy, "ghost").pack(side="right", padx=2)
        dlg.grab_set()

    def _register_daily_updates(self, slug=None, parent=None) -> bool:
        """Register the per-user daily Task Scheduler job for a project via the
        shared helper (frozen -> exe --daily; dev -> py daily_run.py). Returns
        True on success. Shared by the Tools dialog and the wizard closing step."""
        slug = slug or workspace.active_slug()
        try:
            from scripts.setup_schedule import register_daily_task
            rc = register_daily_task(slug)
        except Exception as e:
            messagebox.showerror("Daily updates",
                                 f"Could not register the task:\n{e}",
                                 parent=parent or self)
            return False
        if rc != 0:
            messagebox.showwarning(
                "Daily updates",
                "Windows Task Scheduler returned an error registering the daily "
                f"job (code {rc}). You can still use “Update my Inbox now” any "
                "time.", parent=parent or self)
            return False
        return True

    def _show_daily_updates(self):
        """Register/unregister a per-user daily task (no admin) that runs the same
        ingest as 'Update my Inbox now' every morning. Shows current state."""
        slug = workspace.active_slug()
        from scripts.setup_schedule import task_status, unregister_daily_task
        dlg = tk.Toplevel(self)
        dlg.title("Daily updates")
        dlg.transient(self)
        dlg.configure(bg=theme.WINDOW)
        dlg.resizable(False, False)
        theme.header_bar(dlg, "Turn on daily updates",
                         "Refill your Inbox automatically every morning.")
        body = tk.Frame(dlg, bg=theme.WINDOW)
        body.pack(fill="both", expand=True, padx=16, pady=10)
        status = task_status(slug)
        state_txt = ("Currently ON" + (f" — next run {status['next_run']}"
                                       if status["next_run"] else "")
                     if status["registered"] else "Currently OFF")
        tk.Label(body, text=state_txt, bg=theme.WINDOW, fg=theme.INK,
                 font=theme.FONT_BOLD, anchor="w").pack(anchor="w")
        tk.Label(
            body, justify="left", wraplength=440, bg=theme.WINDOW, fg=theme.MUTED,
            font=theme.FONT_SM,
            text="This adds a Windows task (just for you — no administrator needed) "
                 "that searches your sources every morning and drops fresh matches "
                 "into your Inbox. You can turn it off any time."
        ).pack(anchor="w", pady=(4, 10))
        st = tk.Label(body, text="", bg=theme.WINDOW, fg=theme.MUTED,
                      font=theme.FONT_SM)
        st.pack(anchor="w")

        def turn_on():
            if self._register_daily_updates(slug, parent=dlg):
                st.config(text="Daily updates are ON.", fg=theme.SUCCESS)

        def turn_off():
            unregister_daily_task(slug)
            st.config(text="Daily updates are OFF.", fg=theme.MUTED)

        bb = tk.Frame(dlg, bg=theme.WINDOW)
        bb.pack(fill="x", padx=16, pady=12)
        theme.btn(bb, "Turn on", turn_on, "accent").pack(side="left", padx=2)
        theme.btn(bb, "Turn off", turn_off, "ghost").pack(side="left", padx=2)
        theme.btn(bb, "Close", dlg.destroy, "ghost").pack(side="right", padx=2)
        dlg.grab_set()

    def _show_ai_setup(self):
        """Open the "Set up with your AI" dialog (§6.3): a BYO-AI onboarding path
        that hands the user a copyable prompt and parses the config block their
        AI returns. On apply, refresh tabs so the seeded config/preferences show."""
        try:
            AiSetupDialog(self, on_applied=lambda _s: self._rebuild_tabs())
        except Exception as e:
            messagebox.showerror("Set up with your AI", str(e), parent=self)

    def _show_source_keys(self):
        """Open the 'Connect job sources' dialog. The module is created by the
        other builder this wave; guard the import so this worktree's tests pass
        and a not-yet-merged build degrades gracefully instead of crashing."""
        try:
            from ui import source_keys
        except ImportError:
            messagebox.showinfo(
                "Connect job sources",
                "Job-source key management isn't available in this build yet.\n\n"
                "For now, add Adzuna / USAJobs / Jooble / Careerjet keys to your "
                ".env file. It's coming to the app soon.", parent=self)
            return
        try:
            source_keys.open_dialog(self)
        except Exception as e:
            messagebox.showerror("Connect job sources", str(e), parent=self)

    def _show_seed_area(self):
        """Open the 'Seed my area' dialog: discover local employers from the
        CareerOneStop Business Finder directory, probe each for a live ATS board,
        and add the verified ones to the company list (tagged for this field +
        metro). The dialog is key-gated and honest when no CareerOneStop key is
        set (it routes to the keys dialog). Guarded so a missing/failed module
        degrades gracefully instead of crashing the GUI."""
        try:
            from ui import seed_area
        except ImportError:
            messagebox.showinfo(
                "Seed my area",
                "Local-employer seeding isn't available in this build yet.",
                parent=self)
            return
        try:
            seed_area.open_dialog(self)
        except Exception as e:
            messagebox.showerror("Seed my area", str(e), parent=self)

    def _toggle_browser_capture(self):
        """Start/stop the browser-extension receiver (Flask) as a daemon thread
        INSIDE this GUI process. Captures land in whichever project is ACTIVE
        when each job arrives (the embedded receiver must never take the
        process-wide pin — it would hijack the project switcher for every tab;
        review-fleet critical). The `py -m` standalone mode still pins itself."""
        from scrape import browser_receiver
        running = getattr(self, "_receiver_started", False)
        if running:
            captured = browser_receiver.capture_count()
            messagebox.showinfo(
                "Capture jobs from my browser",
                "Browser capture is already running on "
                f"http://127.0.0.1:{browser_receiver.PORT}.\n"
                f"Jobs captured so far: {captured}.\n\n"
                "It stays on until you close the app. Load the unpacked extension "
                "(see Help ▸ the Guide) and click “Send to Tool” while browsing.",
                parent=self)
            return
        try:
            browser_receiver.start_in_thread()
        except Exception as e:
            messagebox.showerror("Capture jobs from my browser",
                                 f"Could not start the receiver:\n{e}", parent=self)
            return
        if not browser_receiver.wait_until_listening():
            self._receiver_started = False
            messagebox.showerror(
                "Capture jobs from my browser",
                f"The receiver could not listen on port {browser_receiver.PORT} "
                "(is another copy of the app already running?). "
                "Browser capture is OFF.", parent=self)
            return
        self._receiver_started = True
        messagebox.showinfo(
            "Capture jobs from my browser",
            "Browser capture is ON, listening on "
            f"http://127.0.0.1:{browser_receiver.PORT}.\n\n"
            "Load the unpacked browser extension (Help ▸ the Guide walks you "
            "through it), browse LinkedIn / Indeed / Glassdoor, and click "
            "“Send to Tool”. Captured jobs land in the project you're viewing "
            "when they arrive.",
            parent=self)

    def _show_funnel(self):
        """Local application-funnel analytics from status_history (no cloud)."""
        data = analyticsmod.compute()
        f, by_src = data["funnel"], data["by_source"]
        dlg = tk.Toplevel(self)
        dlg.title("Application funnel")
        dlg.transient(self)
        dlg.configure(bg=theme.WINDOW)
        dlg.geometry("560x600")
        since = f" since {f['tracked_since']}" if f["tracked_since"] else ""
        theme.header_bar(dlg, "Your application funnel",
                         f"{f['total_tracked']} tracked{since}")
        body = tk.Frame(dlg, bg=theme.WINDOW)
        body.pack(fill="both", expand=True, padx=16, pady=10)
        if f["total_tracked"] == 0:
            tk.Label(body, text="No tracked applications yet.\nTrack jobs from your "
                                "Inbox and they'll show up here.",
                     bg=theme.WINDOW, fg=theme.MUTED, font=theme.FONT,
                     justify="center").pack(pady=40)
            theme.btn(dlg, "Close", dlg.destroy, "ghost").pack(pady=8)
            return

        tk.Label(body, text="Stages reached", bg=theme.WINDOW, fg=theme.INK,
                 font=theme.FONT_H2).pack(anchor="w")
        for s in f["stage_counts"]:
            name = s["stage"].replace("_", " ").title()
            tk.Label(body, text=f"   {name:14s}  {s['count']}", bg=theme.WINDOW,
                     fg=theme.INK, font=theme.FONT_SM, anchor="w").pack(anchor="w")

        rr = f"{f['response_rate'] * 100:.0f}%"
        mdr = (f"{f['median_days_to_response']:.0f} days"
               if f["median_days_to_response"] is not None else "—")
        tk.Label(body, text=f"\nResponse rate (applied → phone screen): {rr}",
                 bg=theme.WINDOW, fg=theme.INK, font=theme.FONT_SM,
                 anchor="w").pack(anchor="w")
        tk.Label(body, text=f"Median days to first response: {mdr}", bg=theme.WINDOW,
                 fg=theme.MUTED, font=theme.FONT_SM, anchor="w").pack(anchor="w")

        tk.Label(body, text="\nBy source", bg=theme.WINDOW, fg=theme.INK,
                 font=theme.FONT_H2).pack(anchor="w")
        cols = [("source", "Source", 150), ("applied", "Applied", 70),
                ("iv", "Interview+", 90), ("rate", "Interview rate", 100)]
        tree = ttk.Treeview(body, columns=[c[0] for c in cols], show="headings",
                            height=8)
        for c, l, w in cols:
            tree.heading(c, text=l)
            tree.column(c, width=w, anchor="w" if c == "source" else "center")
        theme.zebra(tree)
        for i, s in enumerate(by_src):
            rate = f"{s['interview_rate'] * 100:.0f}%" + (" (low n)" if s["low_n"] else "")
            tree.insert("", "end", tags=(theme.row_tag(i),),
                        values=(s["source"], s["applied"], s["interview_plus"], rate))
        tree.pack(fill="both", expand=True, pady=(2, 0))
        theme.btn(dlg, "Close", dlg.destroy, "ghost").pack(pady=8)

    def _show_due(self):
        """Follow-ups + deadlines that have arrived, plus the auto-ghost
        'no response' nudge (applied but silent > 21 days), with open / snooze /
        mark-ghosted / follow-up-now."""
        rows = list(followups_due(within_days=0))
        # Merge in no-response nudges for applications not already surfaced by a
        # due follow-up (dedup by application id so one job shows once).
        seen_ids = {r["id"] for r in rows}
        for r in stale_applications():
            if r["id"] not in seen_ids:
                rows.append(r)
                seen_ids.add(r["id"])
        dlg = tk.Toplevel(self)
        dlg.title("Due — follow-ups, deadlines & no-response")
        dlg.transient(self)
        dlg.configure(bg=theme.WINDOW)
        dlg.geometry("720x440")
        theme.header_bar(dlg, "Due now",
                         "Follow-ups, deadlines, and applications gone quiet.")
        tf = ttk.Frame(dlg)
        tf.pack(fill="both", expand=True, padx=10, pady=6)
        cols = [("due", "Due", 95), ("kind", "Kind", 100),
                ("title", "Title", 260), ("company", "Company", 150)]
        tree = ttk.Treeview(tf, columns=[c[0] for c in cols], show="headings")
        for c, l, w in cols:
            tree.heading(c, text=l)
            tree.column(c, width=w, anchor="w")
        theme.zebra(tree)
        tree.pack(side="left", fill="both", expand=True)
        rowmap = {}
        for i, r in enumerate(rows):
            iid = str(r["id"])
            rowmap[iid] = r
            tree.insert("", "end", iid=iid, tags=(theme.row_tag(i),),
                        values=(r["due_date"], r["due_kind"], r["title"], r["company"]))
        if not rows:
            tk.Label(dlg, text="Nothing due right now. Nice.", bg=theme.WINDOW,
                     fg=theme.MUTED, font=theme.FONT).pack(pady=8)

        def _sel():
            s = tree.selection()
            return rowmap.get(s[0]) if s else None

        def open_posting():
            r = _sel()
            u = safe_url((r or {}).get("url")) if r else ""
            if u:
                webbrowser.open(u)

        def snooze():
            r = _sel()
            if not r:
                return
            from datetime import timedelta
            # Wrap in db_guard like every other mutation: a mid-daily-run write
            # would otherwise raise sqlite3.Error and crash the callback.
            ok, _ = db_guard(
                dlg,
                lambda: update_job(
                    r["id"],
                    follow_up_date=(date.today() + timedelta(days=7)).isoformat()),
                action="snooze follow-up")
            if not ok:
                return
            dlg.destroy()
            self._show_due()

        def mark_ghosted():
            r = _sel()
            if not r:
                return
            ok, _ = db_guard(dlg, lambda: update_job(r["id"], status="ghosted"),
                             action="mark ghosted")
            if not ok:
                return
            dlg.destroy()
            self._show_due()
            self._refresh_cycle_views()

        def follow_up_now():
            r = _sel()
            if not r:
                return
            # 'Follow up': set follow_up_date to today so it stays actionable and
            # drops out of the no-response bucket into the follow-up one.
            ok, _ = db_guard(
                dlg,
                lambda: update_job(r["id"], follow_up_date=date.today().isoformat()),
                action="set follow-up")
            if not ok:
                return
            dlg.destroy()
            self._show_due()

        bb = tk.Frame(dlg, bg=theme.WINDOW)
        bb.pack(fill="x", padx=10, pady=8)
        theme.btn(bb, "Open posting", open_posting, "ghost").pack(side="left", padx=2)
        theme.btn(bb, "Snooze 7 days", snooze, "ghost").pack(side="left", padx=2)
        theme.btn(bb, "Follow up", follow_up_now, "ghost").pack(side="left", padx=2)
        theme.btn(bb, "Mark ghosted", mark_ghosted, "danger").pack(side="left", padx=2)
        theme.btn(bb, "Close", dlg.destroy, "ghost").pack(side="right", padx=2)

    def _refresh_cycle_views(self):
        """Refresh the tracker/queue tabs + tab badges after a cycle change (a
        due-dialog action, etc.). Guarded so it's a no-op before tabs exist."""
        try:
            if getattr(self, "_tracker", None) is not None:
                self._tracker.refresh()
            if getattr(self, "_board", None) is not None:
                self._board.refresh()
            if getattr(self, "_queue", None) is not None:
                self._queue.refresh(keep_selection=True)
        except (tk.TclError, AttributeError):
            pass
        self._update_badges()

    def _export_applications_csv(self):
        """File → export every application (+ its status timeline) to a CSV."""
        dest = filedialog.asksaveasfilename(
            parent=self, title="Export applications (CSV)",
            defaultextension=".csv", initialfile="applications.csv",
            filetypes=[("CSV", "*.csv"), ("All files", "*.*")])
        if not dest:
            return
        ok, n = db_guard(self, lambda: export_applications_csv(dest),
                         action="export CSV")
        if ok:
            messagebox.showinfo(
                "Export complete",
                f"Exported {n} application(s) to:\n{dest}", parent=self)

    def _show_contacts(self):
        """A small local contacts / referral CRM — manual capture only. Referrals
        convert far better than cold applies; this keeps 'who do I know here' next
        to the search, on this machine."""
        dlg = tk.Toplevel(self)
        dlg.title("Contacts / referrals")
        dlg.transient(self)
        dlg.configure(bg=theme.WINDOW)
        dlg.geometry("760x460")
        theme.header_bar(dlg, "Contacts & referrals",
                         "People you know at target companies. Stays on this computer.")
        tf = ttk.Frame(dlg)
        tf.pack(fill="both", expand=True, padx=10, pady=6)
        cols = [("name", "Name", 140), ("role", "Role", 110), ("company", "Company", 140),
                ("email", "Email", 160), ("linkedin", "LinkedIn", 120), ("note", "Note", 160)]
        tree = ttk.Treeview(tf, columns=[c[0] for c in cols], show="headings")
        for c, l, w in cols:
            tree.heading(c, text=l)
            tree.column(c, width=w, anchor="w")
        theme.zebra(tree)
        tree.pack(side="left", fill="both", expand=True)
        rowmap = {}

        def reload():
            for iid in tree.get_children():
                tree.delete(iid)
            rowmap.clear()
            for i, c in enumerate(list_contacts()):
                iid = str(c["id"])
                rowmap[iid] = c
                tree.insert("", "end", iid=iid, tags=(theme.row_tag(i),),
                            values=(c["name"], c["role"], c["company"], c["email"],
                                    c["linkedin"], c["note"]))

        reload()

        # Add form (name + a few optional fields, incl. last-contacted date and an
        # optional link to a tracked application — the schema already supports
        # app_id + last_contacted, D1 P5).
        form = tk.Frame(dlg, bg=theme.WINDOW)
        form.pack(fill="x", padx=10, pady=(0, 4))
        vars_ = {}
        for label in ("name", "role", "company", "email", "linkedin",
                      "last_contacted", "note"):
            disp = "Last contacted" if label == "last_contacted" else label.title()
            tk.Label(form, text=disp + ":", bg=theme.WINDOW, fg=theme.INK,
                     font=theme.FONT_SM).pack(side="left")
            v = tk.StringVar()
            vars_[label] = v
            ttk.Entry(form, textvariable=v, width=11).pack(side="left", padx=(2, 8))

        # Optional "link to a tracked job" dropdown -> contact.app_id.
        apps = get_all()
        app_choices = ["(no link)"] + [
            f"{a['id']}: {a['title']} @ {a['company']}" for a in apps]
        tk.Label(form, text="Link to job:", bg=theme.WINDOW, fg=theme.INK,
                 font=theme.FONT_SM).pack(side="left")
        link_var = tk.StringVar(value="(no link)")
        ttk.Combobox(form, textvariable=link_var, values=app_choices,
                     state="readonly", width=22).pack(side="left", padx=(2, 8))

        def add():
            name = vars_["name"].get().strip()
            if not name:
                messagebox.showinfo("Name needed", "Enter at least a name.", parent=dlg)
                return
            lc = vars_["last_contacted"].get().strip()
            if lc and not _DATE_RE.match(lc):
                messagebox.showinfo("Bad date",
                                    "Last contacted must be YYYY-MM-DD.", parent=dlg)
                return
            app_id = None
            sel = link_var.get()
            if sel and sel != "(no link)":
                try:
                    app_id = int(sel.split(":", 1)[0])
                except ValueError:
                    app_id = None
            add_contact(name, role=vars_["role"].get().strip(),
                        email=vars_["email"].get().strip(),
                        linkedin=vars_["linkedin"].get().strip(),
                        company=vars_["company"].get().strip(),
                        last_contacted=lc, app_id=app_id,
                        note=vars_["note"].get().strip())
            for v in vars_.values():
                v.set("")
            link_var.set("(no link)")
            reload()

        def remove():
            s = tree.selection()
            if s and s[0] in rowmap:
                delete_contact(int(s[0]))
                reload()

        bb = tk.Frame(dlg, bg=theme.WINDOW)
        bb.pack(fill="x", padx=10, pady=8)
        theme.btn(bb, "Add contact", add, "accent").pack(side="left", padx=2)
        theme.btn(bb, "Delete selected", remove, "ghost").pack(side="left", padx=2)
        theme.btn(bb, "Close", dlg.destroy, "ghost").pack(side="right", padx=2)

    # ── theme (light / dark) ────────────────────────────────────────────────────
    def _toggle_dark(self):
        self._set_theme("dark" if self._dark_var.get() else "light")

    def _set_theme(self, mode: str):
        """Switch light/dark live and remember the choice. ttk widgets restyle
        instantly; tk-colored chrome (project bar) + tab contents are rebuilt so
        they pick up the new palette, keeping the user on their current tab."""
        uisettings.set_theme(mode)
        theme.apply_theme(self, mode=mode)     # restyle ttk + set active palette
        _sync_palette_aliases()
        self.configure(bg=theme.WINDOW)
        # Re-tint the native title bar (root + any open dialog) to the new mode.
        try:
            from ui import titlebar
            titlebar.retheme_all(self)
        except Exception:
            pass
        try:
            sel = self._nb.index(self._nb.select())
        except (tk.TclError, AttributeError):
            sel = None
        self._build_menu()                     # tk menus ignore ttk; re-color them
        self._rebuild_topbar()
        self._rebuild_projectbar()
        self._rebuild_tabs(select_index=sel)

    # ── branded top bar (app identity) ──────────────────────────────────────────
    def _build_topbar(self):
        """Branded hero bar (serif wordmark + accent star + hairline) at the very
        top, above the project bar. Classic-tk chrome, so it's rebuilt on a theme
        switch to pick up the new palette (see _rebuild_topbar / _set_theme)."""
        from ui import topbar
        anchor = getattr(self, "_projbar", None) or getattr(self, "_nb", None)
        # Rebuild the Tools menu fresh for this bar so it belongs to a live parent
        # (and re-reads palette on a theme switch). The menubar keeps its own copy.
        tools_menu = self._make_tools_menu(self)
        self._topbar = topbar.build_top_bar(self, before=anchor,
                                            tools_menu=tools_menu)

    def _rebuild_topbar(self):
        if getattr(self, "_topbar", None) is not None:
            self._topbar.destroy()
            self._topbar = None
        self._build_topbar()

    # ── project bar (switch campaigns without restarting) ──────────────────────
    def _build_projectbar(self):
        self._projbar = None
        if not workspace.has_projects():
            return  # pre-migration: single root workspace, no switcher
        # Group the bar + its hairline under one frame so a theme rebuild can
        # destroy them together; pack it above the notebook when one exists.
        wrap = tk.Frame(self, bg=theme.SURFACE)
        if getattr(self, "_nb", None) is not None:
            wrap.pack(fill="x", side="top", before=self._nb)
        else:
            wrap.pack(fill="x", side="top")
        self._projbar = wrap
        bar = tk.Frame(wrap, bg=theme.SURFACE)
        bar.pack(fill="x", side="top")
        tk.Label(bar, text="Project:", bg=theme.SURFACE, fg=theme.INK,
                 font=theme.FONT_BOLD, padx=12, pady=7).pack(side="left")
        self._proj_var = tk.StringVar()
        self._proj_cb = ttk.Combobox(bar, textvariable=self._proj_var,
                                     state="readonly", width=34)
        self._proj_cb.pack(side="left", padx=4, pady=7)
        self._proj_cb.bind("<<ComboboxSelected>>", self._on_project_change)
        theme.btn(bar, "+ New", self._new_project, "ghost").pack(side="left", padx=6)
        theme.btn(bar, "+ Person", self._new_person, "ghost").pack(side="left", padx=2)
        tk.Frame(wrap, bg=theme.BORDER, height=1).pack(fill="x", side="top")
        self._refresh_projectbar()

    def _rebuild_projectbar(self):
        if getattr(self, "_projbar", None) is not None:
            self._projbar.destroy()
            self._projbar = None
        self._build_projectbar()

    @staticmethod
    def _slug_taken(name):
        slug = workspace.slugify(name)
        return any(p.get("slug") == slug for p in workspace.list_projects())

    @staticmethod
    def _proj_label(p):
        # Show "Person — Campaign" once a project is tagged with a person (GOAL 2),
        # else just the campaign name (unchanged for single-person installs).
        person = p.get("person")
        return f"{person} \N{EM DASH} {p['name']}" if person else p["name"]

    def _refresh_projectbar(self):
        if not self._proj_var:
            return
        projs = workspace.list_projects()
        # Resolve the selection by combobox INDEX, not by label — two projects can
        # render an identical "Person — Campaign" label, and a label→slug map would
        # make one of them unreachable (last-writer-wins).
        self._proj_slugs = [p["slug"] for p in projs]
        self._name_to_slug = {self._proj_label(p): p["slug"] for p in projs}  # legacy
        self._proj_cb["values"] = [self._proj_label(p) for p in projs]
        active = workspace.active_slug()
        for i, p in enumerate(projs):
            if p["slug"] == active:
                self._proj_cb.current(i)
                break

    def _on_project_change(self, _event=None):
        idx = self._proj_cb.current()
        slugs = getattr(self, "_proj_slugs", [])
        if not (0 <= idx < len(slugs)):
            return
        slug = slugs[idx]
        # While a pinned run (Update my Inbox now) is in flight, every DB call
        # resolves to the PINNED project — switching the dropdown would show
        # project B over project A's data (review-fleet major). Refuse until
        # the run finishes, and snap the dropdown back.
        if workspace.pinned() and slug != workspace.pinned():
            messagebox.showinfo(
                "Project switch",
                "An inbox update is still running for the current project.\n"
                "Wait for it to finish, then switch.", parent=self)
            self._refresh_projectbar()  # snap the dropdown back to the pinned project
            return
        if slug and slug != workspace.active_slug():
            workspace.set_active(slug)
            self._rebuild_tabs()
            self._update_title()

    def _new_project(self):
        name = simpledialog.askstring(
            "New Project", "Name for the new campaign:", parent=self)
        if not name or not name.strip():
            return
        if self._slug_taken(name):
            messagebox.showwarning(
                "New Project",
                f"A project that maps to '{name.strip()}' already exists — pick it "
                "from the Project dropdown, or choose a different name.", parent=self)
            return
        # C1 guard: resume copy is OPT-IN. Auto-copying the active project's
        # experience.md silently shipped the wrong person's resume into a new
        # campaign (the dad-data bug). Config (keywords/salary) still seeds for a
        # working start; the resume (identity/PII) only copies if asked. Default No.
        active = workspace.active_slug()
        copy_resume = bool(active) and messagebox.askyesno(
            "New Project",
            f"Copy your resume (experience.md) from '{active}' into the new "
            "campaign?\n\nChoose No to start from a blank template — pick No if "
            "this campaign is for someone else.",
            default=messagebox.NO, parent=self)
        try:
            workspace.create_project(name.strip(), config=workspace.load_config(),
                                     copy_resume_from=(active if copy_resume else None),
                                     make_active=True)
        except Exception as exc:
            messagebox.showerror("New Project", str(exc))
            return
        self._refresh_projectbar()
        self._rebuild_tabs()
        self._update_title()

    def _new_person(self):
        # A person is just a project tagged with an owner (GOAL 2). New person =>
        # a fresh blank campaign (NO resume copy — different identity/PII) + the
        # setup wizard so they onboard their own profile.
        person = simpledialog.askstring(
            "New Person", "Whose job search is this? (their name)", parent=self)
        if not person or not person.strip():
            return
        person = person.strip()
        name = simpledialog.askstring(
            "New Person", f"Name {person}'s search campaign:",
            initialvalue=f"{person} — search", parent=self)
        if not name or not name.strip():
            return
        if self._slug_taken(name):
            # Without this guard create_project would silently re-activate the
            # existing project and the wizard would OVERWRITE its profile.
            messagebox.showwarning(
                "New Person",
                f"A project that maps to '{name.strip()}' already exists — pick it "
                "from the Project dropdown, or choose a different name.", parent=self)
            return
        try:
            workspace.create_project(name.strip(), person=person, make_active=True)
        except Exception as exc:
            messagebox.showerror("New Person", str(exc))
            return
        self._refresh_projectbar()
        self._rebuild_tabs()
        self._update_title()
        # Onboard the new person's profile into the now-active project. Use the
        # SAME 2-arg finish handler as first-run so the wizard's closing "Keep
        # jobs coming" step is honored here too (daily-updates registration,
        # Build-My-List, and the forced first Inbox update) — a 1-arg lambda
        # silently drops those actions (setup_wizard._close arity dispatch).
        try:
            from ui import setup_wizard
            setup_wizard.run(self, on_finish=self._after_new_person_setup)
        except Exception:
            pass

    def _after_new_person_setup(self, applied: bool, actions: dict | None = None):
        """New-person finish: keep the title in sync with the freshly-created
        project, then delegate to the shared closing-step handler so an
        additional profile gets the same daily-updates / Build-My-List / forced
        Inbox-update treatment as first-run (finding: New-person wizard silently
        discarded the closing step)."""
        self._update_title()
        self._after_setup(applied, actions)

    # ── tabs ───────────────────────────────────────────────────────────────────
    def _build_tabs(self):
        init_db()  # ensure the active project's tracker.db exists/upgraded
        self._inbox    = InboxTab(self._nb, on_change=self._update_badges)
        self._toppicks = TopPicksTab(self._nb, on_change=self._update_badges)
        self._search   = SearchTab(self._nb,
                                   open_guide_cb=lambda: self._nb.select(self._guide))
        self._queue    = ApplyQueueTab(self._nb)
        self._tracker  = TrackerTab(self._nb)
        self._board    = KanbanTab(self._nb)
        self._resume   = ResumeTab(self._nb)
        self._guide    = uihelp.GuideTab(self._nb, app=self)
        self._nb.add(self._inbox,    text="Inbox")
        self._nb.add(self._toppicks, text="Top Picks")
        self._nb.add(self._search,   text="Search")
        self._nb.add(self._queue,   text="Apply Queue")
        self._nb.add(self._tracker, text="Job Tracker")
        self._nb.add(self._board,   text="Board")
        self._nb.add(self._resume,  text="Resume Generator")
        self._nb.add(self._guide,   text="\N{BLACK QUESTION MARK ORNAMENT} Guide")
        # A Board (Kanban) move mutates the same tracker.db the Tracker + Apply
        # Queue tabs read; the board fires <<KanbanChanged>> after each move/edit.
        # Bind it so those sibling views + the tab badges refresh immediately
        # instead of only on the next tab-switch (previously the event was dead —
        # nothing listened for it).
        self._board.bind("<<KanbanChanged>>", self._on_kanban_changed)
        self._update_badges()

    def _on_kanban_changed(self, _event=None):
        """A card moved/edited on the Board: keep the other DB-backed views and
        the tab counts in sync without waiting for a manual tab switch."""
        try:
            self._tracker.refresh()
        except Exception:
            pass
        try:
            self._queue.refresh(keep_selection=True)
        except Exception:
            pass
        self._update_badges()

    def _rebuild_tabs(self, select_index=None):
        for tab in (self._inbox, self._toppicks, self._search, self._queue,
                    self._tracker, self._board, self._resume, self._guide):
            tab.destroy()
        self._build_tabs()
        if select_index is not None:
            tabs = self._nb.tabs()
            if tabs:
                self._nb.select(tabs[min(select_index, len(tabs) - 1)])
        elif inbox_count() == 0:
            self._nb.select(self._search)

    def _update_title(self):
        if workspace.has_projects():
            self.title(f"Zaggregate — {workspace.active_slug()}")
        else:
            self.title("Zaggregate")

    def _update_badges(self):
        if not self._nb.tabs():
            return  # InboxTab refreshes during __init__, before tabs exist
        n = inbox_count()
        self._nb.tab(0, text=f"Inbox ({n})" if n else "Inbox")
        # Job Tracker tab gains a due-count badge (follow-ups/deadlines + the new
        # no-response nudge), so a user who lives in the Inbox still sees pending
        # cycle work. Guarded: the tab may not exist yet mid-rebuild.
        try:
            due = count_followups_due()
            self._nb.tab(self._tracker,
                         text=f"Job Tracker ({due})" if due else "Job Tracker")
        except (tk.TclError, AttributeError):
            pass

    # ── Startup banner + data safety (D1 P5) ────────────────────────────────────
    def _show_banner(self, text, action_text=None, action=None, kind="info"):
        """A slim dismissible banner strip below the project bar / above the
        notebook. Not a modal — the user can ignore it. Replaces any prior banner.
        `kind` picks the accent ('info' | 'warn')."""
        self._dismiss_banner()
        bg = theme.ALT if kind == "info" else theme.WARN
        fg = theme.INK if kind == "info" else "#ffffff"
        bar = tk.Frame(self, bg=bg)
        # Sit directly above the notebook.
        bar.pack(fill="x", side="top", before=self._nb)
        self._banner = bar
        tk.Label(bar, text=text, bg=bg, fg=fg, font=theme.FONT_SM, anchor="w",
                 padx=14, pady=6).pack(side="left")
        tk.Button(bar, text="\N{MULTIPLICATION SIGN}", command=self._dismiss_banner,
                  bg=bg, fg=fg, relief="flat", bd=0, font=theme.FONT_SM,
                  activebackground=bg, cursor="hand2").pack(side="right", padx=8)
        if action_text and action:
            tk.Button(bar, text=action_text, command=action, bg=bg, fg=fg,
                      relief="flat", bd=0, font=theme.FONT_BOLD,
                      activebackground=bg, cursor="hand2").pack(side="right", padx=4)

    def _dismiss_banner(self):
        b = getattr(self, "_banner", None)
        if b is not None:
            try:
                b.destroy()
            except tk.TclError:
                pass
            self._banner = None

    def _maybe_show_due_banner(self):
        """Show the proactive due banner when count_followups_due() > 0. Yields to
        an existing (higher-priority) integrity-warning banner."""
        if getattr(self, "_banner", None) is not None:
            return  # a data-safety warning is already showing; don't clobber it
        try:
            due = count_followups_due()
        except Exception:
            return
        if not due:
            return
        def open_due():
            self._dismiss_banner()
            self._show_due()
        self._show_banner(
            f"You have {due} application(s) that need attention "
            "(follow-ups, deadlines, or gone quiet).",
            action_text="Review due", action=open_due, kind="info")

    def _data_safety_check(self):
        """PRAGMA quick_check + rolling daily backup, once per launch. A failed
        integrity check surfaces a warning banner but never crashes."""
        try:
            rolling_backup()
        except Exception as e:
            # A missed rolling backup is non-fatal (the next launch retries), but
            # log it once so a persistently-failing backup isn't silently invisible.
            applog.warn_once(
                f"Rolling daily backup failed ({e}); will retry next launch.",
                key="gui_rolling_backup_failed")
        try:
            ok, msg = quick_check()
        except Exception:
            return
        if not ok:
            self._show_banner(
                f"Warning: your data file failed an integrity check ({msg}). "
                "Consider restoring from a backup (File menu).",
                action_text="Back up now",
                action=lambda: uihelp.backup_data(self), kind="warn")

    def _on_tab_changed(self, _event=None):
        current = self._nb.nametowidget(self._nb.select())
        if current is self._queue:
            self._queue.refresh(keep_selection=True)
        elif current is self._tracker:
            self._tracker.refresh()
        elif current is self._board:
            self._board.refresh()
        elif current is self._toppicks:
            self._toppicks.refresh()
        elif current is self._inbox:
            self._inbox.refresh()
        self._update_badges()

    def _on_tk_exception(self, exc_type, exc_value, exc_tb):
        """Tk callback-exception hook: append the traceback to a log file under
        the output dir and show a short error dialog, so a callback failure is
        visible instead of silently dead in a windowed build."""
        import traceback
        from datetime import datetime
        tb = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        log_path = None
        try:
            from config import OUTPUT_DIR
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            log_path = OUTPUT_DIR / "gui_error.log"
            with open(log_path, "a", encoding="utf-8") as fh:
                fh.write(f"\n[{datetime.now().isoformat()}]\n{tb}\n")
        except Exception:
            pass  # never let the error handler itself crash the app
        detail = f"{exc_type.__name__}: {exc_value}"
        where = f"\n\nLogged to {log_path}" if log_path else ""
        try:
            messagebox.showerror(
                "Something went wrong",
                f"An unexpected error occurred:\n\n{detail}{where}")
        except Exception:
            pass


def _log_fatal(exc: BaseException) -> str:
    """Write a fatal startup/runtime traceback to output/gui_error.log and return
    it. Used by main() so a CONSTRUCTION-time crash in a windowed build leaves a
    log + dialog instead of the raw PyInstaller 'Unhandled exception' box."""
    import traceback
    from datetime import datetime
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    try:
        from config import OUTPUT_DIR
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_DIR / "gui_error.log", "a", encoding="utf-8") as fh:
            fh.write(f"\n[{datetime.now().isoformat()}]\n{tb}\n")
    except Exception:
        pass
    return tb


def _run_headless_daily(argv) -> int:
    """Handle `--daily [--project <slug>]`: run the same ingest as the in-GUI
    'Update my Inbox now' button and exit, with NO Tk. This is what the shipped
    single exe runs from the Task Scheduler job (build_package/app.spec build
    only gui.py, so the exe must serve both the windowed app AND the headless
    daily run, flag-switched). Prints the pipeline output straight to stdout so
    the scheduled task's log redirect captures per-source counts / failures."""
    import argparse
    ap = argparse.ArgumentParser(prog="JobProgram", add_help=False)
    ap.add_argument("--daily", action="store_true")
    ap.add_argument("--project", type=str, default=None)
    args, _unknown = ap.parse_known_args(argv)
    slug = args.project or workspace.active_slug()
    # run_daily_ingest pins/unpins and calls daily_run.run_main(); no on_line so
    # the pipeline prints straight through to the redirected stdout.
    return run_daily_ingest(slug)


def _web_smoke(port: int | None = None) -> dict:
    """Headless proof that the frozen bundle can serve the web UI, WITHOUT Tk.

    Runs the receiver's Flask app (webui blueprint already mounted at import) on
    a loopback port in a daemon thread, then GETs ``/app`` and ``/api/status``
    over urllib and returns a result dict. This exercises the exact bundle seams
    Phase 0d must prove: app.spec's ``collect_submodules('webui')`` (no frozen
    ImportError) and the ``webui/static`` datas entry resolving through
    ``paths.static_dir()`` (the ``_MEIPASS`` branch when frozen). Env-gated in
    ``main()`` so it never runs for real users; port defaults to
    ``$ZAGGREGATE_SMOKE_PORT`` or 5003 (NOT the live 5002 receiver/preview port).
    """
    import os
    import json as _json
    import socket as _sk
    import threading as _th
    import time as _time
    import urllib.request as _req

    if port is None:
        port = int(os.environ.get("ZAGGREGATE_SMOKE_PORT", "5003"))
    host = "127.0.0.1"

    # The receiver module builds `app` and calls register_webui(app) at import,
    # so this is the frozen-bundle Flask app with /app + /api mounted.
    from scrape import browser_receiver as _rcv

    def _serve():
        # threaded=True so /app and /api/status can be served without the single
        # dev-server request from blocking the poll below.
        _rcv.app.run(host=host, port=port, debug=False,
                     use_reloader=False, threaded=True)

    t = _th.Thread(target=_serve, name="web-smoke", daemon=True)
    t.start()

    # Wait until the socket accepts connections (or the thread died on bind).
    deadline = _time.monotonic() + 8.0
    listening = False
    while _time.monotonic() < deadline:
        try:
            with _sk.create_connection((host, port), timeout=0.25):
                listening = True
                break
        except OSError:
            if not t.is_alive():
                break
            _time.sleep(0.1)

    result: dict = {"ok": False, "port": port, "listening": listening,
                    "app": {}, "status": {}}
    if not listening:
        result["error"] = "receiver did not start listening"
        return result

    def _get(path: str) -> tuple[int, str, str]:
        # Capture HTTP error codes (4xx/5xx) instead of raising so one failing
        # probe doesn't abort the rest of the smoke sweep — the frozen exe must
        # report EVERY endpoint's status, not stop at the first non-2xx.
        import urllib.error as _uerr
        try:
            with _req.urlopen(f"http://{host}:{port}{path}", timeout=5) as r:
                body = r.read().decode("utf-8", "replace")
                return r.status, r.headers.get("Content-Type", ""), body
        except _uerr.HTTPError as he:
            body = he.read().decode("utf-8", "replace") if he.fp else ""
            return he.code, he.headers.get("Content-Type", "") if he.headers else "", body

    try:
        a_code, a_ctype, a_body = _get("/app")
        app_ok = (a_code == 200 and "text/html" in a_ctype
                  and 'id="root"' in a_body)
        result["app"] = {"code": a_code, "content_type": a_ctype,
                         "has_root": 'id="root"' in a_body, "ok": app_ok}

        s_code, _s_ctype, s_body = _get("/api/status")
        try:
            s_json = _json.loads(s_body)
        except ValueError:
            s_json = {}
        status_ok = (s_code == 200 and bool(s_json.get("ok")))
        result["status"] = {"code": s_code, "ok": status_ok,
                            "project": s_json.get("project"),
                            "version": s_json.get("version")}

        # Extended frozen probes (deep-test D5.3): read-only endpoints from the
        # Phase 3-5 modules (toppicks/guide/settings/onboarding) + one hashed
        # asset, all served from inside the bundle. Each asserts 200 + the shape
        # key the frontend depends on. This catches frozen-only ImportError/data
        # gaps that /app + /api/status alone would miss. `probes` is ADDITIVE —
        # existing keys (app/status/ok/listening/port) are unchanged.
        def _probe_json(path: str, shape_key: str) -> dict:
            code, _ct, body = _get(path)
            try:
                j = _json.loads(body)
            except ValueError:
                j = {}
            has_shape = isinstance(j, dict) and (shape_key in j)
            return {"code": code, "ok": bool(code == 200 and j.get("ok")
                                             and has_shape),
                    "shape_key": shape_key, "has_shape": has_shape}

        probes: dict = {}
        probes["toppicks"] = _probe_json("/api/toppicks", "rows")
        probes["guide"] = _probe_json("/api/guide", "sections")
        probes["settings_keys"] = _probe_json("/api/settings/keys", "sources")
        probes["onboarding"] = _probe_json("/api/onboarding", "prefill")

        # One hashed asset: discover the built JS filename from index.html so the
        # probe follows the frozen bundle's Vite output (no stale hardcode).
        import re as _re
        m = _re.search(r'assets/(index-[A-Za-z0-9_-]+\.js)', a_body)
        asset_name = m.group(1) if m else None
        if asset_name:
            ac, act, _ab = _get(f"/app/assets/{asset_name}")
            probes["asset"] = {"name": asset_name, "code": ac,
                               "content_type": act,
                               "ok": bool(ac == 200
                                          and "javascript" in act.lower())}
        else:
            probes["asset"] = {"name": None, "code": 0, "ok": False,
                               "error": "no hashed asset in index.html"}

        result["probes"] = probes
        probes_ok = all(p.get("ok") for p in probes.values())

        result["ok"] = bool(app_ok and status_ok and probes_ok)
    except Exception as e:  # noqa: BLE001 — smoke reports, never raises
        result["error"] = f"{type(e).__name__}: {e}"
    return result


def main() -> int:
    # Frozen web-UI smoke (Phase 0d): env-gated, BEFORE any Tk. Proves the
    # bundle carries webui + its static assets by serving /app + /api/status
    # in-process and printing the result as JSON. Never trips for real users.
    import os as _os
    if _os.environ.get("ZAGGREGATE_WEB_SMOKE") == "1":
        import json as _json
        res = _web_smoke()
        print(_json.dumps(res))
        return 0 if res.get("ok") else 1

    # Web-UI mode: `--web` (browser) / `--desktop` (native pywebview window)
    # delegate to the headless `py -m webui` launcher BEFORE any Tk import/window,
    # so a friend can run the modern web UI from the same single exe. The
    # PyInstaller entry stays gui.py, so the frozen bundle gets both for free
    # (app.spec only needs the pywebview hidden imports for --desktop).
    if "--web" in sys.argv[1:] or "--desktop" in sys.argv[1:]:
        try:
            from webui.__main__ import main as _web_main
            return _web_main(sys.argv[1:])
        except Exception as e:
            _log_fatal(e)
            return 1

    # Headless daily mode: the single shipped exe serves both the GUI and the
    # scheduled `--daily` run (app.spec builds only gui.py). Detect the flag
    # before creating any Tk window.
    if "--daily" in sys.argv[1:]:
        try:
            return _run_headless_daily(sys.argv[1:])
        except Exception as e:
            _log_fatal(e)
            return 1
    try:
        App().mainloop()
        return 0
    except Exception as e:
        _log_fatal(e)
        try:
            messagebox.showerror(
                "Zaggregate could not start",
                "An unexpected error occurred at startup. Details were saved to "
                "output/gui_error.log.")
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
