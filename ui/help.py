"""In-app help: a scrollable Guide tab plus Help-menu dialogs (Quick Start,
What do the tabs do?, About) and an Open-data-folder action. Plain English,
written for someone who has never used a job-search tool before."""
import subprocess
import sys
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import config
from ui import theme
# The static Guide content + Tk-free backup/restore now live in ui.help_core so
# the web Guide page + backup-download/restore-upload flow can reuse them without
# importing tkinter (S36 *_core split). Re-exported here so every caller/test that
# reaches ``help.GUIDE`` / ``help.make_backup`` / ``help.restore_backup`` /
# ``help.auto_backup`` keeps working byte-for-byte.
from ui.help_core import (  # noqa: F401  (re-exported public surface)
    GUIDE, guide_sections, make_backup, restore_backup, safe_extract_zip,
    UnsafeZipEntry, BACKUP_DIR_NAME, backups_dir, auto_backup, _prune_backups,
    APP_NAME,
)



def _open_path(path: Path) -> None:
    """Open a folder in the OS file browser (Windows/macOS/Linux)."""
    try:
        if sys.platform.startswith("win"):
            subprocess.Popen(["explorer", str(path)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception:
        webbrowser.open(path.as_uri())


def open_data_folder() -> None:
    """Reveal the user's data folder (preferences, resume, database live here)."""
    folder = Path(config.USER_DATA_DIR)
    folder.mkdir(parents=True, exist_ok=True)
    _open_path(folder)



def _providers_configured() -> dict:
    """A redacted snapshot of which API keys/credentials are set — NAMES and a
    set/unset flag ONLY, never a value. So a bug report shows "anthropic key: set,
    adzuna: unset" without ever leaking the secret itself."""
    snapshot = {}
    try:
        from ui import settings as ui_settings
        for provider in sorted(ui_settings._KEY_FILES):
            try:
                snapshot[provider] = "set" if ui_settings.has_api_key(provider) else "unset"
            except Exception:
                snapshot[provider] = "unknown"
    except Exception:
        pass
    return snapshot


def _report_meta() -> dict:
    """The redaction-safe metadata blob for a problem report: version, platform,
    timestamp, a sync-folder warning if any, and which providers have keys set
    (values redacted). No secret values, resume text, or personal data."""
    import platform
    from datetime import datetime as _dt
    meta = {
        "app_version": config.APP_VERSION,
        "generated": _dt.now().isoformat(timespec="seconds"),
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "providers_configured": _providers_configured(),
    }
    try:
        import userdata
        warn = userdata.sync_folder_warning()
        if warn:
            meta["sync_folder_warning"] = warn
    except Exception:
        pass
    # A quick registry of known projects so support knows which last_run.json's to
    # look at. Names only — no config contents.
    try:
        import workspace
        meta["projects"] = [p.get("slug") for p in workspace.list_projects()]
    except Exception:
        pass
    return meta


def build_report_zip(dest_dir=None) -> str:
    """Assemble a timestamped diagnostic zip for "Report a problem" and return its
    path. ALLOWLIST by construction — it copies ONLY non-secret diagnostics:

      * report_meta.json  (version, platform, redacted provider flags, sync warn)
      * logs/             (the rotating app.log family)
      * last_run.json     (per project: root + each project dir)

    It deliberately never touches secrets/, experience.md, preferences, or the
    tracker DB, so a friend can send it without leaking their API keys or resume.
    Written to ``dest_dir`` (default: the data folder), so the caller can reveal
    the containing folder."""
    import json as _json
    import shutil
    import tempfile
    from datetime import datetime as _dt

    src = Path(config.USER_DATA_DIR)
    stamp = _dt.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(dest_dir) if dest_dir else src
    out_dir.mkdir(parents=True, exist_ok=True)
    base = out_dir / f"jobscout-report-{stamp}"

    with tempfile.TemporaryDirectory() as staging:
        stage = Path(staging) / "report"
        stage.mkdir(parents=True, exist_ok=True)
        # 1. redaction-safe metadata
        (stage / "report_meta.json").write_text(
            _json.dumps(_report_meta(), indent=2), encoding="utf-8")
        # 2. logs/ (rotating app.log family) — support's primary evidence.
        # CONTENT-SCRUBBED on copy: the live logger already redacts, but lines
        # written before the redaction filter existed (or by older versions)
        # may carry URL-borne credentials — never ship them verbatim.
        from applog import redact as _redact

        def _copy_scrubbed(fsrc: Path, fdst: Path):
            try:
                fdst.write_text(
                    _redact(fsrc.read_text(encoding="utf-8", errors="replace")),
                    encoding="utf-8")
            except OSError:
                pass

        logs_src = src / config.LOG_DIR_NAME
        if logs_src.is_dir():
            (stage / "logs").mkdir(parents=True, exist_ok=True)
            for f in sorted(logs_src.iterdir()):
                if f.is_file():
                    _copy_scrubbed(f, stage / "logs" / f.name)
        # 3. every last_run.json (root + per project). Machine-readable run summary
        # (scrubbed on copy, same rationale) — added by daily_run.
        seen = set()
        candidates = [src]
        try:
            import workspace
            for p in workspace.list_projects():
                try:
                    candidates.append(Path(workspace.project_dir(p.get("slug"))))
                except Exception:
                    pass
        except Exception:
            pass
        for i, proj_dir in enumerate(candidates):
            lr = Path(proj_dir) / "last_run.json"
            if lr.is_file() and lr.resolve() not in seen:
                seen.add(lr.resolve())
                # Flatten to a unique name so multiple projects don't collide.
                name = "last_run.json" if i == 0 else f"last_run.{i}.json"
                _copy_scrubbed(lr, stage / name)
        out = shutil.make_archive(str(base), "zip", root_dir=str(stage))
    return out


def report_problem(parent=None) -> None:
    """Help -> "Report a problem...": build a redaction-safe diagnostic zip
    (logs + version + last-run status, NO keys/resume) and open the folder so the
    user can attach it to a message. The menu wiring for this lives in gui.py; if
    the other builder hasn't added the Help item yet, this function is ready to
    call (recorded as a deviation for the orchestrator)."""
    try:
        out = build_report_zip()
    except Exception as e:
        messagebox.showerror("Report a problem", f"Could not build the report:\n{e}",
                             parent=parent)
        return
    messagebox.showinfo(
        "Report a problem",
        "A diagnostic report was saved to:\n" + out + "\n\n"
        "It contains app logs, your version, and the last-run summary — but NOT "
        "your API keys, resume, or job data. Attach it to your message so the "
        "problem can be diagnosed.",
        parent=parent)
    _open_path(Path(out).parent)



def backup_data(parent=None) -> None:
    """Pick a destination and snapshot the data folder — so 'local-first' isn't
    'lose-everything-if-the-laptop-dies'."""
    dest = filedialog.asksaveasfilename(
        parent=parent, title="Back up my data", defaultextension=".zip",
        initialfile="jobscout-backup.zip", filetypes=[("Zip archive", "*.zip")])
    if not dest:
        return
    try:
        out = make_backup(dest)
        messagebox.showinfo(
            "Backup complete",
            f"Your data was backed up to:\n{out}\n\nNote: this archive includes any "
            "saved API key — don't share it.", parent=parent)
    except Exception as e:
        messagebox.showerror("Backup failed", str(e), parent=parent)


def restore_data(parent=None) -> None:
    """Restore the data folder from a backup zip (overwrites current data)."""
    path = filedialog.askopenfilename(
        parent=parent, title="Restore from backup",
        filetypes=[("Zip archive", "*.zip"), ("All files", "*.*")])
    if not path:
        return
    if not messagebox.askyesno(
            "Restore from backup",
            "This overwrites your current data (preferences, tracker, settings) "
            "with the backup. Continue?", parent=parent):
        return
    try:
        restore_backup(path)
        messagebox.showinfo("Restore complete",
                            "Your data was restored. Please restart Zaggregate.",
                            parent=parent)
    except Exception as e:
        messagebox.showerror("Restore failed", str(e), parent=parent)


def show_quick_start(parent=None) -> None:
    """A short, friendly three-step popup."""
    messagebox.showinfo(
        "Quick Start",
        "Getting started takes three steps:\n\n"
        "1.  FIND JOBS\n"
        "     Open your Inbox and click “Update my Inbox now”, or\n"
        "     use the Search tab to search on demand.\n"
        "     Every job is scored 0–100 for how well it fits you.\n\n"
        "2.  KEEP THE GOOD ONES\n"
        "     Select a job and click “Track ▸ Interested”.\n"
        "     It moves to your Apply Queue. Dismiss the rest.\n\n"
        "3.  APPLY\n"
        "     In Apply Queue, make a tailored resume, open the\n"
        "     posting, submit, then “Mark Applied ▸ Next”.\n\n"
        "Open the Guide tab any time for the full walkthrough.",
        parent=parent)


def show_tabs_help(parent=None) -> None:
    """Explain each tab in one popup."""
    messagebox.showinfo(
        "What do the tabs do?",
        "Inbox — your daily shortlist of fresh matches to triage.\n\n"
        "Search — search many job boards at once for keywords + location.\n\n"
        "Apply Queue — jobs you liked; make documents and mark applied.\n\n"
        "Job Tracker — every tracked job and its status, with follow-ups.\n\n"
        "Resume Generator — paste any posting to tailor a resume + cover letter.\n\n"
        "Guide — the full, plain-English walkthrough.",
        parent=parent)


def show_ai_help(parent=None) -> None:
    """A focused popup on using AI well — the app's core workflow."""
    messagebox.showinfo(
        "Getting the most from AI",
        "This app works best WITH an AI assistant.\n\n"
        "RANK YOUR JOBS  (free — no key needed)\n"
        "   1. Click “Ask AI to rank these” — copies a prompt.\n"
        "   2. Paste it into any AI chat (Claude, ChatGPT, …).\n"
        "   3. Copy the reply, then click “Paste AI ranking”.\n"
        "   4. Sort by Fit and work down from the top.\n\n"
        "GET BETTER RANKINGS\n"
        "   • In Setup, fill the “Anything else?” box with what you\n"
        "     love, what to avoid, and your deal-breakers.\n"
        "   • Be specific, keep your resume current, and re-rank if\n"
        "     a result feels off — the AI mirrors what you tell it.\n\n"
        "WRITE APPLICATIONS\n"
        "   • The Apply Queue & Resume Generator use AI to tailor a\n"
        "     resume + cover letter to each posting (this needs an\n"
        "     API key — add it in Tools ▸ Connect your AI). Always\n"
        "     review before you send — you stay in control.\n\n"
        "Ranking your jobs is free and needs no key.\n\n"
        "Open the Guide tab for the full walkthrough.",
        parent=parent)


def show_privacy(parent=None) -> None:
    """Make the local-first promise concrete: exactly what does and doesn't leave
    this computer. The strongest differentiator, shown not just asserted."""
    messagebox.showinfo(
        "Privacy — what leaves this computer",
        "Zaggregate runs on your machine. The only things ever sent out are:\n\n"
        "JOB SEARCHES\n"
        "   When you Search (or the daily update runs), Zaggregate queries public\n"
        "   job boards and company career pages — Greenhouse, Lever, Ashby,\n"
        "   Workday, Adzuna, USAJobs, The Muse, RemoteOK, Hacker News and the\n"
        "   like. It sends only your search KEYWORDS and LOCATION to look up\n"
        "   matching public postings. Never your resume, profile, or tracker.\n\n"
        "AI RANKING  (only if you use it)\n"
        "   “Ask AI to rank these” copies a prompt to YOUR clipboard. Nothing is\n"
        "   sent until YOU paste it into the AI chat you chose. If you add an\n"
        "   optional API key, the job text + a profile summary go to YOUR key's\n"
        "   provider — and nowhere else.\n\n"
        "CHECKING LINKS\n"
        "   “Clean dead links” visits each job's URL to see if it still exists.\n\n"
        "WHAT NEVER LEAVES\n"
        "   Your resume, experience, preferences, scores, notes, and application\n"
        "   tracker stay in your local data folder. No account, no cloud, no\n"
        "   analytics or telemetry. Zaggregate never applies for you.",
        parent=parent)


def show_about(parent=None) -> None:
    messagebox.showinfo(
        "About " + APP_NAME,
        f"{APP_NAME}\n"
        f"Version {config.APP_VERSION}\n\n"
        "A private, on-your-computer job-search assistant: it finds and scores "
        "jobs in your field, helps you tailor a resume, and tracks your "
        "applications.\n\n"
        "It never applies for you and never uploads your data — everything "
        "stays on this machine.",
        parent=parent)


class GuideTab(ttk.Frame):
    """A scrollable, read-only in-app guide rendered from GUIDE."""

    def __init__(self, parent, app=None):
        super().__init__(parent)
        self._app = app
        self._build()

    def _build(self):
        theme.header_bar(
            self, "Guide",
            "Everything you need to use this app — no tech skills required.")

        wrap = ttk.Frame(self)
        wrap.pack(fill="both", expand=True)
        txt = tk.Text(wrap, wrap="word", bg=theme.SURFACE, fg=theme.INK,
                      relief="flat", padx=24, pady=18, font=theme.FONT,
                      cursor="arrow", borderwidth=0, highlightthickness=0)
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=vsb.set)
        txt.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        # Editorial hierarchy on the 8px rhythm: serif h1 (the "document, not a
        # settings panel" signal), sans accent h2, comfortable body line spacing.
        # All from theme tokens so a font swap flows through automatically.
        txt.tag_configure("h1", font=theme.FONT_GUIDE_H1,
                          foreground=theme.INK, spacing1=24, spacing3=8)
        txt.tag_configure("h2", font=theme.FONT_GUIDE_H2,
                          foreground=theme.ACCENT, spacing1=16, spacing3=4)
        txt.tag_configure("body", font=theme.FONT, foreground=theme.INK,
                          spacing2=3, spacing3=8, lmargin1=2, lmargin2=2)
        txt.tag_configure("bullet", font=theme.FONT, foreground=theme.INK,
                          spacing2=2, spacing3=4, lmargin1=18, lmargin2=34)
        txt.tag_configure("muted", font=theme.FONT_SM, foreground=theme.MUTED,
                          spacing1=16, spacing3=4)

        for tag, text in GUIDE:
            txt.insert("end", text + "\n", tag)
        txt.configure(state="disabled")
        self._text = txt
