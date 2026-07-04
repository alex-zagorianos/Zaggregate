"""Regression: importing ``webui`` must stay GUI-free and must not trigger
``tracker.app``'s import-time ``init_db()``.

The web layer replaces the tk GUI; if it dragged in tkinter/ttkbootstrap it would
fail on a headless server, and importing ``tracker.app`` runs ``init_db()`` at
import time (a documented hazard in the migration plan) — resolving+creating a DB
against whatever project is active, from a mere import. We assert neither happens,
in a FRESH interpreter (a subprocess) so another test that already imported these
modules can't mask the leak.
"""
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]

_PROBE = r"""
import sys
import webui  # noqa: F401
# Also import the api submodules that a request would pull in, so the check
# covers the full Phase-0b surface, not just the package __init__.
import webui.api, webui.jobs, webui.security, webui.serializers, webui.paths  # noqa
from webui.api import build_api_blueprint
build_api_blueprint()

banned = [m for m in ("tkinter", "ttkbootstrap") if m in sys.modules]
if banned:
    print("GUI_LEAK:" + ",".join(banned))
    sys.exit(2)
if "tracker.app" in sys.modules:
    print("TRACKER_APP_LEAK")
    sys.exit(3)
print("CLEAN")
"""


def test_webui_import_is_gui_free_and_no_tracker_app():
    proc = subprocess.run(
        [sys.executable, "-c", _PROBE],
        cwd=str(_ROOT), capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, (
        f"probe failed ({proc.returncode}): {proc.stdout!r} {proc.stderr!r}")
    assert proc.stdout.strip().endswith("CLEAN"), proc.stdout
