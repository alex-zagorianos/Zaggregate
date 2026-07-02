"""Visual Kanban board over the existing tracker DB — Huntr's #1-loved feature,
rebuilt local-first as a pure GUI view (SB-5). Every application already lives in
``tracker.db``; this renders those rows as status columns of cards and moves them
between columns through the SAME service verbs the Tracker tab uses
(``tracker.service.set_status`` → ``db.update_job``), so the Kanban and the list
Tracker are two views of one source of truth.

Design notes:
  * Columns are the funnel stages in order. Terminal/outcome stages
    (accepted / rejected / ghosted / withdrawn) are shown but a card there gets
    NO "advance" affordance — we never offer a downgrade, honoring the Wave-1
    round/status coherence (no-downgrade) at the UI. A card can still be *edited*
    (double-click) from any column, and a stuck-terminal card can be reopened via
    the edit dialog's status field, but the board itself only offers forward moves.
  * Moves are button/menu based, not drag-and-drop: DnD in Tk is fragile and the
    plan explicitly says not to over-engineer it. Each card has a "Move ▸" menu
    listing only the valid forward targets for its current stage.
  * Cards show company + title + days-in-stage, matching the plan's spec, styled
    with the Aegean-Paper chrome (status-tinted left rule, surface cards, muted
    metadata) so it sits natively beside the other tabs.
"""
import tkinter as tk
from tkinter import ttk, messagebox

from ui import theme

# Column order. The eight named funnel stages (SB-5), plus 'withdrawn' at the end
# so no tracked application is ever invisible on the board (it's a real status a
# row can hold). Kept as a module constant so the headless tests assert the layout
# without a display.
COLUMNS = ["interested", "applied", "phone_screen", "interview", "offer",
           "accepted", "rejected", "withdrawn", "ghosted"]

# Terminal / outcome stages: a card here is done moving forward, so the board
# offers no "advance" button (never a downgrade). Editing (double-click) still
# lets the user correct a status via the dialog if they truly need to.
_TERMINAL = frozenset({"accepted", "rejected", "withdrawn", "ghosted"})

# The forward moves the board offers from each stage. Progression stages advance
# to the next funnel step AND to any outcome; the model in tracker.db permits any
# status set, but we only surface non-downgrading choices so the board can't be
# used to walk an application backwards by accident.
_OUTCOMES = ["offer", "accepted", "rejected", "withdrawn", "ghosted"]


def forward_targets(status: str) -> list[str]:
    """The statuses the board lets a card in ``status`` move to — forward funnel
    step(s) plus outcomes, de-duplicated, never the card's own status, and never a
    downgrade. Terminal stages return [] (no advance offered). Pure/​testable."""
    if status in _TERMINAL:
        return []
    order = ["interested", "applied", "phone_screen", "interview", "offer",
             "accepted"]
    out: list[str] = []
    if status in order:
        idx = order.index(status)
        # the immediate next funnel step (if any)
        if idx + 1 < len(order):
            out.append(order[idx + 1])
    # plus every outcome that isn't the current status and isn't already queued
    for s in _OUTCOMES:
        if s != status and s not in out:
            out.append(s)
    return out


def days_in_stage(row: dict, today=None) -> int | None:
    """Whole days the application has sat in its current status, best-effort from
    the row's own dates (no DB round-trip): the later of date_applied/date_added is
    the reference for a fresh row. Returns None when no usable date is present.

    A precise "entered this status at" would need status_history; the board keeps
    it dependency-free and cheap by reading the row it already has. ``today`` is
    injectable for deterministic tests.
    """
    from datetime import date
    if today is None:
        today = date.today()
    elif isinstance(today, str):
        try:
            today = date.fromisoformat(today[:10])
        except ValueError:
            return None
    ref = ""
    # date_applied is the meaningful clock once applied; before that, date_added.
    status = (row.get("status") or "")
    if status not in ("interested",):
        ref = (row.get("date_applied") or "").strip()
    if not ref:
        ref = (row.get("date_added") or "").strip()
    if not ref:
        return None
    try:
        ref_date = date.fromisoformat(ref[:10])
    except ValueError:
        return None
    delta = (today - ref_date).days
    return delta if delta >= 0 else 0


