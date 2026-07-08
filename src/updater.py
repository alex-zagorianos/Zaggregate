"""In-app auto-update, backed by Velopack. The ONLY module that imports `velopack`.

Design (brain/plan-2026-07-08-velopack-auto-update.md):

* The app is installed by a Velopack `Setup.exe` into ``%LOCALAPPDATA%/Zaggregate/``,
  whose ``current/`` subfolder (the exe + its PyInstaller ``_internal/``) is replaced
  WHOLESALE on every update. User data therefore lives at ``%LOCALAPPDATA%/JobProgram``
  (``config.USER_DATA_DIR``), outside the swap zone.
* Every step is user-clicked: check -> download -> "restart to finish". Nothing here
  runs on a timer and nothing calls out until the user asks, which is what
  ``PRIVACY.md`` promises. There is no ``set_auto_apply_on_startup``.
* Windows locks a running exe, so we never overwrite ourselves. ``apply_and_restart``
  hands off to Velopack's ``Update.exe``, which waits for THIS pid to exit, swaps
  ``current/``, then relaunches us with the same argv.

Degradation contract — the whole point of this module:

    A dev checkout, a plain unzipped copy, or a build without the `velopack` wheel
    is "not managed". `is_managed()` returns False and every other entry point
    returns a benign, falsy answer. NOTHING here may raise into a Flask route.

`velopack.UpdateManager(...)` raises ``RuntimeError("This application is not properly
installed")`` outside a Velopack install — that is the detector, verified empirically
against velopack 1.2.0. We do not sniff for marker files.
"""
from __future__ import annotations

import os
import threading
import time
from typing import Any

import config

# Velopack's own default Windows channel name. A build packed with `--channel beta`
# reports "beta" here instead; the SDK bakes the channel into the install manifest
# so a beta tester keeps polling the beta feed with no client-side config.
_DEFAULT_CHANNEL = "win"

# `--daily` runs as a separate scheduled process out of the same install. Applying an
# update mid-run would swap the exe under it. daily_run holds this lock while it works.
DAILY_LOCK_NAME = "daily.lock"

# Guarded module state for the async download. A single download at a time; the UI
# polls progress(). Never holds a velopack object across a request boundary except
# the pending UpdateInfo, which apply() needs.
_lock = threading.Lock()
_state: dict[str, Any] = {
    "phase": "idle",      # idle | checking | downloading | ready | error
    "percent": 0,
    "version": None,
    # NOT named "error": the JSON envelope reserves that for "the request failed".
    # A download that dies still rides on ok:true, so its reason is `failure`.
    "failure": None,
}
_pending: Any = None      # velopack.UpdateInfo of a fully-downloaded update
_manager_cache: Any = None
_manager_probed = False


class NotManaged(RuntimeError):
    """This install is not Velopack-managed (dev run, plain zip, missing wheel)."""


def _repo_url() -> str:
    """The GitHub repo Velopack polls. Mirrors config.UPDATE_REPO (env-overridable),
    expressed as the full https URL that GithubSource expects."""
    return f"https://github.com/{config.UPDATE_REPO}"


def is_supported() -> bool:
    """True if the `velopack` wheel is importable at all. False in a source checkout
    that never installed it, or a frozen build that failed to bundle it."""
    try:
        import velopack  # noqa: F401
    except Exception:
        return False
    return True


