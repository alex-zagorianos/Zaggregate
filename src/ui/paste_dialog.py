"""Paste dialog (Claude copy-paste bridge).

Extracted from gui.py (S35 gui-split) as a pure move — no behavior change.
"""
import tkinter as tk
from tkinter import ttk

from ui import theme


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
        self._text = theme.text_widget(body, font=theme.FONT_MONO_SM)
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
