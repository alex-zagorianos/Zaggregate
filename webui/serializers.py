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


def app_row(row: dict) -> dict:
    """Serialize a tracked-application row (``tracker.db.get_all`` / ``get_job``)
    to a JSON-safe dict. Applications have no ``extras`` column, so this is a pure
    JSON-safety pass over the known engine columns."""
    if not isinstance(row, dict):
        return {}
    return {str(key): _json_safe(value) for key, value in row.items()}
