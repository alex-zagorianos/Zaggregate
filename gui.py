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
import re
import sys
import sqlite3
import threading
import subprocess
import webbrowser
from datetime import date
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog

sys.path.insert(0, str(Path(__file__).resolve().parent))

import workspace
from tracker import service as tracker_service
from tracker.db import (
    init_db, add_job, get_all, get_counts, count_followups_due, update_job, delete_job, get_job,
    archive_job, unarchive_job,
    seen_urls, normalize_url, dismiss_url,
    inbox_all, inbox_count, inbox_track, inbox_dismiss, inbox_set_fit,
    STATUSES, STATUS_LABELS,
)
from config import DEFAULT_LOCATION, OUTPUT_DIR
from claude_bridge import (
    BridgeParseError, to_clipboard,
    build_fit_prompt, parse_fit_response, profile_summary,
)
from ui import theme
from ui import help as uihelp
from ui import setup_wizard

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

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


def set_status(label, text, kind="muted"):
    """Set a tk.Label's text and color by semantic kind (ok/work/info/muted/err)
    instead of repeating inline hex at each call site."""
    label.config(text=text, fg=_STATUS_COLORS.get(kind, MUTED))

STATUS_FG = {
    "interested":   "#1565c0",
    "applied":      "#2e7d32",
    "phone_screen": "#e65100",
    "interview":    "#bf360c",
    "offer":        "#1b5e20",
    "rejected":     "#c62828",
    "withdrawn":    "#757575",
}


# ── Add / Edit dialog ─────────────────────────────────────────────────────────
class JobDialog(tk.Toplevel):
    """Modal form for adding or editing a job entry."""

    def __init__(self, parent, job=None):
        super().__init__(parent)
        self.title("Edit Job" if job else "Add Job")
        self.resizable(False, False)
        self.grab_set()
        self.result = None

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
        ttk.Label(form, text="YYYY-MM-DD", foreground="#888").grid(
            row=1, column=4, sticky="w")

        ttk.Label(form, text="Status").grid(row=2, column=2, sticky="w", **p)
        sv = tk.StringVar(value=(job or {}).get("status", "interested"))
        self._vars["status"] = sv
        ttk.Combobox(form, textvariable=sv, values=STATUSES,
                     state="readonly", width=16).grid(
            row=2, column=3, sticky="w", **p)

        # Job-hunt fields
        entry("Follow-up",  "follow_up_date", 3, 1, width=14)
        entry("Deadline",   "deadline",       5, 0)
        entry("Contact",    "contact",        5, 1, width=42, span=3)

        # Notes — full width
        ttk.Label(form, text="Notes").grid(row=4, column=0, sticky="nw", **p)
        self._notes = tk.Text(form, width=70, height=5, wrap="word",
                              font=("Segoe UI", 9), relief="solid", bd=1)
        self._notes.grid(row=4, column=1, columnspan=4, sticky="ew", **p)
        if job and job.get("notes"):
            self._notes.insert("1.0", job["notes"])

        # Buttons
        btns = ttk.Frame(self, padding=(16, 0, 16, 16))
        btns.pack(fill="x")
        theme.btn(btns, "Save", self._save, "accent").pack(side="right", padx=4)
        theme.btn(btns, "Cancel", self.destroy, "ghost").pack(side="right")

        self.transient(parent)
        self.wait_window()

    def _save(self):
        title   = self._vars["title"].get().strip()
        company = self._vars["company"].get().strip()
        if not title or not company:
            messagebox.showerror("Required",
                "Title and Company are required.", parent=self)
            return
        for key, label in (("date_applied", "Date Applied"),
                           ("follow_up_date", "Follow-up"),
                           ("deadline", "Deadline")):
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
        self._text = tk.Text(body, wrap="word", font=("Consolas", 9),
                             relief="solid", bd=1)
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
            show="headings", selectmode="browse")
        for col, label, width, anchor in self._COLS:
            self._tree.heading(col, text=label,
                               command=lambda c=col: self._sort_by(c))
            self._tree.column(col, width=width, anchor=anchor, minwidth=60)
        for status, fg in STATUS_FG.items():
            self._tree.tag_configure(status, foreground=fg)
        theme.zebra(self._tree)

        vsb = ttk.Scrollbar(tf, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self._tree.bind("<Double-1>", lambda _e: self._edit())
        self._tree.bind("<<TreeviewSelect>>", self._on_select)

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
        if url:
            webbrowser.open(url)
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
        self._text = tk.Text(txt_f, wrap="word", font=("Segoe UI", 10),
                             relief="solid", bd=1)
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
        self._status_lbl.config(text="", fg="#666")
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
                     lambda m: self._status_lbl.config(text=m, fg="#e65100"))

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
            text="Generating with Claude...  (15–30 sec)", fg="#e65100")
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
        self._status_lbl.config(text="Done — saved to:", fg="#2e7d32")
        self._out_lbl.config(text=str(out_dir))

    def _on_error(self, msg):
        if self._gen_btn:
            self._gen_btn.config(state="normal")
        self._status_lbl.config(text=f"Error: {msg}", fg=ERR)

    def _open_folder(self, _event=None):
        if self._output_dir:
            subprocess.Popen(f'explorer "{self._output_dir}"')


