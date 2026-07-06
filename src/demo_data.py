"""Bundled sample inbox loader (plan §6.1 — time-to-first-value).

A brand-new user's very first Inbox screen — before any source is connected —
shows ~20 realistic, pre-scored DEMO rows so the aha (a scored, location-clean
inbox that shows the Score-vs-Fit split) lands in seconds. The rows live in
``data_templates/demo_inbox.json``; this module is the pure, headless-testable
loader that normalizes them into the same row-dict shape the Inbox renders
(``inbox_all()`` rows), plus the tiny bit of state that decides whether the demo
should still be shown.

Read-only by construction: demo rows carry ``is_demo=True`` and negative ids,
never touch the tracker DB, and are hidden the instant a real inbox exists or the
user runs their first real update. A one-line marker file records that the demo
has been retired so it never reappears once the real inbox has been seen.
"""
from __future__ import annotations

import json
from pathlib import Path

# A synthetic source label every demo row carries, so the UI can badge them and
# so they can never be confused with a real source in the Source filter.
DEMO_SOURCE = "Demo"

# Marker (in the user data dir) written the first time a real inbox is present or
# a real update runs — after which the demo never shows again.
_RETIRED_MARKER = ".demo_inbox_retired"


def _data_file() -> Path:
    """The bundled JSON. Resolved relative to this module so it works both from
    source and from the frozen exe (data_templates ships alongside)."""
    return Path(__file__).resolve().parent / "data_templates" / "demo_inbox.json"


def _normalize_row(raw: dict, idx: int) -> dict:
    """Map a JSON demo entry into the row-dict shape the Inbox tree renders. Fills
    every key the renderer/detail-pane reads with a safe default, stamps a
    negative id (so it can never collide with a real inbox row id) and marks it
    ``is_demo`` + ``DEMO_SOURCE``."""
    def _int(v, default=-1):
        try:
            return int(v)
        except (TypeError, ValueError):
            return default

    return {
        # Negative, deterministic id: real inbox ids are positive autoincrement.
        "id": -(idx + 1),
        "is_demo": True,
        "score": _int(raw.get("score"), -1),
        "fit": _int(raw.get("fit"), -1),
        "title": str(raw.get("title") or ""),
        "company": str(raw.get("company") or ""),
        "location": str(raw.get("location") or ""),
        "salary_text": str(raw.get("salary_text") or ""),
        "source": DEMO_SOURCE,
        "date_added": str(raw.get("date_added") or ""),
        "created": str(raw.get("created") or ""),
        "url": str(raw.get("url") or ""),
        "board_count": _int(raw.get("board_count"), -1),
        "description": str(raw.get("description") or ""),
        "fit_why": str(raw.get("fit_why") or ""),
        "score_notes": str(raw.get("score_notes") or ""),
    }


def demo_inbox_rows(path: Path | None = None) -> list[dict]:
    """Return the bundled demo rows, normalized to the Inbox row-dict shape.
    Never raises: a missing/corrupt file yields []. Pure (reads only the bundled
    JSON), so it is unit-testable without a Tk root or a database."""
    p = path or _data_file()
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    rows = raw.get("rows") if isinstance(raw, dict) else None
    if not isinstance(rows, list):
        return []
    return [_normalize_row(r, i) for i, r in enumerate(rows) if isinstance(r, dict)]


def _marker_path(user_data_dir) -> Path:
    return Path(user_data_dir) / _RETIRED_MARKER


def is_demo_retired(user_data_dir) -> bool:
    """True once the demo inbox has been retired (a real inbox was seen / a real
    update ran). Best-effort; False on any error."""
    try:
        return _marker_path(user_data_dir).exists()
    except Exception:
        return False


def retire_demo(user_data_dir) -> None:
    """Permanently retire the demo inbox (idempotent). Best-effort; never raises."""
    try:
        p = _marker_path(user_data_dir)
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            p.write_text("retired\n", encoding="utf-8")
    except OSError:
        pass


def should_show_demo(user_data_dir, real_inbox_count: int) -> bool:
    """Decide whether the demo inbox should render: only when the real inbox is
    empty AND the demo hasn't been retired yet. A non-empty real inbox means the
    user has already reached the real value, so the demo is suppressed (and the
    caller should retire it)."""
    if real_inbox_count > 0:
        return False
    return not is_demo_retired(user_data_dir)
