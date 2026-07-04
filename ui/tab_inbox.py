"""Inbox tab: the daily-run triage queue (scored matches from daily_run.py).

Extracted from gui.py (S35 gui-split) as a pure move — no behavior change.
"""
import json
import subprocess
import threading
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from config import DEFAULT_LOCATION, OUTPUT_DIR
from geo.filter import location_visible, LOCATION_MODES, DEFAULT_LOCATION_MODE
from claude_bridge import BridgeParseError
from match import ghost as ghostmod
from match import comp as compmod
from match import ats_hint as atshintmod
from match.scorer import score_breakdown, extract_skill_terms
from scrape.inbox_health import prune_inbox
from tracker import service as tracker_service
from tracker.db import inbox_all, inbox_count, inbox_delete_urls
import ranker as _ranker_mod
import workspace
from ui import theme
from ui import chrome
from ui import settings as uisettings
from ui import common
from ui.common import safe_url, db_guard, set_status, copy_or_warn, _call_prompt_via_api, _scored_status
from ui.paste_dialog import PasteDialog

# ── Inbox tab (daily-run results) ─────────────────────────────────────────────
def _row_new_batch(row) -> str:
    """The freshness batch stamped on an inbox row's extras ('' if none)."""
    raw = row.get("extras")
    if not raw:
        return ""
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return ""
    return data.get("new_batch", "") if isinstance(data, dict) else ""


def _row_browse(row) -> dict:
    """Browser-harvest metadata stamped on an inbox row's extras under "browse"
    (work mode, employment type, seniority, applicants, easy-apply, promoted).
    Empty dict when the row didn't come from the browser extension."""
    raw = row.get("extras")
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    browse = data.get("browse") if isinstance(data, dict) else None
    return browse if isinstance(browse, dict) else {}


def _browse_summary(b: dict) -> str:
    """One-line ' · '-joined summary of browse metadata ('' if nothing useful)."""
    bits = []
    for key in ("work_mode", "employment_type", "seniority"):
        if b.get(key):
            bits.append(str(b[key]))
    if b.get("applicants") is not None:
        n = b["applicants"]
        bits.append(f"{n} applicant" + ("" if n == 1 else "s"))
    if b.get("easy_apply"):
        bits.append("Easy Apply")
    if b.get("promoted"):
        bits.append("Promoted")
    return " · ".join(bits)


def _latest_new_batch(rows) -> "str | None":
    """Most recent freshness batch across rows (None if none stamped). Latest
    batch wins, mirroring Top Picks' rec_batch convention."""
    batches = [b for b in (_row_new_batch(r) for r in rows) if b]
    return max(batches) if batches else None


def _is_new_row(row, latest) -> bool:
    return bool(latest) and _row_new_batch(row) == latest


