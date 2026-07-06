"""Settings routes: theme (Phase 0b) + job-source API keys (Phase 1).

Theme is persisted via ``ui.settings.set_theme`` — a zero-Tk module that writes
``ui_settings.json`` under the user data dir, reused verbatim by the web layer.
The PUT is origin-gated (it mutates persisted state) and validates the mode
against the known set; anything other than ``light``/``dark`` is a 400.

Source keys re-host the Tk-free core (``ui.source_keys_core``: the SOURCES
catalog, the live probe, the Adzuna paste-splitter) + ``ui.settings`` get/set:

* ``GET  /api/settings/keys``                -> masked status (NEVER raw values)
* ``PUT  /api/settings/keys/<source>``       -> persist fields (shape warnings,
                                                 non-blocking) [origin-gated]
* ``POST /api/settings/keys/<source>/test``  -> live probe (no-op under pytest)
                                                 [origin-gated]
* ``POST /api/settings/keys/adzuna/split``   -> split a clipboard blob into
                                                 app_id/app_key [origin-gated]

Security: the GET returns last-4 only for a set field and never echoes a stored
value; the raw secret never leaves ``config.SECRETS_DIR``. Writes go through
``ui.settings.set_api_key`` (the same secrets/ mechanism the tk dialog uses), and
a blank value clears the field (delegated to set_api_key's clear-on-blank path).
"""
from __future__ import annotations

from flask import Blueprint, request, jsonify

from ui import settings as ui_settings
from ui import source_keys_core
from ..security import require_local_origin

settings_bp = Blueprint("webui_settings", __name__)

_VALID_THEMES = ("light", "dark")

# source_key -> source metadata dict, for O(1) lookup on the per-source routes.
_SOURCES_BY_KEY = {s["key"]: s for s in source_keys_core.SOURCES}


@settings_bp.get("/settings/theme")
def get_theme():
    return jsonify({"ok": True, "mode": ui_settings.get_theme()})


@settings_bp.put("/settings/theme")
@require_local_origin
def put_theme():
    data = request.get_json(force=True, silent=True) or {}
    mode = data.get("mode")
    if mode not in _VALID_THEMES:
        return jsonify({"ok": False, "error": "invalid theme"}), 400
    ui_settings.set_theme(mode)
    return jsonify({"ok": True, "mode": ui_settings.get_theme()})


# ── High-fit notification toggle ──────────────────────────────────────────────
# Same zero-Tk persistence as theme (ui.settings, ui_settings.json). Opt-in,
# default False; the daily run reads this via ui_settings.get_notify_high_fit()
# to decide whether to raise a Windows balloon/toast (notify_win.py) for new
# high-fit matches.

@settings_bp.get("/settings/notify")
def get_notify():
    return jsonify({"ok": True, "notify_high_fit": ui_settings.get_notify_high_fit()})


@settings_bp.put("/settings/notify")
@require_local_origin
def put_notify():
    data = request.get_json(force=True, silent=True) or {}
    if "notify_high_fit" not in data:
        return jsonify({"ok": False, "error": "missing notify_high_fit"}), 400
    value = data.get("notify_high_fit")
    if not isinstance(value, bool):
        return jsonify({"ok": False, "error": "notify_high_fit must be a boolean"}), 400
    ui_settings.set_notify_high_fit(value)
    return jsonify({"ok": True, "notify_high_fit": ui_settings.get_notify_high_fit()})


# ── Job-source API keys ───────────────────────────────────────────────────────

def _mask(value: str) -> str | None:
    """A last-4-only mask for a SET credential, e.g. ``••••1234``. Returns None
    for an unset/blank value (so the client shows an empty field, not a mask). A
    short secret (<4 chars) is fully dotted so we never leak the whole thing."""
    v = (value or "").strip()
    if not v:
        return None
    tail = v[-4:] if len(v) >= 4 else ""
    return "••••" + tail


def _field_status(secret_name: str, label: str) -> dict:
    """Serialize one credential field to its SAFE public shape: name, label,
    whether it is set, and a last-4 mask (never the raw value)."""
    raw = ui_settings.get_api_key(secret_name)
    is_set = bool(raw)
    return {
        "name": secret_name,
        "label": label,
        "set": is_set,
        "masked": _mask(raw) if is_set else None,
    }


@settings_bp.get("/settings/keys")
def keys_list():
    """Masked status of every keyed source. NEVER returns a raw credential — only
    a set/unset flag and a last-4 mask, plus the metadata the web form needs
    (label, per-field labels, get-a-free-key URL, impact line)."""
    sources = []
    for src in source_keys_core.SOURCES:
        sources.append({
            "id": src["key"],
            "label": src["title"],
            "fields": [_field_status(name, label) for name, label in src["fields"]],
            "get_key_url": src["url"],
            "impact": src.get("impact", ""),
        })
    return jsonify({"ok": True, "sources": sources})


@settings_bp.put("/settings/keys/<source>")
@require_local_origin
def keys_put(source: str):
    """Persist one or more credential fields for a source. Body: ``{field: value}``
    for fields belonging to this source (unknown fields are ignored). Shape
    warnings from ``looks_like_key`` are RETURNED, never blocking — a value that
    fails the offline sanity check is still saved (inclusion over precision; the
    live Test button is the real validator)."""
    src = _SOURCES_BY_KEY.get(source)
    if src is None:
        return jsonify({"ok": False, "error": "unknown source"}), 404
    data = request.get_json(force=True, silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"ok": False, "error": "expected a JSON object body"}), 400

    valid_fields = {name for name, _ in src["fields"]}
    saved: list[str] = []
    warnings: list[dict] = []
    for name, value in data.items():
        if name not in valid_fields:
            continue  # ignore stray keys rather than erroring
        value = "" if value is None else str(value)
        if ui_settings.set_api_key(name, value):
            saved.append(name)
        # Non-blocking shape warning (only for a non-empty value being set).
        if value.strip() and not ui_settings.looks_like_key(name, value):
            warnings.append({"field": name, "warning": "value looks unusually short"})

    return jsonify({"ok": True, "saved": saved, "warnings": warnings})


@settings_bp.post("/settings/keys/<source>/test")
@require_local_origin
def keys_test(source: str):
    """Run the source's ONE live probe and report a normalized result. Under
    pytest the probe self-skips (``source_keys_core.test_source`` guards on
    PYTEST_CURRENT_TEST) so this returns the no-op shape without any network."""
    if source not in _SOURCES_BY_KEY:
        return jsonify({"ok": False, "error": "unknown source"}), 404
    ok, detail = source_keys_core.test_source(source)
    return jsonify({
        "ok": True,
        "result": {"status": "ok" if ok else "failed", "detail": detail},
    })


@settings_bp.post("/settings/keys/adzuna/split")
@require_local_origin
def keys_adzuna_split():
    """Split a pasted clipboard blob into Adzuna's app_id / app_key by SHAPE
    (8-hex id, 32-hex key), reusing the unit-tested core splitter. Returns
    ``{ok:false}`` when neither shape is present so the client can nudge the user
    to paste the values manually."""
    data = request.get_json(force=True, silent=True) or {}
    clipboard = data.get("clipboard", "")
    if not isinstance(clipboard, str):
        clipboard = str(clipboard or "")
    app_id, app_key = source_keys_core.split_adzuna_paste(clipboard)
    if not (app_id or app_key):
        return jsonify({
            "ok": False,
            "error": "no Adzuna App ID / App Key found in the pasted text",
        })
    return jsonify({"ok": True, "app_id": app_id, "app_key": app_key})
