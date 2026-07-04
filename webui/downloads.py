"""Shared, traversal-safe file-download helpers for the web API (Phase 4).

Every file the web UI hands back to the browser is served through
:func:`send_locked` — a single containment gate that resolves the requested path
against a locked base directory and 404s anything that escapes it (``../``
traversal, an absolute path, a symlink out of the tree). This generalizes the
Phase-3 inbox export/download lock (``webui.api.inbox.export_download``) so the
resume + apply-queue download families don't each hand-roll the check.

Design (binding):

* All resume/queue file handoffs are HTTP downloads under
  ``workspace.output_dir()`` — server code NEVER shells out to explorer (repo
  rule). :func:`output_subtree` resolves a named subtree of the active project's
  output dir (creating it) as the download base.
* The base is resolved absolute; the requested target is resolved absolute; the
  target must be a descendant of the base (``is_relative_to``, with a str-prefix
  fallback for Py<3.9) AND be a real file, or the answer is a flat 404 — never a
  leak, never a distinct "forbidden vs missing" oracle.
* ``output_dir()`` is resolved per-request (never a process-wide pin), so a
  project switch routes downloads to the right project's tree.
"""
from __future__ import annotations

import os
from pathlib import Path

from flask import jsonify, send_file

import workspace


def output_subtree(*parts: str) -> Path:
    """The absolute, existing base directory a download family is locked to:
    ``workspace.output_dir()/<parts...>``. Created if absent, resolved absolute so
    the containment check has a canonical base. Resolved per-call (the active
    project can change between requests)."""
    base = Path(workspace.output_dir())
    for p in parts:
        base = base / p
    base.mkdir(parents=True, exist_ok=True)
    return base.resolve()


def is_contained(base: Path, name: str) -> Path | None:
    """Resolve ``name`` against ``base`` and return the resolved target IFF it is a
    real file living inside ``base``; otherwise None. This is the whole traversal
    defense: ``..`` segments, an absolute ``name``, or a symlink escaping the tree
    all resolve to a path outside ``base`` and fail the containment test."""
    try:
        target = (base / name).resolve()
    except (OSError, ValueError):
        return None
    try:
        inside = target.is_relative_to(base)
    except AttributeError:  # pragma: no cover - Py<3.9
        inside = str(target).startswith(str(base) + os.sep)
    if not inside or not target.is_file():
        return None
    return target


def send_locked(base: Path, name: str):
    """Serve ``base/name`` as a download attachment, LOCKED to ``base``. A path
    that escapes the base (or isn't a real file) is a flat 404 ``{ok:false,
    error:"not found"}`` — never a leak. On success returns a ``send_file``
    attachment response named after the file's basename."""
    target = is_contained(base, name)
    if target is None:
        return jsonify({"ok": False, "error": "not found"}), 404
    return send_file(str(target), as_attachment=True, download_name=target.name)
