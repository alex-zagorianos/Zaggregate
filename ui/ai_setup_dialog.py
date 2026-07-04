"""AiSetupDialog — "Set me up with my AI" (§6.3) Tools dialog.

Extracted from gui.py (S35 gui-split) as a pure move — no behavior change.
"""
import tkinter as tk
from tkinter import messagebox

from ui import theme
from ui.common import copy_or_warn


class AiSetupDialog(tk.Toplevel):
    """"Set me up with my AI" (§6.3): a BYO-AI onboarding path. The app never
    calls an LLM — it hands the user a copyable prompt to paste (with their
    résumé + one sentence of intent) into THEIR own AI, then parses the canonical
    config block the AI returns and applies it to config.json +
    preferences.{json,md}. The wizard steps are owned by a parallel builder; this
    is a standalone Tools dialog over ui.ai_setup's pure functions."""

    def __init__(self, parent, on_applied=None):
        super().__init__(parent)
        self.title("Set up with your AI")
        self.geometry("720x600")
        self.configure(bg=theme.WINDOW)
        self.transient(parent)
        self.grab_set()
        self._on_applied = on_applied
        self._build()

    def _build(self):
        from ui import ai_setup
        tk.Label(self, justify="left", wraplength=690, fg=theme.INK, bg=theme.WINDOW,
                 text="Have a Claude or ChatGPT subscription? Let it set you up.\n"
                      "1. Copy the prompt below. 2. Paste it into your AI, then "
                      "paste your résumé and one sentence about the job you want. "
                      "3. Copy your AI's reply back into the box below and click "
                      "Apply."
                 ).pack(fill="x", padx=12, pady=(12, 6))

        tk.Label(self, text="Step 1 — copy this prompt:", anchor="w",
                 fg=theme.MUTED, bg=theme.WINDOW).pack(fill="x", padx=12)
        self._prompt_box = theme.text_widget(self, height=8, wrap="word")
        self._prompt_box.pack(fill="both", expand=True, padx=12, pady=(2, 4))
        self._prompt_box.insert("1.0", ai_setup.build_setup_prompt())
        self._prompt_box.configure(state="disabled")

        prow = tk.Frame(self, bg=theme.WINDOW)
        prow.pack(fill="x", padx=12, pady=(0, 6))
        theme.btn(prow, "Copy prompt", self._copy_prompt, "accent").pack(side="left")

        tk.Label(self, text="Step 2 — paste your AI's reply here:", anchor="w",
                 fg=theme.MUTED, bg=theme.WINDOW).pack(fill="x", padx=12)
        self._reply_box = theme.text_widget(self, height=8, wrap="word")
        self._reply_box.pack(fill="both", expand=True, padx=12, pady=(2, 4))

        arow = tk.Frame(self, bg=theme.WINDOW)
        arow.pack(fill="x", padx=12, pady=(0, 6))
        theme.btn(arow, "Apply setup", self._apply, "accent").pack(side="left")
        theme.btn(arow, "Close", self.destroy, "ghost").pack(side="right")

        self._status = tk.Label(self, text="", fg=theme.MUTED, bg=theme.WINDOW,
                                anchor="w", justify="left", wraplength=690)
        self._status.pack(fill="x", padx=12, pady=(0, 10))

    def _copy_prompt(self):
        from ui import ai_setup
        copy_or_warn(self, ai_setup.build_setup_prompt(),
                     status_cb=lambda m: self._status.config(text=m))

    def _apply(self):
        from ui import ai_setup
        text = self._reply_box.get("1.0", "end-1c").strip()
        if not text:
            self._status.config(text="Paste your AI's reply first.")
            return
        try:
            summary = ai_setup.apply_setup(text)
        except ai_setup.SetupBlockError as e:
            messagebox.showwarning("Couldn't apply setup", str(e), parent=self)
            self._status.config(text=str(e))
            return
        titles = ", ".join(summary.get("target_titles", [])[:4])
        loc = "Remote" if summary.get("remote_only") else summary.get("location", "")
        self._status.config(
            text=f"Applied. Field: {summary.get('field')} · Titles: {titles} · "
                 f"Where: {loc}. Your preferences are saved.")
        messagebox.showinfo(
            "You're set up",
            f"Field: {summary.get('field')}\n"
            f"Titles: {titles}\n"
            f"Location: {loc}\n"
            f"Salary floor: {summary.get('salary_min') or '—'}\n\n"
            "Your search config and preferences are saved. Run an inbox update "
            "to see your first jobs.", parent=self)
        if callable(self._on_applied):
            try:
                self._on_applied(summary)
            except Exception:
                pass
        self.destroy()
