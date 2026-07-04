"""AddCompaniesDialog + BuildCompanyListDialog: the two company-list-building
Tools dialogs, plus the pure partition_add_entries helper they share.

Extracted from gui.py (S35 gui-split) as a pure move — no behavior change.
"""
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from ui import theme
from ui.common import copy_or_warn
from ui.paste_dialog import PasteDialog

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
