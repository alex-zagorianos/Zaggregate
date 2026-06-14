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
import threading
import subprocess
import webbrowser
from datetime import date
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

sys.path.insert(0, str(Path(__file__).resolve().parent))

import workspace
from tracker.db import (
    init_db, add_job, get_all, get_counts, update_job, delete_job, get_job,
    archive_job, unarchive_job,
    seen_urls, normalize_url, dismiss_url,
    inbox_all, inbox_count, inbox_track, inbox_dismiss, inbox_set_fit,
    STATUSES, STATUS_LABELS,
)
from config import DEFAULT_LOCATION
from claude_bridge import (
    BridgeParseError, to_clipboard,
    build_fit_prompt, parse_fit_response, profile_summary,
)

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# ── Palette ───────────────────────────────────────────────────────────────────
DARK  = "#1a1a2e"
MID   = "#2d2d52"
BG    = "#f0f0f0"
WHITE = "#ffffff"
ERR   = "#c62828"

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
        tk.Button(btns, text="Save", bg=DARK, fg=WHITE,
                  font=("Segoe UI", 9), relief="flat", padx=14, pady=5,
                  command=self._save).pack(side="right", padx=4)
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="right")

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
        tk.Button(btns, text="OK", bg=DARK, fg=WHITE, relief="flat",
                  padx=16, pady=4, command=self._ok).pack(side="right", padx=4)
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="right")
        self._text.focus_set()
        self.transient(parent)
        self.wait_window()

    def _ok(self):
        self.result = self._text.get("1.0", "end-1c").strip()
        self.destroy()


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
        hdr = tk.Frame(self, bg=DARK)
        hdr.pack(fill="x")
        tk.Label(hdr, text="Job Application Tracker",
                 bg=DARK, fg=WHITE, font=("Segoe UI", 13, "bold"),
                 padx=14, pady=10).pack(side="left")
        self._count_lbl = tk.Label(hdr, text="", bg=DARK, fg="#9999bb",
                                    font=("Segoe UI", 9), padx=6)
        self._count_lbl.pack(side="left")
        tk.Button(hdr, text="+ Add Job", bg=WHITE, fg=DARK,
                  font=("Segoe UI", 9, "bold"), relief="flat",
                  padx=10, pady=3, command=self._add).pack(
            side="right", padx=10, pady=8)

        # Status filter bar
        self._fbar = tk.Frame(self, bg=BG, pady=5)
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

        def btn(text, cmd, bg=DARK):
            tk.Button(self._abar, text=text, bg=bg, fg=WHITE,
                      font=("Segoe UI", 9), relief="flat",
                      padx=10, pady=3, command=cmd).pack(side="left", padx=2)

        if self._active == "archived":
            btn("Restore", self._restore)
            btn("Delete permanently", self._delete, bg=ERR)
            btn("Open URL", self._open_url)
            return

        btn("Edit", self._edit)
        btn("Archive", self._archive)
        btn("Open URL", self._open_url)
        tk.Label(self._abar, text="   Quick status:", bg=BG,
                 font=("Segoe UI", 9)).pack(side="left")
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
            tk.Button(self._fbar, text=label,
                      bg=DARK if active else WHITE,
                      fg=WHITE if active else "#555",
                      font=("Segoe UI", 8, "bold" if active else "normal"),
                      relief="flat", padx=9, pady=2,
                      command=lambda k=key: self._filter(k)).pack(
                side="left", padx=1)

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
        # arrived (set automatically a week after Mark Applied).
        today = date.today().isoformat()
        due = sum(1 for j in get_all()
                  if (j.get("follow_up_date") or "") and j["follow_up_date"] <= today
                  and j.get("status") in ("applied", "phone_screen", "interview"))
        label = f"{counts['all']} total"
        if due:
            label += f"  •  {due} follow-up(s) due"
        # Amber stands out on the dark header; #9999bb is the label's default.
        self._count_lbl.config(text=label, fg=("#ffb74d" if due else "#9999bb"))

        for row in self._tree.get_children():
            self._tree.delete(row)
        for j in jobs:
            self._tree.insert("", "end", iid=str(j["id"]),
                              tags=(j["status"],),
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
            add_job(**dlg.result)
            self.refresh()

    def _edit(self):
        iid = self._sel_iid()
        if not iid:
            messagebox.showinfo("No selection", "Select a job row first.")
            return
        dlg = JobDialog(self, job=get_job(int(iid)))
        if dlg.result:
            update_job(int(iid), **dlg.result)
            self.refresh()

    def _archive(self):
        iid = self._sel_iid()
        if not iid:
            return
        job = get_job(int(iid))
        if messagebox.askyesno("Archive?",
                f"Archive '{job['title']}' at {job['company']}?\n\n"
                "It moves to the Archive view and stops showing in searches. "
                "You can restore it any time."):
            archive_job(int(iid))
            self.refresh()

    def _restore(self):
        iid = self._sel_iid()
        if not iid:
            return
        unarchive_job(int(iid))
        self.refresh()

    def _delete(self):
        iid = self._sel_iid()
        if not iid:
            return
        job = get_job(int(iid))
        if messagebox.askyesno("Delete permanently?",
                f"Permanently delete '{job['title']}' at {job['company']}?\n\n"
                "This cannot be undone.", icon="warning"):
            delete_job(int(iid))
            self.refresh()

    def _open_url(self):
        iid = self._sel_iid()
        if not iid:
            return
        url = (get_job(int(iid)) or {}).get("url", "")
        if url:
            webbrowser.open(url)
        else:
            messagebox.showinfo("No URL", "This job has no URL saved.")

    def _quick_status(self, _event=None):
        iid = self._sel_iid()
        if not iid:
            return
        update_job(int(iid), status=self._qstatus.get())
        self.refresh()


# ── Resume Generator tab ──────────────────────────────────────────────────────
class ResumeTab(ttk.Frame):

    def __init__(self, parent):
        super().__init__(parent)
        self._output_dir = None
        self._build()

    def _build(self):
        # Header
        hdr = tk.Frame(self, bg=DARK)
        hdr.pack(fill="x")
        tk.Label(hdr, text="Resume & Cover Letter Generator",
                 bg=DARK, fg=WHITE, font=("Segoe UI", 13, "bold"),
                 padx=14, pady=10).pack(side="left")
        tk.Label(hdr,
                 text="Paste a job posting — Claude generates a tailored resume + cover letter",
                 bg=DARK, fg="#9999bb", font=("Segoe UI", 9)).pack(
            side="left", padx=6)

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
        bar = tk.Frame(self, bg=BG, pady=8)
        bar.pack(fill="x", padx=12, side="bottom")

        tk.Button(bar, text="1. Copy Prompt",
                  bg=DARK, fg=WHITE, font=("Segoe UI", 10, "bold"),
                  relief="flat", padx=14, pady=7,
                  command=self._copy_prompt).pack(side="left")
        tk.Button(bar, text="2. Paste Reply ▸ DOCX",
                  bg=DARK, fg=WHITE, font=("Segoe UI", 10, "bold"),
                  relief="flat", padx=14, pady=7,
                  command=self._paste_reply).pack(side="left", padx=8)

        from resume.service import api_available
        self._gen_btn = None
        if api_available():
            self._gen_btn = tk.Button(
                bar, text="Generate via API",
                bg="#2d2d52", fg=WHITE, font=("Segoe UI", 10),
                relief="flat", padx=16, pady=7, command=self._generate)
            self._gen_btn.pack(side="left")

        tk.Button(bar, text="Clear", bg="#dddddd", fg="#333",
                  font=("Segoe UI", 9), relief="flat",
                  padx=10, pady=7, command=self._clear).pack(
            side="left", padx=8)

        self._status_lbl = tk.Label(bar, text="", bg=BG,
                                     fg="#666", font=("Segoe UI", 9))
        self._status_lbl.pack(side="left", padx=6)

        self._out_lbl = tk.Label(bar, text="", bg=BG, fg="#1565c0",
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
        hdr = tk.Frame(self, bg=DARK)
        hdr.pack(fill="x")
        tk.Label(hdr, text="Inbox — fresh matches from the daily search",
                 bg=DARK, fg=WHITE, font=("Segoe UI", 13, "bold"),
                 padx=14, pady=10).pack(side="left")
        self._count_lbl = tk.Label(hdr, text="", bg=DARK, fg="#9999bb",
                                   font=("Segoe UI", 9))
        self._count_lbl.pack(side="left")

        # Filter bar — applied client-side over the cached snapshot, so
        # typing in a filter never hits the database.
        fbar = tk.Frame(self, bg=BG)
        fbar.pack(fill="x", padx=6, pady=(4, 0))
        tk.Label(fbar, text="Min score:", bg=BG,
                 font=("Segoe UI", 9)).pack(side="left")
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
        tk.Button(fbar, text="Clear", bg=WHITE, fg="#555",
                  font=("Segoe UI", 8), relief="flat", padx=8,
                  command=self._clear_filters).pack(side="left")

        tf = ttk.Frame(self)
        tf.pack(fill="both", expand=True, padx=6, pady=2)
        self._tree = ttk.Treeview(tf, columns=[c[0] for c in self._COLS],
                                  show="headings", selectmode="extended")
        for col, label, width, anchor in self._COLS:
            self._tree.heading(col, text=label,
                               command=lambda c=col: self._sort_by(c))
            self._tree.column(col, width=width, anchor=anchor, minwidth=40)
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
        self._detail = tk.Text(self, height=4, wrap="word", bg=BG, fg="#555",
                               font=("Segoe UI", 9), relief="flat",
                               padx=8, state="disabled")
        self._detail.pack(fill="x", padx=6)
        self._tree.bind("<<TreeviewSelect>>", self._show_detail)

        abar = tk.Frame(self, bg=BG, pady=6)
        abar.pack(fill="x", padx=6, side="bottom")
        for text, cmd in [("Track ▸ Interested", self._track),
                          ("Dismiss", self._dismiss),
                          ("Dismiss Company", self._dismiss_company),
                          ("Open URL", self._open_url),
                          ("Refresh", self.refresh)]:
            tk.Button(abar, text=text, bg=DARK, fg=WHITE, font=("Segoe UI", 9),
                      relief="flat", padx=10, pady=3, command=cmd).pack(
                side="left", padx=2)
        tk.Button(abar, text="Copy Fit Prompt", bg="#2d2d52", fg=WHITE,
                  font=("Segoe UI", 9), relief="flat", padx=10, pady=3,
                  command=self._copy_fit_prompt).pack(side="left", padx=(16, 2))
        tk.Button(abar, text="Paste Fit Results", bg="#2d2d52", fg=WHITE,
                  font=("Segoe UI", 9), relief="flat", padx=10, pady=3,
                  command=self._paste_fit).pack(side="left", padx=2)
        self._status = tk.Label(abar, text="", bg=BG, fg="#666",
                                font=("Segoe UI", 9))
        self._status.pack(side="left", padx=10)

        self._fit_order: list[int] = []  # inbox ids in last fit-prompt order

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
        for r in rows:
            iid = str(r["id"])
            self._rows[iid] = r
            self._tree.insert("", "end", iid=iid, values=(
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
        for r in sel:
            inbox_track(r["id"])
        self._status.config(text=f"Tracked {len(sel)} job(s).", fg="#1565c0")
        self.refresh()
        self._restore_focus(idx)

    def _dismiss(self):
        sel = self._selected()
        if not sel:
            return
        idx = self._focus_index()
        for r in sel:
            inbox_dismiss(r["id"])
        self._status.config(
            text=f"Dismissed {len(sel)} — hidden from future searches.",
            fg="#757575")
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
        for r in targets:
            inbox_dismiss(r["id"])
        self._status.config(
            text=f"Dismissed {len(targets)} row(s) from {names}.",
            fg="#757575")
        self.refresh()
        self._restore_focus(idx)

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
            from collections import defaultdict
            per_co: dict[str, int] = defaultdict(int)
            for r in self._rows.values():
                if r["fit"] >= 0:
                    continue
                key = (r["company"] or "").lower()
                if per_co[key] >= 2:
                    continue
                per_co[key] += 1
                rows.append(r)
        rows = rows[:20]  # one Claude reply handles ~20 jobs well
        if not rows:
            messagebox.showinfo("Inbox empty", "Nothing left to score.")
            return
        from models import JobResult
        jobs = [JobResult(
            title=r["title"], company=r["company"], location=r["location"],
            salary_min=None, salary_max=None,
            # Prepend the stored salary text: salary_display() on a rebuilt
            # JobResult would say "Not listed" even when we know it.
            description=f"Salary: {r['salary_text']}\n{r['description']}",
            url=r["url"], source_keyword="", created=r["created"],
            board_count=r.get("board_count", -1),
        ) for r in rows]
        prompt = build_fit_prompt(jobs, profile_summary())
        self._fit_order = [r["id"] for r in rows]
        copy_or_warn(self, prompt,
                     lambda m: self._status.config(text=m, fg="#e65100"))

    def _paste_fit(self):
        if not self._fit_order:
            messagebox.showinfo("No prompt", "Copy a fit prompt first.")
            return
        dlg = PasteDialog(self)
        if not dlg.result:
            return
        try:
            scores = parse_fit_response(dlg.result, len(self._fit_order))
        except BridgeParseError as e:
            messagebox.showerror("Parse failed", str(e), parent=self)
            return
        applied = 0
        for n, data in scores.items():
            if 1 <= n <= len(self._fit_order):
                inbox_set_fit(self._fit_order[n - 1], data["fit"],
                              f"{data['why']} {data['flags']}".strip())
                applied += 1
        self._status.config(text=f"Applied {applied} fit score(s).", fg="#2e7d32")
        self.refresh()


# ── Search tab ────────────────────────────────────────────────────────────────
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

    def _build(self):
        hdr = tk.Frame(self, bg=DARK)
        hdr.pack(fill="x")
        tk.Label(hdr, text="Job Search", bg=DARK, fg=WHITE,
                 font=("Segoe UI", 13, "bold"), padx=14, pady=10).pack(side="left")

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
        self._search_btn = tk.Button(ctrl, text="Search", bg=DARK, fg=WHITE,
                                     font=("Segoe UI", 9, "bold"), relief="flat",
                                     padx=14, pady=4, command=self._search)
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
        self._status = tk.Label(ctrl, text="", font=("Segoe UI", 9), fg="#666")
        self._status.grid(row=2, column=1, columnspan=4, sticky="w")
        ctrl.columnconfigure(1, weight=1)

        tf = ttk.Frame(self)
        tf.pack(fill="both", expand=True, padx=6, pady=2)
        self._tree = ttk.Treeview(tf, columns=[c[0] for c in self._COLS],
                                  show="headings", selectmode="extended")
        for col, label, width, anchor in self._COLS:
            self._tree.heading(col, text=label)
            self._tree.column(col, width=width, anchor=anchor, minwidth=45)
        vsb = ttk.Scrollbar(tf, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self._tree.bind("<Double-1>", lambda _e: self._open_url())

        # Why-this-score detail line
        self._detail = tk.Label(self, text="", anchor="w", bg=BG, fg="#555",
                                font=("Segoe UI", 9), padx=8)
        self._detail.pack(fill="x", padx=6)
        self._tree.bind("<<TreeviewSelect>>", self._show_detail)

        abar = tk.Frame(self, bg=BG, pady=6)
        abar.pack(fill="x", padx=6, side="bottom")
        for text, cmd in [("Track ▸ Interested", self._track),
                          ("Dismiss", self._dismiss), ("Open URL", self._open_url)]:
            tk.Button(abar, text=text, bg=DARK, fg=WHITE, font=("Segoe UI", 9),
                      relief="flat", padx=10, pady=3, command=cmd).pack(
                side="left", padx=2)
        tk.Label(abar, text="  Ctrl/Shift-click to select multiple",
                 bg=BG, fg="#999", font=("Segoe UI", 8)).pack(side="left")

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
        self._search_btn.config(state="disabled")
        self._status.config(text="Searching…", fg="#e65100")
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
        self._search_btn.config(state="normal")
        self._results = results
        for row in self._tree.get_children():
            self._tree.delete(row)
        for i, j in enumerate(results):
            self._tree.insert("", "end", iid=str(i), values=(
                j.score if j.score >= 0 else "",
                j.title, j.company, j.location, j.salary_display(), j.source_api))
        if not had_clients:
            self._status.config(
                text="No sources configured — add API keys to .env.", fg=ERR)
        else:
            self._status.config(text=f"{len(results)} result(s).", fg="#2e7d32")

    def _on_error(self, msg):
        self._search_btn.config(state="normal")
        self._status.config(text=f"Error: {msg}", fg=ERR)

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
        tracked = seen_urls()
        added = skipped = 0
        for j in sel:
            if normalize_url(j.url) in tracked:
                skipped += 1  # already in tracker or dismissed — no dupes
                continue
            add_job(title=j.title, company=j.company, location=j.location,
                    url=j.url, salary_text=j.salary_display(),
                    source=j.source_api, status="interested",
                    description=(j.description or "")[:5000], score=j.score)
            added += 1
        msg = f"Tracked {added} job(s)."
        if skipped:
            msg += f" Skipped {skipped} already tracked/dismissed."
        self._status.config(text=msg, fg="#1565c0")

    def _dismiss(self):
        sel_iids = list(self._tree.selection())
        if not sel_iids:
            return
        for iid in sel_iids:
            dismiss_url(self._results[int(iid)].url)
            self._tree.delete(iid)
        self._status.config(
            text=f"Dismissed {len(sel_iids)} — hidden from future searches.",
            fg="#757575")

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
        self._build()
        self.refresh()

    def _build(self):
        hdr = tk.Frame(self, bg=DARK)
        hdr.pack(fill="x")
        tk.Label(hdr, text="Apply Queue — interested jobs, best match first",
                 bg=DARK, fg=WHITE, font=("Segoe UI", 13, "bold"),
                 padx=14, pady=10).pack(side="left")
        self._count_lbl = tk.Label(hdr, text="", bg=DARK, fg="#9999bb",
                                   font=("Segoe UI", 9))
        self._count_lbl.pack(side="left")

        tf = ttk.Frame(self)
        tf.pack(fill="both", expand=True, padx=6, pady=2)
        self._tree = ttk.Treeview(tf, columns=[c[0] for c in self._COLS],
                                  show="headings", selectmode="browse")
        for col, label, width, anchor in self._COLS:
            self._tree.heading(col, text=label)
            self._tree.column(col, width=width, anchor=anchor, minwidth=40)
        vsb = ttk.Scrollbar(tf, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self._tree.bind("<Double-1>", lambda _e: self._open_url())
        self._tree.bind("<<TreeviewSelect>>", self._show_detail)

        self._detail = tk.Label(self, text="", anchor="w", justify="left",
                                bg=BG, fg="#555", font=("Segoe UI", 9),
                                padx=8, wraplength=1100)
        self._detail.pack(fill="x", padx=6)

        abar = tk.Frame(self, bg=BG, pady=6)
        abar.pack(fill="x", padx=6, side="bottom")
        tk.Button(abar, text="Open Posting", bg=DARK, fg=WHITE,
                  font=("Segoe UI", 9), relief="flat", padx=10, pady=3,
                  command=self._open_url).pack(side="left", padx=2)
        tk.Button(abar, text="Copy Resume Prompt", bg="#2d2d52", fg=WHITE,
                  font=("Segoe UI", 9), relief="flat", padx=10, pady=3,
                  command=self._copy_resume_prompt).pack(side="left", padx=2)
        tk.Button(abar, text="Paste Reply ▸ DOCX", bg="#2d2d52", fg=WHITE,
                  font=("Segoe UI", 9), relief="flat", padx=10, pady=3,
                  command=self._paste_resume).pack(side="left", padx=2)
        tk.Button(abar, text=f"Batch Prompt ({self._BATCH_LIMIT})",
                  bg="#2d2d52", fg=WHITE,
                  font=("Segoe UI", 9), relief="flat", padx=10, pady=3,
                  command=self._copy_batch_prompt).pack(side="left", padx=(10, 2))
        tk.Button(abar, text="Paste Batch ▸ DOCX", bg="#2d2d52", fg=WHITE,
                  font=("Segoe UI", 9), relief="flat", padx=10, pady=3,
                  command=self._paste_batch).pack(side="left", padx=2)
        from resume.service import api_available
        if api_available():
            tk.Button(abar, text="Generate via API", bg="#2d2d52", fg=WHITE,
                      font=("Segoe UI", 9), relief="flat", padx=10, pady=3,
                      command=self._generate_api).pack(side="left", padx=2)
        tk.Button(abar, text="Mark Applied ▸ Next", bg="#2e7d32", fg=WHITE,
                  font=("Segoe UI", 9, "bold"), relief="flat", padx=12, pady=3,
                  command=self._mark_applied).pack(side="left", padx=(16, 2))
        tk.Button(abar, text="Copy Fit Prompt", bg="#555577", fg=WHITE,
                  font=("Segoe UI", 9), relief="flat", padx=10, pady=3,
                  command=self._copy_fit_prompt).pack(side="left", padx=(16, 2))
        tk.Button(abar, text="Paste Fit Results", bg="#555577", fg=WHITE,
                  font=("Segoe UI", 9), relief="flat", padx=10, pady=3,
                  command=self._paste_fit).pack(side="left", padx=2)
        self._status = tk.Label(abar, text="", bg=BG, fg="#666",
                                font=("Segoe UI", 9))
        self._status.pack(side="left", padx=10)

    def refresh(self, keep_selection=False):
        prev = self._tree.selection()
        self._rows = {}
        for iid in self._tree.get_children():
            self._tree.delete(iid)
        jobs = get_all("interested")
        jobs.sort(key=lambda j: (j.get("fit_score") or -1,
                                 j.get("score") or -1), reverse=True)
        for j in jobs:
            iid = str(j["id"])
            self._rows[iid] = j
            self._tree.insert("", "end", iid=iid, values=(
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

    # ── Resume docs (bridge) ──────────────────────────────────────────────────

    def _posting_text(self, j: dict) -> str | None:
        """Job description from the DB, or ask the user to paste the posting."""
        if (j.get("description") or "").strip():
            return j["description"]
        dlg = PasteDialog(self, title="Paste the job posting",
                          hint="No saved description for this job — paste the "
                               "posting text from the job page:")
        if dlg.result:
            update_job(j["id"], description=dlg.result[:5000])
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
        j = get_job(self._prompt_job_id)
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
        update_job(j["id"], resume_path=str(resume_path),
                   cover_path=str(cover_path) if cover_path else "")
        self._status.config(text=f"Docs saved: {resume_path.name}", fg="#2e7d32")
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
            j = get_job(self._batch_order[n - 1])
            if not j:
                continue
            try:
                resume_path, cover_path = save_bundle_from_data(
                    data, workspace.output_dir(), company=j["company"])
            except Exception as e:
                failed.append(f"{j['company']}: {e}")
                continue
            update_job(j["id"], resume_path=str(resume_path),
                       cover_path=str(cover_path) if cover_path else "")
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
        self._status.config(text="Generating with Claude API…", fg="#e65100")

        def worker():
            try:
                from resume.service import save_bundle
                resume_path, cover_path = save_bundle(posting, workspace.output_dir(),
                                                      company=j["company"])
                self.after(0, lambda: self._api_done(j["id"], resume_path, cover_path))
            except Exception as e:
                self.after(0, lambda: self._status.config(
                    text=f"Error: {e}", fg=ERR))
        threading.Thread(target=worker, daemon=True).start()

    def _api_done(self, job_id, resume_path, cover_path=None):
        update_job(job_id, resume_path=str(resume_path),
                   cover_path=str(cover_path) if cover_path else "")
        self._status.config(text=f"Docs saved: {resume_path.name}", fg="#2e7d32")
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
        update_job(j["id"], status="applied",
                   date_applied=date.today().isoformat(), **kwargs)
        self._status.config(
            text=f"Applied: {j['title']} @ {j['company']}", fg="#2e7d32")
        self.refresh()
        if nxt and nxt in self._rows:
            self._tree.selection_set(nxt)
            self._tree.see(nxt)

    # ── Claude fit scoring (bridge) ───────────────────────────────────────────

    def _copy_fit_prompt(self):
        rows = list(self._rows.values())[:20]
        if not rows:
            messagebox.showinfo("Queue empty", "Nothing to score.")
            return
        from models import JobResult
        jobs = [JobResult(
            title=r["title"], company=r["company"],
            location=r.get("location", ""), salary_min=None, salary_max=None,
            description=r.get("description", ""), url=r.get("url", ""),
            source_keyword="", created="",
        ) for r in rows]
        prompt = build_fit_prompt(jobs, profile_summary())
        self._fit_order = [r["id"] for r in rows]
        copy_or_warn(self, prompt,
                     lambda m: self._status.config(text=m, fg="#e65100"))

    def _paste_fit(self):
        if not self._fit_order:
            messagebox.showinfo("No prompt", "Copy a fit prompt first.")
            return
        dlg = PasteDialog(self)
        if not dlg.result:
            return
        try:
            scores = parse_fit_response(dlg.result, len(self._fit_order))
        except BridgeParseError as e:
            messagebox.showerror("Parse failed", str(e), parent=self)
            return
        applied = 0
        for n, data in scores.items():
            if 1 <= n <= len(self._fit_order):
                update_job(self._fit_order[n - 1], fit_score=data["fit"],
                           fit_rationale=f"{data['why']} {data['flags']}".strip())
                applied += 1
        self._status.config(text=f"Applied {applied} fit score(s).", fg="#2e7d32")
        self.refresh(keep_selection=True)


# ── App root ──────────────────────────────────────────────────────────────────
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.geometry("1280x780")
        self.minsize(980, 620)

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

    # ── project bar (switch campaigns without restarting) ──────────────────────
    def _build_projectbar(self):
        if not workspace.has_projects():
            return  # pre-migration: single root workspace, no switcher
        bar = tk.Frame(self, bg=DARK)
        bar.pack(fill="x", side="top")
        tk.Label(bar, text="Project:", bg=DARK, fg=WHITE,
                 font=("Segoe UI", 9, "bold"), padx=12, pady=6).pack(side="left")
        self._proj_var = tk.StringVar()
        self._proj_cb = ttk.Combobox(bar, textvariable=self._proj_var,
                                     state="readonly", width=34)
        self._proj_cb.pack(side="left", padx=4, pady=6)
        self._proj_cb.bind("<<ComboboxSelected>>", self._on_project_change)
        tk.Button(bar, text="+ New", bg=WHITE, fg=DARK, relief="flat",
                  font=("Segoe UI", 9, "bold"), padx=10, pady=2,
                  command=self._new_project).pack(side="left", padx=6)
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
        try:
            # Seed from the current project so it opens with working keywords/resume.
            workspace.create_project(name.strip(), config=workspace.load_config(),
                                     copy_resume_from=workspace.active_slug(),
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
        self._nb.add(self._inbox,   text="  Inbox  ")
        self._nb.add(self._search,  text="  Search  ")
        self._nb.add(self._queue,   text="  Apply Queue  ")
        self._nb.add(self._tracker, text="  Job Tracker  ")
        self._nb.add(self._resume,  text="  Resume Generator  ")
        self._update_badges()

    def _rebuild_tabs(self):
        for tab in (self._inbox, self._search, self._queue, self._tracker, self._resume):
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
        self._nb.tab(0, text=f"  Inbox ({n})  " if n else "  Inbox  ")

    def _on_tab_changed(self, _event=None):
        current = self._nb.nametowidget(self._nb.select())
        if current is self._queue:
            self._queue.refresh(keep_selection=True)
        elif current is self._tracker:
            self._tracker.refresh()
        elif current is self._inbox:
            self._inbox.refresh()
        self._update_badges()


if __name__ == "__main__":
    App().mainloop()
