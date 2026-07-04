"""Shared GUI infrastructure used by multiple gui.py tabs/dialogs: status-label
helpers, DB-error guarding, clipboard helpers, URL scheme sanitizing, the daily-
ingest stdout line sink, and the theme-aware status/palette colors.

Extracted from gui.py (S35 gui-split) so the moved tab/dialog modules have one
authoritative home for this module-level state instead of each importing a
copy. gui.py re-imports and re-exports every name here so existing
`gui.set_status` / `gui.db_guard` / etc. call sites and test patch targets
keep working unchanged.
"""
import io
import re
import sqlite3
from urllib.parse import urlparse
from tkinter import messagebox

import ranker as _ranker_mod
from claude_bridge import to_clipboard
from ui import theme

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def safe_url(url):
    """Return url unchanged only when its scheme is http or https.
    Rejects javascript:, data:, file:, and any other scheme.
    Returns '' so callers can test: if u := safe_url(raw): webbrowser.open(u)"""
    if not url:
        return ""
    try:
        return url if urlparse(url).scheme in ("http", "https") else ""
    except ValueError:
        return ""


def _call_prompt_via_api(prompt):
    """Send a pre-built prompt to the Anthropic API and return the raw text reply.
    Uses the key from ranker.api_key() and config.ANTHROPIC_MODEL. Raises
    RuntimeError when no key is configured; re-raises any API error."""
    import config as _cfg
    key = _ranker_mod.api_key()
    if not key:
        raise RuntimeError(
            "No Anthropic API key -- set ANTHROPIC_API_KEY or save one in "
            "Tools > Connect your AI.")
    import anthropic
    client = anthropic.Anthropic(api_key=key, base_url=_cfg.anthropic_base_url())
    msg = client.messages.create(
        model=_cfg.ANTHROPIC_MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(
        getattr(b, "text", "") for b in msg.content
        if getattr(b, "type", None) == "text"
    )


def _scored_status(applied, asked, missed) -> str:
    """Status line for a fit-scoring round, surfacing partial coverage:
    'Scored 17/20 - 3 not scored' (bridge partial-coverage, C2 P4). No missed
    -> 'Scored 20/20.'"""
    n_missed = len(missed) if missed else 0
    if n_missed:
        return f"Scored {applied}/{asked} - {n_missed} not scored"
    return f"Scored {applied}/{asked}."


class _LineSink(io.TextIOBase):
    """A minimal text stream that forwards whole lines to a callback. Used to
    capture the daily-ingest pipeline's print() output (per-source counts, a
    429'd source, an expired key) so the GUI can render live progress instead of
    discarding it — daily_run narrates via print(), not a passed-in log sink."""

    def __init__(self, on_line):
        self._on_line = on_line
        self._buf = ""

    def write(self, s):
        if not s:
            return 0
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            try:
                self._on_line(line)
            except Exception:
                pass
        return len(s)

    def flush(self):
        if self._buf:
            try:
                self._on_line(self._buf)
            except Exception:
                pass
            self._buf = ""


# ── Palette ── all sourced from ui.theme (clean light/modern) so the whole app
# shares one set of colors. Legacy names kept so existing call sites still read.
DARK  = theme.INK       # dark ink (was the dark header navy)
MID   = theme.MUTED
BG    = theme.WINDOW    # app/background fills
WHITE = theme.SURFACE   # cards / white surfaces
ERR   = theme.DANGER

# Named status colors for set_status(label, text, kind).
OK    = theme.SUCCESS   # success / done (green)
WORK  = theme.WARN      # in-progress (amber)
INFO  = theme.ACCENT    # neutral notice (accent)
MUTED = theme.MUTED     # de-emphasized (grey)

_STATUS_COLORS = {
    "ok": OK, "work": WORK, "info": INFO, "muted": MUTED, "err": ERR,
}


def _sync_palette_aliases():
    """Re-point the legacy module-level color aliases at the *active* theme
    palette. The aliases above are captured at import; after a light/dark switch
    (theme.set_mode) this refreshes them so widgets rebuilt next use new colors."""
    global DARK, MID, BG, WHITE, ERR, OK, WORK, INFO, MUTED, _STATUS_COLORS
    DARK, MID, BG = theme.INK, theme.MUTED, theme.WINDOW
    WHITE, ERR = theme.SURFACE, theme.DANGER
    OK, WORK, INFO, MUTED = theme.SUCCESS, theme.WARN, theme.ACCENT, theme.MUTED
    _STATUS_COLORS = {"ok": OK, "work": WORK, "info": INFO, "muted": MUTED,
                      "err": ERR}


def set_status(label, text, kind="muted"):
    """Set a tk.Label's text and color by semantic kind (ok/work/info/muted/err)
    instead of repeating inline hex at each call site."""
    label.config(text=text, fg=_STATUS_COLORS.get(kind, MUTED))

# Job-Tracker status badge colors are theme-aware (light/dark) via theme.STATUS_BADGE;
# tabs are rebuilt on a theme switch so the tree re-reads the active set.


def db_guard(parent, op, *, status_cb=None, action="operation"):
    """Run a DB-mutating op, converting an sqlite3.Error (e.g. the daily run is
    mid-write) into visible feedback instead of a silent crash. Returns
    (ok, result): result is the op's return value on success, else None."""
    try:
        return True, op()
    except sqlite3.Error as e:
        msg = f"Database busy — {action} failed. Try again. ({e})"
        if status_cb:
            status_cb(msg)
        else:
            messagebox.showerror("Database error", msg, parent=parent)
        return False, None


def copy_or_warn(parent, text: str, status_cb=None) -> bool:
    """Clipboard copy with a visible failure path; returns success."""
    if to_clipboard(text):
        if status_cb:
            status_cb("Prompt copied — paste it into claude.ai, then paste "
                      "the reply back here.")
        return True
    messagebox.showerror("Clipboard", "Could not copy to clipboard.",
                         parent=parent)
    return False
