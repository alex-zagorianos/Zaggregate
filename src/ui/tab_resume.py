"""Resume Generator tab.

Extracted from gui.py (S35 gui-split) as a pure move — no behavior change.
"""
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox

import workspace
from claude_bridge import BridgeParseError
from ui import theme
from ui import common
from ui.common import copy_or_warn
from ui.paste_dialog import PasteDialog


# ── Resume Generator tab ──────────────────────────────────────────────────────
class ResumeTab(ttk.Frame):

    def __init__(self, parent):
        super().__init__(parent)
        self._output_dir = None
        self._build()

    def _build(self):
        # Header
        theme.header_bar(
            self, "Resume & Cover Letter Generator",
            "Paste a job posting — Claude generates a tailored resume + cover letter.")
        theme.tip_strip(
            self, "Paste any job posting below, then click 1. Copy Prompt → paste "
                  "it into claude.ai → 2. Paste the reply to get Word documents.")

        # Text input area
        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Job Posting", style="H2.TLabel").pack(anchor="w")

        txt_f = ttk.Frame(body)
        txt_f.pack(fill="both", expand=True, pady=4)
        self._text = theme.text_widget(txt_f, font=theme.FONT)
        vsb = ttk.Scrollbar(txt_f, orient="vertical", command=self._text.yview)
        self._text.configure(yscrollcommand=vsb.set)
        self._text.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        # Control bar — copy-paste bridge is the default path; the API button
        # appears only when ANTHROPIC_API_KEY is configured.
        bar = tk.Frame(self, bg=theme.WINDOW, pady=8)
        bar.pack(fill="x", padx=12, side="bottom")

        theme.tip(theme.btn(bar, "1. Copy Prompt", self._copy_prompt, "accent"),
                  "Copies a tailoring prompt for the pasted job. Paste it into "
                  "claude.ai.").pack(side="left")
        theme.tip(theme.btn(bar, "2. Paste Reply \N{BLACK RIGHT-POINTING SMALL TRIANGLE} DOCX",
                            self._paste_reply, "ghost"),
                  "Paste Claude's reply here to build the resume + cover-letter "
                  "Word files.").pack(side="left", padx=8)

        from resume.service import api_available
        self._gen_btn = None
        if api_available():
            self._gen_btn = theme.btn(bar, "Generate via API", self._generate, "ghost")
            self._gen_btn.pack(side="left")

        theme.btn(bar, "Clear", self._clear, "ghost").pack(side="left", padx=8)

        self._status_lbl = tk.Label(bar, text="", bg=theme.WINDOW,
                                     fg=theme.MUTED, font=theme.FONT_SM)
        self._status_lbl.pack(side="left", padx=6)

        self._out_lbl = tk.Label(bar, text="", bg=theme.WINDOW, fg=theme.ACCENT,
                                  font=(theme.SANS, 9, "underline"),
                                  cursor="hand2")
        self._out_lbl.pack(side="left")
        self._out_lbl.bind("<Button-1>", self._open_folder)

    def _clear(self):
        self._text.delete("1.0", "end")
        self._status_lbl.config(text="", fg=theme.MUTED)
        self._out_lbl.config(text="")
        self._output_dir = None

    def _posting(self) -> str | None:
        posting = self._text.get("1.0", "end-1c").strip()
        if not posting:
            messagebox.showwarning("Empty", "Paste a job posting first.",
                                   parent=self)
            return None
        return posting

    # Bridge path (no API key): copy prompt -> claude.ai -> paste reply.
    def _copy_prompt(self):
        posting = self._posting()
        if not posting:
            return
        from resume.service import build_prompt
        try:
            prompt = build_prompt(posting)
        except Exception as e:
            self._status_lbl.config(text=f"Error: {e}", fg=common.ERR)
            return
        copy_or_warn(self, prompt,
                     lambda m: self._status_lbl.config(text=m, fg=theme.WARN))

    def _paste_reply(self):
        dlg = PasteDialog(self)
        if not dlg.result:
            return
        from resume.service import data_from_paste, save_bundle_from_data
        try:
            data = data_from_paste(dlg.result)
            resume_path, _cover = save_bundle_from_data(data, workspace.output_dir())
        except BridgeParseError as e:
            messagebox.showerror("Parse failed", str(e), parent=self)
            return
        except Exception as e:
            messagebox.showerror("DOCX failed", str(e), parent=self)
            return
        self._on_done(resume_path.parent)

    # API path
    def _generate(self):
        posting = self._posting()
        if not posting:
            return
        self._gen_btn.config(state="disabled")
        self._status_lbl.config(
            text="Generating with Claude...  (15–30 sec)", fg=theme.WARN)
        self._out_lbl.config(text="")
        threading.Thread(target=self._worker, args=(posting,),
                         daemon=True).start()

    def _worker(self, posting):
        try:
            from resume.service import save_bundle
            save_bundle(posting, workspace.output_dir())
            self.after(0, self._on_done, workspace.output_dir())
        except Exception as exc:
            self.after(0, self._on_error, str(exc))

    def _on_done(self, out_dir):
        if self._gen_btn:
            self._gen_btn.config(state="normal")
        self._output_dir = out_dir
        self._status_lbl.config(text="Done — saved to:", fg=theme.SUCCESS)
        self._out_lbl.config(text=str(out_dir))

    def _on_error(self, msg):
        if self._gen_btn:
            self._gen_btn.config(state="normal")
        self._status_lbl.config(text=f"Error: {msg}", fg=common.ERR)

    def _open_folder(self, _event=None):
        if self._output_dir:
            try:
                subprocess.Popen(["explorer", str(self._output_dir)])
            except OSError:
                pass
