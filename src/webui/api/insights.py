"""Insights route — channel conversion + application cadence (B6 beta buildout).

A single READ-only endpoint over the tracker tables. The heavy lifting lives in
the top-level :mod:`insights` module (which reuses ``tracker.analytics`` for the
funnel math); this is a thin HTTP shell that opens the active project DB and
returns the three views the Insights tab renders.

    GET /api/insights  -> {ok, funnel, by_source, cadence}   (read-only, no gate)

No mutation, no origin gate (read-only), no user data leaves the machine.
"""
from __future__ import annotations

from flask import Blueprint, jsonify

import insights as core

insights_bp = Blueprint("webui_insights", __name__)


@insights_bp.get("/insights")
def get_insights():
    """The whole Insights payload in one call: the funnel counts+rates, the
    per-source conversion table (sources with >=1 applied), and the 8-week
    cadence. Computed over the ACTIVE project's tracker DB. Read-only."""
    data = core.compute()
    return jsonify({"ok": True, **data})
