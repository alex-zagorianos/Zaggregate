"""Job Tracker tab.

Extracted from gui.py (S35 gui-split) as a pure move — no behavior change.
"""
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox

from tracker.db import get_all, get_counts, count_followups_due, get_job, STATUSES, STATUS_LABELS
from tracker import service as tracker_service
from ui import theme
from ui import common
from ui.common import safe_url, db_guard
from ui.job_dialog import JobDialog


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
        self._abar = tk.Frame(self, bg=common.BG, pady=6)
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