def _build_manager() -> Any:
    """A velopack.UpdateManager bound to our GitHub releases, or raise NotManaged.

    `prerelease=True` lets a beta-channel install see `vX.Y.Z-betaN` GitHub
    pre-releases. It does NOT put a stable install on beta builds: the channel baked
    into the install manifest still selects which RELEASES-<channel> feed is read.
    """
    try:
        import velopack
    except Exception as e:  # wheel missing / broken native module
        raise NotManaged(f"velopack unavailable: {e}") from e
    try:
        # ZAGGREGATE_UPDATE_FEED points the updater at a static file/HTTP feed
        # instead of GitHub — for a self-hosted fork, an air-gapped mirror, or a
        # local pre-release smoke test (a directory of `vpk pack` output served
        # over HTTP). Absent (the norm) → the public GitHub releases feed.
        feed = os.getenv("ZAGGREGATE_UPDATE_FEED")
        if feed:
            source = velopack.HttpSource(feed)
        else:
            source = velopack.GithubSource(_repo_url(), None, True)
        # UpdateOptions takes 2 REQUIRED positional args (verified against 1.2.0):
        # (AllowVersionDowngrade, MaximumDeltasBeforeFallback[, ExplicitChannel]).
        # Downgrade is allowed so pulling a bad release from GitHub rolls testers
        # back to the previous version on their next check.
        options = velopack.UpdateOptions(True, 10, None)
        return velopack.UpdateManager(source, options)
    except RuntimeError as e:
        # "This application is not properly installed: Could not auto-locate app
        # manifest" — the canonical not-a-Velopack-install signal.
        raise NotManaged(str(e)) from e
    except Exception as e:
        raise NotManaged(f"velopack init failed: {e}") from e


def _manager() -> Any:
    """The cached UpdateManager. Probed once; a not-managed verdict is sticky, so a
    dev run pays the construction cost (and its stderr noise) exactly once."""
    global _manager_cache, _manager_probed
    if not _manager_probed:
        _manager_probed = True
        try:
            _manager_cache = _build_manager()
        except NotManaged:
            _manager_cache = None
    if _manager_cache is None:
        raise NotManaged("not a Velopack-managed install")
    return _manager_cache


def is_managed() -> bool:
    """True iff this process runs from a Velopack install and can self-update."""
    try:
        _manager()
        return True
    except NotManaged:
        return False


def daily_run_active() -> bool:
    """True if a `--daily` scheduled run currently holds the lock.

    A stale lock (the process died without cleaning up) must not wedge updates
    forever, so a lock older than 6h is ignored. Any read error -> False: a missing
    or unreadable lock means "no daily run", not "block the user"."""
    path = config.USER_DATA_DIR / DAILY_LOCK_NAME
    try:
        age = time.time() - path.stat().st_mtime
    except OSError:
        return False
    return age < 6 * 60 * 60


def status() -> dict:
    """A cheap, never-raising snapshot for the UI.

    ``managed`` False means the caller should fall back to the link-out-to-GitHub
    behaviour that shipped in v1.0.2."""
    if not is_managed():
        return {"managed": False, "supported": is_supported(),
                "current": config.APP_VERSION, "channel": None, "phase": "idle"}
    mgr = _manager()
    try:
        current = mgr.get_current_version()
    except Exception:
        current = config.APP_VERSION
    with _lock:
        snapshot = dict(_state)
    return {"managed": True, "supported": True, "current": current,
            "channel": _installed_channel(), "pending_restart": pending_restart(),
            **{k: snapshot[k] for k in ("phase", "percent", "version", "failure")}}


def _installed_channel() -> str:
    """The update feed this install polls. Velopack has no public getter for it, so we
    report the default unless a packed override is present in the environment (used by
    tests and by a tester temporarily switching feeds)."""
    return os.getenv("ZAGGREGATE_CHANNEL", _DEFAULT_CHANNEL)


def pending_restart() -> bool:
    """True if an update is already downloaded and waiting for a restart, including
    from a PREVIOUS run of the app (Velopack persists this on disk)."""
    try:
        return _manager().get_update_pending_restart() is not None
    except Exception:
        return False


def check() -> dict:
    """User-clicked "is there an update?".

    Returns ``{managed, newer, latest, current}``. ``newer`` False and ``latest``
    None both mean "nothing to do" — a network failure is NOT an error envelope,
    matching the graceful contract of the v1.0.2 update-check route."""
    if not is_managed():
        return {"managed": False, "newer": False, "latest": None,
                "current": config.APP_VERSION}
    try:
        info = _manager().check_for_updates()
    except Exception as e:
        with _lock:
            _state["failure"] = f"{type(e).__name__}: {e}"
        return {"managed": True, "newer": False, "latest": None,
                "current": config.APP_VERSION, "failure": "check-failed"}
    if info is None:
        return {"managed": True, "newer": False, "latest": None,
                "current": config.APP_VERSION}
    latest = info.TargetFullRelease.Version
    with _lock:
        _state.update(phase="idle", percent=0, version=latest, failure=None)
    return {"managed": True, "newer": True, "latest": latest,
            "current": config.APP_VERSION}