class InboxTab(ttk.Frame):
    """Triage queue fed by daily_run.py: ranked fresh matches. Track moves a
    row to the tracker; Dismiss hides the posting from all future searches."""

    _COLS = [
        ("score",    "Score",     72, "center"),
        ("fit",      "Fit",       62, "center"),
        ("title",    "Title",    300, "w"),
        ("company",  "Company",  150, "w"),
        ("size",     "Size",      60, "center"),
        ("location", "Location", 130, "w"),
        ("salary",   "Salary",   100, "w"),
        ("source",   "Source",    80, "w"),
        ("added",    "Added",     85, "center"),
    ]

    @staticmethod
    def _score_cell(n) -> str:
        """A score/fit value with a leading colored band circle, blank if unscored.
        The emoji carries its own color, so a single cell reads red/amber/green
        without ttk per-cell styling (works in light and dark)."""
        try:
            n = int(n)
        except (TypeError, ValueError):
            return ""
        if n < 0:
            return ""
        return str(n)   # band color now shown as a colored chip in the #0 gutter

    @staticmethod
    def _size_badge(board_count) -> str:
        """Company-size proxy from total careers-board postings."""
        bc = board_count if board_count is not None else -1
        if bc < 0:
            return ""
        if bc <= 30:
            return f"S ({bc})"
        if bc <= 100:
            return f"M ({bc})"
        if bc <= 250:
            return f"L ({bc})"
        return f"XL ({bc})"

    @staticmethod
    def _size_letter(board_count) -> str:
        badge = InboxTab._size_badge(board_count)
        return badge.split(" ")[0] if badge else "?"

    # Client-side sort keys over the cached inbox rows. Default (no sort
    # column) keeps inbox_all()'s round-robin order so one company can't
    # monopolize the top of the queue.
    _SORT_KEYS = {
        "score":    lambda r: r["score"],
        "fit":      lambda r: r["fit"],
        "title":    lambda r: (r["title"] or "").lower(),
        "company":  lambda r: (r["company"] or "").lower(),
        "size":     lambda r: r.get("board_count") if r.get("board_count") is not None else -1,
        "location": lambda r: (r["location"] or "").lower(),
        "salary":   lambda r: (r["salary_text"] or "").lower(),
        "source":   lambda r: (r["source"] or "").lower(),
        "added":    lambda r: r["date_added"] or "",
    }
    _NUMERIC_COLS = ("score", "fit", "size")  # first click sorts these desc

    def __init__(self, parent, on_change=None):
        super().__init__(parent)
        self._rows: dict[str, dict] = {}
        self._all: list[dict] = []   # unfiltered inbox snapshot
        self._sort_col: str | None = None  # None = round-robin default
        self._sort_asc = True
        self._skill_terms = None     # cached per project for the skill-gap readout
        self._pay_floor = None       # resolved per project in _resolve_home()
        self._empty_widget = None    # overlay shown when the table is empty
        self._on_change = on_change  # notify App to refresh the tab badge
        # Home metro for the Location view-filter; resolved per active project in
        # refresh(). Agnostic defaults until then.
        self._home_area = DEFAULT_LOCATION
        self._home_remote_ok = True
        self._build()
        self.refresh()

    def _build(self):
        # "Jobs For You" curated-feed framing (SB-4): the free scorer is now
        # trustworthy (Wave-1 seniority/remote/salary fixes), so present the daily
        # inbox as a matched, ranked feed — not a raw dump. Copy/framing only; the
        # ranking engine (round-robin over Fit-else-Score) is unchanged.
        hdr = theme.header_bar(
            self, "Jobs For You",
            "Your daily matched feed — ranked for you, best matches first.")
        # Close the daily loop in-GUI: run the same pipeline the scheduled task
        # runs, right now, without a Python install or a terminal (P0 #2).
        self._update_btn = theme.tip(
            theme.btn(hdr, "Update my Inbox now", self._update_inbox_now, "accent"),
            "Search your sources now and add any fresh matches to this Inbox. "
            "Runs in the background; you can keep working.")
        self._update_btn.pack(side="right", padx=10, pady=8)
        self._count_lbl = tk.Label(hdr, text="", bg=theme.SURFACE,
                                    fg=theme.MUTED, font=theme.FONT_SM)
        self._count_lbl.pack(side="right", padx=14)
        self._update_running = False   # single-flight guard for the update run
        # Reach badge (goal: certify how wide the net is) — honest capture-recapture
        # verdict from the last daily_run, or blank until one exists. See coverage/reach.py.
        self._reach_lbl = tk.Label(hdr, text="", bg=theme.SURFACE,
                                   fg=theme.MUTED, font=theme.FONT_SM)
        self._reach_lbl.pack(side="right", padx=14)
        # Actionable reach (§6.8 / SB-6): when reach is low/uncertifiable because a
        # headline free key (Adzuna/CareerOneStop) is missing, name the reason and
        # offer a one-click fix that opens the same 'Connect job sources' dialog.
        # Blank (and unpacked) when nothing is actionable.
        self._reach_fix_lbl = tk.Label(hdr, text="", bg=theme.SURFACE,
                                       fg=theme.ACCENT, font=theme.FONT_SM,
                                       cursor="hand2")
        self._reach_fix_lbl.bind("<Button-1>", lambda _e: self._open_source_keys())
        # Last-update stamp from the run beacon (applog.last_run_info), so a user
        # can tell "no new jobs" from "updates stopped running" at a glance.
        self._lastrun_lbl = tk.Label(hdr, text="", bg=theme.SURFACE,
                                     fg=theme.MUTED, font=theme.FONT_SM)
        self._lastrun_lbl.pack(side="right", padx=14)
        # Silent-zero surfacing: sources that self-skipped last run for a missing
        # free key contribute 0 with only console lines today. Name the count and
        # the one-click fix, in the WARN color so it reads as actionable. Click
        # opens the same 'Connect job sources' dialog. Blank when nothing skipped.
        self._keyless_lbl = tk.Label(hdr, text="", bg=theme.SURFACE,
                                     fg=theme.WARN, font=theme.FONT_SM,
                                     cursor="hand2")
        self._keyless_lbl.pack(side="right", padx=14)
        self._keyless_lbl.bind("<Button-1>", lambda _e: self._open_source_keys())
        theme.tip_strip(
            self, "Jobs matched to you, ranked best-first. Score is our free "
                  "match; Fit is your AI grade. Pick jobs you like and click "
                  "“Track ▸ Interested” — they move to Apply Queue. "
                  "Tip: click a row and press T (track), D (dismiss), O (open).")
        # Sample-inbox banner (§6.1): shown ONLY while the demo rows are on screen,
        # so a first-run user knows these are illustrative and how to get real ones.
        self._demo_banner = tk.Label(
            self, text="", bg=theme.ACCENT, fg="#ffffff", font=theme.FONT_SM,
            anchor="w", justify="left", padx=12, pady=6)
        # Not packed yet — _render packs/forgets it based on self._demo_active.

        # Filter bar — applied client-side over the cached snapshot, so
        # typing in a filter never hits the database.
        fbar = tk.Frame(self, bg=theme.WINDOW)
        fbar.pack(fill="x", padx=6, pady=(6, 0))
        tk.Label(fbar, text="Min score:", bg=theme.WINDOW, fg=theme.INK,
                 font=theme.FONT_SM).pack(side="left")
        self._f_minscore = tk.StringVar()
        ms = ttk.Entry(fbar, textvariable=self._f_minscore, width=4)
        ms.pack(side="left", padx=(2, 10))
        ms.bind("<KeyRelease>", self._schedule_render)
        tk.Label(fbar, text="Source:", bg=theme.WINDOW, fg=theme.INK,
                 font=theme.FONT_SM).pack(side="left")
        self._f_source = tk.StringVar(value="All")
        self._source_cb = ttk.Combobox(fbar, textvariable=self._f_source,
                                       state="readonly", width=12,
                                       values=["All"])
        self._source_cb.pack(side="left", padx=(2, 10))
        self._source_cb.bind("<<ComboboxSelected>>", lambda _e: self._render())
        tk.Label(fbar, text="Size:", bg=theme.WINDOW, fg=theme.INK,
                 font=theme.FONT_SM).pack(side="left")
        self._f_size = tk.StringVar(value="All")
        sz = ttk.Combobox(fbar, textvariable=self._f_size, state="readonly",
                          width=4, values=["All", "S", "M", "L", "XL", "?"])
        sz.pack(side="left", padx=(2, 10))
        sz.bind("<<ComboboxSelected>>", lambda _e: self._render())
        tk.Label(fbar, text="Location:", bg=theme.WINDOW, fg=theme.INK,
                 font=theme.FONT_SM).pack(side="left")
        self._f_location = tk.StringVar(value=uisettings.get_location_mode())
        loc_cb = ttk.Combobox(fbar, textvariable=self._f_location, state="readonly",
                              width=13, values=list(LOCATION_MODES))
        loc_cb.pack(side="left", padx=(2, 10))
        theme.tip(loc_cb, "Focus the inbox on your area. “Local + remote” (the "
                          "default) shows jobs in your metro plus remote roles; "
                          "“Local only” hides remote; “All locations” shows "
                          "everything. Your home metro comes from this project’s "
                          "configured location.")
        loc_cb.bind("<<ComboboxSelected>>", lambda _e: self._on_location_change())
        self._f_unscored = tk.BooleanVar(value=False)
        tk.Checkbutton(fbar, text="Unscored only", variable=self._f_unscored,
                       bg=theme.WINDOW, fg=theme.INK, selectcolor=theme.SURFACE,
                       activebackground=theme.WINDOW, activeforeground=theme.INK,
                       font=theme.FONT_SM,
                       command=self._render).pack(side="left", padx=(0, 10))
        self._f_new = tk.BooleanVar(value=False)
        theme.tip(tk.Checkbutton(fbar, text="New only", variable=self._f_new,
                                 bg=theme.WINDOW, fg=theme.INK, selectcolor=theme.SURFACE,
                                 activebackground=theme.WINDOW, activeforeground=theme.INK,
                                 font=theme.FONT_SM, command=self._render),
                  "Show only jobs new since the last daily update.").pack(side="left", padx=(0, 10))
        self._f_hide_stale = tk.BooleanVar(value=False)
        theme.tip(tk.Checkbutton(fbar, text="Hide stale", variable=self._f_hide_stale,
                                 bg=theme.WINDOW, fg=theme.INK, selectcolor=theme.SURFACE,
                                 activebackground=theme.WINDOW, activeforeground=theme.INK,
                                 font=theme.FONT_SM, command=self._render),
                  "Hide listings that look likely-dead or evergreen — old postings "
                  "or perpetual 'always hiring' reqs.").pack(side="left", padx=(0, 10))
        self._f_floor = tk.BooleanVar(value=False)
        theme.tip(tk.Checkbutton(fbar, text="Meets pay floor", variable=self._f_floor,
                                 bg=theme.WINDOW, fg=theme.INK, selectcolor=theme.SURFACE,
                                 activebackground=theme.WINDOW, activeforeground=theme.INK,
                                 font=theme.FONT_SM, command=self._render),
                  "Show only jobs whose listed pay meets your salary floor (from "
                  "your preferences). Jobs with no pay listed are hidden.").pack(side="left", padx=(0, 10))
        tk.Label(fbar, text="Find:", bg=theme.WINDOW, fg=theme.INK,
                 font=theme.FONT_SM).pack(side="left")
        self._f_text = tk.StringVar()
        ft = ttk.Entry(fbar, textvariable=self._f_text, width=18)
        ft.pack(side="left", padx=(2, 6))
        ft.bind("<KeyRelease>", self._schedule_render)
        theme.btn(fbar, "Clear", self._clear_filters, "ghost").pack(side="left")

        self._tf = tf = ttk.Frame(self)
        tf.pack(fill="both", expand=True, padx=6, pady=2)
        self._tree = ttk.Treeview(tf, columns=[c[0] for c in self._COLS],
                                  show="headings", selectmode="extended")
        for col, label, width, anchor in self._COLS:
            self._tree.heading(col, text=label,
                               command=lambda c=col: self._sort_by(c))
            self._tree.column(col, width=width, anchor=anchor, minwidth=40)
        chrome.enable_score_chips(self._tree)   # left #0 gutter for the score-band chip
        theme.zebra(self._tree)
        vsb = ttk.Scrollbar(tf, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self._tree.bind("<Double-1>", lambda _e: self._open_url())
        # Keyboard triage: with focus on the list, t/d/o handle a row and the
        # selection advances, so a whole screen can be cleared without the mouse.
        self._tree.bind("t", lambda _e: self._track())
        self._tree.bind("d", lambda _e: self._dismiss())
        self._tree.bind("o", lambda _e: self._open_url())
        # Ctrl+A selects every visible row — bulk triage at 660-row scale.
        self._tree.bind("<Control-a>", self._select_all)
        self._tree.bind("<Control-A>", self._select_all)

        # Detail pane: why this job scored what it did (AI rationale + the local
        # scorecard), what the JD also wants, a staleness advisory, and a preview.
        self._detail = theme.text_widget(self, height=7, fg=theme.MUTED,
                                         padx=8, state="disabled")
        self._detail.pack(fill="x", padx=6)
        self._tree.bind("<<TreeviewSelect>>", self._show_detail)

        abar = tk.Frame(self, bg=theme.WINDOW, pady=6)
        abar.pack(fill="x", padx=6, side="bottom")
        theme.tip(theme.btn(abar, "Track \N{BLACK RIGHT-POINTING SMALL TRIANGLE} Interested (T)",
                            self._track, "accent"),
                  "Move the selected job(s) to your Apply Queue.  Shortcut: T").pack(side="left", padx=2)
        theme.tip(theme.btn(abar, "Dismiss (D)", self._dismiss, "ghost"),
                  "Hide the selected job(s) from all future searches.  Shortcut: D").pack(side="left", padx=2)
        theme.tip(theme.btn(abar, "Dismiss Company", self._dismiss_company, "ghost"),
                  "Hide every visible job from the selected company.").pack(side="left", padx=2)
        theme.tip(theme.btn(abar, "Dismiss all shown", self._dismiss_all_shown, "ghost"),
                  "Dismiss every row currently visible (respects your filters). "
                  "Undo available.").pack(side="left", padx=2)
        theme.tip(theme.btn(abar, "Open (O)", self._open_url, "ghost"),
                  "Open the selected job in your browser.  Shortcut: O").pack(side="left", padx=2)
        theme.btn(abar, "Refresh", self.refresh, "ghost").pack(side="left", padx=2)
        theme.tip(theme.btn(abar, "Clean dead links", self._clean_dead_links, "ghost"),
                  "Check every job link and remove postings that have been taken "
                  "down (they 404 on the company's job board).").pack(side="left", padx=2)
        # Undo: dismiss permanently deletes the inbox row, so keep the last
        # batch and offer to re-insert it. Disabled until something's dismissed.
        self._undo_btn = theme.btn(abar, "Undo Dismiss", self._undo_dismiss, "ghost")
        self._undo_btn.config(state="disabled")
        self._undo_btn.pack(side="left", padx=2)

        # AI ranking group (relabeled in plain English; tooltips explain each).
        tk.Label(abar, text="   AI ranking:", bg=theme.WINDOW, fg=theme.MUTED,
                 font=theme.FONT_SM).pack(side="left", padx=(8, 2))
        theme.tip(theme.btn(abar, "Ask AI to rank these", self._copy_fit_prompt, "ghost"),
                  "Copies a ready-made prompt to your clipboard. Paste it into "
                  "any AI chat (Claude, ChatGPT…).").pack(side="left", padx=2)
        theme.tip(theme.btn(abar, "Paste AI ranking", self._paste_fit, "ghost"),
                  "Paste the AI's reply here; its Fit grades land back on the "
                  "right jobs.").pack(side="left", padx=2)
        self._export_scope = tk.StringVar(value="Entire inbox")
        esc = ttk.Combobox(abar, textvariable=self._export_scope, state="readonly",
                           width=13, values=["Entire inbox", "Current view"])
        theme.tip(esc, "What to hand the AI: the whole inbox (so it can judge "
                       "relevance and pick your top matches), or just the rows "
                       "currently shown by your filters.")
        esc.pack(side="left", padx=(8, 0))
        # Chunk size: split a big export so each file fits a free chatbot's window
        # (the AI answers each file separately; job_key joins them on import).
        self._export_chunk = tk.StringVar(value="All in one file")
        ccb = ttk.Combobox(abar, textvariable=self._export_chunk, state="readonly",
                           width=15, values=["All in one file",
                                             "Split by 100", "Split by 50"])
        theme.tip(ccb, "For a large inbox: split the export into smaller files so "
                       "each fits a free AI chat. The AI ranks each file "
                       "separately; results join back automatically on import.")
        ccb.pack(side="left", padx=(6, 0))
        # Compact: swap long descriptions for one-line facts (~15x fewer tokens).
        self._export_compact = tk.BooleanVar(value=False)
        cchk = ttk.Checkbutton(abar, text="Compact", variable=self._export_compact)
        theme.tip(cchk, "Shrink the export by replacing each job's long "
                        "description with a one-line facts summary (~15x fewer "
                        "tokens) so a much bigger inbox fits a free AI chat.")
        cchk.pack(side="left", padx=(6, 0))
        theme.tip(theme.btn(abar, "Export for AI", self._export_for_ai, "ghost"),
                  "Save the inbox as a spreadsheet you can hand to any AI tool.").pack(side="left", padx=(8, 2))
        theme.tip(theme.btn(abar, "Load AI results", self._import_scores, "ghost"),
                  "Read AI scores back from a returned CSV/JSON file.").pack(side="left", padx=2)
        # Friendly merge choices map to the import policy values.
        merge_choices = [("Replace it", "overwrite"),
                         ("Keep the old one", "keep_existing"),
                         ("Only fill blanks", "add_only")]
        disp_to_val = {d: v for d, v in merge_choices}
        self._merge_policy = tk.StringVar(value="overwrite")   # value read by _import_scores
        self._merge_display = tk.StringVar(value=merge_choices[0][0])
        tk.Label(abar, text="if a job already has a Fit grade:", bg=theme.WINDOW,
                 fg=theme.MUTED, font=theme.FONT_SM).pack(side="left", padx=(6, 2))
        mcb = ttk.Combobox(abar, textvariable=self._merge_display, state="readonly",
                           width=15, values=[d for d, _ in merge_choices])
        mcb.bind("<<ComboboxSelected>>",
                 lambda _e: self._merge_policy.set(disp_to_val[self._merge_display.get()]))
        theme.tip(mcb, "When importing AI scores, what to do with jobs that "
                       "already have a Fit grade.")
        mcb.pack(side="left", padx=2)
        theme.tip(theme.btn(abar, "Undo AI ranking", self._undo_rerank, "ghost"),
                  "Revert the last AI ranking - whether it came from a file "
                  "import, a pasted reply, the API, or Claude Code.").pack(side="left", padx=2)
        self._status = tk.Label(abar, text="", bg=theme.WINDOW, fg=theme.MUTED,
                                font=theme.FONT_SM)
        self._status.pack(side="left", padx=10)

        self._fit_order: list[int] = []  # inbox ids in last fit-prompt order
        self._fit_jobs: list = []        # JobResults for the last fit prompt
        self._undo_rows: list[dict] = [] # last-dismissed rows, for Undo

    def _resolve_home(self):
        """Agnostic home metro + remote policy for the Location view-filter:
        the active project's configured location, else the first preferences
        location, else the global default. Never hardcoded to one city."""
        area = (workspace.load_config().get("location") or "").strip()
        remote_ok = True
        floor = None
        try:
            import preferences
            hard = preferences.load().get("hard", {})
            if not area and hard.get("locations"):
                area = str(hard["locations"][0]).strip()
            remote_ok = bool(hard.get("remote_ok", True))
            floor = hard.get("salary_min")
        except Exception:
            pass
        if not floor:
            floor = workspace.load_config().get("salary_min")
        self._home_area = area or DEFAULT_LOCATION
        # No configured home metro (DEFAULT_LOCATION is now '' — agnostic): a
        # local-focus filter has nothing to key on, so fall back to 'All
        # locations' and hint the user to set their location in Setup, instead of
        # silently hiding jobs against an empty home string.
        self._has_home = bool((self._home_area or "").strip())
        self._home_remote_ok = remote_ok
        try:
            self._pay_floor = int(floor) if floor else None
        except (TypeError, ValueError):
            self._pay_floor = None

    def _on_location_change(self):
        uisettings.set_location_mode(self._f_location.get())
        self._render()

    def refresh(self):
        self._resolve_home()
        # No home metro: force the Location filter to 'All locations' so the local
        # view isn't silently empty, and hint where to set it. Done once per
        # refresh (not per keystroke) so it never fights the user mid-typing.
        if not getattr(self, "_has_home", True):
            if self._f_location.get() != "All locations":
                self._f_location.set("All locations")
        self._skill_terms = None   # project may have changed -> reparse on demand
        self._all = list(inbox_all())
        # Bundled sample inbox (§6.1): a first-run user with a genuinely empty
        # inbox sees ~20 pre-scored DEMO rows so the aha (a scored, Score-vs-Fit
        # inbox) lands before anything is connected. Read-only: demo rows never
        # touch the DB, are hidden the moment a real inbox exists, and are retired
        # permanently once the user has seen a real inbox / run a real update.
        self._demo_active = False
        try:
            import config
            import demo_data
            if self._all:
                demo_data.retire_demo(config.USER_DATA_DIR)  # real inbox -> retire
            elif demo_data.should_show_demo(config.USER_DATA_DIR, len(self._all)):
                self._all = demo_data.demo_inbox_rows()
                self._demo_active = bool(self._all)
        except Exception:
            self._demo_active = False
        # Normalize disclosed pay once per load (not per filter keystroke) so the
        # Salary column and the pay-floor filter are cheap to render.
        for r in self._all:
            r["_comp"] = compmod.normalize_comp(r)
        sources = sorted({r["source"] for r in self._all if r["source"]})
        self._source_cb["values"] = ["All", *sources]
        if self._f_source.get() not in self._source_cb["values"]:
            self._f_source.set("All")
        self._render()
        self._update_reach_badge()
        if self._on_change:
            self._on_change()

    def _update_reach_badge(self):
        """Best-effort: read the last persisted reach snapshot for the active
        project. Never let a reach/coverage error touch the inbox render."""
        # While the first-run SAMPLE inbox is on screen there is no real reach
        # state to describe — the curated demo rows are location-varied by design,
        # so a real-reach "Seeing mostly remote/tech jobs…" fix badge would
        # contradict what the user is looking at. The demo banner already tells
        # them this is a sample; suppress the reach line + fix affordance until a
        # real inbox exists.
        if getattr(self, "_demo_active", False):
            self._reach_lbl.config(text="")
            self._set_reach_fix(None)
        else:
            try:
                from coverage.reach import badge_line, badge_reason, load_latest
                snap = load_latest(workspace.active_slug() or "root")
                self._reach_lbl.config(text=badge_line(snap))
                self._set_reach_fix(badge_reason(snap))
            except Exception:
                self._reach_lbl.config(text="")
                self._set_reach_fix(None)
        info = None
        try:
            import applog
            info = applog.last_run_info(workspace.active_slug())
            if info and info.get("timestamp"):
                when = str(info["timestamp"])[:16].replace("T", " ")
                self._lastrun_lbl.config(
                    text=f"Last updated {when} — {info.get('added', 0)} new")
            else:
                self._lastrun_lbl.config(text="")
        except Exception:
            self._lastrun_lbl.config(text="")
        # Silent-zero: name the sources that self-skipped for a missing free key.
        try:
            self._keyless_lbl.config(text=self._keyless_badge_text(info))
        except Exception:
            self._keyless_lbl.config(text="")

    def _set_reach_fix(self, reason):
        """Show/hide the clickable '[Connect a free key]' reach-fix affordance.
        `reason` is the plain-English cause (from coverage.reach.badge_reason) or
        None to hide it entirely."""
        lbl = getattr(self, "_reach_fix_lbl", None)
        if lbl is None or not lbl.winfo_exists():
            return
        if reason:
            lbl.config(text=f"Seeing {reason} \N{EM DASH} [Connect a free key]")
            if not lbl.winfo_ismapped():
                lbl.pack(side="right", padx=6)
        else:
            lbl.config(text="")
            lbl.pack_forget()

    @staticmethod
    def _keyless_badge_text(last_run_info: dict | None) -> str:
        """Compact, actionable line from last_run.json's keyless_skipped list.
        Empty when nothing skipped or no run yet. Pure/static so it is unit-
        testable without a Tk root. The count comes from the actual run's skip
        events, never a hardcoded source list."""
        skipped = (last_run_info or {}).get("keyless_skipped") or []
        n = len(skipped)
        if not n:
            return ""
        noun = "source" if n == 1 else "sources"
        return (f"{n} {noun} skipped (no key) — "
                f"unlock in Tools ▸ Connect job sources")

    def _open_source_keys(self):
        """Open the existing 'Connect job sources' dialog from the Inbox header's
        keyless badge. Self-contained + guarded so a not-yet-merged/headless build
        degrades gracefully instead of crashing the tab."""
        try:
            from ui import source_keys
        except ImportError:
            messagebox.showinfo(
                "Connect job sources",
                "Job-source key management isn't available in this build yet.",
                parent=self)
            return
        try:
            source_keys.open_dialog(self.winfo_toplevel())
        except Exception as e:
            messagebox.showerror("Connect job sources", str(e), parent=self)

    # ── Update my Inbox now (the daily loop, in-GUI) ──────────────────────────
    def _update_inbox_now(self):
        """Run the daily search->score->inbox pipeline in a worker thread, pinned
        to the active project, with live per-source progress and a running-flag so
        it can't start twice. The worker uses run_daily_ingest (pins BEFORE any db
        write, unpins in finally) — the S27-safe pattern."""
        if self._update_running:
            return
        slug = workspace.active_slug()
        # The user chose to fetch real jobs: retire the sample inbox now so it
        # never returns, even if this run happens to add zero rows (§6.1).
        try:
            import config
            import demo_data
            demo_data.retire_demo(config.USER_DATA_DIR)
        except Exception:
            pass
        self._update_running = True
        self._update_before = inbox_count()
        try:
            self._update_btn.config(state="disabled", text="Updating…")
        except Exception:
            pass
        self._count_lbl.config(text="Updating your inbox…", fg=theme.WARN)

        def on_line(line):
            # Marshal every pipeline line back onto the Tk thread for the count
            # label; keep only the informative ones so the header isn't noisy.
            self.after(0, self._update_progress_line, line)

        def work():
            err = None
            try:
                # Late import: run_daily_ingest stays defined in gui.py (the
                # frozen exe's --daily headless path also calls it there), and
                # tests patch gui.run_daily_ingest -- going through the gui
                # module attribute (instead of a frozen `from gui import
                # run_daily_ingest`) keeps that patch target working after
                # InboxTab's move to ui/tab_inbox.py (S35 gui-split).
                import gui
                gui.run_daily_ingest(slug, on_line=on_line)
            except Exception as e:
                err = f"{type(e).__name__}: {e}"
            self.after(0, self._update_inbox_done, err)

        threading.Thread(target=work, daemon=True).start()

    def _update_progress_line(self, line):
        if not self.winfo_exists():
            return
        line = (line or "").strip()
        # Surface source/inbox lines the daily pipeline prints; skip blank noise.
        if not line:
            return
        marker = None
        if "] " in line and line.startswith("["):
            # "[Adzuna] 12 results in ~1.3s" etc.
            marker = line.split("] ", 1)[1]
        elif "->" in line or "inbox" in line.lower() or "found" in line.lower():
            marker = line
        if marker:
            self._count_lbl.config(text=marker[:90], fg=theme.WARN)

    def _update_inbox_done(self, err):
        if not self.winfo_exists():
            return
        self._update_running = False
        try:
            self._update_btn.config(state="normal", text="Update my Inbox now")
        except Exception:
            pass
        if err:
            self._count_lbl.config(text=f"Update failed: {err}", fg=common.ERR)
            messagebox.showerror(
                "Update my Inbox", f"The update didn't finish:\n\n{err}",
                parent=self)
            return
        before = getattr(self, "_update_before", 0)
        self.refresh()               # reload rows + counts + badges
        added = max(0, inbox_count() - before)
        self._count_lbl.config(
            text=(f"Added {added} new job(s)." if added
                  else "No new jobs this time."),
            fg=(theme.SUCCESS if added else theme.MUTED))

    def _filtered(self) -> list[dict]:
        rows = self._all
        # Sample inbox (§6.1): show every demo row as-is. Its varied locations
        # ARE the demo (they teach the location-clean, Score-vs-Fit split), so the
        # user's configured local-focus filter must not whittle it down before
        # they've even run a real search. Gate on the rows ACTUALLY being demo
        # rows (not just the flag) so a caller that swaps in real rows isn't
        # accidentally left unfiltered.
        if (getattr(self, "_demo_active", False) and rows
                and all(r.get("is_demo") for r in rows)):
            return list(rows)
        try:
            min_score = int(self._f_minscore.get().strip())
        except ValueError:
            min_score = None
        if min_score is not None:
            rows = [r for r in rows if r["score"] >= min_score]
        src = self._f_source.get()
        if src and src != "All":
            rows = [r for r in rows if r["source"] == src]
        size = self._f_size.get()
        if size and size != "All":
            rows = [r for r in rows
                    if self._size_letter(r.get("board_count", -1)) == size]
        if self._f_unscored.get():
            rows = [r for r in rows if r["fit"] < 0]
        if self._f_new.get():
            latest = _latest_new_batch(self._all)
            rows = [r for r in rows if _is_new_row(r, latest)]
        if self._f_hide_stale.get():
            rows = [r for r in rows
                    if ghostmod.ghost_score(r).get("level") != "stale"]
        if self._f_floor.get() and self._pay_floor:
            def _meets(c):
                if not c or not c.get("disclosed"):
                    return False
                top = c["max"] if c["max"] is not None else c["min"]
                return top is not None and top >= self._pay_floor
            rows = [r for r in rows if _meets(r.get("_comp"))]
        mode = self._f_location.get()
        # With no configured home metro, a local-focus mode has nothing to match
        # against — behave as 'All locations' so we don't hide every job.
        if mode and mode != "All locations" and getattr(self, "_has_home", True):
            rows = [r for r in rows
                    if location_visible(r["location"] or "", r["title"] or "",
                                        self._home_area, mode,
                                        remote_ok=self._home_remote_ok)]
        q = self._f_text.get().strip().lower()
        if q:
            rows = [r for r in rows
                    if q in (r["title"] or "").lower()
                    or q in (r["company"] or "").lower()]
        return rows

    def _schedule_render(self, _event=None):
        """Debounce per-keystroke filter renders: typing in a filter box rebuilds
        the table at most once per ~200ms instead of on every key (keeps a large
        inbox responsive)."""
        job = getattr(self, "_render_job", None)
        if job is not None:
            try:
                self.after_cancel(job)
            except Exception:
                pass
        self._render_job = self.after(200, self._render)

    def _render(self):
        self._render_job = None
        rows = self._filtered()
        if self._sort_col:
            rows = sorted(rows, key=self._SORT_KEYS[self._sort_col],
                          reverse=not self._sort_asc)
        for col, label, *_ in self._COLS:
            arrow = ""
            if col == self._sort_col:
                arrow = " ▲" if self._sort_asc else " ▼"
            self._tree.heading(col, text=label + arrow)

        self._rows = {}
        for iid in self._tree.get_children():
            self._tree.delete(iid)
        for i, r in enumerate(rows):
            iid = str(r["id"])
            self._rows[iid] = r
            self._tree.insert("", "end", iid=iid, tags=(theme.row_tag(i),),
                              image=chrome.score_chip(self._tree, r["score"]), values=(
                self._score_cell(r["score"]),
                self._score_cell(r["fit"]),
                r["title"], r["company"],
                self._size_badge(r.get("board_count", -1)),
                r["location"],
                (r.get("_comp") or {}).get("display") or r["salary_text"],
                r["source"], r["date_added"]))
        total = len(self._all)
        if getattr(self, "_demo_active", False):
            # Demo mode: don't call these "awaiting triage" (they're not real).
            label = f"Sample inbox — {total} example jobs"
        else:
            label = (f"{len(rows)} of {total} awaiting triage"
                     if len(rows) != total else f"{total} awaiting triage")
            if not getattr(self, "_has_home", True):
                label += "  •  All locations (set your location in Setup to enable local focus)"
        self._count_lbl.config(text=label)
        self._toggle_demo_banner()
        self._update_empty(rows)

    def _toggle_demo_banner(self):
        """Show the sample-inbox banner only while demo rows are on screen."""
        banner = getattr(self, "_demo_banner", None)
        if banner is None or not banner.winfo_exists():
            return
        if getattr(self, "_demo_active", False):
            banner.config(
                text="DEMO — this is a sample inbox to show you what scored "
                     "matches look like (Score = our free match; Fit = an AI "
                     "grade). Click “Update my Inbox now” to replace it with real "
                     "jobs from your sources.")
            banner.pack(fill="x", before=self._tf)
        else:
            banner.pack_forget()

    def _update_empty(self, rows):
        """Overlay a friendly empty state on the table: distinguish a genuinely
        empty inbox (run a search) from one filtered down to nothing (clear)."""
        if self._empty_widget is not None:
            self._empty_widget.destroy()
            self._empty_widget = None
        if rows:
            return
        if not self._all:
            # Point at the real way the inbox fills: "Update my Inbox now" (and
            # daily updates) write here — a GUI Search does NOT (it lands on the
            # Search tab). The old copy told users to Search, which never filled
            # the inbox (P0 #2 / empty-state lie).
            self._empty_widget = theme.empty_state(
                self._tf,
                "Your inbox is empty.\nClick “Update my Inbox now” to search your "
                "sources and pull in fresh matches. Turn on daily updates "
                "(Tools ▸ Turn on daily updates) and it refills every morning.",
                "Update my Inbox now", self._update_inbox_now)
        else:
            self._empty_widget = theme.empty_state(
                self._tf, "No jobs match your current filters.",
                "Clear filters", self._clear_filters)
        self._empty_widget.place(relx=0, rely=0, relwidth=1, relheight=1)

    def _sort_by(self, col):
        default_asc = col not in self._NUMERIC_COLS
        if self._sort_col != col:
            self._sort_col, self._sort_asc = col, default_asc
        elif self._sort_asc == default_asc:
            self._sort_asc = not default_asc
        else:
            self._sort_col = None  # third click: back to round-robin order
        self._render()

    def _clear_filters(self):
        self._f_minscore.set("")
        self._f_source.set("All")
        self._f_size.set("All")
        self._f_unscored.set(False)
        self._f_new.set(False)
        self._f_hide_stale.set(False)
        self._f_floor.set(False)
        self._f_text.set("")
        # Clear returns the view to the local-focused default (and persists it),
        # not to "All" — local focus is the intended out-of-box behavior.
        self._f_location.set(DEFAULT_LOCATION_MODE)
        uisettings.set_location_mode(DEFAULT_LOCATION_MODE)
        self._render()

    def _selected(self) -> list[dict]:
        return [self._rows[iid] for iid in self._tree.selection()
                if iid in self._rows]

    def _block_if_demo(self, sel) -> bool:
        """Guard triage on the read-only sample inbox: demo rows have no DB row,
        so tracking/dismissing them is meaningless. Returns True (and nudges the
        user toward a real update) when any selected row is a demo row."""
        if any(r.get("is_demo") for r in sel):
            messagebox.showinfo(
                "Sample inbox",
                "These are example jobs to show you what a scored inbox looks "
                "like — you can't track or dismiss them. Click “Update my Inbox "
                "now” to pull in real jobs you can act on.", parent=self)
            return True
        return False

    def _show_detail(self, _event=None):
        sel = self._selected()
        text = self._detail_text(sel[0]) if len(sel) == 1 else ""
        self._detail.config(state="normal")
        self._detail.delete("1.0", "end")
        self._detail.insert("1.0", text)
        self._detail.config(state="disabled")

    def _detail_text(self, r) -> str:
        """Compose the why/scorecard/skill-gap/staleness/preview readout for one
        row from data the pipeline already produced (no AI call, no network)."""
        lines = []
        why = (r.get("fit_why") or "").strip()
        if why:
            lines.append(f"Why this matches: {why}")

        bd = score_breakdown(r.get("score_notes") or "")
        if bd["components"]:
            parts = [f"{c['label']} {c['pct'] * 100:.0f}%" for c in bd["components"]]
            line = f"Score {r.get('score', '')}: " + "  ".join(parts)
            if bd["confidence"]:
                line += f"   (confidence {bd['confidence']['present']}/{bd['confidence']['total']})"
            if bd["penalties"]:
                line += "   penalties: " + ", ".join(p["label"] for p in bd["penalties"])
            lines.append(line)

        # Browser-harvest extras (work mode / type / seniority / applicants /
        # easy-apply / promoted) when this row was collected while browsing.
        summary = _browse_summary(_row_browse(r))
        if summary:
            lines.append("Captured while browsing: " + summary)

        desc = r.get("description") or ""
        # Free local "ATS match hint" (Jobscan-lite, SB-6): name the ATS the
        # posting runs on (from its URL) and the local keyword overlap between the
        # user's skills and the JD — honest guidance, no AI, no network, no fake
        # "ATS score". ats_hint reuses the same skill-gap machinery as before.
        if self._skill_terms is None:
            try:
                self._skill_terms = extract_skill_terms()
            except Exception:
                self._skill_terms = frozenset()
        try:
            hint = atshintmod.match_hint(
                desc, r.get("url", ""), skill_terms=self._skill_terms)
            for line in atshintmod.hint_lines(hint):
                lines.append(line)
        except Exception:
            pass

        try:
            g = ghostmod.ghost_score(r)
            if g["level"] in ("aging", "stale"):
                lines.append(f"\N{WARNING SIGN} Listing looks {g['level']}: "
                             + "; ".join(g["reasons"][:2]))
        except Exception:
            pass

        if desc.strip():
            lines.append(" ".join(desc.split())[:500])
        return "\n".join(lines)

    def _clean_dead_links(self):
        """Probe inbox career links and remove postings that now 404. The probe
        is network-bound (~1 call/row), so it runs on a worker thread; the preview
        + delete marshal back to the Tk thread via .after()."""
        if getattr(self, "_cleaning", False):
            return
        self._cleaning = True
        self._status.config(text="Checking links… this can take a minute.")

        def work():
            try:
                dead, err = prune_inbox(dry_run=True), None
            except Exception as e:        # network/db hiccup — report, don't crash
                dead, err = None, str(e)
            self.after(0, lambda: self._clean_dead_links_done(dead, err))

        threading.Thread(target=work, daemon=True).start()

    def _clean_dead_links_done(self, dead, err):
        self._cleaning = False
        if not self.winfo_exists():
            return  # tab torn down while the worker ran (GUI-7 pattern)
        self._status.config(text="")
        if err is not None:
            messagebox.showerror("Clean dead links", f"Could not check links:\n{err}")
            return
        if not dead:
            messagebox.showinfo("Clean dead links",
                                "No dead links found — every posting is still reachable.")
            return
        sample = "\n".join(f"• {d['company']}: {d['title']}" for d in dead[:12])
        more = f"\n…and {len(dead) - 12} more" if len(dead) > 12 else ""
        if not messagebox.askyesno(
                "Clean dead links",
                f"{len(dead)} posting(s) appear to be gone (they 404 on the "
                f"company's job board):\n\n{sample}{more}\n\nRemove them from your inbox?"):
            return
        # Delete the exact rows the dry-run found — no second network sweep.
        removed = inbox_delete_urls([d["url"] for d in dead])
        self.refresh()
        messagebox.showinfo("Clean dead links", f"Removed {removed} dead link(s).")

    def _focus_index(self) -> int | None:
        """Position of the first selected row, so the selection can land on
        the next row after Track/Dismiss removes the current one."""
        children = self._tree.get_children()
        idxs = [children.index(i) for i in self._tree.selection()
                if i in children]
        return min(idxs) if idxs else None

    def _restore_focus(self, idx):
        if idx is None:
            return
        children = self._tree.get_children()
        if not children:
            return
        iid = children[min(idx, len(children) - 1)]
        self._tree.selection_set(iid)
        self._tree.focus(iid)
        self._tree.see(iid)
        self._tree.focus_set()  # keep t/d/o keys live for the next row

    def _track(self):
        sel = self._selected()
        if not sel:
            messagebox.showinfo("No selection", "Select inbox row(s) first.")
            return
        if self._block_if_demo(sel):
            return
        idx = self._focus_index()
        # Dup-guard (Search already has one): skip rows whose URL is already
        # tracked or dismissed, so a posting can't be double-added.
        ok, seen = db_guard(self, tracker_service.seen_urls,
                            status_cb=lambda m: set_status(self._status, m, "err"),
                            action="track jobs")
        if not ok:
            return
        skipped = 0

        def do_track():
            nonlocal skipped
            tracked = 0
            for r in sel:
                if tracker_service.normalize_url(r.get("url", "")) in seen:
                    skipped += 1
                    continue
                tracker_service.track_job(r["id"])
                tracked += 1
            return tracked

        ok, tracked = db_guard(
            self, do_track,
            status_cb=lambda m: set_status(self._status, m, "err"),
            action="track jobs")
        if not ok:
            return
        msg = f"Tracked {tracked} job(s)."
        if skipped:
            msg += f" Skipped {skipped} already tracked/dismissed."
        set_status(self._status, msg, "info")
        self.refresh()
        self._restore_focus(idx)

    def _dismiss(self):
        sel = self._selected()
        if not sel:
            return
        if self._block_if_demo(sel):
            return
        idx = self._focus_index()
        ok, _ = db_guard(
            self, lambda: [tracker_service.dismiss_job(r["id"]) for r in sel],
            status_cb=lambda m: set_status(self._status, m, "err"),
            action="dismiss jobs")
        if not ok:
            return
        self._remember_undo(sel)
        set_status(
            self._status,
            f"Dismissed {len(sel)} — hidden from future searches. (Undo available)",
            "muted")
        self.refresh()
        self._restore_focus(idx)

    def _dismiss_company(self):
        """Bulk-dismiss every visible row from the selected row's company —
        the fast way to clear a flood from one mega-board."""
        sel = self._selected()
        if not sel:
            messagebox.showinfo("No selection", "Select a row first.")
            return
        if self._block_if_demo(sel):
            return
        companies = {(r["company"] or "") for r in sel}
        targets = [r for r in self._rows.values()
                   if (r["company"] or "") in companies]
        names = ", ".join(sorted(c for c in companies if c)) or "(unknown)"
        if not messagebox.askyesno(
                "Dismiss company",
                f"Dismiss all {len(targets)} visible row(s) from {names}?",
                parent=self):
            return
        idx = self._focus_index()
        ok, _ = db_guard(
            self, lambda: [tracker_service.dismiss_job(r["id"]) for r in targets],
            status_cb=lambda m: set_status(self._status, m, "err"),
            action="dismiss company")
        if not ok:
            return
        self._remember_undo(targets)
        set_status(
            self._status,
            f"Dismissed {len(targets)} row(s) from {names}. (Undo available)",
            "muted")
        self.refresh()
        self._restore_focus(idx)

    def _select_all(self, _event=None):
        """Ctrl+A: select every currently-visible (filtered) row, then keep the
        keyboard on the tree so a following D dismisses the lot. Returns 'break'
        so Tk's default Ctrl+A (which does nothing on a Treeview) is suppressed."""
        children = self._tree.get_children()
        if children:
            self._tree.selection_set(children)
            self._tree.focus_set()
        return "break"

    def _dismiss_all_shown(self):
        """Dismiss every row currently shown (respects the active filters). Reuses
        the same batch-dismiss + _remember_undo path as single-row Dismiss, so
        Undo restores the whole batch."""
        targets = list(self._rows.values())
        if not targets:
            messagebox.showinfo("Dismiss all shown",
                                "There are no rows to dismiss.", parent=self)
            return
        if self._block_if_demo(targets):
            return
        if not messagebox.askyesno(
                "Dismiss all shown",
                f"Dismiss all {len(targets)} row(s) currently shown?\n\n"
                "This respects your current filters and hides them from future "
                "searches. Undo is available.", parent=self):
            return
        ok, _ = db_guard(
            self, lambda: [tracker_service.dismiss_job(r["id"]) for r in targets],
            status_cb=lambda m: set_status(self._status, m, "err"),
            action="dismiss all shown")
        if not ok:
            return
        self._remember_undo(targets)
        set_status(
            self._status,
            f"Dismissed {len(targets)} row(s). (Undo available)", "muted")
        self.refresh()

    def _remember_undo(self, rows):
        """Stash the just-dismissed rows so Undo can re-insert them."""
        self._undo_rows = list(rows)
        if self._undo_btn.winfo_exists():
            self._undo_btn.config(
                state="normal" if self._undo_rows else "disabled")

    def _undo_dismiss(self):
        if not self._undo_rows:
            return
        ok, restored = db_guard(
            self,
            lambda: tracker_service.restore_dismissed_rows(self._undo_rows),
            status_cb=lambda m: set_status(self._status, m, "err"),
            action="undo dismiss")
        if not ok:
            return
        self._undo_rows = []
        self._undo_btn.config(state="disabled")
        set_status(self._status, f"Restored {restored} dismissed row(s).", "ok")
        self.refresh()

    def _open_url(self):
        for r in self._selected()[:5]:  # cap tab-storm
            u = safe_url(r.get("url"))
            if u:
                webbrowser.open(u)

    # Claude fit-scoring (copy-paste bridge) — selected rows, or a diverse
    # batch of unscored rows if none selected.
    def _copy_fit_prompt(self):
        rows = self._selected()
        if not rows:
            # Unscored first, max 2 per company, so one mega-board can't burn
            # all 20 slots. _rows is already round-robin ordered (inbox_all),
            # so repeated copy/paste rounds walk down the inbox naturally.
            rows = tracker_service.unscored_inbox_rows(
                list(self._rows.values()), per_company=2, limit=20)
        rows = rows[:20]  # one Claude reply handles ~20 jobs well
        if not rows:
            messagebox.showinfo("Inbox empty", "Nothing left to score.")
            return
        # Compact, gated AI request (spec-2026-06-29): facts+rubric instead of raw
        # descriptions, and structural non-fits are filtered out before the prompt
        # so no AI is spent on them.
        prompt, jobs, dropped = tracker_service.compact_fit_prompt_for_rows(rows)
        if dropped:
            try:
                tracker_service.mark_inbox_gated(dropped)
            except Exception:
                pass
            self.refresh()  # gated rows now carry a fit -> won't re-surface
        if not jobs:
            reasons = ", ".join(sorted({r for d in dropped for r in d["reasons"]}))
            messagebox.showinfo(
                "All auto-filtered",
                f"All {len(rows)} job(s) were auto-filtered ({reasons}). They kept a "
                "low local fit and won't re-surface — nothing to AI-rank.", parent=self)
            return
        self._fit_jobs = jobs
        self._fit_order = [r["id"] for r in rows]  # legacy/back-compat
        # API auto-route: when a key is present, rank directly without paste step.
        if _ranker_mod.has_api_key():
            # Single-flight: a second click during the multi-second round-trip
            # would mint a SECOND score_history batch over overlapping rows and
            # break one-click Undo (review-fleet major finding).
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
                         lambda m: set_status(self._status, m, "work"))
            if dropped:
                set_status(self._status,
                           f"Copied -- AI-ranking {len(jobs)}; auto-filtered "
                           f"{len(dropped)} (kept local score)", "work")

    def _api_rank_worker(self, prompt, jobs):
        """Background thread: call the API with the compact fit prompt and apply
        scores back to inbox rows. Posts results to the main thread via after()."""
        try:
            reply = _call_prompt_via_api(prompt)
        except Exception as exc:
            self._api_ranking = False
            self.after(0, lambda: set_status(self._status, f"API error: {exc}", "err"))
            return
        try:
            applied, missed = tracker_service.score_inbox_from_reply(
                jobs, reply, source="api")
        except Exception as exc:
            self._api_ranking = False
            self.after(0, lambda: set_status(
                self._status, f"Parse error: {exc}", "err"))
            return
        self.after(0, self._api_rank_done, applied, len(jobs), missed)

    def _api_rank_done(self, applied, asked, missed):
        self._api_ranking = False
        if not self.winfo_exists():
            return
        set_status(self._status, _scored_status(applied, asked, missed),
                   "ok" if not missed else "work")
        if missed:
            self._show_not_scored(missed)
        self.refresh()

    def _show_not_scored(self, missed):
        """Detail popup listing the jobs the AI was asked to score but didn't —
        parity with the file-import unmatched report."""
        if not missed:
            return
        titles = "\n".join(
            f"- {(m.get('title') or '(untitled)')} - {(m.get('company') or '')}".rstrip(" -")
            for m in missed[:40])
        more = f"\n...and {len(missed) - 40} more" if len(missed) > 40 else ""
        messagebox.showinfo(
            "Some jobs weren't scored",
            f"{len(missed)} job(s) were sent to the AI but came back without a "
            f"score, so their Fit grade is unchanged:\n\n{titles}{more}",
            parent=self)

    def _paste_fit(self):
        if not self._fit_jobs:
            messagebox.showinfo("No prompt", "Copy a fit prompt first.")
            return
        dlg = PasteDialog(self)
        if not dlg.result:
            return
        # Token-verified mapping (SCORE-5): the service uses the bridge's
        # match_fit_to_jobs so scores land on the right row even if the reply
        # reordered or skipped jobs — not positional trust.
        asked = len(self._fit_jobs)
        try:
            ok, res = db_guard(
                self,
                lambda: tracker_service.score_inbox_from_reply(
                    self._fit_jobs, dlg.result, source="bridge"),
                status_cb=lambda m: set_status(self._status, m, "err"),
                action="apply fit scores")
        except BridgeParseError as e:
            messagebox.showerror("Parse failed", str(e), parent=self)
            return
        if not ok:
            return
        applied, missed = res
        set_status(self._status, _scored_status(applied, asked, missed),
                   "ok" if not missed else "work")
        if missed:
            self._show_not_scored(missed)
        self.refresh()

    def _export_rows(self) -> list[dict]:
        """Rows to hand the AI: the entire inbox by default (so it can judge
        relevance over everything and pick a top-X), or just the current
        filtered view when chosen. Fictional sample-inbox rows are never
        exportable (defense in depth — _export_for_ai also blocks while the demo
        is active), so they can't reach the AI round-trip via any path."""
        rows = (self._filtered() if self._export_scope.get() == "Current view"
                else list(self._all))
        return [r for r in rows if not r.get("is_demo")]

    def _export_for_ai(self):
        """Write the round-trip trio (csv+md+prompt) for the chosen inbox scope
        to a timestamped folder under OUTPUT_DIR/rerank, then open the folder."""
        from datetime import datetime
        from rerank.export import export_inbox
        # The sample inbox is fictional (source "Demo", negative ids): never hand
        # it to the user's AI as if it were their real scored inbox. Block export
        # while the demo is active — the same nudge every triage action shows —
        # so the round-trip only ever carries real jobs.
        if getattr(self, "_demo_active", False):
            messagebox.showinfo(
                "Sample inbox",
                "These are example jobs to show you what a scored inbox looks "
                "like — there's nothing real to export yet. Click “Update my "
                "Inbox now” to pull in real jobs, then export those.",
                parent=self)
            return
        rows = self._export_rows()
        if not rows:
            messagebox.showinfo(
                "Nothing to export",
                "The inbox is empty — run a search first."
                if self._export_scope.get() == "Entire inbox"
                else "No jobs match the current filters.")
            return
        stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
        out_dir = Path(OUTPUT_DIR) / "rerank" / stamp
        chunk_map = {"All in one file": None, "Split by 100": 100, "Split by 50": 50}
        chunk_size = chunk_map.get(self._export_chunk.get())
        compact = bool(self._export_compact.get())
        try:
            paths = export_inbox(rows, out_dir, fmt="both",
                                 chunk_size=chunk_size, compact=compact)
        except Exception as e:
            messagebox.showerror("Export failed", str(e))
            return
        n_files = len(paths.get("csvs", [paths.get("csv")]))
        extra = (f" ({n_files} files)" if n_files > 1 else "") + \
                (" [compact]" if compact else "")
        set_status(self._status,
                   f"Exported {len(rows)} rows -> {out_dir}{extra}", "info")
        try:
            subprocess.Popen(["explorer", str(out_dir)])
        except Exception:
            pass

    def _import_scores(self):
        """Pick an AI-returned CSV/JSON, show a dry-run preview of matched/
        unmatched, and on confirm apply with the selected merge policy."""
        from rerank.import_ import import_scores
        path = filedialog.askopenfilename(
            title="Import AI scores",
            filetypes=[("CSV or JSON", "*.csv *.json"), ("All files", "*.*")])
        if not path:
            return
        policy = self._merge_policy.get()
        rows_by_key = tracker_service.inbox_rows_by_key()
        # Dry-run preview: a no-op apply so nothing is written yet.
        preview = import_scores(path, rows_by_key, policy=policy,
                                _apply=lambda u, *, source="file_import": len(u))
        msg = (f"Matched {preview.matched}, would update {preview.updated}, "
               f"skip {preview.skipped}, unmatched {len(preview.unmatched)}.\n"
               f"Policy: {policy}. Apply now?")
        if preview.errors:
            msg += f"\n{len(preview.errors)} row error(s) will be skipped."
        if not messagebox.askyesno("Import preview", msg, parent=self):
            return
        res = import_scores(path, rows_by_key, policy=policy)  # real apply
        set_status(self._status,
                   f"Re-ranked {res.updated} (skipped {res.skipped}, "
                   f"unmatched {len(res.unmatched)}).", "info")
        self.refresh()

    def _undo_rerank(self):
        """Revert the most recent AI re-rank batch on ANY route (file import,
        clipboard bridge, API auto-rank, or MCP) via score_history. scope='any'
        makes Undo work after a paste/MCP rank, not just a file import — the
        biggest BYO-AI trust hazard (arbitrary AIs writing scores)."""
        n = tracker_service.undo_last_rerank("any")
        set_status(self._status,
                   f"Undid last AI ranking: restored {n} job(s)." if n else
                   "No AI ranking to undo.", "muted" if n else "info")
        self.refresh()
