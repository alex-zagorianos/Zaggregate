"""Ctrl+K command palette — a fast fuzzy launcher over the app's actions (the
signature 'modern dev-tool' motif). Self-contained overlay; opening it needs only
the running App. Isolated from theme/ttk styling so it cannot destabilize the rest
of the UI."""
import tkinter as tk

from ui import theme


def filter_commands(labels, query):
    """Subset of `labels` matching `query` case-insensitively, best-first: direct
    substring matches (earlier position first) before scattered-subsequence
    matches, then alphabetical. Empty query returns all. Pure + testable."""
    q = (query or "").strip().lower()
    if not q:
        return list(labels)
    scored = []
    for lab in labels:
        low = lab.lower()
        pos = low.find(q)
        if pos != -1:
            scored.append((0, pos, lab))
            continue
        it = iter(low)
        if all(ch in it for ch in q):   # subsequence match
            scored.append((1, 0, lab))
    scored.sort(key=lambda t: (t[0], t[1], t[2].lower()))
    return [lab for _, _, lab in scored]


def build_commands(app):
    """List of (label, callable) derived from the running App. Each lookup is
    guarded so a missing attribute simply omits that command."""
    cmds = []
    nb = getattr(app, "_nb", None)

    def go(tab_attr):
        tab = getattr(app, tab_attr, None)
        if nb is not None and tab is not None:
            return lambda: nb.select(tab)
        return None

    for label, attr in (("Go to Inbox", "_inbox"),
                        ("Go to Top Picks", "_toppicks"),
                        ("Go to Search", "_search"),
                        ("Go to Apply Queue", "_queue"),
                        ("Go to Job Tracker", "_tracker"),
                        ("Go to Resume Generator", "_resume"),
                        ("Open the Guide", "_guide")):
        fn = go(attr)
        if fn:
            cmds.append((label, fn))

    if hasattr(app, "_toggle_dark") and hasattr(app, "_dark_var"):
        def _toggle():
            app._dark_var.set(not app._dark_var.get())
            app._toggle_dark()
        cmds.append(("Toggle dark mode", _toggle))

    for label, attr in (("New Project…", "_new_project"),
                        ("New Person…", "_new_person")):
        fn = getattr(app, attr, None)
        if callable(fn):
            cmds.append((label, fn))
    return cmds


class CommandPalette(tk.Toplevel):
    def __init__(self, app, commands):
        super().__init__(app)
        self._labels = [c[0] for c in commands]
        self._map = dict(commands)
        self._matches = list(self._labels)
        self.withdraw()
        self.overrideredirect(True)
        self.transient(app)
        self.configure(bg=theme.BORDER)
        outer = tk.Frame(self, bg=theme.BORDER)
        outer.pack(fill="both", expand=True, padx=1, pady=1)
        self._var = tk.StringVar()
        ent = tk.Entry(outer, textvariable=self._var, bg=theme.SURFACE, fg=theme.INK,
                       insertbackground=theme.INK, relief="flat", font=theme.FONT,
                       highlightthickness=0)
        ent.pack(fill="x", ipady=8)
        self._list = tk.Listbox(outer, bg=theme.SURFACE, fg=theme.INK,
                                selectbackground=theme.ACCENT,
                                selectforeground=theme.ACCENT_FG, relief="flat",
                                font=theme.FONT, height=8, highlightthickness=0,
                                activestyle="none")
        self._list.pack(fill="both", expand=True)
        self._refresh()
        self._var.trace_add("write", lambda *_: self._refresh())
        ent.bind("<Down>", lambda e: self._move(1))
        ent.bind("<Up>", lambda e: self._move(-1))
        ent.bind("<Return>", lambda e: self._run())
        ent.bind("<Escape>", lambda e: self.destroy())
        self._list.bind("<Double-Button-1>", lambda e: self._run())
        self.update_idletasks()
        w, h = 520, 320
        px, py = app.winfo_rootx(), app.winfo_rooty()
        pw, ph = app.winfo_width(), app.winfo_height()
        self.geometry(f"{w}x{h}+{px + (pw - w) // 2}+{py + max(60, (ph - h) // 3)}")
        self.deiconify()
        ent.focus_set()

    def _refresh(self):
        self._matches = filter_commands(self._labels, self._var.get())
        self._list.delete(0, "end")
        for m in self._matches:
            self._list.insert("end", m)
        if self._matches:
            self._list.selection_set(0)

    def _move(self, d):
        if not self._matches:
            return
        cur = self._list.curselection()
        i = max(0, min(len(self._matches) - 1, (cur[0] if cur else 0) + d))
        self._list.selection_clear(0, "end")
        self._list.selection_set(i)
        self._list.see(i)

    def _run(self):
        if not self._matches:
            return
        cur = self._list.curselection()
        label = self._matches[cur[0] if cur else 0]
        fn = self._map.get(label)
        self.destroy()
        if fn:
            try:
                fn()
            except Exception:
                pass


def open_palette(app):
    """Open the command palette over `app` (no-op-safe if there are no commands)."""
    cmds = build_commands(app)
    if not cmds:
        return
    CommandPalette(app, cmds)
