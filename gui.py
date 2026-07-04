"""
gui.py — Local desktop GUI replacing the Flask browser apps.
Run: py gui.py

Tabs:
  Inbox            — scored matches from the daily headless run (daily_run.py)
  Search           — multi-source search with match scoring
  Apply Queue      — ranked 'interested' jobs; docs + mark-applied workflow
  Job Tracker      — replaces tracker/app.py  (http://localhost:5001)
  Resume Generator — replaces resume/app.py   (http://localhost:5000)
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
    `--daily` headless mode so both take the identical, S27-safe path."""
    import daily_run
    slug = slug or workspace.active_slug()
    prev_argv = sys.argv
    # daily_run.main() re-parses argv and re-pins from --project; pin here too so
    # the pin is live even if that internal pin is ever removed. run_main()'s
    # finally clears the process pin.
    workspace.pin_active(slug)
    sys.argv = ["daily_run.py"] + (["--project", slug] if slug else [])
    sink = _LineSink(on_line) if on_line else None
    try:
        if sink is not None:
            with contextlib.redirect_stdout(sink):
                rc = daily_run.run_main()
            sink.flush()
        else:
            rc = daily_run.run_main()
        return rc
    finally:
        sys.argv = prev_argv
        workspace.unpin_active()  # daily_run.run_main already unpins; idempotent


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


class AiSetupDialog(tk.Toplevel):
    """"Set me up with my AI" (§6.3): a BYO-AI onboarding path. The app never
    calls an LLM — it hands the user a copyable prompt to paste (with their
    résumé + one sentence of intent) into THEIR own AI, then parses the canonical
    config block the AI returns and applies it to config.json +
    preferences.{json,md}. The wizard steps are owned by a parallel builder; this
    is a standalone Tools dialog over ui.ai_setup's pure functions."""

    def __init__(self, parent, on_applied=None):
        super().__init__(parent)
        self.title("Set up with your AI")
        self.geometry("720x600")
        self.configure(bg=theme.WINDOW)
        self.transient(parent)
        self.grab_set()
        self._on_applied = on_applied
        self._build()

    def _build(self):
        from ui import ai_setup
        tk.Label(self, justify="left", wraplength=690, fg=theme.INK, bg=theme.WINDOW,
                 text="Have a Claude or ChatGPT subscription? Let it set you up.\n"
                      "1. Copy the prompt below. 2. Paste it into your AI, then "
                      "paste your résumé and one sentence about the job you want. "
                      "3. Copy your AI's reply back into the box below and click "
                      "Apply."
                 ).pack(fill="x", padx=12, pady=(12, 6))

        tk.Label(self, text="Step 1 — copy this prompt:", anchor="w",
                 fg=theme.MUTED, bg=theme.WINDOW).pack(fill="x", padx=12)
        self._prompt_box = theme.text_widget(self, height=8, wrap="word")
        self._prompt_box.pack(fill="both", expand=True, padx=12, pady=(2, 4))
        self._prompt_box.insert("1.0", ai_setup.build_setup_prompt())
        self._prompt_box.configure(state="disabled")

        prow = tk.Frame(self, bg=theme.WINDOW)
        prow.pack(fill="x", padx=12, pady=(0, 6))
        theme.btn(prow, "Copy prompt", self._copy_prompt, "accent").pack(side="left")

        tk.Label(self, text="Step 2 — paste your AI's reply here:", anchor="w",
                 fg=theme.MUTED, bg=theme.WINDOW).pack(fill="x", padx=12)
        self._reply_box = theme.text_widget(self, height=8, wrap="word")
        self._reply_box.pack(fill="both", expand=True, padx=12, pady=(2, 4))

        arow = tk.Frame(self, bg=theme.WINDOW)
        arow.pack(fill="x", padx=12, pady=(0, 6))
        theme.btn(arow, "Apply setup", self._apply, "accent").pack(side="left")
        theme.btn(arow, "Close", self.destroy, "ghost").pack(side="right")

        self._status = tk.Label(self, text="", fg=theme.MUTED, bg=theme.WINDOW,
                                anchor="w", justify="left", wraplength=690)
        self._status.pack(fill="x", padx=12, pady=(0, 10))

    def _copy_prompt(self):
        from ui import ai_setup
        copy_or_warn(self, ai_setup.build_setup_prompt(),
                     status_cb=lambda m: self._status.config(text=m))

    def _apply(self):
        from ui import ai_setup
        text = self._reply_box.get("1.0", "end-1c").strip()
        if not text:
            self._status.config(text="Paste your AI's reply first.")
            return
        try:
            summary = ai_setup.apply_setup(text)
        except ai_setup.SetupBlockError as e:
            messagebox.showwarning("Couldn't apply setup", str(e), parent=self)
            self._status.config(text=str(e))
            return
        titles = ", ".join(summary.get("target_titles", [])[:4])
        loc = "Remote" if summary.get("remote_only") else summary.get("location", "")
        self._status.config(
            text=f"Applied. Field: {summary.get('field')} · Titles: {titles} · "
                 f"Where: {loc}. Your preferences are saved.")
        messagebox.showinfo(
            "You're set up",
            f"Field: {summary.get('field')}\n"
            f"Titles: {titles}\n"
            f"Location: {loc}\n"
            f"Salary floor: {summary.get('salary_min') or '—'}\n\n"
            "Your search config and preferences are saved. Run an inbox update "
            "to see your first jobs.", parent=self)
        if callable(self._on_applied):
            try:
                self._on_applied(summary)
            except Exception:
                pass
        self.destroy()


# ── Search tab ────────────────────────────────────────────────────────────────
def partition_add_entries(entries, status_by_idx):
    """Split add-companies entries by their probe verdict (P0-6). Returns
    (verified, unreachable): 'live' and 'direct' rows are verified; 'unreachable'
    rows failed their live probe. Any row with no recorded verdict is treated as
    unreachable (unknown-is-unsafe: a board we never confirmed live shouldn't be
    scraped without the user opting in). Pure/UI-free so it's unit-testable."""
    verified, unreachable = [], []
    for i, e in enumerate(entries):
        kind = status_by_idx.get(i)
        if kind in ("live", "direct"):
            verified.append(e)
        else:
            unreachable.append(e)
    return verified, unreachable


