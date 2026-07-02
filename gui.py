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
from match import skillgap as skillgapmod
from match import comp as compmod
from match.scorer import score_breakdown, extract_skill_terms
from tracker import analytics as analyticsmod
from scrape.inbox_health import prune_inbox
from ui import theme
from ui import chrome
from ui import help as uihelp
from ui import setup_wizard
from ui import settings as uisettings

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def safe_url(url):
    """Return url unchanged only when its scheme is http or https.
    Rejects javascript:, data:, file:, and any other scheme.
    Returns '' so callers can test: if u := safe_url(raw): webbrowser.open(u)"""
    if not url:
        return ""
    try:
        return url if urlparse(url).scheme in ("http", "https") else ""
    except ValueError:
        return ""


def _call_prompt_via_api(prompt):
    """Send a pre-built prompt to the Anthropic API and return the raw text reply.
    Uses the key from ranker.api_key() and config.ANTHROPIC_MODEL. Raises
    RuntimeError when no key is configured; re-raises any API error."""
    import config as _cfg
    key = _ranker_mod.api_key()
    if not key:
        raise RuntimeError(
            "No Anthropic API key -- set ANTHROPIC_API_KEY or save one in "
            "Tools > Connect your AI.")
    import anthropic
    client = anthropic.Anthropic(api_key=key, base_url=_cfg.anthropic_base_url())
    msg = client.messages.create(
        model=_cfg.ANTHROPIC_MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(
        getattr(b, "text", "") for b in msg.content
        if getattr(b, "type", None) == "text"
    )


def _scored_status(applied, asked, missed) -> str:
    """Status line for a fit-scoring round, surfacing partial coverage:
    'Scored 17/20 - 3 not scored' (bridge partial-coverage, C2 P4). No missed
    -> 'Scored 20/20.'"""
    n_missed = len(missed) if missed else 0
    if n_missed:
        return f"Scored {applied}/{asked} - {n_missed} not scored"
    return f"Scored {applied}/{asked}."


class _LineSink(io.TextIOBase):
    """A minimal text stream that forwards whole lines to a callback. Used to
    capture the daily-ingest pipeline's print() output (per-source counts, a
    429'd source, an expired key) so the GUI can render live progress instead of
    discarding it — daily_run narrates via print(), not a passed-in log sink."""

    def __init__(self, on_line):
        self._on_line = on_line
        self._buf = ""

    def write(self, s):
        if not s:
            return 0
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            try:
                self._on_line(line)
            except Exception:
                pass
        return len(s)

    def flush(self):
        if self._buf:
            try:
                self._on_line(self._buf)
            except Exception:
                pass
            self._buf = ""


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


# ── Palette ── all sourced from ui.theme (clean light/modern) so the whole app
# shares one set of colors. Legacy names kept so existing call sites still read.
DARK  = theme.INK       # dark ink (was the dark header navy)
MID   = theme.MUTED
BG    = theme.WINDOW    # app/background fills
WHITE = theme.SURFACE   # cards / white surfaces
ERR   = theme.DANGER

# Named status colors for set_status(label, text, kind).
OK    = theme.SUCCESS   # success / done (green)
WORK  = theme.WARN      # in-progress (amber)
INFO  = theme.ACCENT    # neutral notice (accent)
MUTED = theme.MUTED     # de-emphasized (grey)

_STATUS_COLORS = {
    "ok": OK, "work": WORK, "info": INFO, "muted": MUTED, "err": ERR,
}


def _sync_palette_aliases():
    """Re-point the legacy module-level color aliases at the *active* theme
    palette. The aliases above are captured at import; after a light/dark switch
    (theme.set_mode) this refreshes them so widgets rebuilt next use new colors."""
    global DARK, MID, BG, WHITE, ERR, OK, WORK, INFO, MUTED, _STATUS_COLORS
    DARK, MID, BG = theme.INK, theme.MUTED, theme.WINDOW
    WHITE, ERR = theme.SURFACE, theme.DANGER
    OK, WORK, INFO, MUTED = theme.SUCCESS, theme.WARN, theme.ACCENT, theme.MUTED
    _STATUS_COLORS = {"ok": OK, "work": WORK, "info": INFO, "muted": MUTED,
                      "err": ERR}


def set_status(label, text, kind="muted"):
    """Set a tk.Label's text and color by semantic kind (ok/work/info/muted/err)
    instead of repeating inline hex at each call site."""
    label.config(text=text, fg=_STATUS_COLORS.get(kind, MUTED))

# Job-Tracker status badge colors are theme-aware (light/dark) via theme.STATUS_BADGE;
# tabs are rebuilt on a theme switch so the tree re-reads the active set.


# ── Add / Edit dialog ─────────────────────────────────────────────────────────
_ROUND_KINDS = ["phone", "tech", "onsite", "final", "other"]


class JobDialog(tk.Toplevel):
    """Modal form for adding or editing a job entry. When editing an existing
    application it also surfaces the full application cycle: offer fields (shown
    when status is offer/accepted), interview rounds (add/edit/.ics), a referral
    hint from known contacts, an 'Add note' quick action, and a read-only
    timeline of status changes + notes."""

    def __init__(self, parent, job=None):
        super().__init__(parent)
        self.title("Edit Job" if job else "Add Job")
        self.resizable(False, False)
        self.grab_set()
        self.result = None
        self._job = job
        self._job_id = job.get("id") if job else None

        p = {"padx": 8, "pady": 5}
        form = ttk.Frame(self, padding=16)
        form.pack(fill="both", expand=True)

        self._vars = {}

        def entry(label, key, row, col, width=28, span=1):
            ttk.Label(form, text=label).grid(
                row=row, column=col * 2, sticky="w", **p)
            var = tk.StringVar(value=(job or {}).get(key, ""))
            self._vars[key] = var
            ttk.Entry(form, textvariable=var, width=width).grid(
                row=row, column=col * 2 + 1, columnspan=span, sticky="ew", **p)

        # Left column
        entry("Title *",   "title",       0, 0)
        entry("Company *", "company",     1, 0)
        entry("Location",  "location",    2, 0)
        entry("Salary",    "salary_text", 3, 0)

        # Right column
        entry("Job URL",      "url",          0, 1, width=42, span=3)
        entry("Date Applied", "date_applied", 1, 1, width=14)
        ttk.Label(form, text="YYYY-MM-DD", foreground=theme.MUTED).grid(
            row=1, column=4, sticky="w")

        ttk.Label(form, text="Status").grid(row=2, column=2, sticky="w", **p)
        sv = tk.StringVar(value=(job or {}).get("status", "interested"))
        self._vars["status"] = sv
        sv.trace_add("write", lambda *_a: self._sync_offer_visibility())
        ttk.Combobox(form, textvariable=sv, values=STATUSES,
                     state="readonly", width=16).grid(
            row=2, column=3, sticky="w", **p)

        # Job-hunt fields
        entry("Follow-up",  "follow_up_date", 3, 1, width=14)
        entry("Deadline",   "deadline",       5, 0)
        entry("Contact",    "contact",        5, 1, width=42, span=3)

        # Notes — full width
        ttk.Label(form, text="Notes").grid(row=4, column=0, sticky="nw", **p)
        self._notes = theme.text_widget(form, width=70, height=5,
                                        font=("Segoe UI", 9))
        self._notes.grid(row=4, column=1, columnspan=4, sticky="ew", **p)
        if job and job.get("notes"):
            self._notes.insert("1.0", job["notes"])

        # Referral hint (from known contacts at this company).
        if job:
            hint = tracker_service.referral_hint(job.get("company", ""))
            if hint:
                tk.Label(form, text="\N{BUST IN SILHOUETTE}  " + hint,
                         bg=theme.WINDOW, fg=theme.ACCENT, font=theme.FONT_SM,
                         anchor="w", justify="left", wraplength=760).grid(
                    row=6, column=0, columnspan=5, sticky="w", padx=8, pady=(2, 4))

        # Offer fields — created always, gridded/hidden by status (offer/accepted).
        self._offer_frame = tk.Frame(form, bg=theme.WINDOW)
        self._offer_frame.grid(row=7, column=0, columnspan=5, sticky="ew",
                               padx=6, pady=(2, 2))
        of = self._offer_frame
        tk.Label(of, text="Offer:", bg=theme.WINDOW, fg=theme.INK,
                 font=theme.FONT_BOLD).pack(side="left", padx=(2, 8))
        for label, key, width in (("Amount", "offer_amount", 14),
                                  ("Decide by", "offer_deadline", 12)):
            tk.Label(of, text=label + ":", bg=theme.WINDOW, fg=theme.INK,
                     font=theme.FONT_SM).pack(side="left")
            v = tk.StringVar(value=(job or {}).get(key, ""))
            self._vars[key] = v
            ttk.Entry(of, textvariable=v, width=width).pack(side="left", padx=(2, 10))
        tk.Label(of, text="Notes:", bg=theme.WINDOW, fg=theme.INK,
                 font=theme.FONT_SM).pack(side="left")
        onv = tk.StringVar(value=(job or {}).get("offer_notes", ""))
        self._vars["offer_notes"] = onv
        ttk.Entry(of, textvariable=onv, width=30).pack(side="left", padx=2)

        # Cycle sections only make sense once the job is a tracked application.
        if self._job_id is not None:
            self._build_rounds(form)
            self._build_timeline(form)

        # Buttons
        btns = ttk.Frame(self, padding=(16, 0, 16, 16))
        btns.pack(fill="x")
        theme.btn(btns, "Save", self._save, "accent").pack(side="right", padx=4)
        theme.btn(btns, "Cancel", self.destroy, "ghost").pack(side="right")
        if self._job_id is not None:
            theme.btn(btns, "Add note", self._add_note, "ghost").pack(side="left")

        self._sync_offer_visibility()
        self.transient(parent)
        self.wait_window()

    # ── Offer fields visibility ──────────────────────────────────────────────
    def _sync_offer_visibility(self):
        show = self._vars["status"].get() in ("offer", "accepted")
        try:
            if show:
                self._offer_frame.grid()
            else:
                self._offer_frame.grid_remove()
        except tk.TclError:
            pass

    # ── Interview rounds ─────────────────────────────────────────────────────
    def _build_rounds(self, form):
        box = tk.LabelFrame(form, text="Interview rounds", bg=theme.WINDOW,
                            fg=theme.INK, font=theme.FONT_SM, padx=8, pady=6)
        box.grid(row=8, column=0, columnspan=5, sticky="ew", padx=6, pady=(6, 2))
        cols = [("round", "#", 30), ("kind", "Kind", 70),
                ("when", "Scheduled", 140), ("who", "Interviewer", 130),
                ("outcome", "Outcome", 100)]
        self._rounds_tree = ttk.Treeview(box, columns=[c[0] for c in cols],
                                         show="headings", height=4,
                                         selectmode="browse")
        for c, l, w in cols:
            self._rounds_tree.heading(c, text=l)
            self._rounds_tree.column(c, width=w, anchor="w")
        theme.zebra(self._rounds_tree)
        self._rounds_tree.pack(fill="x")
        self._rounds_tree.bind("<Double-1>", lambda _e: self._edit_round())
        bb = tk.Frame(box, bg=theme.WINDOW)
        bb.pack(fill="x", pady=(4, 0))
        theme.btn(bb, "Add round", self._add_round, "ghost").pack(side="left", padx=2)
        theme.btn(bb, "Edit", self._edit_round, "ghost").pack(side="left", padx=2)
        theme.btn(bb, "Remove", self._remove_round, "ghost").pack(side="left", padx=2)
        theme.btn(bb, "Add to calendar", self._round_ics, "ghost").pack(side="left", padx=2)
        self._reload_rounds()

    def _reload_rounds(self):
        for iid in self._rounds_tree.get_children():
            self._rounds_tree.delete(iid)
        for i, r in enumerate(list_interview_rounds(self._job_id)):
            self._rounds_tree.insert(
                "", "end", iid=str(r["id"]), tags=(theme.row_tag(i),),
                values=(r["round_no"], r["kind"], r["scheduled_at"],
                        r["interviewer"], r["outcome"]))

    def _sel_round_id(self):
        s = self._rounds_tree.selection()
        return int(s[0]) if s else None

    def _add_round(self):
        dlg = _RoundDialog(self)
        if dlg.result:
            db_guard(self, lambda: add_interview_round(self._job_id, **dlg.result),
                     action="add interview round")
            self._reload_rounds()

    def _edit_round(self):
        rid = self._sel_round_id()
        if rid is None:
            messagebox.showinfo("No selection", "Select a round first.", parent=self)
            return
        rnd = tracker_service.get_interview_round(rid)
        dlg = _RoundDialog(self, rnd=rnd)
        if dlg.result:
            db_guard(self, lambda: tracker_service.update_interview_round(rid, **dlg.result),
                     action="update interview round")
            self._reload_rounds()

    def _remove_round(self):
        rid = self._sel_round_id()
        if rid is None:
            return
        if messagebox.askyesno("Remove round?", "Delete this interview round?",
                               parent=self):
            db_guard(self, lambda: delete_interview_round(rid),
                     action="delete interview round")
            self._reload_rounds()

    def _round_ics(self):
        rid = self._sel_round_id()
        if rid is None:
            messagebox.showinfo("No selection", "Select a round first.", parent=self)
            return
        rnd = tracker_service.get_interview_round(rid)
        try:
            path = tracker_service.write_round_ics(
                self._job or {}, rnd, workspace.output_dir())
        except ValueError as e:
            messagebox.showinfo("Add to calendar", str(e), parent=self)
            return
        except Exception as e:
            messagebox.showerror("Add to calendar", str(e), parent=self)
            return
        uihelp._open_path(path.parent)
        messagebox.showinfo(
            "Add to calendar",
            f"Saved {path.name}. Opening its folder — double-click the .ics to add "
            "it to your calendar.", parent=self)

    # ── Timeline ─────────────────────────────────────────────────────────────
    def _build_timeline(self, form):
        box = tk.LabelFrame(form, text="Timeline", bg=theme.WINDOW, fg=theme.INK,
                            font=theme.FONT_SM, padx=8, pady=6)
        box.grid(row=9, column=0, columnspan=5, sticky="ew", padx=6, pady=(2, 4))
        self._timeline = theme.text_widget(box, width=90, height=6,
                                           font=("Segoe UI", 9))
        self._timeline.pack(fill="x")
        self._reload_timeline()

    def _reload_timeline(self):
        events = status_timeline(self._job_id)
        lines = []
        for e in events:
            when = (e["changed_at"] or "")[:16].replace("T", " ")
            if e["kind"] == "note":
                lines.append(f"{when}  note: {e['note']}")
            else:
                base = f"{when}  {e['old_status']} -> {e['new_status']}"
                if e["note"]:
                    base += f"  ({e['note']})"
                lines.append(base)
        text = "\n".join(lines) if lines else "No history yet."
        self._timeline.config(state="normal")
        self._timeline.delete("1.0", "end")
        self._timeline.insert("1.0", text)
        self._timeline.config(state="disabled")

    def _add_note(self):
        note = simpledialog.askstring(
            "Add note", "Add a timestamped note to this application:", parent=self)
        if not note or not note.strip():
            return
        ok, _ = db_guard(self, lambda: add_status_note(self._job_id, note.strip()),
                         action="add note")
        if ok:
            self._reload_timeline()

    def _save(self):
        title   = self._vars["title"].get().strip()
        company = self._vars["company"].get().strip()
        if not title or not company:
            messagebox.showerror("Required",
                "Title and Company are required.", parent=self)
            return
        for key, label in (("date_applied", "Date Applied"),
                           ("follow_up_date", "Follow-up"),
                           ("deadline", "Deadline"),
                           ("offer_deadline", "Offer decide-by")):
            v = self._vars[key].get().strip()
            if v and not _DATE_RE.match(v):
                messagebox.showerror("Bad date",
                    f"{label} must be YYYY-MM-DD (got {v!r}).", parent=self)
                return
        self.result = {
            "title":          title,
            "company":        company,
            "location":       self._vars["location"].get().strip(),
            "salary_text":    self._vars["salary_text"].get().strip(),
            "url":            self._vars["url"].get().strip(),
            "status":         self._vars["status"].get(),
            "date_applied":   self._vars["date_applied"].get().strip(),
            "follow_up_date": self._vars["follow_up_date"].get().strip(),
            "deadline":       self._vars["deadline"].get().strip(),
            "contact":        self._vars["contact"].get().strip(),
            "notes":          self._notes.get("1.0", "end-1c").strip(),
            "offer_amount":   self._vars["offer_amount"].get().strip(),
            "offer_deadline": self._vars["offer_deadline"].get().strip(),
            "offer_notes":    self._vars["offer_notes"].get().strip(),
        }
        self.destroy()


class _RoundDialog(tk.Toplevel):
    """Small modal to add/edit one interview round. .result is the field dict
    (or None on cancel)."""

    def __init__(self, parent, rnd=None):
        super().__init__(parent)
        self.title("Edit round" if rnd else "Add interview round")
        self.resizable(False, False)
        self.grab_set()
        self.result = None
        rnd = rnd or {}
        form = ttk.Frame(self, padding=14)
        form.pack(fill="both", expand=True)
        self._vars = {}

        ttk.Label(form, text="Kind").grid(row=0, column=0, sticky="w", padx=6, pady=5)
        kv = tk.StringVar(value=rnd.get("kind", "phone"))
        self._vars["kind"] = kv
        ttk.Combobox(form, textvariable=kv, values=_ROUND_KINDS,
                     state="readonly", width=14).grid(row=0, column=1, sticky="w",
                                                      padx=6, pady=5)

        def entry(label, key, row, hint=""):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w",
                                             padx=6, pady=5)
            v = tk.StringVar(value=rnd.get(key, ""))
            self._vars[key] = v
            ttk.Entry(form, textvariable=v, width=32).grid(
                row=row, column=1, sticky="ew", padx=6, pady=5)
            if hint:
                ttk.Label(form, text=hint, foreground=theme.MUTED).grid(
                    row=row, column=2, sticky="w")

        entry("Scheduled", "scheduled_at", 1, "YYYY-MM-DD or ...THH:MM")
        entry("Interviewer", "interviewer", 2)
        entry("Outcome", "outcome", 3)
        ttk.Label(form, text="Notes").grid(row=4, column=0, sticky="nw", padx=6, pady=5)
        self._notes = theme.text_widget(form, width=40, height=3, font=("Segoe UI", 9))
        self._notes.grid(row=4, column=1, columnspan=2, sticky="ew", padx=6, pady=5)
        if rnd.get("notes"):
            self._notes.insert("1.0", rnd["notes"])

        bb = ttk.Frame(self, padding=(14, 0, 14, 14))
        bb.pack(fill="x")
        theme.btn(bb, "Save", self._save, "accent").pack(side="right", padx=4)
        theme.btn(bb, "Cancel", self.destroy, "ghost").pack(side="right")
        self.transient(parent)
        self.wait_window()

    def _save(self):
        sched = self._vars["scheduled_at"].get().strip()
        # Accept a bare date or an ISO datetime; validate the date portion only.
        if sched and not _DATE_RE.match(sched[:10]):
            messagebox.showerror(
                "Bad date", "Scheduled must start with YYYY-MM-DD.", parent=self)
            return
        self.result = {
            "kind": self._vars["kind"].get(),
            "scheduled_at": sched,
            "interviewer": self._vars["interviewer"].get().strip(),
            "outcome": self._vars["outcome"].get().strip(),
            "notes": self._notes.get("1.0", "end-1c").strip(),
        }
        self.destroy()


