"""Referral-network routes — LinkedIn/Google contact import + company matching
(B4 beta buildout).

Thin HTTP shell over the top-level :mod:`network` module. The frontend reads the
user's exported CSV client-side (FileReader) and POSTs the raw text here; nothing
about the contacts ever leaves the machine (the store is a local JSON file under
the user data dir — see network.py). Web-only, isolated for one-commit removal.

    POST   /api/network/import  {text, source}  -> {ok, added, total}   [gated]
    GET    /api/network/summary                 -> {ok, total, companies, last_import}
    POST   /api/network/clear                   -> {ok, removed}         [gated]
    GET    /api/network/company/<name>          -> {ok, contacts:[...]}

The warm-path prompt routes live on the inbox/applications blueprints (they need
those rows' job context); this module owns the import + summary + lookup surface.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

import network as core
from ..security import require_local_origin

network_bp = Blueprint("webui_network", __name__)

# A CSV export is small; cap the POST body so a pasted-in giant file can't wedge
# the parser. 5 MB comfortably holds tens of thousands of connections.
_MAX_IMPORT_BYTES = 5 * 1024 * 1024
_SOURCES = ("linkedin", "google")


@network_bp.post("/network/import")
@require_local_origin
def import_contacts():
    """Import a connections CSV (raw text). Body ``{text, source}``; ``source`` is
    'linkedin' (default) or 'google'. Merges into the user-level store (dedup by
    name+company). 400 on a missing/oversized body."""
    data = request.get_json(silent=True) or {}
    text = data.get("text")
    if not isinstance(text, str) or not text.strip():
        return jsonify({"ok": False, "error": "no CSV text provided"}), 400
    if len(text.encode("utf-8")) > _MAX_IMPORT_BYTES:
        return jsonify({"ok": False,
                        "error": "that file is too large (5 MB max)"}), 400
    source = str(data.get("source") or "linkedin").strip().lower()
    if source not in _SOURCES:
        source = "linkedin"
    result = core.import_text(text, source)
    return jsonify({"ok": True, **result})


@network_bp.get("/network/summary")
def network_summary():
    """A compact overview for the Sources card: total contacts, distinct matchable
    companies, and the last import stamp. Read-only, no gate."""
    return jsonify({"ok": True, **core.summary()})


@network_bp.post("/network/clear")
@require_local_origin
def clear_network():
    """Forget the whole imported network. Returns the count removed."""
    return jsonify({"ok": True, "removed": core.clear()})


@network_bp.get("/network/company/<path:name>")
def company_contacts(name: str):
    """Contacts the user knows at a given company (canonical-company matched).
    Read-only; ``<path:name>`` so a company name with a slash still resolves."""
    contacts = core.matches_for(name)
    return jsonify({
        "ok": True,
        "contacts": [{"name": c.get("name", ""),
                      "position": c.get("position", ""),
                      "company": c.get("company", "")}
                     for c in contacts],
    })
