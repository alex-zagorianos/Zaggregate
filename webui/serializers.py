"""Engine row -> JSON dict shaping for the web API.

Engine rows (``tracker.db.inbox_all`` / ``get_all``) are already sqlite ``dict``s
of JSON-friendly scalars, so these serializers are deliberately THIN: their real
jobs are (1) parsing the ``extras`` column from a JSON *string* into a nested
object so the frontend doesn't re-parse, and (2) a defensive JSON-safety pass that
coerces any stray ``bytes``/``Path`` a future column might carry. Inbox and
application rows carry no secrets (credentials live in ``config.SECRETS_DIR``,
never in the DB), so there is nothing to mask here — but we still never echo a key
by construction because we only pass through the known engine columns.
"""
from __future__ import annotations

import json
from pathlib import Path, PurePath


def _json_safe(value):
    """Coerce a single value to something ``json.dumps`` accepts. Scalars and
    already-JSON containers pass through; ``Path``/``bytes`` (which a column could
    theoretically hold) are stringified rather than crashing the response."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (PurePath, Path)):
        return str(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return str(value)


def _parse_extras(raw):
    """Parse the inbox ``extras`` column (a JSON string, or already a dict, or
    empty) into a plain object. Mirrors ``tracker.service._parse_extras`` — a
    malformed blob becomes ``{}`` rather than raising."""
    if not raw:
        return {}
    if isinstance(raw, dict):
        return {str(k): _json_safe(v) for k, v in raw.items()}
    try:
        loaded = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    if not isinstance(loaded, dict):
        return {}
    # Same JSON-safety treatment as the already-dict branch above: a parsed blob
    # can still carry values a future column shape makes non-JSON-safe.
    return {str(k): _json_safe(v) for k, v in loaded.items()}


def inbox_row(row: dict) -> dict:
    """Serialize an inbox row (``tracker.db.inbox_all`` / ``service.top_picks``)
    to a JSON-safe dict. Passes engine columns through unchanged, parses ``extras``
    into a nested object, and preserves the ``rank`` key ``top_picks`` augments
    rows with."""
    if not isinstance(row, dict):
        return {}
    out = {}
    for key, value in row.items():
        if key == "extras":
            out["extras"] = _parse_extras(value)
        else:
            out[str(key)] = _json_safe(value)
    return out


def _ghost_badge(row: dict) -> dict:
    """The list-view ghost/staleness badge: ``{level, reasons}`` off
    :func:`match.ghost.ghost_score` (day-bucketed + cached, so recomputing it for
    every row on every list request is cheap). ``reasons`` is capped to the few
    the tooltip shows. Best-effort — any failure yields a neutral abstain badge so
    the list never breaks over a bad row. NEVER hides a row: this only annotates;
    the opt-in ``hide_stale`` view filter remains the sole hiding mechanism.

    The reasons already carried by ghost_score cover longevity/repost history
    (age from ``created``, evergreen/pipeline titles, publisher-declared expiry,
    and — when a repost_info map is threaded in upstream — S29 repost/evergreen
    coalescing); we surface exactly what fired, we do not compute new signals."""
    try:
        from match import ghost as _ghost
        g = _ghost.ghost_score(row)
    except Exception:  # noqa: BLE001 — a bad row must never break the list payload
        return {"level": "unknown", "reasons": []}
    reasons = g.get("reasons") or []
    return {"level": str(g.get("level") or "unknown"),
            "reasons": [str(r) for r in reasons[:4]]}


def inbox_row_list(row: dict) -> dict:
    """List-context variant of :func:`inbox_row`: identical shape minus
    ``description`` — the inbox/board/queue/top-picks LIST views never render a
    description preview (only the per-row detail route does), so list responses
    drop the column to cut payload size. DETAIL routes must keep using
    :func:`inbox_row`.

    Adds a ``ghost`` badge (``{level, reasons}``) so the Inbox table can flag
    aged / reposted / evergreen postings inline (B7). Only ``level`` in
    {"aging","stale"} draws a visible badge client-side; "fresh"/"unknown" are
    carried but rendered as nothing."""
    out = inbox_row(row)
    out.pop("description", None)
    out["ghost"] = _ghost_badge(row)
    return out


def app_row(row: dict) -> dict:
    """Serialize a tracked-application row (``tracker.db.get_all`` / ``get_job``)
    to a JSON-safe dict. Applications have no ``extras`` column, so this is a pure
    JSON-safety pass over the known engine columns."""
    if not isinstance(row, dict):
        return {}
    return {str(key): _json_safe(value) for key, value in row.items()}


def app_row_list(row: dict) -> dict:
    """List-context variant of :func:`app_row`: identical shape minus
    ``description`` — the Applications/Board/Queue LIST views never render a
    description preview, so list responses drop the column to cut payload size.
    The single-application detail route (``GET /api/applications/<id>``) must keep
    using :func:`app_row`."""
    out = app_row(row)
    out.pop("description", None)
    return out


# ── search JobResult round-trip ───────────────────────────────────────────────
# The Search API returns SCORED ``models.JobResult`` dataclasses to the client and
# later receives rows back to Track / Add-to-Inbox. Rather than a lossy hand-mapped
# dict, we serialize EVERY dataclass field (so the frontend has score, salary
# range, source, notes) plus a couple of computed conveniences, and provide an
# exact inverse (``job_result_from_row``) that reconstructs the dataclass from the
# same dict — the engine seams (``track_search_results`` / ``inbox_add_many``)
# require real ``JobResult`` objects, and a full-field round-trip keeps their input
# byte-for-byte what the tk tab passed (parity). Non-field keys the serializer adds
# for display (``salary``, ``seen``) are ignored on the way back in.

# Dataclass fields we round-trip. Derived from models.JobResult; declared
# explicitly (not via dataclasses.fields at import time) so a stray future field
# can't silently start leaking through the API without a conscious add here.
_JOBRESULT_FIELDS = (
    "title", "company", "location", "salary_min", "salary_max", "description",
    "url", "source_keyword", "created", "job_id", "source_api", "score",
    "score_notes", "board_count", "is_new", "valid_through",
)


def job_result(job, *, seen: bool = False) -> dict:
    """Serialize a scored ``models.JobResult`` to a JSON-safe dict carrying every
    dataclass field (the reconstruction contract) plus display conveniences:
    ``salary`` (the tk ``salary_display()`` string) and ``seen`` (this URL is
    already tracked/dismissed — the tk 'Hide tracked/dismissed' flag, surfaced so
    the client can badge/hide without a second call). ``score`` is passed through
    as-is (-1 = unscored, rendered blank client-side, exactly like the tk tree)."""
    out = {name: _json_safe(getattr(job, name, None)) for name in _JOBRESULT_FIELDS}
    try:
        out["salary"] = job.salary_display()
    except Exception:  # noqa: BLE001 — display-only; never break the response
        out["salary"] = ""
    out["seen"] = bool(seen)
    return out


def job_result_from_row(row: dict):
    """Reconstruct a ``models.JobResult`` from a row produced by :func:`job_result`
    (the exact inverse over the dataclass fields; non-field display keys like
    ``salary``/``seen`` are ignored). Used by the Track / Add-to-Inbox routes so the
    engine seams receive real ``JobResult`` objects identical to what the tk Search
    tab passes them. Missing scalars fall back to the dataclass defaults so a
    partial client row never crashes construction."""
    from models import JobResult
    data = row if isinstance(row, dict) else {}
    return JobResult(
        title=str(data.get("title") or ""),
        company=str(data.get("company") or ""),
        location=str(data.get("location") or ""),
        salary_min=data.get("salary_min"),
        salary_max=data.get("salary_max"),
        description=str(data.get("description") or ""),
        url=str(data.get("url") or ""),
        source_keyword=str(data.get("source_keyword") or ""),
        created=str(data.get("created") or ""),
        job_id=str(data.get("job_id") or ""),
        source_api=str(data.get("source_api") or ""),
        score=int(data["score"]) if _is_intish(data.get("score")) else -1,
        score_notes=str(data.get("score_notes") or ""),
        board_count=int(data["board_count"]) if _is_intish(data.get("board_count")) else -1,
        is_new=bool(data.get("is_new")),
        valid_through=str(data.get("valid_through") or ""),
    )


def _is_intish(value) -> bool:
    """True when ``int(value)`` is safe (a real int/float or a numeric string)."""
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        try:
            int(value)
            return True
        except ValueError:
            return False
    return False
