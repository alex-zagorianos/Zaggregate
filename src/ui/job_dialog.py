"""Add/Edit job dialog + the interview-round sub-dialog it uses.

Extracted from gui.py (S35 gui-split) as a pure move — no behavior change.
"""
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

from tracker.db import (
    STATUSES,
    add_status_note, status_timeline,
    add_interview_round, list_interview_rounds, delete_interview_round,
)
from tracker import service as tracker_service
import workspace
from ui import theme
from ui import help as uihelp
from ui.common import db_guard, _DATE_RE

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
                                        font=theme.FONT_SM)
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
                                           font=theme.FONT_MONO_SM)
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
        self._notes = theme.text_widget(form, width=40, height=3, font=theme.FONT_SM)
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