def days_label(n: int | None) -> str:
    """A compact 'Nd here' badge for a day count (or '' when unknown)."""
    if n is None:
        return ""
    if n == 0:
        return "today"
    if n == 1:
        return "1 day"
    return f"{n} days"


def group_by_status(rows: list[dict]) -> dict[str, list[dict]]:
    """Bucket application rows into ``{status: [rows...]}`` for every COLUMN.
    A row whose status isn't a known column is dropped from the board (it would be
    an archived/unknown state); every known column key is always present (possibly
    empty). Newest-first within a column (rows arrive date_added DESC from db)."""
    buckets: dict[str, list[dict]] = {c: [] for c in COLUMNS}
    for r in rows:
        s = r.get("status")
        if s in buckets:
            buckets[s].append(r)
    return buckets


class KanbanTab(ttk.Frame):
    """A horizontally-scrolling board of status columns, each a stack of cards.
    Reads the active project's tracker via the same service the Tracker tab uses;
    refresh() re-reads on demand and on tab focus."""

    _CARD_W = 200

    def __init__(self, parent):
        super().__init__(parent)
        self._build()
        self.refresh()

    # ── scaffolding ───────────────────────────────────────────────────────────
    def _build(self):
        theme.header_bar(self, "Application Board")
        self._count_lbl = None
        theme.tip_strip(
            self, "Your applications as a board — one column per stage. Use a "
                  "card's Move button to advance it as you hear back; double-click "
                  "to edit. It's the same data as the Job Tracker tab.")

        # A horizontally-scrolling canvas holds the columns row.
        outer = tk.Frame(self, bg=theme.WINDOW)
        outer.pack(fill="both", expand=True, padx=6, pady=6)
        self._canvas = tk.Canvas(outer, bg=theme.WINDOW, highlightthickness=0)
        hsb = ttk.Scrollbar(outer, orient="horizontal", command=self._canvas.xview)
        self._canvas.configure(xscrollcommand=hsb.set)
        hsb.pack(side="bottom", fill="x")
        self._canvas.pack(side="top", fill="both", expand=True)
        self._board = tk.Frame(self._canvas, bg=theme.WINDOW)
        self._board_win = self._canvas.create_window(
            (0, 0), window=self._board, anchor="nw")
        self._board.bind(
            "<Configure>",
            lambda _e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        self._canvas.bind(
            "<Configure>",
            lambda e: self._canvas.itemconfigure(self._board_win, height=e.height))

    # ── data ──────────────────────────────────────────────────────────────────
    def refresh(self):
        """Re-read the tracker and rebuild the columns."""
        from tracker import service as tracker_service
        try:
            rows = tracker_service.list_jobs()
        except Exception:
            rows = []
        buckets = group_by_status(rows)
        for w in self._board.winfo_children():
            w.destroy()
        total = sum(len(v) for v in buckets.values())
        for col in COLUMNS:
            self._build_column(col, buckets[col], total)

    def _build_column(self, status: str, rows: list[dict], total: int):
        from tracker.db import STATUS_LABELS
        fg = theme.STATUS_BADGE.get(status, theme.MUTED)
        col = tk.Frame(self._board, bg=theme.WINDOW, width=self._CARD_W + 20)
        col.pack(side="left", fill="y", padx=4, pady=2)
        col.pack_propagate(False)

        # Column header: status name + count, tinted with the status color.
        head = tk.Frame(col, bg=theme.SURFACE)
        head.pack(fill="x", pady=(0, 4))
        tk.Frame(head, bg=fg, height=3).pack(side="top", fill="x")
        tk.Label(head, text=STATUS_LABELS.get(status, status.title()),
                 bg=theme.SURFACE, fg=fg, font=theme.FONT_BOLD,
                 anchor="w").pack(side="left", padx=8, pady=5)
        tk.Label(head, text=str(len(rows)), bg=theme.SURFACE, fg=theme.MUTED,
                 font=theme.FONT_SM).pack(side="right", padx=8)

        body = tk.Frame(col, bg=theme.WINDOW)
        body.pack(fill="both", expand=True)
        if not rows:
            tk.Label(body, text="—", bg=theme.WINDOW, fg=theme.FAINT,
                     font=theme.FONT_SM).pack(anchor="n", pady=6)
            return
        for r in rows:
            self._build_card(body, r, status, fg)

    def _build_card(self, parent, row: dict, status: str, fg: str):
        card = tk.Frame(parent, bg=theme.SURFACE, highlightthickness=1,
                        highlightbackground=theme.BORDER)
        card.pack(fill="x", pady=3, padx=1)
        # status-tinted left rule
        rule = tk.Frame(card, bg=fg, width=4)
        rule.pack(side="left", fill="y")
        inner = tk.Frame(card, bg=theme.SURFACE)
        inner.pack(side="left", fill="both", expand=True, padx=6, pady=5)

        company = (row.get("company") or "").strip() or "—"
        title = (row.get("title") or "").strip() or "(no title)"
        tk.Label(inner, text=company, bg=theme.SURFACE, fg=theme.INK,
                 font=theme.FONT_BOLD, anchor="w", justify="left",
                 wraplength=self._CARD_W - 20).pack(anchor="w")
        tk.Label(inner, text=title, bg=theme.SURFACE, fg=theme.MUTED,
                 font=theme.FONT_SM, anchor="w", justify="left",
                 wraplength=self._CARD_W - 20).pack(anchor="w")

        dl = days_label(days_in_stage(row))
        meta = tk.Frame(inner, bg=theme.SURFACE)
        meta.pack(fill="x", pady=(4, 0))
        if dl:
            tk.Label(meta, text=dl + " here", bg=theme.SURFACE, fg=theme.FAINT,
                     font=theme.FONT_SM).pack(side="left")

        targets = forward_targets(status)
        if targets:
            mb = ttk.Menubutton(meta, text="Move ▸", style="Ghost.TButton")
            menu = theme.style_menu(tk.Menu(mb, tearoff=0))
            from tracker.db import STATUS_LABELS
            for t in targets:
                menu.add_command(
                    label=STATUS_LABELS.get(t, t.title()),
                    command=lambda tgt=t, jid=row["id"]: self._move(jid, tgt))
            mb.configure(menu=menu)
            mb.pack(side="right")

        # Double-click a card anywhere to open the full edit dialog (reuses the
        # Tracker's JobDialog so the board and list stay one workflow).
        for w in (card, inner, meta,
                  *inner.winfo_children(), *meta.winfo_children()):
            w.bind("<Double-1>", lambda _e, jid=row["id"]: self._edit(jid))

    # ── mutations (through the shared service) ────────────────────────────────
    def _move(self, job_id: int, status: str):
        from tracker import service as tracker_service
        try:
            tracker_service.set_status(int(job_id), status)
        except Exception as e:
            messagebox.showerror("Move failed",
                                 f"Could not move this application.\n\n{e}",
                                 parent=self)
            return
        self.refresh()
        self.event_generate("<<KanbanChanged>>")

    def _edit(self, job_id: int):
        from tracker import service as tracker_service
        import gui
        job = tracker_service.get_job(int(job_id))
        if not job:
            return
        dlg = gui.JobDialog(self, job=job)
        if dlg.result:
            try:
                tracker_service.update_job(int(job_id), **dlg.result)
            except Exception as e:
                messagebox.showerror("Update failed", str(e), parent=self)
                return
            self.refresh()
            self.event_generate("<<KanbanChanged>>")