class AddCompaniesDialog(tk.Toplevel):
    """Paste career-page URLs -> auto-detect ATS + slug -> validate the board is
    live -> append to companies.json, tagged with the active project's industry
    so they show up in this campaign's 'careers' searches. Boards that fail the
    live probe are NOT scraped unless the user explicitly keeps them (they're
    saved flagged-unverified and excluded until they verify) — P0-6."""

    _COLS = [("name", "Name", 170, "w"), ("type", "Type", 95, "w"),
             ("slug", "Slug", 230, "w"), ("status", "Status", 120, "w")]

    def __init__(self, parent, default_industry="", default_metro=""):
        super().__init__(parent)
        self.title("Add Companies")
        self.geometry("780x560")
        self.configure(bg=theme.WINDOW)
        self.transient(parent)
        self.grab_set()
        self._entries = []
        self._default_metro = default_metro or ""
        # Probe status per entry (index-aligned with self._entries), set by the
        # validate worker: "live" / "direct" = verified, "unreachable" = failed
        # its live probe. Missing = not yet probed. _add gates on this (P0-6).
        self._status_by_idx: dict[int, str] = {}
        # Set when _add triggered validation itself; _validate_done then resumes
        # the add once verdicts are in.
        self._pending_add = False
        self._build(default_industry)

    def _build(self, default_industry):
        tk.Label(self, justify="left", wraplength=740, fg=theme.INK,
                 bg=theme.WINDOW,
                 text="Paste one career-page URL per line (or 'Name | URL'). "
                      "Greenhouse / Lever / Ashby / SmartRecruiters / Workday are "
                      "auto-detected; anything else is saved as a direct page.\n"
                      "Examples:  boards.greenhouse.io/acme   jobs.lever.co/acme   "
                      "Acme | acme.wd5.myworkdayjobs.com/Careers"
                 ).pack(fill="x", padx=10, pady=(10, 4))

        # §6.7 / SB-2a: don't know which employers to add? Copy an AI prompt that
        # asks for careers-page URLs ONLY (what AIs get right — slug-guessing is
        # ~50% wrong), paste the reply into the box below, and the app resolves
        # the slug + verifies each board (P0-6).
        seedrow = tk.Frame(self, bg=theme.WINDOW)
        seedrow.pack(fill="x", padx=10, pady=(0, 2))
        tk.Label(seedrow, text="Don't have a list? ", bg=theme.WINDOW,
                 fg=theme.MUTED).pack(side="left")
        theme.btn(seedrow, "Copy AI prompt", self._copy_seed_prompt,
                  "ghost").pack(side="left", padx=4)

        self._box = theme.text_widget(self, height=7, wrap="none")
        self._box.pack(fill="x", padx=10)

        row = tk.Frame(self, bg=theme.WINDOW)
        row.pack(fill="x", padx=10, pady=6)
        tk.Label(row, text="Industry tag:", bg=theme.WINDOW,
                 fg=theme.INK).pack(side="left")
        self._industry = tk.StringVar(value=default_industry)
        ttk.Entry(row, textvariable=self._industry, width=22).pack(side="left", padx=6)
        self._detect_btn = theme.btn(row, "Detect", self._detect, "ghost")
        self._detect_btn.pack(side="left", padx=4)
        self._val_btn = theme.btn(row, "Validate", self._validate, "ghost")
        self._val_btn.pack(side="left", padx=4)
        theme.btn(row, "Add \N{BLACK RIGHT-POINTING SMALL TRIANGLE} companies.json",
                  self._add, "accent").pack(side="left", padx=4)
        theme.btn(row, "Close", self.destroy, "ghost").pack(side="right")

        tf = ttk.Frame(self)
        tf.pack(fill="both", expand=True, padx=10, pady=(2, 4))
        self._tree = ttk.Treeview(tf, columns=[c[0] for c in self._COLS],
                                  show="headings", selectmode="browse")
        for col, label, w, anc in self._COLS:
            self._tree.heading(col, text=label)
            self._tree.column(col, width=w, anchor=anc)
        self._tree.pack(side="left", fill="both", expand=True)
        vsb = ttk.Scrollbar(tf, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")

        self._status = tk.Label(self, text="", fg=theme.MUTED, bg=theme.WINDOW,
                                anchor="w")
        self._status.pack(fill="x", padx=10, pady=(0, 8))

    def _copy_seed_prompt(self):
        """Copy the URL-only company-seeding prompt (§6.7/SB-2a) to the clipboard,
        pre-filled with the current industry tag + the active project's metro."""
        from ui import ai_setup
        prompt = ai_setup.build_seed_prompt(
            self._industry.get().strip(), self._default_metro)
        copy_or_warn(self, prompt,
                     status_cb=lambda m: self._status.config(
                         text="Prompt copied — paste it into your AI, then paste "
                              "the Name | URL lines it returns into the box above."))

    def _detect(self):
        from scrape.ats_detect import parse_line
        lines = self._box.get("1.0", "end").splitlines()
        self._entries = [e for e in (parse_line(l) for l in lines) if e]
        # Re-detecting rebuilds _entries, so any prior probe verdict is stale.
        self._status_by_idx = {}
        for r in self._tree.get_children():
            self._tree.delete(r)
        for i, e in enumerate(self._entries):
            self._tree.insert("", "end", iid=str(i),
                              values=(e.name, e.ats_type, e.slug, "—"))
        direct = sum(1 for e in self._entries if e.ats_type == "direct")
        self._status.config(
            text=f"Detected {len(self._entries)} compan(ies); {direct} direct (uncountable).")

    def _validate(self):
        if not self._entries:
            self._detect()
        if not self._entries:
            return
        # Disable both Detect and Validate while the worker runs: re-detecting
        # mid-validate would mutate _entries under the thread (GUI-9). The worker
        # gets its own snapshot so a later Detect can't shift indices either.
        self._val_btn.config(state="disabled")
        self._detect_btn.config(state="disabled")
        self._status.config(text="Validating…")
        snapshot = list(self._entries)
        threading.Thread(target=self._validate_worker, args=(snapshot,),
                         daemon=True).start()

    def _validate_worker(self, entries):
        from scrape.ats_detect import probe_board
        for i, e in enumerate(entries):
            if e.ats_type == "direct":
                # A 'direct' page is uncountable, not unreachable — the user
                # supplied the exact careers URL, so treat it as verified-manual.
                self.after(0, self._set_status_cell, i, "direct (manual)", "direct")
                continue
            # probe_board's `reachable` (not "count is not None") is the verdict:
            # a genuinely-live board with 0 open jobs is reachable => "live (0)"
            # (verified), but a CSRF/Cloudflare-walled workday_cxs tenant (HTTP 422)
            # is unreachable => "unreachable" (flagged-unverified). A bare count
            # can't tell those apart — both look like 0.
            pr = probe_board(e)
            if pr.reachable:
                n = pr.count if pr.count is not None else 0
                self.after(0, self._set_status_cell, i, f"live ({n})", "live")
            else:
                self.after(0, self._set_status_cell, i, "unreachable", "unreachable")
        self.after(0, self._validate_done)

    def _validate_done(self):
        # The dialog may have been closed while the worker ran — don't touch
        # destroyed widgets (GUI-7).
        if not self.winfo_exists():
            return
        self._val_btn.config(state="normal")
        self._detect_btn.config(state="normal")
        self._status.config(text="Validation done.")
        # If the user hit Add on unvalidated entries, we ran validation for them;
        # now resume the add with verdicts in hand (P0-6).
        if self._pending_add:
            self._pending_add = False
            self._do_gated_add()

    def _set_status_cell(self, i, txt, kind=None):
        # Record the probe verdict regardless of whether the tree still exists,
        # so _add can gate on it even if the dialog was scrolled/closed-and-
        # reopened between validate and add.
        if kind is not None:
            self._status_by_idx[i] = kind
        if not self.winfo_exists():
            return  # GUI-7: dialog closed before this after() fired
        if self._tree.exists(str(i)):
            self._tree.set(str(i), "status", txt)

    def _add(self):
        if not self._entries:
            self._detect()
        if not self._entries:
            messagebox.showinfo("Add Companies", "Nothing to add — paste some URLs first.")
            return
        ind = self._industry.get().strip()
        for e in self._entries:
            e.industries = [ind] if ind else []
        # P0-6: the probe verdict must matter, so a board is never saved-as-live
        # without having been probed. If any entry hasn't been validated yet,
        # validate now and resume the add when the verdicts land.
        needs_probe = any(i not in self._status_by_idx
                          for i in range(len(self._entries)))
        if needs_probe:
            self._pending_add = True
            self._status.config(text="Verifying boards before adding…")
            self._validate()
            return
        self._do_gated_add()

    def _do_gated_add(self):
        """Persist entries with the probe verdict enforced (P0-6): verified
        boards (live/direct) are saved normally; unreachable boards are saved
        only if the user confirms, and then flagged-unverified so they're
        excluded from scraping until they verify."""
        from scrape.company_registry import (UNVERIFIED_FLAG, save_companies)
        verified, unreachable = partition_add_entries(self._entries,
                                                       self._status_by_idx)
        keep_unreachable = []
        if unreachable:
            names = ", ".join(e.name for e in unreachable[:6])
            more = "" if len(unreachable) <= 6 else f" (+{len(unreachable) - 6} more)"
            keep = messagebox.askyesno(
                "Some boards didn't verify",
                f"{len(unreachable)} board(s) could not be verified as live:\n"
                f"  {names}{more}\n\n"
                "These are usually wrong/guessed ATS slugs. Keep them anyway?\n\n"
                "If you keep them, they're saved but marked unverified and are "
                "NOT scraped until they verify (so they can't quietly break every "
                "future run). Choose No to discard them.")
            if keep:
                for e in unreachable:
                    e.extra = dict(getattr(e, "extra", None) or {})
                    e.extra[UNVERIFIED_FLAG] = True
                keep_unreachable = unreachable

        to_save = verified + keep_unreachable
        added = save_companies(to_save) if to_save else 0
        dropped = len(unreachable) - len(keep_unreachable)
        skipped = len(to_save) - added
        msg = f"Added {added} verified compan(ies) to companies.json."
        if keep_unreachable:
            msg += (f"\nKept {len(keep_unreachable)} unverified (excluded from "
                    "scraping until they verify).")
        if dropped:
            msg += f"\nDiscarded {dropped} unreachable board(s)."
        if skipped:
            msg += f"\nSkipped {skipped} already present."
        messagebox.showinfo("Add Companies", msg)
        if added:
            self._status.config(
                text=f"Added {added}. They're scraped on the next 'careers' search.")
        else:
            self._status.config(text="Nothing added.")


class BuildCompanyListDialog(tk.Toplevel):
    """One-click 'Build My Company List' for ANY field. Runs the
    build_company_list orchestrator: harvest employers already seen in the Inbox,
    ask an AI to name more local + remote employers for the field (auto if an API
    key is set, else a copy-paste prompt), verify each has live jobs, and save
    them to companies.json so future 'careers' searches cover them."""

    def __init__(self, parent, default_industry="", default_metro=""):
        super().__init__(parent)
        self.title("Build My Company List")
        self.geometry("760x560")
        self.configure(bg=theme.WINDOW)
        self.transient(parent)
        self.grab_set()
        self._running = False
        self._build(default_industry, default_metro)

    def _build(self, default_industry, default_metro):
        tk.Label(
            self, justify="left", wraplength=720, fg=theme.INK, bg=theme.WINDOW,
            text="Automatically build your target-company list for any field. It "
                 "harvests employers already seen in your Inbox, asks an AI to name "
                 "more local + remote employers for your field, checks each has live "
                 "jobs, and saves them — so future searches cover them.\n"
                 "No API key? Use “Get AI prompt” to copy a prompt into claude.ai, "
                 "then “Load AI reply…”. (The Inbox harvest runs with or without a key.)"
        ).pack(fill="x", padx=12, pady=(12, 6))

        row = tk.Frame(self, bg=theme.WINDOW)
        row.pack(fill="x", padx=12, pady=4)
        tk.Label(row, text="Field:", bg=theme.WINDOW, fg=theme.INK).pack(side="left")
        self._industry = tk.StringVar(value=default_industry)
        ttk.Entry(row, textvariable=self._industry, width=22).pack(side="left", padx=(4, 12))
        tk.Label(row, text="Location:", bg=theme.WINDOW, fg=theme.INK).pack(side="left")
        self._metro = tk.StringVar(value=default_metro)
        ttk.Entry(row, textvariable=self._metro, width=18).pack(side="left", padx=4)
        self._national = tk.BooleanVar(value=True)
        ttk.Checkbutton(row, text="Include nationwide/remote",
                        variable=self._national).pack(side="left", padx=8)

        # Deep seed from the open jobhive dataset — the biggest measured
        # raw-reach lever (build_company_list already supports jobhive=True).
        self._jobhive = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            self, variable=self._jobhive,
            text="Deep seed from open dataset (jobhive — finds many more employers)"
        ).pack(anchor="w", padx=12, pady=(0, 2))

        btnrow = tk.Frame(self, bg=theme.WINDOW)
        btnrow.pack(fill="x", padx=12, pady=6)
        self._build_btn = theme.btn(btnrow, "Build now", self._on_build, "accent")
        self._build_btn.pack(side="left")
        self._prompt_btn = theme.btn(btnrow, "Get AI prompt", self._on_prompt, "ghost")
        self._prompt_btn.pack(side="left", padx=6)
        self._load_btn = theme.btn(btnrow, "Load AI reply\N{HORIZONTAL ELLIPSIS}",
                                   self._on_load_reply, "ghost")
        self._load_btn.pack(side="left", padx=6)
        self._paste_btn = theme.btn(btnrow, "Paste AI reply\N{HORIZONTAL ELLIPSIS}",
                                    self._on_paste_reply, "ghost")
        self._paste_btn.pack(side="left", padx=6)
        theme.btn(btnrow, "Close", self._on_close, "ghost").pack(side="right")

        self._log = theme.text_widget(self, height=15, wrap="word")
        self._log.pack(fill="both", expand=True, padx=12, pady=(4, 6))
        self._status = tk.Label(self, text="Ready.", fg=theme.MUTED, bg=theme.WINDOW,
                                anchor="w")
        self._status.pack(fill="x", padx=12, pady=(0, 10))

    # ── logging (thread-safe: all widget writes go through self.after) ──────────
    def _append(self, text):
        if not self.winfo_exists():
            return
        self._log.insert("end", text)
        self._log.see("end")

    def _run_orchestrator(self, **kwargs):
        """Worker body shared by Build/Load: run the orchestrator with a
        thread-safe log sink and report via _build_done on the UI thread. We
        pass a `log` callback rather than redirecting sys.stdout — a global
        redirect would race with any other thread's print() (e.g. an in-flight
        Search) and funnel its output into this dialog."""
        from build_company_list import build_company_list

        def sink(*args, **kw):  # print()-compatible line sink -> UI thread
            text = " ".join(str(a) for a in args) + kw.get("end", "\n")
            self.after(0, self._append, text)

        summary = err = None
        try:
            summary = build_company_list(log=sink, **kwargs)
        except Exception as e:  # surface, never crash the GUI thread
            err = f"{type(e).__name__}: {e}"
        self.after(0, self._build_done, summary, err)

    def _on_build(self):
        if self._running:
            return
        industry = self._industry.get().strip()
        metro = self._metro.get().strip()
        if not industry and not metro:
            messagebox.showinfo("Build My Company List",
                                "Enter a field and/or location first.", parent=self)
            return
        try:
            import build_company_list as _bcl
            if not _bcl._detect_api_key():
                self._append("(No AI key configured — the Inbox harvest still runs; "
                             "a copy-paste AI prompt will appear below. For the "
                             "cleanest flow use “Get AI prompt”.)\n")
        except Exception:
            pass
        self._set_running(True)
        self._append("== Building company list… this can take a minute or two ==\n")
        if self._jobhive.get():
            self._append("(Deep seed from jobhive enabled — this pulls a large open "
                         "dataset and can take longer.)\n")
        threading.Thread(target=self._run_orchestrator,
                         kwargs=dict(industry=industry or None, metro=metro or None,
                                     national=self._national.get(), use_inbox=True,
                                     jobhive=self._jobhive.get()),
                         daemon=True).start()

    def _on_prompt(self):
        industry = self._industry.get().strip()
        metro = self._metro.get().strip() or "your area"
        try:
            from discover.enumerate import build_enumeration_prompt
            from scrape.company_registry import get_registry
            existing = [e.name for e in get_registry()]
            prompt = build_enumeration_prompt(
                metro, [industry] if industry else [], exclude_names=existing,
                angle="Include a mix of company sizes and types.", limit=60)
        except Exception as e:
            messagebox.showerror("Get AI prompt", str(e), parent=self)
            return
        self._log.delete("1.0", "end")
        self._append(prompt + "\n\n# Copy everything above into claude.ai, save its "
                     "JSON reply to a file, then click “Load AI reply…”.\n")
        self._status.config(text="Prompt ready — paste into claude.ai, then Load AI reply.")

    def _on_load_reply(self):
        if self._running:
            return
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            parent=self, title="Select the saved AI reply",
            filetypes=[("JSON/text", "*.json *.txt"), ("All files", "*.*")])
        if not path:
            return
        industry = self._industry.get().strip()
        metro = self._metro.get().strip()
        self._set_running(True)
        self._append(f"== Importing employers from {path} ==\n")
        threading.Thread(target=self._run_orchestrator,
                         kwargs=dict(industry=industry or None, metro=metro or None,
                                     use_inbox=False, in_file=path),
                         daemon=True).start()

    def _on_paste_reply(self):
        """Paste the AI's reply directly (beside the Load-file flow) — the most
        technical step a novice faces is the file picker, so accept a paste too.
        The pasted text is written to a temp file and fed through the same
        in_file import path."""
        if self._running:
            return
        dlg = PasteDialog(self, title="Paste the AI's employer list",
                          hint="Paste the AI's JSON reply of employers below:")
        if not dlg.result:
            return
        import tempfile
        try:
            fh = tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False, encoding="utf-8")
            fh.write(dlg.result)
            fh.close()
            path = fh.name
        except OSError as e:
            messagebox.showerror("Paste AI reply", str(e), parent=self)
            return
        industry = self._industry.get().strip()
        metro = self._metro.get().strip()
        self._set_running(True)
        self._append("== Importing employers from pasted reply ==\n")
        threading.Thread(target=self._run_orchestrator,
                         kwargs=dict(industry=industry or None, metro=metro or None,
                                     use_inbox=False, in_file=path),
                         daemon=True).start()

    def _build_done(self, summary, err):
        if not self.winfo_exists():
            return
        self._set_running(False)
        if err:
            self._status.config(text=f"Failed: {err}")
            self._append(f"\nERROR: {err}\n")
            return
        stats = (summary or {}).get("registry_stats") or {}
        total = sum(stats.values()) if stats else 0
        # S33: browser-only boards (Cloudflare/CSRF-walled — verified from the
        # extension) are real companies but the server can't scrape them, so call
        # them out: the user keeps them fresh by browsing with the extension, not
        # by a 'careers' run. One cheap count() call, one readout — no new state.
        try:
            from scrape.company_registry import browser_only_count
            bo = browser_only_count()
        except Exception:
            bo = 0
        bo_note = (f" ({bo} are browser-only — refresh those by visiting them "
                   "with the extension)") if bo else ""
        self._status.config(text=f"Done — registry now has {total} companies.")
        self._append(f"\nDone. Registry now has {total} companies across "
                     f"{len(stats)} tag(s){bo_note}. They're searched on your next "
                     f"'careers' run.\n")

    def _set_running(self, running):
        self._running = running
        state = "disabled" if running else "normal"
        for b in (self._build_btn, self._prompt_btn, self._load_btn,
                  self._paste_btn):
            try:
                b.config(state=state)
            except Exception:
                pass
        if running:
            self._status.config(text="Working\N{HORIZONTAL ELLIPSIS}")

    def _on_close(self):
        if self._running and not messagebox.askyesno(
                "Close", "A build is still running. Close anyway?", parent=self):
            return
        self.destroy()