def progress() -> dict:
    """The current download phase/percent. Pure read, safe to poll."""
    with _lock:
        return dict(_state)


def download_async() -> dict:
    """Start downloading the available update on a daemon thread. Idempotent-ish: a
    second call while a download is in flight is a no-op that returns the live state.

    Returns the state dict the UI should start polling."""
    if not is_managed():
        return {"phase": "error", "percent": 0, "version": None,
                "failure": "not-managed"}
    with _lock:
        if _state["phase"] == "downloading":
            return dict(_state)
        _state.update(phase="checking", percent=0, failure=None)

    def _work() -> None:
        global _pending
        try:
            mgr = _manager()
            info = mgr.check_for_updates()
            if info is None:
                with _lock:
                    _state.update(phase="idle", percent=0, version=None)
                return
            with _lock:
                _state.update(phase="downloading", percent=0,
                              version=info.TargetFullRelease.Version)

            def _on_progress(pct: int) -> None:
                with _lock:
                    # Velopack reports 0..100; clamp defensively.
                    _state["percent"] = max(0, min(100, int(pct)))

            mgr.download_updates(info, _on_progress)
            _pending = info
            with _lock:
                _state.update(phase="ready", percent=100)
        except Exception as e:  # noqa: BLE001 — a failed download must never crash
            with _lock:
                _state.update(phase="error",
                              failure=f"{type(e).__name__}: {e}")

    threading.Thread(target=_work, name="zaggregate-update", daemon=True).start()
    with _lock:
        return dict(_state)


def apply_and_restart(restart_args: list[str] | None = None) -> dict:
    """Hand off to Velopack's Update.exe, which waits for this pid to exit, swaps the
    `current/` folder, and relaunches us with ``restart_args``.

    Returns ``{ok, exiting}``. It does NOT exit the process — the caller (the Flask
    route) must flush its HTTP response first, then exit. That ordering is why we use
    ``wait_exit_then_apply_updates`` rather than ``apply_updates_and_restart``, which
    would kill us mid-response.

    Refuses while a `--daily` scheduled run holds the lock: swapping the exe out from
    under a live ingest would corrupt a half-written run."""
    if not is_managed():
        return {"ok": False, "exiting": False, "error": "not-managed"}
    if daily_run_active():
        return {"ok": False, "exiting": False, "error": "daily-run-active"}
    update = _pending
    if update is None:
        # A download from a previous app run may already be staged on disk.
        try:
            update = _manager().get_update_pending_restart()
        except Exception:
            update = None
    if update is None:
        return {"ok": False, "exiting": False, "error": "nothing-downloaded"}
    args = list(restart_args or [])
    try:
        _manager().wait_exit_then_apply_updates(update, False, True, args)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "exiting": False, "error": f"{type(e).__name__}: {e}"}
    return {"ok": True, "exiting": True}


def restart_args_for_current_process(argv: list[str] | None = None) -> list[str]:
    """The argv Velopack should relaunch us with, so a `--web` or `--classic` tester
    is not silently bounced into desktop mode after every update.

    Drops `--daily` (a scheduled headless run must never be resurrected as an
    interactive window) and, with it, the `--project <slug>` pin that only means
    anything to a daily run. Also drops Velopack's own `--veloapp-*` hook flags,
    which would make the relaunched process think it is mid-install, and the retired
    `--classic` flag — the frozen exe stopped shipping the legacy Tk window on
    2026-07-08, so relaunching with it would just be noise."""
    import sys
    source = list(sys.argv[1:] if argv is None else argv)
    daily = "--daily" in source
    keep: list[str] = []
    i = 0
    while i < len(source):
        a = source[i]
        if a in ("--daily", "--classic") or a.startswith("--veloapp"):
            i += 1
            continue
        if daily and a == "--project":
            i += 2          # skip the flag and its value
            continue
        if daily and a.startswith("--project="):
            i += 1
            continue
        keep.append(a)
        i += 1
    return keep