# ── Inbox tab (daily-run results) ─────────────────────────────────────────────
class InboxTab(ttk.Frame):
    """Triage queue fed by daily_run.py: ranked fresh matches. Track moves a
    row to the tracker; Dismiss hides the posting from all future searches."""

    _COLS = [
        ("score",    "Score",     55, "center"),
        ("fit",      "Fit",       45, "center"),
        ("title",    "Title",    300, "w"),
        ("company",  "Company",  150, "w"),
        ("size",     "Size",      60, "center"),
        ("location", "Location", 130, "w"),
        ("salary",   "Salary",   100, "w"),
        ("source",   "Source",    80, "w"),
        ("added",    "Added",     85, "center"),
    ]

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
        self._on_change = on_change  # notify App to refresh the tab badge
        self._build()
        self.refresh()

    def _build(self):
        hdr = theme.header_bar(self, "Inbox", "Fresh matches from the daily search.")
        self._count_lbl = tk.Label(hdr, text="", bg=theme.SURFACE,
                                    fg=theme.MUTED, font=theme.FONT_SM)
        self._count_lbl.pack(side="right", padx=14)
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
        ms.bind("<KeyRelease>", lambda _e: self._render())
        tk.Label(fbar, text="Source:", bg=BG,
                 font=("Segoe UI", 9)).pack(side="left")
        self._f_source = tk.StringVar(value="All")
        self._source_cb = ttk.Combobox(fbar, textvariable=self._f_source,
                                       state="readonly", width=12,
                                       values=["All"])
        self._source_cb.pack(side="left", padx=(2, 10))
        self._source_cb.bind("<<ComboboxSelected>>", lambda _e: self._render())
        tk.Label(fbar, text="Size:", bg=BG,
                 font=("Segoe UI", 9)).pack(side="left")
        self._f_size = tk.StringVar(value="All")
        sz = ttk.Combobox(fbar, textvariable=self._f_size, state="readonly",
                          width=4, values=["All", "S", "M", "L", "XL", "?"])
        sz.pack(side="left", padx=(2, 10))
        sz.bind("<<ComboboxSelected>>", lambda _e: self._render())
        self._f_unscored = tk.BooleanVar(value=False)
        tk.Checkbutton(fbar, text="Unscored only", variable=self._f_unscored,
                       bg=BG, font=("Segoe UI", 9),
                       command=self._render).pack(side="left", padx=(0, 10))
        tk.Label(fbar, text="Find:", bg=BG,
                 font=("Segoe UI", 9)).pack(side="left")
        self._f_text = tk.StringVar()
        ft = ttk.Entry(fbar, textvariable=self._f_text, width=18)
        ft.pack(side="left", padx=(2, 6))
        ft.bind("<KeyRelease>", lambda _e: self._render())
        theme.btn(fbar, "Clear", self._clear_filters, "ghost").pack(side="left")

        tf = ttk.Frame(self)
        tf.pack(fill="both", expand=True, padx=6, pady=2)
        self._tree = ttk.Treeview(tf, columns=[c[0] for c in self._COLS],
                                  show="headings", selectmode="extended")
        for col, label, width, anchor in self._COLS:
            self._tree.heading(col, text=label,
                               command=lambda c=col: self._sort_by(c))
            self._tree.column(col, width=width, anchor=anchor, minwidth=40)
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

        # Detail pane: why this job scored what it did + description preview
        self._detail = tk.Text(self, height=4, wrap="word", bg=theme.SURFACE,
                               fg=theme.MUTED, font=theme.FONT_SM, relief="flat",
                               padx=8, state="disabled")
        self._detail.pack(fill="x", padx=6)
        self._tree.bind("<<TreeviewSelect>>", self._show_detail)

        abar = tk.Frame(self, bg=theme.WINDOW, pady=6)
        abar.pack(fill="x", padx=6, side="bottom")
        theme.tip(theme.btn(abar, "Track \N{BLACK RIGHT-POINTING SMALL TRIANGLE} Interested",
                            self._track, "accent"),
                  "Move the selected job(s) to your Apply Queue.").pack(side="left", padx=2)
        theme.tip(theme.btn(abar, "Dismiss", self._dismiss, "ghost"),
                  "Hide the selected job(s) from all future searches.").pack(side="left", padx=2)
        theme.tip(theme.btn(abar, "Dismiss Company", self._dismiss_company, "ghost"),
                  "Hide every visible job from the selected company.").pack(side="left", padx=2)
        theme.btn(abar, "Open", self._open_url, "ghost").pack(side="left", padx=2)
        theme.btn(abar, "Refresh", self.refresh, "ghost").pack(side="left", padx=2)
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
                  "Revert the last imported AI ranking.").pack(side="left", padx=2)
        self._status = tk.Label(abar, text="", bg=theme.WINDOW, fg=theme.MUTED,
                                font=theme.FONT_SM)
        self._status.pack(side="left", padx=10)

        self._fit_order: list[int] = []  # inbox ids in last fit-prompt order
        self._fit_jobs: list = []        # JobResults for the last fit prompt
        self._undo_rows: list[dict] = [] # last-dismissed rows, for Undo

    def refresh(self):
        self._all = list(inbox_all())
        sources = sorted({r["source"] for r in self._all if r["source"]})
        self._source_cb["values"] = ["All", *sources]
        if self._f_source.get() not in self._source_cb["values"]:
            self._f_source.set("All")
        self._render()
        if self._on_change:
            self._on_change()

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
        q = self._f_text.get().strip().lower()
        if q:
            rows = [r for r in rows
                    if q in (r["title"] or "").lower()
                    or q in (r["company"] or "").lower()]
        return rows

    def _render(self):
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
            self._tree.insert("", "end", iid=iid, tags=(theme.row_tag(i),), values=(
                r["score"] if r["score"] >= 0 else "",
                r["fit"] if r["fit"] >= 0 else "",
                r["title"], r["company"],
                self._size_badge(r.get("board_count", -1)),
                r["location"],
                r["salary_text"], r["source"], r["date_added"]))
        total = len(self._all)
        label = (f"{len(rows)} of {total} awaiting triage"
                 if len(rows) != total else f"{total} awaiting triage")
        self._count_lbl.config(text=label)

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
        self._f_text.set("")
        self._render()

    def _selected(self) -> list[dict]:
        return [self._rows[iid] for iid in self._tree.selection()
                if iid in self._rows]

    def _show_detail(self, _event=None):
        sel = self._selected()
        text = ""
        if len(sel) == 1:
            r = sel[0]
            why = r["fit_why"] or r["score_notes"] or ""
            desc = " ".join((r["description"] or "").split())[:600]
            text = f"{why}\n{desc}" if why and desc else (why or desc)
        self._detail.config(state="normal")
        self._detail.delete("1.0", "end")
        self._detail.insert("1.0", text)
        self._detail.config(state="disabled")

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
            if r["url"]:
                webbrowser.open(r["url"])

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
        prompt, jobs = tracker_service.fit_prompt_for_rows(rows)
        self._fit_jobs = jobs
        self._fit_order = [r["id"] for r in rows]  # legacy/back-compat
        copy_or_warn(self, prompt,
                     lambda m: set_status(self._status, m, "work"))

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
        try:
            ok, applied = db_guard(
                self,
                lambda: tracker_service.score_inbox_from_reply(
                    self._fit_jobs, dlg.result),
                status_cb=lambda m: set_status(self._status, m, "err"),
                action="apply fit scores")
        except BridgeParseError as e:
            messagebox.showerror("Parse failed", str(e), parent=self)
            return
        if not ok:
            return
        set_status(self._status, f"Applied {applied} fit score(s).", "ok")
        self.refresh()

    def _export_for_ai(self):
        """Write the round-trip trio (csv+md+prompt) for the current inbox to a
        timestamped folder under OUTPUT_DIR/rerank, then open the folder."""
        from datetime import datetime
        from rerank.export import export_inbox
        rows = list(self._all)
        if not rows:
            messagebox.showinfo("Nothing to export", "The inbox is empty.")
            return
        stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
        out_dir = Path(OUTPUT_DIR) / "rerank" / stamp
        try:
            paths = export_inbox(rows, out_dir, fmt="both")
        except Exception as e:
            messagebox.showerror("Export failed", str(e))
            return
        set_status(self._status,
                   f"Exported {len(rows)} rows -> {out_dir}", "info")
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
        """Revert the most recent file-import re-rank batch via score_history."""
        n = tracker_service.undo_last_rerank("file_import")
        set_status(self._status,
                   f"Undid last re-rank: restored {n} row(s)." if n else
                   "No re-rank to undo.", "muted" if n else "info")
        self.refresh()


