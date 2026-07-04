"""Search tab: multi-source search with match scoring, run in-app.

Extracted from gui.py (S35 gui-split) as a pure move — no behavior change.
"""
import threading
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox

import workspace
from config import DEFAULT_LOCATION
from tracker import service as tracker_service
from tracker.db import seen_urls, normalize_url
from ui import theme
from ui.common import safe_url, db_guard, set_status
from ui.companies_dialogs import AddCompaniesDialog, BuildCompanyListDialog

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

