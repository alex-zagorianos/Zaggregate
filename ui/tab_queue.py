"""Apply Queue tab.

Extracted from gui.py (S36 gui-split) as a pure move — no behavior change.
"""
import threading
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox

import ranker as _ranker_mod
import workspace
from claude_bridge import BridgeParseError
from match import ats_hint as atshintmod
from tracker import service as tracker_service
from tracker.db import get_all
from ui import theme
from ui import common
from ui.common import safe_url, db_guard, set_status, copy_or_warn, _call_prompt_via_api
from ui.paste_dialog import PasteDialog


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
        self._status.config(text=text, fg=theme.SUCCESS if saved else common.ERR)
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