# ── Search tab ────────────────────────────────────────────────────────────────
class AddCompaniesDialog(tk.Toplevel):
    """Paste career-page URLs -> auto-detect ATS + slug -> (optionally validate
    the board is live) -> append to companies.json, tagged with the active
    project's industry so they show up in this campaign's 'careers' searches."""

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
        self._box = tk.Text(self, height=7, wrap="none")
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
                self.after(0, self._set_status_cell, i, "direct (manual)")
                continue
            n = probe_count(e)
            self.after(0, self._set_status_cell, i,
                       f"live ({n})" if n is not None else "unreachable")
        self.after(0, self._validate_done)

    def _validate_done(self):
        # The dialog may have been closed while the worker ran — don't touch
        # destroyed widgets (GUI-7).
        if not self.winfo_exists():
            return
        self._val_btn.config(state="normal")
        self._detect_btn.config(state="normal")
        self._status.config(text="Validation done.")

    def _set_status_cell(self, i, txt):
        if not self.winfo_exists():
            return  # GUI-7: dialog closed before this after() fired
        if self._tree.exists(str(i)):
            self._tree.set(str(i), "status", txt)

    def _add(self):
        from scrape.company_registry import save_companies
        if not self._entries:
            self._detect()
        if not self._entries:
            messagebox.showinfo("Add Companies", "Nothing to add — paste some URLs first.")
            return
        ind = self._industry.get().strip()
        for e in self._entries:
            e.industries = [ind] if ind else []
        added = save_companies(self._entries)
        skipped = len(self._entries) - added
        messagebox.showinfo(
            "Add Companies",
            f"Added {added} compan(ies) to companies.json."
            + (f"\nSkipped {skipped} already present." if skipped else ""))
        if added:
            self._status.config(
                text=f"Added {added}. They're scraped on the next 'careers' search.")


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

    def __init__(self, parent):
        super().__init__(parent)
        self._results = []  # list[JobResult], indexed by tree iid
        self._user_cfg = self._load_cfg()
        self._build()

    @staticmethod
    def _load_cfg() -> dict:
        from search.cli import load_user_config
        return load_user_config()

    def _add_companies(self):
        AddCompaniesDialog(self, default_industry=self._user_cfg.get("industry", ""))

    def _build(self):
        hdr = theme.header_bar(self, "Job Search",
                               "Search many job boards at once.")
        theme.tip(theme.btn(hdr, "+ Add Companies", self._add_companies, "ghost"),
                  "Paste a company's careers-page link so its jobs appear in "
                  "future searches.").pack(side="right", padx=10, pady=8)
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
                 ("Open", self._open_url, "ghost")]
        for text, cmd, kind in specs:
            b = theme.btn(abar, text, cmd, kind)
            b.pack(side="left", padx=2)
            self._action_btns.append(b)
        tk.Label(abar, text="  Ctrl/Shift-click to select multiple",
                 bg=theme.WINDOW, fg=theme.FAINT, font=theme.FONT_SM).pack(side="left")

    def _set_busy(self, busy: bool):
        """Disable/enable the search + result controls for the worker's
        duration, so a second search can't fire mid-flight (GUI-8)."""
        state = "disabled" if busy else "normal"
        self._search_btn.config(state=state)
        for b in self._action_btns:
            b.config(state=state)

    def _search(self):
        keywords = [k.strip() for k in self._kw.get().split(",") if k.strip()]
        if not keywords:
            messagebox.showinfo("Keywords needed", "Enter at least one keyword.")
            return
        try:
            salary_min = int(self._salary.get().strip() or 0) or None
        except ValueError:
            messagebox.showerror("Bad salary", "Min salary must be a number.")
            return
        self._set_busy(True)
        set_status(self._status, "Searching…", "work")
        threading.Thread(
            target=self._worker,
            args=(keywords, self._loc.get().strip() or DEFAULT_LOCATION,
                  salary_min, self._hide_tracked.get()),
            daemon=True,
        ).start()

    def _worker(self, keywords, location, salary_min, hide_tracked):
        try:
            from search.cli import build_clients, ALL_SOURCES
            from search.search_engine import SearchEngine
            from match.scorer import score_jobs
            clients = build_clients(ALL_SOURCES, cache_enabled=True)
            results = (
                SearchEngine(clients).run_full_search(
                    keywords=keywords, location=location,
                    salary_min=salary_min, max_pages_per_keyword=1)
                if clients else []
            )
            if hide_tracked and results:
                seen = seen_urls()
                results = [r for r in results if normalize_url(r.url) not in seen]
            if results:
                score_jobs(results, keywords=keywords, location=location,
                           salary_floor=salary_min,
                           exclude_keywords=self._user_cfg.get("exclude_keywords", []),
                           exclude_titles=self._user_cfg.get("exclude_titles"),
                           title_miss_penalty=self._user_cfg.get("title_miss_penalty"),
                           seniority_exclude=self._user_cfg.get("seniority_exclude"))
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
        if not had_clients:
            set_status(self._status,
                       "No sources configured — add API keys to .env.", "err")
        else:
            set_status(self._status, f"{len(results)} result(s).", "ok")

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
            if j.url:
                webbrowser.open(j.url)


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
        if j.get("resume_path"):
            bits.append(f"Docs: {j['resume_path']}")
        self._detail.config(text="   |   ".join(bits))

    def _open_url(self):
        j = self._sel()
        if j and j.get("url"):
            webbrowser.open(j["url"])
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
                     lambda m: self._status.config(text=m, fg="#e65100"))

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
        self._status.config(text=f"Batch of {len(batch)}: {names}", fg="#e65100")
        copy_or_warn(self, prompt,
                     lambda m: self._status.config(text=m, fg="#e65100"))

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
        self._status.config(text=text, fg="#2e7d32" if saved else ERR)
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
        # Auto-set a follow-up nudge one week out unless one is already set.
        from datetime import timedelta
        kwargs = {}
        if not (j.get("follow_up_date") or "").strip():
            kwargs["follow_up_date"] = (date.today() + timedelta(days=7)).isoformat()
        ok, _ = db_guard(self, lambda: tracker_service.update_job(
            j["id"], status="applied",
            date_applied=date.today().isoformat(), **kwargs),
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
        prompt, jobs = tracker_service.fit_prompt_for_rows(rows)
        self._fit_jobs = jobs
        self._fit_order = [r["id"] for r in rows]  # legacy/back-compat
        copy_or_warn(self, prompt,
                     lambda m: self._status.config(text=m, fg="#e65100"))

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
        self._status.config(text=f"Applied {applied} fit score(s).", fg="#2e7d32")
        self.refresh(keep_selection=True)


# ── App root ──────────────────────────────────────────────────────────────────
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        import userdata
        userdata.bootstrap()  # first-run: seed the data folder + runtime dirs
        theme.apply_theme(self)         # clean light/modern look, before any widgets
        self.geometry("1280x780")
        self.minsize(980, 620)

        # Global Tk callback exception handler: in a windowed .exe an unguarded
        # error inside a button/after callback otherwise vanishes silently (dead
        # button, no feedback). Log the traceback and show the user something.
        self.report_callback_exception = self._on_tk_exception

        self._build_menu()

        self._proj_var = None
        self._build_projectbar()       # shown only when projects exist

        self._nb = ttk.Notebook(self)
        self._nb.pack(fill="both", expand=True)
        self._build_tabs()

        # Tracker/queue contents change from other tabs; refresh on focus.
        self._nb.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        self._update_title()

        # Open where the work is: inbox if the daily run found anything.
        if inbox_count() == 0:
            self._nb.select(self._search)

        # First launch (no .onboarded marker): walk the user through Setup.
        self.after(120, lambda: setup_wizard.maybe_run(self, on_finish=self._after_setup))

    # ── menu bar ────────────────────────────────────────────────────────────────
    def _build_menu(self):
        menubar = tk.Menu(self)

        filem = tk.Menu(menubar, tearoff=0)
        filem.add_command(label="New Project…", command=self._new_project)
        filem.add_command(label="Open my data folder",
                          command=uihelp.open_data_folder)
        filem.add_separator()
        filem.add_command(label="Exit", command=self.destroy)
        menubar.add_cascade(label="File", menu=filem)

        helpm = tk.Menu(menubar, tearoff=0)
        helpm.add_command(label="Quick Start",
                          command=lambda: uihelp.show_quick_start(self))
        helpm.add_command(label="Open the Guide", command=self._open_guide)
        helpm.add_command(label="What do the tabs do?",
                          command=lambda: uihelp.show_tabs_help(self))
        helpm.add_separator()
        helpm.add_command(label="Run Setup Wizard…",
                          command=lambda: setup_wizard.run(self, on_finish=self._after_setup))
        helpm.add_command(label="Open my data folder",
                          command=uihelp.open_data_folder)
        helpm.add_separator()
        helpm.add_command(label="About", command=lambda: uihelp.show_about(self))
        menubar.add_cascade(label="Help", menu=helpm)

        self.config(menu=menubar)

    def _open_guide(self):
        if getattr(self, "_guide", None) is not None:
            self._nb.select(self._guide)

    def _after_setup(self, applied: bool):
        """Called when the Setup wizard closes. On apply, refresh tabs so the
        seeded preferences/config show up. Either way land on the Guide so a
        brand-new user (including one who skipped) has an obvious next step
        instead of an empty Search tab."""
        if applied:
            self._rebuild_tabs()
        self._open_guide()

    # ── project bar (switch campaigns without restarting) ──────────────────────
    def _build_projectbar(self):
        if not workspace.has_projects():
            return  # pre-migration: single root workspace, no switcher
        bar = tk.Frame(self, bg=theme.SURFACE)
        bar.pack(fill="x", side="top")
        tk.Label(bar, text="Project:", bg=theme.SURFACE, fg=theme.INK,
                 font=theme.FONT_BOLD, padx=12, pady=7).pack(side="left")
        self._proj_var = tk.StringVar()
        self._proj_cb = ttk.Combobox(bar, textvariable=self._proj_var,
                                     state="readonly", width=34)
        self._proj_cb.pack(side="left", padx=4, pady=7)
        self._proj_cb.bind("<<ComboboxSelected>>", self._on_project_change)
        theme.btn(bar, "+ New", self._new_project, "ghost").pack(side="left", padx=6)
        tk.Frame(self, bg=theme.BORDER, height=1).pack(fill="x", side="top")
        self._refresh_projectbar()

    def _refresh_projectbar(self):
        if not self._proj_var:
            return
        projs = workspace.list_projects()
        self._name_to_slug = {p["name"]: p["slug"] for p in projs}
        self._proj_cb["values"] = [p["name"] for p in projs]
        active = workspace.active_slug()
        for p in projs:
            if p["slug"] == active:
                self._proj_var.set(p["name"])
                break

    def _on_project_change(self, _event=None):
        slug = self._name_to_slug.get(self._proj_var.get())
        if slug and slug != workspace.active_slug():
            workspace.set_active(slug)
            self._rebuild_tabs()
            self._update_title()

    def _new_project(self):
        name = simpledialog.askstring(
            "New Project", "Name for the new campaign:", parent=self)
        if not name or not name.strip():
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

    # ── tabs ───────────────────────────────────────────────────────────────────
    def _build_tabs(self):
        init_db()  # ensure the active project's tracker.db exists/upgraded
        self._inbox   = InboxTab(self._nb, on_change=self._update_badges)
        self._search  = SearchTab(self._nb)
        self._queue   = ApplyQueueTab(self._nb)
        self._tracker = TrackerTab(self._nb)
        self._resume  = ResumeTab(self._nb)
        self._guide   = uihelp.GuideTab(self._nb, app=self)
        self._nb.add(self._inbox,   text="Inbox")
        self._nb.add(self._search,  text="Search")
        self._nb.add(self._queue,   text="Apply Queue")
        self._nb.add(self._tracker, text="Job Tracker")
        self._nb.add(self._resume,  text="Resume Generator")
        self._nb.add(self._guide,   text="\N{BLACK QUESTION MARK ORNAMENT} Guide")
        self._update_badges()

    def _rebuild_tabs(self):
        for tab in (self._inbox, self._search, self._queue, self._tracker,
                    self._resume, self._guide):
            tab.destroy()
        self._build_tabs()
        if inbox_count() == 0:
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

    def _on_tab_changed(self, _event=None):
        current = self._nb.nametowidget(self._nb.select())
        if current is self._queue:
            self._queue.refresh(keep_selection=True)
        elif current is self._tracker:
            self._tracker.refresh()
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


if __name__ == "__main__":
    App().mainloop()