class SearchTab(ttk.Frame):
    """Run a multi-source search without leaving the app; Track or Dismiss each
    result. Dismissed/tracked jobs are hidden from future searches."""

    _COLS = [
        ("score",    "Score",     55, "center"),
        ("title",    "Title",    300, "w"),
        ("company",  "Company",  160, "w"),
        ("location", "Location", 140, "w"),
        ("salary",   "Salary",   105, "w"),
        ("source",   "Source",    90, "w"),
    ]

    def __init__(self, parent, open_guide_cb=None):
        super().__init__(parent)
        self._results = []  # list[JobResult], indexed by tree iid
        self._user_cfg = self._load_cfg()
        self._open_guide_cb = open_guide_cb   # () -> None, opens Guide tab
        # Source names that self-skipped THIS search for a missing free key
        # (finding #1/#19) — populated by build_clients' skipped_keyless
        # out-param so "skipped, no key" can be told apart from "ran, found 0".
        self._skipped_keyless: list[str] = []
        self._build()

    @staticmethod
    def _load_cfg() -> dict:
        from search.cli import load_user_config
        return load_user_config()

    def _add_companies(self):
        AddCompaniesDialog(self, default_industry=self._user_cfg.get("industry", ""),
                           default_metro=self._user_cfg.get("location", ""))

    def _build_company_list(self):
        BuildCompanyListDialog(
            self, default_industry=self._user_cfg.get("industry", ""),
            default_metro=self._user_cfg.get("location", ""))

    def _build(self):
        hdr = theme.header_bar(self, "Job Search",
                               "Search many job boards at once.")
        theme.tip(theme.btn(hdr, "+ Add Companies", self._add_companies, "ghost"),
                  "Paste a company's careers-page link so its jobs appear in "
                  "future searches.").pack(side="right", padx=10, pady=8)
        theme.tip(theme.btn(hdr, "\N{SPARKLES} Build My List",
                            self._build_company_list, "accent"),
                  "Auto-build your target-company list for your field — harvest "
                  "from your Inbox, AI-suggest more, verify live jobs.").pack(
                      side="right", padx=(10, 0), pady=8)
        theme.tip_strip(
            self, "Enter keywords and a location, then click Search. Every result "
                  "is scored 0–100 for fit — Track the good ones, Dismiss the rest.")

        cfg = self._user_cfg
        ctrl = ttk.Frame(self, padding=8)
        ctrl.pack(fill="x")
        ttk.Label(ctrl, text="Keywords (comma-sep)").grid(row=0, column=0, sticky="w")
        self._kw = tk.StringVar(value=", ".join(cfg.get("keywords", [])))
        ttk.Entry(ctrl, textvariable=self._kw, width=50).grid(
            row=0, column=1, sticky="ew", padx=6)
        ttk.Label(ctrl, text="Location").grid(row=0, column=2, sticky="w")
        self._loc = tk.StringVar(value=cfg.get("location") or DEFAULT_LOCATION)
        ttk.Entry(ctrl, textvariable=self._loc, width=18).grid(row=0, column=3, padx=6)
        self._search_btn = theme.btn(ctrl, "Search", self._search, "accent")
        self._search_btn.grid(row=0, column=4, padx=8)
        # Cancel is enabled only while a search runs; backed by a threading.Event
        # the engine checks between clients/keywords/companies.
        self._cancel_event = None
        self._cancel_btn = theme.btn(ctrl, "Cancel", self._cancel_search, "ghost")
        self._cancel_btn.grid(row=0, column=6, padx=4)
        self._cancel_btn.config(state="disabled")
        self._save_btn = theme.btn(ctrl, "Save", self._save_searches, "ghost")
        theme.tip(self._save_btn, "Save current keywords/location/salary as "
                  "defaults for this project.")
        self._save_btn.grid(row=0, column=5, padx=4)
        self._hide_tracked = tk.BooleanVar(value=True)
        ttk.Checkbutton(ctrl, text="Hide tracked / dismissed",
                        variable=self._hide_tracked).grid(
            row=1, column=1, sticky="w", pady=4)
        ttk.Label(ctrl, text="Min salary $").grid(row=1, column=2, sticky="e")
        self._salary = tk.StringVar(
            value=str(cfg.get("salary_min") or ""))
        ttk.Entry(ctrl, textvariable=self._salary, width=10).grid(
            row=1, column=3, sticky="w", padx=6)
        self._status = tk.Label(ctrl, text="", font=theme.FONT_SM,
                                bg=theme.WINDOW, fg=theme.MUTED)
        self._status.grid(row=2, column=1, columnspan=4, sticky="w")
        # Progress bar -- visible only while a search is running. Switches to
        # determinate once the engine reports how many sources it will query.
        self._pb = ttk.Progressbar(ctrl, mode='indeterminate', length=200)
        self._pb.grid(row=2, column=5, sticky="w", padx=4)
        self._pb.grid_remove()   # hidden until search starts
        # End-of-run source-health summary + a Details popup over the collected
        # per-source table. Blank until a search finishes.
        self._health = tk.StringVar(value="")
        self._health_lbl = tk.Label(ctrl, textvariable=self._health,
                                    font=theme.FONT_SM, bg=theme.WINDOW,
                                    fg=theme.MUTED, cursor="hand2")
        self._health_lbl.grid(row=2, column=6, sticky="w", padx=4)
        self._health_lbl.bind("<Button-1>", lambda _e: self._show_health_details())
        self._source_health: list[dict] = []  # per-source rows from the last run
        ctrl.columnconfigure(1, weight=1)

        tf = ttk.Frame(self)
        tf.pack(fill="both", expand=True, padx=6, pady=2)
        self._tree = ttk.Treeview(tf, columns=[c[0] for c in self._COLS],
                                  show="headings", selectmode="extended")
        for col, label, width, anchor in self._COLS:
            self._tree.heading(col, text=label)
            self._tree.column(col, width=width, anchor=anchor, minwidth=45)
        theme.zebra(self._tree)
        vsb = ttk.Scrollbar(tf, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self._tree.bind("<Double-1>", lambda _e: self._open_url())

        # Why-this-score detail line
        self._detail = tk.Label(self, text="", anchor="w", bg=theme.SURFACE,
                                fg=theme.MUTED, font=theme.FONT_SM, padx=8)
        self._detail.pack(fill="x", padx=6)
        self._tree.bind("<<TreeviewSelect>>", self._show_detail)

        abar = tk.Frame(self, bg=theme.WINDOW, pady=6)
        abar.pack(fill="x", padx=6, side="bottom")
        # Keep references so the whole action bar can be disabled during a
        # search worker (GUI-8: re-entrancy guard, not just the Search button).
        self._action_btns = []
        specs = [("Track \N{BLACK RIGHT-POINTING SMALL TRIANGLE} Interested",
                  self._track, "accent"),
                 ("Dismiss", self._dismiss, "ghost"),
                 ("Add all to Inbox", self._add_results_to_inbox, "ghost"),
                 ("Open", self._open_url, "ghost")]
        for text, cmd, kind in specs:
            b = theme.btn(abar, text, cmd, kind)
            b.pack(side="left", padx=2)
            self._action_btns.append(b)
        tk.Label(abar, text="  Ctrl/Shift-click to select multiple",
                 bg=theme.WINDOW, fg=theme.FAINT, font=theme.FONT_SM).pack(side="left")

    def _save_searches(self):
        """Persist current keyword/location/salary fields to the workspace config
        so the Search tab pre-fills them next session."""
        keywords = [k.strip() for k in self._kw.get().split(",") if k.strip()]
        loc = self._loc.get().strip()
        try:
            salary_min = int(self._salary.get().strip() or 0) or None
        except ValueError:
            salary_min = None
        cfg = workspace.load_config()
        if keywords:
            cfg["keywords"] = keywords
        elif "keywords" in cfg:
            del cfg["keywords"]
        if loc:
            cfg["location"] = loc
        if salary_min:
            cfg["salary_min"] = salary_min
        elif "salary_min" in cfg:
            del cfg["salary_min"]
        workspace.save_config(cfg)
        set_status(self._status, "Search settings saved to this project.", "ok")

    def _set_busy(self, busy: bool):
        """Disable/enable the search + result controls for the worker's
        duration, so a second search can't fire mid-flight (GUI-8)."""
        state = "disabled" if busy else "normal"
        self._search_btn.config(state=state)
        self._save_btn.config(state=state)
        for b in self._action_btns:
            b.config(state=state)
        # Cancel is the inverse: live only while a search runs.
        self._cancel_btn.config(state="normal" if busy else "disabled")
        if busy:
            self._pb.grid()
            # Start indeterminate; the engine's first "start" event flips it to
            # determinate once it knows the source count.
            self._pb.configure(mode="indeterminate")
            self._pb.start(15)
        else:
            self._pb.stop()
            self._pb.configure(mode="indeterminate", value=0)
            self._pb.grid_remove()

    def _search(self):
        keywords = [k.strip() for k in self._kw.get().split(",") if k.strip()]
        if not keywords:
            if self._open_guide_cb:
                self._open_guide_cb()
            else:
                set_status(self._status,
                           "Enter at least one keyword, then click Search.", "err")
            return
        try:
            salary_min = int(self._salary.get().strip() or 0) or None
        except ValueError:
            messagebox.showerror("Bad salary", "Min salary must be a number.")
            return
        self._cancel_event = threading.Event()
        self._source_health = []
        self._skipped_keyless = []
        self._health.set("")
        self._set_busy(True)
        set_status(self._status, "Searching…", "work")
        threading.Thread(
            target=self._worker,
            args=(keywords, self._loc.get().strip() or DEFAULT_LOCATION,
                  salary_min, self._hide_tracked.get(), self._cancel_event),
            daemon=True,
        ).start()

    def _cancel_search(self):
        """Signal the running search to stop after in-flight sources finish."""
        if self._cancel_event is not None:
            self._cancel_event.set()
            set_status(self._status, "Cancelling — finishing in-flight sources…",
                       "muted")
            self._cancel_btn.config(state="disabled")

    def _on_progress(self, event):
        """Engine progress callback (worker thread) -> marshal to the Tk thread."""
        self.after(0, self._render_progress, event)

    def _render_progress(self, event):
        if not self.winfo_exists():
            return
        phase = event.get("phase")
        if phase == "start":
            total = event.get("total", 0) or 0
            self._pb.stop()
            self._pb.configure(mode="determinate", maximum=max(total, 1), value=0)
        elif phase == "source_start":
            set_status(self._status,
                       f"Searching — {event.get('source', '')}…", "work")
        elif phase == "source_done":
            done = event.get("done", 0)
            total = event.get("total", 0)
            try:
                self._pb.configure(value=done)
            except tk.TclError:
                pass
            src = event.get("source", "")
            skipped = self._class_is_keyless_skipped(src, self._skipped_keyless)
            self._source_health.append({
                "source": src,
                "count": event.get("count", 0),
                "ok": bool(event.get("ok", True)),
                "error": event.get("error", ""),
                "skipped_keyless": skipped,
            })
            set_status(self._status,
                       self._progress_line(src, done, total,
                                           event.get("count", 0), skipped),
                       "work")

    @staticmethod
    def _class_is_keyless_skipped(class_name: str, skipped_keyless: list[str]) -> bool:
        """True when `class_name` (a progress event's source, e.g. 'JoobleClient')
        names one of the sources build_clients reported as keyless-skipped this
        run (e.g. 'jooble'). Matches by case-insensitive prefix — every client
        class is named '<SourceKey>Client' (AdzunaClient, CareerOneStopClient,
        JoobleClient, ...) — so this never needs a hardcoded name table and
        tracks whatever build_clients' own skip logic actually reported. Pure/
        static so it is unit-testable without a Tk root."""
        low = (class_name or "").lower()
        return any(low.startswith((s or "").lower()) for s in (skipped_keyless or []))

    @staticmethod
    def _progress_line(src: str, done: int, total: int, count: int,
                       skipped_keyless: bool) -> str:
        """The per-source progress status text. A source build_clients flagged
        as self-skipped (no key) says so explicitly instead of a bare '(0)',
        which otherwise looks identical to a source that ran and legitimately
        found nothing today. Pure/static so it is unit-testable without a Tk
        root."""
        if skipped_keyless:
            return (f"source {done}/{total} — {src}: skipped — needs a free key "
                    f"(Settings → Source keys)")
        return f"source {done}/{total} — {src} ({count})"

    def _worker(self, keywords, location, salary_min, hide_tracked, cancel=None):
        try:
            from search.cli import build_clients, ALL_SOURCES
            from search.search_engine import SearchEngine
            from match.scorer import score_jobs
            # Respect the user's source toggles (Settings) like the CLI does
            # (cli.py: [s for s in ALL_SOURCES if cfg_sources.get(s, True)]).
            # Previously the GUI queried ALL_SOURCES unconditionally, so every
            # search spent the paid JSearch 200/month quota and hit sources the
            # user had disabled.
            _cfg_sources = (self._user_cfg or {}).get("sources", {}) or {}
            _ind = (self._user_cfg or {}).get("industry") or ""
            _sources = [s for s in ALL_SOURCES if _cfg_sources.get(s, True)]
            # Drop tech/remote-skewed boards for a non-knowledge-work field
            # (no-op for eng/knowledge-work fields; explicit toggle still wins).
            from search.keyword_strategy import gate_tech_sources
            _sources = gate_tech_sources(_sources, _ind, _cfg_sources)
            # Scope the careers registry to the project's field and let the
            # careers leg tier its scrape (active boards first) — the params
            # already exist in cli.build_clients; the GUI was running a full,
            # unfiltered 627-board scrape (P6). No-op for a blank industry.
            # Collect sources that self-skipped for a missing free key this run
            # (finding #1/#19) so the progress line + end summary can tell that
            # apart from a source that ran and legitimately found 0.
            _skipped: list[str] = []
            clients = build_clients(_sources, cache_enabled=True,
                                    industry_filter=_ind or None,
                                    tiered_careers=True,
                                    location=location,
                                    skipped_keyless=_skipped)
            self._skipped_keyless = _skipped
            # Broaden the QUERY keywords for API recall (search broad, score
            # narrow); the original `keywords` stay the scoring set below. No-op
            # for eng IC titles. Opt out with "broaden_keywords": false in config.
            from search.keyword_strategy import broad_query_keywords
            if (self._user_cfg or {}).get("broaden_keywords", True):
                import industry_profile
                _syn = industry_profile.resolve(_ind).query_synonyms
                query_keywords = broad_query_keywords(keywords, _ind, synonyms=_syn)
            else:
                query_keywords = keywords
            if clients:
                _engine = SearchEngine(clients)
                results = _engine.run_full_search(
                    keywords=query_keywords, location=location,
                    salary_min=salary_min, max_pages_per_keyword=2,
                    progress=self._on_progress, cancel=cancel)
                # Persist tiering state so a tiered careers leg advances its
                # active/quiet board buckets (mirrors daily_run).
                for c in clients:
                    if hasattr(c, "finalize_tiering"):
                        try:
                            c.finalize_tiering()
                        except Exception:
                            pass
            else:
                results = []
            if hide_tracked and results:
                seen = seen_urls()
                results = [r for r in results if normalize_url(r.url) not in seen]
            if results:
                try:
                    import preferences as _prefs
                    _hard = _prefs.load().get("hard", {})
                    _remote_ok = bool(_hard.get("remote_ok", True))
                    _remote_regions_ok = bool(_hard.get("remote_regions_ok", False))
                except Exception:
                    _remote_ok = True
                    _remote_regions_ok = False
                score_jobs(results, keywords=keywords, location=location,
                           salary_floor=salary_min,
                           exclude_keywords=self._user_cfg.get("exclude_keywords", []),
                           exclude_titles=self._user_cfg.get("exclude_titles"),
                           title_miss_penalty=self._user_cfg.get("title_miss_penalty"),
                           seniority_exclude=self._user_cfg.get("seniority_exclude"),
                           remote_ok=_remote_ok,
                           seniority_target=self._user_cfg.get("seniority_target"),
                           years_cap=self._user_cfg.get("years_cap"),
                           remote_regions_ok=_remote_regions_ok,
                           title_context_required=self._user_cfg.get("title_context_required"))
            self.after(0, self._on_done, results, bool(clients))
        except Exception as exc:
            self.after(0, self._on_error, str(exc))

    def _on_done(self, results, had_clients):
        # The tab may have been destroyed (project switch) while the search ran
        # — bail before touching widgets (GUI-7).
        if not self.winfo_exists():
            return
        self._set_busy(False)
        self._results = results
        for row in self._tree.get_children():
            self._tree.delete(row)
        for i, j in enumerate(results):
            self._tree.insert("", "end", iid=str(i), tags=(theme.row_tag(i),), values=(
                j.score if j.score >= 0 else "",
                j.title, j.company, j.location, j.salary_display(), j.source_api))
        self._update_health_summary()
        if not had_clients:
            set_status(self._status,
                       "No sources configured -- add API keys to .env.", "err")
        elif not results:
            set_status(self._status,
                       "No results. Try broader keywords or a different location.",
                       "muted")
        else:
            set_status(self._status, f"{len(results)} result(s).", "ok")

    def _update_health_summary(self):
        """One-line end-of-run source health: 'N ok, M skipped (no key), K
        throttled'. Click it for a per-source Details popup."""
        self._health.set(self._health_summary_line(self._source_health))

    @staticmethod
    def _health_summary_line(rows: list[dict]) -> str:
        """Pure formatter for the end-of-run source-health line. `skipped` is
        counted from each row's real `skipped_keyless` flag (set from
        build_clients' own skip data — finding #1/#19) first; the old
        error-string heuristic ("key"/"auth"/401/403) is kept only as a
        fallback for a row that predates the flag, so a genuine auth failure
        from a source that HAS a key (e.g. a revoked/expired one) still shows
        as skipped rather than a bare failure. Pure/static so it is unit-
        testable without a Tk root."""
        if not rows:
            return ""
        ok = throttled = skipped = failed = 0
        for r in rows:
            if r.get("skipped_keyless"):
                skipped += 1
                continue
            if r["ok"] and r["count"] >= 0:
                ok += 1
                continue
            err = (r.get("error") or "").lower()
            if "429" in err or "throttl" in err or "rate" in err:
                throttled += 1
            elif "key" in err or "auth" in err or "401" in err or "403" in err:
                skipped += 1
            else:
                failed += 1
        parts = [f"{ok} ok"]
        if skipped:
            parts.append(f"{skipped} skipped (no key)")
        if throttled:
            parts.append(f"{throttled} throttled")
        if failed:
            parts.append(f"{failed} failed")
        return "Sources: " + ", ".join(parts) + "  (details)"

    def _show_health_details(self):
        if not self._source_health:
            return
        messagebox.showinfo("Source health (last search)",
                            self._health_details_text(self._source_health),
                            parent=self)

    @staticmethod
    def _health_details_text(rows: list[dict]) -> str:
        """Pure formatter for the per-source Details popup body. A row flagged
        skipped_keyless names the real reason instead of a bare result count.
        Pure/static so it is unit-testable without a Tk root."""
        lines = []
        for r in sorted(rows, key=lambda x: x["source"].lower()):
            if r.get("skipped_keyless"):
                lines.append(f"{r['source']}: skipped — needs a free key")
            elif r["ok"]:
                lines.append(f"{r['source']}: {r['count']} result(s)")
            else:
                lines.append(f"{r['source']}: FAILED — {r.get('error') or 'unknown'}")
        return "\n".join(lines)

    def _add_results_to_inbox(self):
        """Offer to add the current search results to the Inbox for triage. Uses
        inbox_add_many with the project's per-company cap, pinned to the active
        project (the S27-safe pattern) so a background project switch can't
        misroute the write."""
        if not self._results:
            messagebox.showinfo("Add to Inbox", "Run a search first.", parent=self)
            return
        n = len(self._results)
        if not messagebox.askyesno(
                "Add to Inbox",
                f"Add these {n} result(s) to your Inbox for triage?",
                parent=self):
            return
        slug = workspace.active_slug()
        cap = 0
        try:
            cap = int(self._user_cfg.get("max_per_company", 15) or 0)
        except (TypeError, ValueError):
            cap = 0
        from tracker.db import inbox_add_many
        workspace.pin_active(slug)   # pin BEFORE the db write
        try:
            ok, added = db_guard(
                self, lambda: inbox_add_many(self._results, per_company_cap=cap),
                status_cb=lambda m: set_status(self._status, m, "err"),
                action="add to inbox")
        finally:
            workspace.unpin_active()
        if not ok:
            return
        set_status(self._status, f"Added {added} to your Inbox.", "ok")

    def _on_error(self, msg):
        if not self.winfo_exists():
            return  # GUI-7
        self._set_busy(False)
        set_status(self._status, f"Error: {msg}", "err")

    def _sel_many(self):
        return [self._results[int(iid)] for iid in self._tree.selection()]

    def _show_detail(self, _event=None):
        sel = self._sel_many()
        self._detail.config(
            text=sel[0].score_notes if len(sel) == 1 else "")

    def _track(self):
        sel = self._sel_many()
        if not sel:
            messagebox.showinfo("No selection", "Select result(s) first.")
            return
        # Dedup + insert moved into the service (dup-guard lives there now).
        ok, res = db_guard(
            self, lambda: tracker_service.track_search_results(sel),
            status_cb=lambda m: set_status(self._status, m, "err"),
            action="track results")
        if not ok:
            return
        added, skipped = res
        msg = f"Tracked {added} job(s)."
        if skipped:
            msg += f" Skipped {skipped} already tracked/dismissed."
        set_status(self._status, msg, "info")

    def _dismiss(self):
        sel_iids = list(self._tree.selection())
        if not sel_iids:
            return
        ok, _ = db_guard(
            self,
            lambda: [tracker_service.dismiss_url(self._results[int(i)].url)
                     for i in sel_iids],
            status_cb=lambda m: set_status(self._status, m, "err"),
            action="dismiss results")
        if not ok:
            return
        for iid in sel_iids:
            self._tree.delete(iid)
        set_status(
            self._status,
            f"Dismissed {len(sel_iids)} — hidden from future searches.", "muted")

    def _open_url(self):
        for j in self._sel_many()[:5]:
            u = safe_url(j.url)
            if u:
                webbrowser.open(u)


# ── Apply Queue tab ───────────────────────────────────────────────────────────
class ApplyQueueTab(ttk.Frame):
    """Throughput core: every 'interested' job ranked best-first. Per job —
    open the posting, generate tailored docs (clipboard bridge or API), then
    one click marks it applied and advances to the next."""

    _COLS = [
        ("fit",      "Fit",       45, "center"),
        ("score",    "Score",     55, "center"),
        ("title",    "Title",    290, "w"),
        ("company",  "Company",  150, "w"),
        ("location", "Location", 120, "w"),
        ("salary",   "Salary",   100, "w"),
        ("docs",     "Docs",      45, "center"),
    ]

    _BATCH_LIMIT = 5  # resumes per paste round-trip — more starves each one

    def __init__(self, parent):
        super().__init__(parent)
        self._rows: dict[str, dict] = {}
        self._prompt_job_id: int | None = None  # job the copied prompt is for
        self._batch_order: list[int] = []  # job ids in last batch-prompt order
        self._fit_order: list[int] = []
        self._fit_jobs: list = []  # JobResults for the last fit prompt
        self._build()
        self.refresh()

    def _build(self):
        hdr = theme.header_bar(self, "Apply Queue",
                               "Interested jobs, best match first.")
        self._count_lbl = tk.Label(hdr, text="", bg=theme.SURFACE,
                                    fg=theme.MUTED, font=theme.FONT_SM)
        self._count_lbl.pack(side="right", padx=14)
        theme.tip_strip(
            self, "Jobs you're interested in. Make a tailored resume, open the "
                  "posting and submit, then “Mark Applied ▸ Next”. "
                  "Keys: T applied · D dismiss · O open.")

        tf = ttk.Frame(self)
        tf.pack(fill="both", expand=True, padx=6, pady=2)
        self._tree = ttk.Treeview(tf, columns=[c[0] for c in self._COLS],
                                  show="headings", selectmode="browse")
        for col, label, width, anchor in self._COLS:
            self._tree.heading(col, text=label)
            self._tree.column(col, width=width, anchor=anchor, minwidth=40)
        theme.zebra(self._tree)
        vsb = ttk.Scrollbar(tf, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self._tree.bind("<Double-1>", lambda _e: self._open_url())
        self._tree.bind("<<TreeviewSelect>>", self._show_detail)
        # Keyboard triage with auto-advance, matching the Inbox tab (UX gap a):
        # t = mark applied & advance, d = dismiss/archive & advance, o = open.
        self._tree.bind("t", lambda _e: self._mark_applied())
        self._tree.bind("d", lambda _e: self._dismiss_queue())
        self._tree.bind("o", lambda _e: self._open_url())

        self._detail = tk.Label(self, text="", anchor="w", justify="left",
                                bg=theme.SURFACE, fg=theme.MUTED, font=theme.FONT_SM,
                                padx=8, wraplength=1100)
        self._detail.pack(fill="x", padx=6)

        abar = tk.Frame(self, bg=theme.WINDOW, pady=6)
        abar.pack(fill="x", padx=6, side="bottom")
        self._abar = abar  # disabled wholesale during the API worker (GUI-8)
        TRI = "\N{BLACK RIGHT-POINTING SMALL TRIANGLE}"
        theme.btn(abar, "Open", self._open_url, "ghost").pack(side="left", padx=2)
        theme.tip(theme.btn(abar, "Copy Resume Prompt", self._copy_resume_prompt, "ghost"),
                  "Copy a tailoring prompt for the selected job; paste it into "
                  "claude.ai.").pack(side="left", padx=2)
        theme.btn(abar, f"Paste Reply {TRI} DOCX", self._paste_resume, "ghost").pack(side="left", padx=2)
        theme.tip(theme.btn(abar, f"Batch Prompt ({self._BATCH_LIMIT})",
                            self._copy_batch_prompt, "ghost"),
                  f"Make one prompt for the next {self._BATCH_LIMIT} jobs at once.").pack(side="left", padx=(10, 2))
        theme.btn(abar, f"Paste Batch {TRI} DOCX", self._paste_batch, "ghost").pack(side="left", padx=2)
        from resume.service import api_available
        if api_available():
            theme.btn(abar, "Generate via API", self._generate_api, "ghost").pack(side="left", padx=2)
        theme.tip(theme.btn(abar, f"Mark Applied {TRI} Next", self._mark_applied, "success"),
                  "Mark the selected job applied and jump to the next one.").pack(side="left", padx=(16, 2))
        theme.tip(theme.btn(abar, "Ask AI to rank", self._copy_fit_prompt, "ghost"),
                  "Copy a prompt asking an AI to grade these jobs' fit.").pack(side="left", padx=(16, 2))
        theme.tip(theme.btn(abar, "Paste AI ranking", self._paste_fit, "ghost"),
                  "Paste the AI's reply to apply its Fit grades.").pack(side="left", padx=2)
        self._status = tk.Label(abar, text="", bg=theme.WINDOW, fg=theme.MUTED,
                                font=theme.FONT_SM)
        self._status.pack(side="left", padx=10)

    def refresh(self, keep_selection=False):
        prev = self._tree.selection()
        self._rows = {}
        for iid in self._tree.get_children():
            self._tree.delete(iid)
        jobs = get_all("interested")
        jobs.sort(key=lambda j: (j.get("fit_score") or -1,
                                 j.get("score") or -1), reverse=True)
        for i, j in enumerate(jobs):
            iid = str(j["id"])
            self._rows[iid] = j
            self._tree.insert("", "end", iid=iid, tags=(theme.row_tag(i),), values=(
                j["fit_score"] if (j.get("fit_score") or -1) >= 0 else "",
                j["score"] if (j.get("score") or -1) >= 0 else "",
                j["title"], j["company"], j.get("location", ""),
                j.get("salary_text", ""),
                "✓" if j.get("resume_path") else ""))
        self._count_lbl.config(text=f"{len(jobs)} to apply")
        if keep_selection and prev and prev[0] in self._rows:
            self._tree.selection_set(prev[0])
        elif self._tree.get_children():
            first = self._tree.get_children()[0]
            self._tree.selection_set(first)
            self._tree.see(first)

    def _sel(self) -> dict | None:
        sel = self._tree.selection()
        return self._rows.get(sel[0]) if sel else None

    def _show_detail(self, _event=None):
        j = self._sel()
        if not j:
            self._detail.config(text="")
            return
        bits = []
        if j.get("fit_rationale"):
            bits.append(j["fit_rationale"])
        # ATS hint (SB-6): naming the applicant-tracking system at apply time lets
        # the user format their resume for that parser. From the URL only — no
        # network, no AI. The fuller keyword-overlap read lives in the Inbox detail.
        try:
            ats = atshintmod.ats_label(j.get("url", ""))
            if ats:
                bits.append(f"Applies through {ats}")
        except Exception:
            pass
        # Referral nudge: surface known contacts at this company (highest-
        # conversion channel). contacts_for_company is queried through the service.
        hint = tracker_service.referral_hint(j.get("company", ""))
        if hint:
            bits.append(hint)
        if j.get("resume_path"):
            bits.append(f"Docs: {j['resume_path']}")
        self._detail.config(text="   |   ".join(bits))

    def _open_url(self):
        j = self._sel()
        surl = safe_url((j or {}).get("url")) if j else ""
        if surl:
            webbrowser.open(surl)
        elif j:
            messagebox.showinfo("No URL", "This job has no URL saved.")

    def _set_busy(self, busy: bool):
        """Disable/enable every action-bar button for the API worker's duration
        so a second generate can't fire mid-flight (GUI-8)."""
        state = "disabled" if busy else "normal"
        for w in self._abar.winfo_children():
            if isinstance(w, (ttk.Button, tk.Button)):
                w.config(state=state)

    # ── Resume docs (bridge) ──────────────────────────────────────────────────

    def _posting_text(self, j: dict) -> str | None:
        """Job description from the DB, or ask the user to paste the posting."""
        if (j.get("description") or "").strip():
            return j["description"]
        dlg = PasteDialog(self, title="Paste the job posting",
                          hint="No saved description for this job — paste the "
                               "posting text from the job page:")
        if dlg.result:
            db_guard(self, lambda: tracker_service.update_job(
                j["id"], description=dlg.result[:5000]),
                status_cb=lambda m: set_status(self._status, m, "err"),
                action="save description")
            return dlg.result
        return None

    def _copy_resume_prompt(self):
        j = self._sel()
        if not j:
            messagebox.showinfo("No selection", "Select a job first.")
            return
        posting = self._posting_text(j)
        if not posting:
            return
        from resume.service import build_prompt
        try:
            prompt = build_prompt(
                f"Title: {j['title']}\nCompany: {j['company']}\n"
                f"Location: {j.get('location','')}\n\n{posting}")
        except Exception as e:
            messagebox.showerror("Prompt failed", str(e), parent=self)
            return
        self._prompt_job_id = j["id"]
        copy_or_warn(self, prompt,
                     lambda m: self._status.config(text=m, fg=theme.WARN))

    def _paste_resume(self):
        if self._prompt_job_id is None:
            messagebox.showinfo("No prompt", "Copy a resume prompt first.")
            return
        j = tracker_service.get_job(self._prompt_job_id)
        if not j:
            return
        dlg = PasteDialog(self)
        if not dlg.result:
            return
        from claude_bridge import parse_resume_response
        from resume.service import save_bundle_from_data
        try:
            data = parse_resume_response(dlg.result)
            resume_path, cover_path = save_bundle_from_data(
                data, workspace.output_dir(), company=j["company"])
        except BridgeParseError as e:
            messagebox.showerror("Parse failed", str(e), parent=self)
            return
        except Exception as e:
            messagebox.showerror("DOCX failed", str(e), parent=self)
            return
        ok, _ = db_guard(self, lambda: tracker_service.update_job(
            j["id"], resume_path=str(resume_path),
            cover_path=str(cover_path) if cover_path else ""),
            status_cb=lambda m: set_status(self._status, m, "err"),
            action="save docs")
        if not ok:
            return
        set_status(self._status, f"Docs saved: {resume_path.name}", "ok")
        self.refresh(keep_selection=True)

    # ── Batch resume docs (bridge) ────────────────────────────────────────────

    def _copy_batch_prompt(self):
        """One prompt covering the next few queue jobs that still need docs.
        Uses selected rows if any; otherwise walks the queue top-down. Only
        jobs with a saved description qualify — batch mode can't stop to ask
        for a paste per job."""
        sel = [r for r in (self._rows.get(i) for i in self._tree.selection())
               if r]
        pool = sel or list(self._rows.values())
        batch = [j for j in pool
                 if not j.get("resume_path")
                 and (j.get("description") or "").strip()][:self._BATCH_LIMIT]
        if not batch:
            messagebox.showinfo(
                "Nothing to batch",
                "No queue jobs with a saved description still need docs.\n"
                "(Jobs without a description need the single-job flow, which "
                "asks you to paste the posting.)", parent=self)
            return
        from resume.service import build_batch_prompt
        postings = [
            f"Title: {j['title']}\nCompany: {j['company']}\n"
            f"Location: {j.get('location', '')}\n\n{j['description']}"
            for j in batch]
        try:
            prompt = build_batch_prompt(postings)
        except Exception as e:
            messagebox.showerror("Prompt failed", str(e), parent=self)
            return
        self._batch_order = [j["id"] for j in batch]
        names = ", ".join(j["company"] for j in batch)
        self._status.config(text=f"Batch of {len(batch)}: {names}", fg=theme.WARN)
        copy_or_warn(self, prompt,
                     lambda m: self._status.config(text=m, fg=theme.WARN))

    def _paste_batch(self):
        if not self._batch_order:
            messagebox.showinfo("No prompt", "Copy a batch prompt first.")
            return
        dlg = PasteDialog(self)
        if not dlg.result:
            return
        from claude_bridge import parse_batch_resume_response
        from resume.service import save_bundle_from_data
        try:
            parsed = parse_batch_resume_response(dlg.result)
        except BridgeParseError as e:
            messagebox.showerror("Parse failed", str(e), parent=self)
            return
        saved, failed = 0, []
        for n, data in parsed.items():
            if not (1 <= n <= len(self._batch_order)):
                continue
            j = tracker_service.get_job(self._batch_order[n - 1])
            if not j:
                continue
            try:
                resume_path, cover_path = save_bundle_from_data(
                    data, workspace.output_dir(), company=j["company"])
            except Exception as e:
                failed.append(f"{j['company']}: {e}")
                continue
            ok, _ = db_guard(self, lambda jid=j["id"], rp=resume_path, cp=cover_path:
                             tracker_service.update_job(
                                 jid, resume_path=str(rp),
                                 cover_path=str(cp) if cp else ""),
                             action="save batch docs")
            if not ok:
                failed.append(f"{j['company']}: database busy")
                continue
            saved += 1
        if failed:
            messagebox.showerror(
                "Some docs failed",
                f"Saved {saved}, failed {len(failed)}:\n" + "\n".join(failed),
                parent=self)
        missing = len(self._batch_order) - saved - len(failed)
        text = f"Batch: saved docs for {saved}/{len(self._batch_order)} job(s)."
        if missing > 0:
            text += f" {missing} missing from the reply — re-paste or run singly."
        self._status.config(text=text, fg=theme.SUCCESS if saved else _ui_common.ERR)
        self.refresh(keep_selection=True)

    def _generate_api(self):
        j = self._sel()
        if not j:
            messagebox.showinfo("No selection", "Select a job first.")
            return
        posting = self._posting_text(j)
        if not posting:
            return
        self._set_busy(True)
        set_status(self._status, "Generating with Claude API…", "work")

        def worker():
            try:
                from resume.service import save_bundle
                resume_path, cover_path = save_bundle(posting, workspace.output_dir(),
                                                      company=j["company"])
                self.after(0, lambda: self._api_done(j["id"], resume_path, cover_path))
            except Exception as e:
                self.after(0, lambda: self._api_error(str(e)))
        threading.Thread(target=worker, daemon=True).start()

    def _api_error(self, msg):
        if not self.winfo_exists():
            return  # GUI-7: tab gone (project switch) before the worker returned
        self._set_busy(False)
        set_status(self._status, f"Error: {msg}", "err")

    def _api_done(self, job_id, resume_path, cover_path=None):
        if not self.winfo_exists():
            return  # GUI-7
        self._set_busy(False)
        ok, _ = db_guard(self, lambda: tracker_service.update_job(
            job_id, resume_path=str(resume_path),
            cover_path=str(cover_path) if cover_path else ""),
            status_cb=lambda m: set_status(self._status, m, "err"),
            action="save docs")
        if not ok:
            return
        set_status(self._status, f"Docs saved: {resume_path.name}", "ok")
        self.refresh(keep_selection=True)

    # ── Applied ▸ next ────────────────────────────────────────────────────────

    def _mark_applied(self):
        sel = self._tree.selection()
        j = self._sel()
        if not j:
            messagebox.showinfo("No selection", "Select a job first.")
            return
        nxt = self._tree.next(sel[0])
        # The date_applied stamp + a +7-day follow-up nudge are now applied
        # centrally in db.update_job's status->'applied' branch (D1 P5), so every
        # entry path (this button, Tracker quick-status, Flask, API, extension)
        # arms the same follow-up engine. This call just sets the status.
        ok, _ = db_guard(self, lambda: tracker_service.update_job(
            j["id"], status="applied"),
            status_cb=lambda m: set_status(self._status, m, "err"),
            action="mark applied")
        if not ok:
            return
        set_status(self._status, f"Applied: {j['title']} @ {j['company']}", "ok")
        self.refresh()
        if nxt and nxt in self._rows:
            self._tree.selection_set(nxt)
            self._tree.see(nxt)
            self._tree.focus(nxt)
            self._tree.focus_set()  # keep t/d/o live for the next row

    def _dismiss_queue(self):
        """Keyboard 'd' triage: archive the selected interested job (removes it
        from the queue, restorable from the Tracker archive) and advance."""
        sel = self._tree.selection()
        j = self._sel()
        if not j:
            return
        nxt = self._tree.next(sel[0])
        ok, _ = db_guard(self, lambda: tracker_service.archive_job(j["id"]),
                         status_cb=lambda m: set_status(self._status, m, "err"),
                         action="dismiss job")
        if not ok:
            return
        set_status(self._status,
                   f"Dismissed: {j['title']} @ {j['company']} (archived)", "muted")
        self.refresh()
        if nxt and nxt in self._rows:
            self._tree.selection_set(nxt)
            self._tree.see(nxt)
            self._tree.focus(nxt)
            self._tree.focus_set()

    # ── Claude fit scoring (bridge) ───────────────────────────────────────────

    def _copy_fit_prompt(self):
        rows = list(self._rows.values())[:20]
        if not rows:
            messagebox.showinfo("Queue empty", "Nothing to score.")
            return
        # Route through the service: preference-anchored prompt + token-verified
        # scoring (so a reordered/skipped reply lands on the right application).
        # Compact, gated AI request (spec-2026-06-29): facts+rubric, structural
        # non-fits filtered out before the prompt.
        prompt, jobs, dropped = tracker_service.compact_fit_prompt_for_rows(rows)
        if not jobs:
            reasons = ", ".join(sorted({r for d in dropped for r in d["reasons"]}))
            messagebox.showinfo(
                "All auto-filtered",
                f"All {len(rows)} queued job(s) were auto-filtered ({reasons}).",
                parent=self)
            return
        self._fit_jobs = jobs
        self._fit_order = [r["id"] for r in rows]  # legacy/back-compat
        # API auto-route: when a key is present, rank directly without paste step.
        if _ranker_mod.has_api_key():
            # Single-flight guard (mirrors the Inbox tab): overlapping ranks
            # mint multiple batches and break one-click Undo.
            if getattr(self, "_api_ranking", False):
                set_status(self._status,
                           "An AI ranking is already running - wait for it to "
                           "finish.", "work")
                return
            self._api_ranking = True
            n = len(jobs)
            suffix = (f"; auto-filtered {len(dropped)}" if dropped else "")
            set_status(self._status, f"Ranking {n} job(s) via API{suffix}...", "work")
            threading.Thread(
                target=self._api_rank_worker, args=(prompt, jobs), daemon=True).start()
        else:
            # Clipboard bridge: user pastes prompt into claude.ai and pastes reply back.
            copy_or_warn(self, prompt,
                         lambda m: self._status.config(text=m, fg=theme.WARN))
            if dropped:
                self._status.config(
                    text=f"AI-ranking {len(jobs)}; auto-filtered {len(dropped)}",
                    fg=theme.WARN)

    def _api_rank_worker(self, prompt, jobs):
        """Background thread: call the API with the compact fit prompt and apply
        scores back to apply-queue applications."""
        try:
            reply = _call_prompt_via_api(prompt)
        except Exception as exc:
            self._api_ranking = False
            self.after(0, lambda: set_status(self._status, f"API error: {exc}", "err"))
            return
        try:
            applied = tracker_service.score_applications_from_reply(jobs, reply)
        except Exception as exc:
            self._api_ranking = False
            self.after(0, lambda: set_status(
                self._status, f"Parse error: {exc}", "err"))
            return
        self.after(0, self._api_rank_done, applied)

    def _api_rank_done(self, applied):
        self._api_ranking = False
        if not self.winfo_exists():
            return
        set_status(self._status, f"Ranked {applied} job(s) via API.", "ok")
        self.refresh(keep_selection=True)

    def _paste_fit(self):
        if not getattr(self, "_fit_jobs", None):
            messagebox.showinfo("No prompt", "Copy a fit prompt first.")
            return
        dlg = PasteDialog(self)
        if not dlg.result:
            return
        try:
            applied = tracker_service.score_applications_from_reply(
                self._fit_jobs, dlg.result)
        except BridgeParseError as e:
            messagebox.showerror("Parse failed", str(e), parent=self)
            return
        self._status.config(text=f"Applied {applied} fit score(s).", fg=theme.SUCCESS)
        self.refresh(keep_selection=True)


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
        top-bar 'Tools ▾' button post the identical actions (Alex's ask: surface
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
            self.title(f"Job Search Tools — {workspace.active_slug()}")
        else:
            self.title("Job Search Tools")

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
        except Exception:
            pass
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


def main() -> int:
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