# ── Paste dialog (Claude copy-paste bridge) ──────────────────────────────────
class PasteDialog(tk.Toplevel):
    """Modal: paste Claude's reply, returns the text in .result (or None)."""

    def __init__(self, parent, title="Paste Claude's reply",
                 hint="Paste the JSON reply from claude.ai below:"):
        super().__init__(parent)
        self.title(title)
        self.grab_set()
        self.result = None
        self.geometry("640x420")

        ttk.Label(self, text=hint, padding=(10, 8)).pack(anchor="w")
        body = ttk.Frame(self, padding=(10, 0, 10, 0))
        body.pack(fill="both", expand=True)
        self._text = theme.text_widget(body, font=("Consolas", 9))
        vsb = ttk.Scrollbar(body, orient="vertical", command=self._text.yview)
        self._text.configure(yscrollcommand=vsb.set)
        self._text.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        btns = ttk.Frame(self, padding=10)
        btns.pack(fill="x")
        theme.btn(btns, "OK", self._ok, "accent").pack(side="right", padx=4)
        theme.btn(btns, "Cancel", self.destroy, "ghost").pack(side="right")
        self._text.focus_set()
        self.transient(parent)
        self.wait_window()

    def _ok(self):
        self.result = self._text.get("1.0", "end-1c").strip()
        self.destroy()


