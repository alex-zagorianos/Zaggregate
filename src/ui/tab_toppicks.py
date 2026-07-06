"""Top Picks tab.

Extracted from gui.py (S35 gui-split) as a pure move — no behavior change.
"""
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox

from tracker import service as tracker_service
from ui import theme
from ui.common import safe_url, set_status


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
