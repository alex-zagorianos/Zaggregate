"""Tk-free core for the Search tab: the pure source-health classifier helpers.

These were already ``@staticmethod`` (Tk-free, unit-tested without a root) on
``ui.tab_search.SearchTab``; the S36 web migration MOVES them here so the web
Search job can import the SAME classification logic without importing tkinter,
and ``SearchTab`` RE-EXPORTS them (so existing patch targets / call sites and the
tk tab keep working byte-for-byte).

Nothing here imports tkinter. The web ``search.search_job`` and the tk
``SearchTab._render_progress`` both build the per-source health rows the same way
and format them through :func:`health_summary_line` / :func:`health_details_text`,
so the tk tab and the web API report source health identically.
"""
from __future__ import annotations


def class_is_keyless_skipped(class_name: str, skipped_keyless: list[str]) -> bool:
    """True when ``class_name`` (a progress event's source, e.g. 'JoobleClient')
    names one of the sources build_clients reported as keyless-skipped this run
    (e.g. 'jooble'). Matches by case-insensitive prefix — every client class is
    named '<SourceKey>Client' (AdzunaClient, CareerOneStopClient, JoobleClient, …)
    — so this never needs a hardcoded name table and tracks whatever build_clients'
    own skip logic actually reported."""
    low = (class_name or "").lower()
    return any(low.startswith((s or "").lower()) for s in (skipped_keyless or []))


def progress_line(src: str, done: int, total: int, count: int,
                  skipped_keyless: bool) -> str:
    """The per-source progress status text. A source build_clients flagged as
    self-skipped (no key) says so explicitly instead of a bare '(0)', which
    otherwise looks identical to a source that ran and legitimately found nothing
    today."""
    if skipped_keyless:
        return (f"source {done}/{total} — {src}: skipped — needs a free key "
                f"(Settings → Source keys)")
    return f"source {done}/{total} — {src} ({count})"


def source_status(row: dict) -> str:
    """Classify one per-source health row into a single status token —
    ``ok`` | ``keyless`` | ``throttled`` | ``failed``.

    Precedence is byte-for-byte the tk ``SearchTab._health_summary_line`` counter,
    so the web health list and the tk summary label always agree:

    1. an explicit ``skipped_keyless`` flag -> ``keyless`` (from build_clients'
       own skip data — finding #1/#19);
    2. else ``ok`` AND ``count >= 0`` -> ``ok`` (a source that produced rows counts
       ok even if some keyword errored — matches tk's early ``continue``);
    3. else the error-string heuristic: 429/throttle/rate -> ``throttled``;
       key/auth/401/403 -> ``keyless``; anything else -> ``failed``.

    ``keyless`` is the web token for what the tk summary labels "skipped (no key)".
    """
    if row.get("skipped_keyless"):
        return "keyless"
    if row.get("ok") and (row.get("count", 0) or 0) >= 0:
        return "ok"
    err = (row.get("error") or "").lower()
    if "429" in err or "throttl" in err or "rate" in err:
        return "throttled"
    if "key" in err or "auth" in err or "401" in err or "403" in err:
        return "keyless"
    return "failed"


def health_summary_line(rows: list[dict]) -> str:
    """One-line end-of-run source health: 'Sources: N ok, M skipped (no key), K
    throttled  (details)'. Counts each row via :func:`source_status` so the tk
    summary label and the web summary agree. Empty string for no rows."""
    if not rows:
        return ""
    ok = throttled = skipped = failed = 0
    for r in rows:
        st = source_status(r)
        if st == "ok":
            ok += 1
        elif st == "keyless":
            skipped += 1
        elif st == "throttled":
            throttled += 1
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


def health_details_text(rows: list[dict]) -> str:
    """Per-source Details popup body. A row flagged skipped_keyless names the real
    reason instead of a bare result count."""
    lines = []
    for r in sorted(rows, key=lambda x: (x.get("source") or "").lower()):
        if r.get("skipped_keyless"):
            lines.append(f"{r['source']}: skipped — needs a free key")
        elif r.get("ok"):
            lines.append(f"{r['source']}: {r.get('count', 0)} result(s)")
        else:
            lines.append(f"{r['source']}: FAILED — {r.get('error') or 'unknown'}")
    return "\n".join(lines)