def db_guard(parent, op, *, status_cb=None, action="operation"):
    """Run a DB-mutating op, converting an sqlite3.Error (e.g. the daily run is
    mid-write) into visible feedback instead of a silent crash. Returns
    (ok, result): result is the op's return value on success, else None."""
    try:
        return True, op()
    except sqlite3.Error as e:
        msg = f"Database busy — {action} failed. Try again. ({e})"
        if status_cb:
            status_cb(msg)
        else:
            messagebox.showerror("Database error", msg, parent=parent)
        return False, None


def copy_or_warn(parent, text: str, status_cb=None) -> bool:
    """Clipboard copy with a visible failure path; returns success."""
    if to_clipboard(text):
        if status_cb:
            status_cb("Prompt copied — paste it into claude.ai, then paste "
                      "the reply back here.")
        return True
    messagebox.showerror("Clipboard", "Could not copy to clipboard.",
                         parent=parent)
    return False


# ── Job Tracker tab ───────────────────────────────────────────────────────────
class TrackerTab(ttk.Frame):

    _COLS = [
        ("title",    "Title",    300, "w"),
        ("company",  "Company",  150, "w"),
        ("location", "Location", 115, "w"),
        ("status",   "Status",   100, "w"),
        ("salary",   "Salary",    85, "w"),
        ("applied",  "Applied",   88, "center"),
        ("added",    "Added",     88, "center"),
    ]
    _KEY = {
        "title":   "title",    "company": "company",
        "location":"location", "status":  "status",
        "salary":  "salary_text",
        "applied": "date_applied", "added": "date_added",
    }

    def __init__(self, parent):
        super().__init__(parent)
        self._active = "all"
        self._sort_col = "added"
        self._sort_asc = False
        self._build()
        self.refresh()

    def _build(self):
        # Header
        hdr = theme.header_bar(self, "Job Application Tracker")
        theme.btn(hdr, "+ Add Job", self._add, "accent").pack(
            side="right", padx=10, pady=8)
        self._count_lbl = tk.Label(hdr, text="", bg=theme.SURFACE,
                                    fg=theme.MUTED, font=theme.FONT_SM)
        self._count_lbl.pack(side="right", padx=8)
        theme.tip_strip(
            self, "Every job you're tracking and its status. Double-click to "
                  "edit; use Quick status to update as you hear back.")

        # Status filter bar
        self._fbar = tk.Frame(self, bg=theme.WINDOW, pady=6)
        self._fbar.pack(fill="x", padx=6)

        # Tree
        tf = ttk.Frame(self)
        tf.pack(fill="both", expand=True, padx=6, pady=2)
        self._tree = ttk.Treeview(
            tf, columns=[c[0] for c in self._COLS],
            show="headings", selectmode="extended")
        for col, label, width, anchor in self._COLS:
            self._tree.heading(col, text=label,
                               command=lambda c=col: self._sort_by(c))
            self._tree.column(col, width=width, anchor=anchor, minwidth=60)
        for status, fg in theme.STATUS_BADGE.items():
            self._tree.tag_configure(status, foreground=fg)
        theme.zebra(self._tree)

        vsb = ttk.Scrollbar(tf, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self._tree.bind("<Double-1>", lambda _e: self._edit())
        self._tree.bind("<<TreeviewSelect>>", self._on_select)
        # Ctrl+A selects every visible row (single-row actions still act on the
        # first selection via _sel_iid()).
        self._tree.bind("<Control-a>", self._select_all)
        self._tree.bind("<Control-A>", self._select_all)

        # Action bar — contents depend on the view (active vs archive), rebuilt
        # by _rebuild_actionbar() when the view mode changes.
        self._abar = tk.Frame(self, bg=BG, pady=6)
        self._abar.pack(fill="x", padx=6, side="bottom")
        self._qstatus = tk.StringVar()
        self._abar_mode = None
        self._rebuild_actionbar()

    def _rebuild_actionbar(self):
        for w in self._abar.winfo_children():
            w.destroy()

        def btn(text, cmd, kind="ghost"):
            theme.btn(self._abar, text, cmd, kind).pack(side="left", padx=2)

        if self._active == "archived":
            btn("Restore", self._restore)
            btn("Delete permanently", self._delete, "danger")
            btn("Open URL", self._open_url)
            return

        btn("Edit", self._edit)
        btn("Archive", self._archive)
        btn("Open URL", self._open_url)
        tk.Label(self._abar, text="   Quick status:", bg=theme.WINDOW,
                 fg=theme.INK, font=theme.FONT_SM).pack(side="left")
        qcb = ttk.Combobox(self._abar, textvariable=self._qstatus,
                           values=STATUSES, state="readonly", width=14)
        qcb.pack(side="left", padx=4)
        qcb.bind("<<ComboboxSelected>>", self._quick_status)

    def _rebuild_filters(self, counts):
        for w in self._fbar.winfo_children():
            w.destroy()
        tabs = [("all", f"All ({counts['all']})")] + [
            (s, f"{STATUS_LABELS[s]} ({counts[s]})") for s in STATUSES]
        tabs.append(("archived", f"Archive ({counts.get('archived', 0)})"))
        for key, label in tabs:
            active = key == self._active
            theme.btn(self._fbar, label, lambda k=key: self._filter(k),
                      "accent" if active else "ghost").pack(side="left", padx=1)

    # ── Selection ─────────────────────────────────────────────────────────────

    def _sel_iid(self):
        sel = self._tree.selection()
        return sel[0] if sel else None

    def _select_all(self, _event=None):
        children = self._tree.get_children()
        if children:
            self._tree.selection_set(children)
            self._tree.focus_set()
        return "break"

    def _on_select(self, _event=None):
        iid = self._sel_iid()
        if iid:
            job = get_job(int(iid))
            if job:
                self._qstatus.set(job["status"])

    # ── Data ops ──────────────────────────────────────────────────────────────

    def _filter(self, key):
        self._active = key
        self.refresh()

    def _sort_by(self, col):
        if self._sort_col == col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col
            self._sort_asc = True
        self.refresh()

    def refresh(self):
        sf   = self._active if self._active != "all" else None
        jobs = get_all(sf)
        key  = self._KEY.get(self._sort_col, "date_added")
        jobs.sort(key=lambda j: (j.get(key) or ""), reverse=not self._sort_asc)

        # Swap the action bar when entering/leaving the archive view.
        mode = "archived" if self._active == "archived" else "active"
        if mode != self._abar_mode:
            self._abar_mode = mode
            self._rebuild_actionbar()

        counts = get_counts()
        self._rebuild_filters(counts)
        # Follow-up nudge: count active applications whose follow_up_date has
        # arrived (set automatically a week after Mark Applied). Targeted COUNT
        # instead of a second full get_all() scan into Python (GUI-10).
        due = count_followups_due()
        label = f"{counts['all']} total"
        if due:
            label += f"  •  {due} follow-up(s) due"
        self._count_lbl.config(text=label,
                               fg=(theme.WARN if due else theme.MUTED))

        for row in self._tree.get_children():
            self._tree.delete(row)
        for i, j in enumerate(jobs):
            self._tree.insert("", "end", iid=str(j["id"]),
                              tags=(j["status"], theme.row_tag(i)),
                              values=(
                                  j["title"], j["company"],
                                  j.get("location", ""),
                                  STATUS_LABELS.get(j["status"], j["status"]),
                                  j.get("salary_text", ""),
                                  j.get("date_applied", ""),
                                  j.get("date_added", ""),
                              ))

    def _add(self):
        dlg = JobDialog(self)
        if dlg.result:
            ok, _ = db_guard(self, lambda: tracker_service.add_manual_job(**dlg.result),
                             action="add job")
            if ok:
                self.refresh()

    def _edit(self):
        iid = self._sel_iid()
        if not iid:
            messagebox.showinfo("No selection", "Select a job row first.")
            return
        dlg = JobDialog(self, job=tracker_service.get_job(int(iid)))
        if dlg.result:
            ok, _ = db_guard(self, lambda: tracker_service.update_job(int(iid), **dlg.result),
                             action="update job")
            if ok:
                self.refresh()

    def _archive(self):
        iid = self._sel_iid()
        if not iid:
            return
        job = tracker_service.get_job(int(iid))
        if messagebox.askyesno("Archive?",
                f"Archive '{job['title']}' at {job['company']}?\n\n"
                "It moves to the Archive view and stops showing in searches. "
                "You can restore it any time."):
            ok, _ = db_guard(self, lambda: tracker_service.archive_job(int(iid)),
                             action="archive job")
            if ok:
                self.refresh()

    def _restore(self):
        iid = self._sel_iid()
        if not iid:
            return
        ok, _ = db_guard(self, lambda: tracker_service.restore_job(int(iid)),
                         action="restore job")
        if ok:
            self.refresh()

    def _delete(self):
        iid = self._sel_iid()
        if not iid:
            return
        job = tracker_service.get_job(int(iid))
        if messagebox.askyesno("Delete permanently?",
                f"Permanently delete '{job['title']}' at {job['company']}?\n\n"
                "This cannot be undone.", icon="warning"):
            ok, _ = db_guard(self, lambda: tracker_service.delete_job(int(iid)),
                             action="delete job")
            if ok:
                self.refresh()

    def _open_url(self):
        iid = self._sel_iid()
        if not iid:
            return
        url = (tracker_service.get_job(int(iid)) or {}).get("url", "")
        surl = safe_url(url)
        if surl:
            webbrowser.open(surl)
        else:
            messagebox.showinfo("No URL", "This job has no URL saved.")

    def _quick_status(self, _event=None):
        iid = self._sel_iid()
        if not iid:
            return
        ok, _ = db_guard(self, lambda: tracker_service.set_status(int(iid), self._qstatus.get()),
                         action="change status")
        if ok:
            self.refresh()


# ── Resume Generator tab ──────────────────────────────────────────────────────
class ResumeTab(ttk.Frame):

    def __init__(self, parent):
        super().__init__(parent)
        self._output_dir = None
        self._build()

    def _build(self):
        # Header
        theme.header_bar(
            self, "Resume & Cover Letter Generator",
            "Paste a job posting — Claude generates a tailored resume + cover letter.")
        theme.tip_strip(
            self, "Paste any job posting below, then click 1. Copy Prompt → paste "
                  "it into claude.ai → 2. Paste the reply to get Word documents.")

        # Text input area
        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Job Posting",
                  font=("Segoe UI", 9, "bold")).pack(anchor="w")

        txt_f = ttk.Frame(body)
        txt_f.pack(fill="both", expand=True, pady=4)
        self._text = theme.text_widget(txt_f, font=("Segoe UI", 10))
        vsb = ttk.Scrollbar(txt_f, orient="vertical", command=self._text.yview)
        self._text.configure(yscrollcommand=vsb.set)
        self._text.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        # Control bar — copy-paste bridge is the default path; the API button
        # appears only when ANTHROPIC_API_KEY is configured.
        bar = tk.Frame(self, bg=theme.WINDOW, pady=8)
        bar.pack(fill="x", padx=12, side="bottom")

        theme.tip(theme.btn(bar, "1. Copy Prompt", self._copy_prompt, "accent"),
                  "Copies a tailoring prompt for the pasted job. Paste it into "
                  "claude.ai.").pack(side="left")
        theme.tip(theme.btn(bar, "2. Paste Reply \N{BLACK RIGHT-POINTING SMALL TRIANGLE} DOCX",
                            self._paste_reply, "ghost"),
                  "Paste Claude's reply here to build the resume + cover-letter "
                  "Word files.").pack(side="left", padx=8)

        from resume.service import api_available
        self._gen_btn = None
        if api_available():
            self._gen_btn = theme.btn(bar, "Generate via API", self._generate, "ghost")
            self._gen_btn.pack(side="left")

        theme.btn(bar, "Clear", self._clear, "ghost").pack(side="left", padx=8)

        self._status_lbl = tk.Label(bar, text="", bg=theme.WINDOW,
                                     fg=theme.MUTED, font=theme.FONT_SM)
        self._status_lbl.pack(side="left", padx=6)

        self._out_lbl = tk.Label(bar, text="", bg=theme.WINDOW, fg=theme.ACCENT,
                                  font=("Segoe UI", 9, "underline"),
                                  cursor="hand2")
        self._out_lbl.pack(side="left")
        self._out_lbl.bind("<Button-1>", self._open_folder)

    def _clear(self):
        self._text.delete("1.0", "end")
        self._status_lbl.config(text="", fg=theme.MUTED)
        self._out_lbl.config(text="")
        self._output_dir = None

    def _posting(self) -> str | None:
        posting = self._text.get("1.0", "end-1c").strip()
        if not posting:
            messagebox.showwarning("Empty", "Paste a job posting first.",
                                   parent=self)
            return None
        return posting

    # Bridge path (no API key): copy prompt -> claude.ai -> paste reply.
    def _copy_prompt(self):
        posting = self._posting()
        if not posting:
            return
        from resume.service import build_prompt
        try:
            prompt = build_prompt(posting)
        except Exception as e:
            self._status_lbl.config(text=f"Error: {e}", fg=ERR)
            return
        copy_or_warn(self, prompt,
                     lambda m: self._status_lbl.config(text=m, fg=theme.WARN))

    def _paste_reply(self):
        dlg = PasteDialog(self)
        if not dlg.result:
            return
        from resume.service import data_from_paste, save_bundle_from_data
        try:
            data = data_from_paste(dlg.result)
            resume_path, _cover = save_bundle_from_data(data, workspace.output_dir())
        except BridgeParseError as e:
            messagebox.showerror("Parse failed", str(e), parent=self)
            return
        except Exception as e:
            messagebox.showerror("DOCX failed", str(e), parent=self)
            return
        self._on_done(resume_path.parent)

    # API path
    def _generate(self):
        posting = self._posting()
        if not posting:
            return
        self._gen_btn.config(state="disabled")
        self._status_lbl.config(
            text="Generating with Claude...  (15–30 sec)", fg=theme.WARN)
        self._out_lbl.config(text="")
        threading.Thread(target=self._worker, args=(posting,),
                         daemon=True).start()

    def _worker(self, posting):
        try:
            from resume.service import save_bundle
            save_bundle(posting, workspace.output_dir())
            self.after(0, self._on_done, workspace.output_dir())
        except Exception as exc:
            self.after(0, self._on_error, str(exc))

    def _on_done(self, out_dir):
        if self._gen_btn:
            self._gen_btn.config(state="normal")
        self._output_dir = out_dir
        self._status_lbl.config(text="Done — saved to:", fg=theme.SUCCESS)
        self._out_lbl.config(text=str(out_dir))

    def _on_error(self, msg):
        if self._gen_btn:
            self._gen_btn.config(state="normal")
        self._status_lbl.config(text=f"Error: {msg}", fg=ERR)

    def _open_folder(self, _event=None):
        if self._output_dir:
            try:
                subprocess.Popen(["explorer", str(self._output_dir)])
            except OSError:
                pass


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
        hdr = theme.header_bar(self, "Inbox", "Fresh matches from the daily search.")
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
            self, "Your shortlist. Pick jobs you like and click "
                  "“Track ▸ Interested” — they move to Apply Queue. "
                  "Tip: click a row and press T (track), D (dismiss), O (open).")

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
        try:
            from coverage.reach import badge_line, load_latest
            snap = load_latest(workspace.active_slug() or "root")
            self._reach_lbl.config(text=badge_line(snap))
        except Exception:
            self._reach_lbl.config(text="")
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
                run_daily_ingest(slug, on_line=on_line)
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
            self._count_lbl.config(text=f"Update failed: {err}", fg=ERR)
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
        label = (f"{len(rows)} of {total} awaiting triage"
                 if len(rows) != total else f"{total} awaiting triage")
        if not getattr(self, "_has_home", True):
            label += "  •  All locations (set your location in Setup to enable local focus)"
        self._count_lbl.config(text=label)
        self._update_empty(rows)

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
        if desc.strip():
            if self._skill_terms is None:
                try:
                    self._skill_terms = extract_skill_terms()
                except Exception:
                    self._skill_terms = frozenset()
            try:
                gap = skillgapmod.skill_gap(desc, skill_terms=self._skill_terms)
                if gap["missing"]:
                    lines.append("Job also wants (not in your skills): "
                                 + ", ".join(gap["missing"][:8]))
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
        filtered view when chosen."""
        if self._export_scope.get() == "Current view":
            return self._filtered()
        return list(self._all)

    def _export_for_ai(self):
        """Write the round-trip trio (csv+md+prompt) for the chosen inbox scope
        to a timestamped folder under OUTPUT_DIR/rerank, then open the folder."""
        from datetime import datetime
        from rerank.export import export_inbox
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


# ── Top Picks tab ─────────────────────────────────────────────────────────────
class TopPicksTab(ttk.Frame):
    """The AI's current shortlist over the whole inbox, best-first. Reads
    tracker_service.top_picks (rows carrying an int `rank`); this tab never runs
    AI itself — it shows whatever the round-trip / API / MCP path ranked."""

    _COLS = [
        ("rank",     "#",         40, "center"),
        ("fit",      "Fit",       45, "center"),
        ("title",    "Title",    300, "w"),
        ("company",  "Company",  150, "w"),
        ("location", "Location", 140, "w"),
        ("why",      "Why",      340, "w"),
        ("score",    "Score",     55, "center"),
        ("source",   "Source",    80, "w"),
    ]

    def __init__(self, parent, on_change=None):
        super().__init__(parent)
        self._rows: dict[str, dict] = {}
        self._on_change = on_change
        self._showing_empty = False
        self._build()
        self.refresh()

    def _n(self) -> int:
        v = self._topn.get()
        return 0 if v == "All" else int(v)

    def _build(self):
        theme.header_bar(self, "Top Picks",
                         "The AI's shortlist over your whole inbox, best-first.")
        theme.tip_strip(
            self, "Ask an AI to rank your inbox (Inbox ▸ Export for AI, or the "
                  "find-jobs skill). The ones it recommends land here, ordered "
                  "best-first. Track the ones you like.")

        bar = tk.Frame(self, bg=theme.WINDOW)
        bar.pack(fill="x", padx=6, pady=(6, 0))
        tk.Label(bar, text="Show top:", bg=theme.WINDOW, fg=theme.INK,
                 font=theme.FONT_SM).pack(side="left")
        self._topn = tk.StringVar(value="10")
        ncb = ttk.Combobox(bar, textvariable=self._topn, state="readonly",
                           width=5, values=["10", "15", "20", "25", "50", "All"])
        ncb.pack(side="left", padx=(2, 10))
        ncb.bind("<<ComboboxSelected>>", lambda _e: self.refresh())
        theme.btn(bar, "Refresh", self.refresh, "ghost").pack(side="left")

        tf = ttk.Frame(self)
        tf.pack(fill="both", expand=True, padx=6, pady=2)
        self._tree = ttk.Treeview(tf, columns=[c[0] for c in self._COLS],
                                  show="headings", selectmode="extended")
        for col, label, width, anchor in self._COLS:
            self._tree.heading(col, text=label)
            self._tree.column(col, width=width, anchor=anchor, minwidth=40)
        theme.zebra(self._tree)
        vsb = ttk.Scrollbar(tf, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self._tree.bind("<Double-1>", lambda _e: self._open_url())
        self._tree.bind("t", lambda _e: self._track())
        self._tree.bind("d", lambda _e: self._dismiss())
        self._tree.bind("o", lambda _e: self._open_url())
        self._tree.bind("<Control-a>", self._select_all)
        self._tree.bind("<Control-A>", self._select_all)

        # Empty-state hint, packed only when there are no picks.
        self._empty = tk.Label(
            self, bg=theme.WINDOW, fg=theme.MUTED, font=theme.FONT_SM, justify="left",
            text="No AI picks yet — go to Inbox ▸ Export for AI (or run a "
                 "re-rank), then come back.")

        abar = tk.Frame(self, bg=theme.WINDOW, pady=6)
        abar.pack(fill="x", padx=6, side="bottom")
        theme.tip(theme.btn(abar, "Track \N{BLACK RIGHT-POINTING SMALL TRIANGLE} Interested",
                            self._track, "accent"),
                  "Move the selected job(s) to your Apply Queue.").pack(side="left", padx=2)
        theme.tip(theme.btn(abar, "Dismiss", self._dismiss, "ghost"),
                  "Hide the selected job(s) from all future searches.").pack(side="left", padx=2)
        theme.btn(abar, "Open", self._open_url, "ghost").pack(side="left", padx=2)
        self._status = tk.Label(abar, text="", bg=theme.WINDOW, fg=theme.MUTED,
                                font=theme.FONT_SM)
        self._status.pack(side="left", padx=10)

    def refresh(self):
        picks = tracker_service.top_picks(self._n())
        self._rows = {}
        for iid in self._tree.get_children():
            self._tree.delete(iid)
        for i, r in enumerate(picks):
            iid = str(r["id"])
            self._rows[iid] = r
            self._tree.insert("", "end", iid=iid, tags=(theme.row_tag(i),), values=(
                r["rank"],
                r["fit"] if r.get("fit", -1) >= 0 else "",
                r["title"], r["company"], r.get("location", ""),
                (r.get("fit_why") or "")[:200],
                r["score"] if r.get("score", -1) >= 0 else "",
                r.get("source", "")))
        self._showing_empty = not picks
        if self._showing_empty:
            self._empty.pack(fill="x", padx=14, pady=8)
        else:
            self._empty.pack_forget()
        if self._on_change:
            self._on_change()

    def _selected(self) -> list[dict]:
        return [self._rows[iid] for iid in self._tree.selection()
                if iid in self._rows]

    def _select_all(self, _event=None):
        children = self._tree.get_children()
        if children:
            self._tree.selection_set(children)
            self._tree.focus_set()
        return "break"

    def _track(self):
        sel = self._selected()
        if not sel:
            messagebox.showinfo("No selection", "Select a row first.")
            return
        n = sum(1 for r in sel if tracker_service.track_job(r["id"]) is not None)
        set_status(self._status, f"Tracked {n} job(s).", "ok")
        self.refresh()

    def _dismiss(self):
        sel = self._selected()
        if not sel:
            messagebox.showinfo("No selection", "Select a row first.")
            return
        for r in sel:
            tracker_service.dismiss_job(r["id"])
        set_status(self._status, f"Dismissed {len(sel)} job(s).", "muted")
        self.refresh()

    def _open_url(self):
        for r in self._selected()[:5]:
            u = safe_url(r.get("url"))
            if u:
                webbrowser.open(u)


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

    def __init__(self, parent, default_industry=""):
        super().__init__(parent)
        self.title("Add Companies")
        self.geometry("780x540")
        self.configure(bg=theme.WINDOW)
        self.transient(parent)
        self.grab_set()
        self._entries = []
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
        from scrape.ats_detect import probe_count
        for i, e in enumerate(entries):
            if e.ats_type == "direct":
                # A 'direct' page is uncountable, not unreachable — the user
                # supplied the exact careers URL, so treat it as verified-manual.
                self.after(0, self._set_status_cell, i, "direct (manual)", "direct")
                continue
            n = probe_count(e)
            if n is not None:
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
        self._status.config(text=f"Done — registry now has {total} companies.")
        self._append(f"\nDone. Registry now has {total} companies across "
                     f"{len(stats)} tag(s). They're searched on your next "
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
        self._build()

    @staticmethod
    def _load_cfg() -> dict:
        from search.cli import load_user_config
        return load_user_config()

    def _add_companies(self):
        AddCompaniesDialog(self, default_industry=self._user_cfg.get("industry", ""))

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
            self._source_health.append({
                "source": event.get("source", ""),
                "count": event.get("count", 0),
                "ok": bool(event.get("ok", True)),
                "error": event.get("error", ""),
            })
            src = event.get("source", "")
            set_status(self._status,
                       f"source {done}/{total} — {src} ({event.get('count', 0)})",
                       "work")

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
            clients = build_clients(_sources, cache_enabled=True,
                                    industry_filter=_ind or None,
                                    tiered_careers=True)
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
        rows = self._source_health
        if not rows:
            self._health.set("")
            return
        ok = throttled = skipped = failed = 0
        for r in rows:
            if r["ok"] and r["count"] >= 0:
                ok += 1
            err = (r.get("error") or "").lower()
            if not r["ok"]:
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
        self._health.set("Sources: " + ", ".join(parts) + "  (details)")

    def _show_health_details(self):
        if not self._source_health:
            return
        lines = []
        for r in sorted(self._source_health, key=lambda x: x["source"].lower()):
            if r["ok"]:
                lines.append(f"{r['source']}: {r['count']} result(s)")
            else:
                lines.append(f"{r['source']}: FAILED — {r.get('error') or 'unknown'}")
        messagebox.showinfo("Source health (last search)",
                            "\n".join(lines), parent=self)

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
        self._status.config(text=text, fg=theme.SUCCESS if saved else ERR)
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

        toolsm = theme.style_menu(tk.Menu(menubar, tearoff=0))
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
        toolsm.add_command(label="Connect your AI (API key)…",
                           command=self._show_settings)
        toolsm.add_command(label="Connect job sources…",
                           command=self._show_source_keys)
        toolsm.add_command(label="Seed my area (find local employers)…",
                           command=self._show_seed_area)
        toolsm.add_separator()
        toolsm.add_command(label="Enable stealth fetching (downloads browser)…",
                           command=self._enable_stealth)
        menubar.add_cascade(label="Tools", menu=toolsm)

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
            # fresh user's 'careers' searches have employers to scrape.
            if actions.get("build_list"):
                try:
                    BuildCompanyListDialog(
                        self, default_industry=actions.get("industry", ""),
                        default_metro=actions.get("location", ""))
                except Exception:
                    pass
            # Close the loop: don't strand a fresh user on an empty app — offer to
            # run their first search right now so they SEE scored results.
            if messagebox.askyesno(
                    "You're all set",
                    "Your preferences are saved.\n\nFind your first jobs now?",
                    parent=self):
                self._nb.select(self._search)
                self.update_idletasks()
                try:
                    self._search._search()   # threaded; no-op if keywords are blank
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
        self._topbar = topbar.build_top_bar(self, before=anchor)

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
        # Onboard the new person's profile into the now-active project.
        try:
            from ui import setup_wizard
            setup_wizard.run(self, on_finish=lambda applied: (
                self._rebuild_tabs(), self._update_title()))
        except Exception:
            pass

    # ── tabs ───────────────────────────────────────────────────────────────────
    def _build_tabs(self):
        init_db()  # ensure the active project's tracker.db exists/upgraded
        self._inbox    = InboxTab(self._nb, on_change=self._update_badges)
        self._toppicks = TopPicksTab(self._nb, on_change=self._update_badges)
        self._search   = SearchTab(self._nb,
                                   open_guide_cb=lambda: self._nb.select(self._guide))
        self._queue    = ApplyQueueTab(self._nb)
        self._tracker  = TrackerTab(self._nb)
        self._resume   = ResumeTab(self._nb)
        self._guide    = uihelp.GuideTab(self._nb, app=self)
        self._nb.add(self._inbox,    text="Inbox")
        self._nb.add(self._toppicks, text="Top Picks")
        self._nb.add(self._search,   text="Search")
        self._nb.add(self._queue,   text="Apply Queue")
        self._nb.add(self._tracker, text="Job Tracker")
        self._nb.add(self._resume,  text="Resume Generator")
        self._nb.add(self._guide,   text="\N{BLACK QUESTION MARK ORNAMENT} Guide")
        self._update_badges()

    def _rebuild_tabs(self, select_index=None):
        for tab in (self._inbox, self._toppicks, self._search, self._queue,
                    self._tracker, self._resume, self._guide):
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
