"""Tests for src/updater.py — the Velopack auto-update seam.

The contract under test is the DEGRADATION contract: in a dev checkout (no Velopack
install, and possibly no `velopack` wheel at all) nothing here may raise, and every
entry point must return a benign, falsy answer so the web routes keep serving the
v1.0.2 link-out behaviour.

`velopack` is deliberately NOT required to run this suite. The tests fake the SDK so
they pin OUR logic (channel, restart argv, daily-run refusal, progress state machine)
rather than re-testing Velopack.
"""
import sys
import time
import types

import pytest

import config
import updater


@pytest.fixture(autouse=True)
def _reset_updater_state(monkeypatch):
    """Each test gets a pristine module: the manager probe is sticky by design, and
    the download state is module-global."""
    monkeypatch.setattr(updater, "_manager_cache", None, raising=False)
    monkeypatch.setattr(updater, "_manager_probed", False, raising=False)
    monkeypatch.setattr(updater, "_pending", None, raising=False)
    monkeypatch.setattr(updater, "_state",
                        {"phase": "idle", "percent": 0, "version": None,
                         "failure": None},
                        raising=False)
    yield


# ── the degradation contract ──────────────────────────────────────────────────

def test_not_managed_in_a_dev_checkout(monkeypatch):
    """A source checkout is never Velopack-managed, even if the wheel is installed:
    UpdateManager cannot locate an app manifest."""
    monkeypatch.setattr(updater, "_build_manager",
                        lambda: (_ for _ in ()).throw(updater.NotManaged("no manifest")))
    assert updater.is_managed() is False


def test_unmanaged_entry_points_never_raise(monkeypatch):
    """check/download/apply/status/progress all answer benignly when unmanaged."""
    monkeypatch.setattr(updater, "is_managed", lambda: False)

    assert updater.check() == {"managed": False, "newer": False, "latest": None,
                               "current": config.APP_VERSION}
    assert updater.download_async()["failure"] == "not-managed"
    assert updater.apply_and_restart([]) == {"ok": False, "exiting": False,
                                             "error": "not-managed"}
    st = updater.status()
    assert st["managed"] is False and st["current"] == config.APP_VERSION
    assert updater.progress()["phase"] == "idle"


def test_missing_wheel_degrades_to_not_managed(monkeypatch):
    """A frozen build that failed to bundle velopack must not crash the app."""
    monkeypatch.setitem(sys.modules, "velopack", None)  # `import velopack` -> ImportError
    with pytest.raises(updater.NotManaged):
        updater._build_manager()
    assert updater.is_managed() is False


def test_runtime_error_from_sdk_is_the_not_managed_detector(monkeypatch):
    """velopack 1.2.0 raises RuntimeError('This application is not properly
    installed: ...') outside an install. That IS how we detect a plain zip/dev run —
    it must be caught, not propagated."""
    fake = types.SimpleNamespace(
        GithubSource=lambda *a, **k: object(),
        UpdateOptions=lambda *a, **k: object(),
        UpdateManager=lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError("This application is not properly installed: "
                         "Could not auto-locate app manifest")),
    )
    monkeypatch.setitem(sys.modules, "velopack", fake)
    with pytest.raises(updater.NotManaged):
        updater._build_manager()
    assert updater.is_managed() is False


def test_manager_probe_is_sticky(monkeypatch):
    """A not-managed verdict is cached, so a dev run constructs UpdateManager (and
    emits its stderr noise) exactly once, not on every route hit."""
    calls = []

    def _boom():
        calls.append(1)
        raise updater.NotManaged("nope")

    monkeypatch.setattr(updater, "_build_manager", _boom)
    for _ in range(5):
        assert updater.is_managed() is False
    assert len(calls) == 1


# ── UpdateOptions positional-arg contract (velopack 1.2.0) ────────────────────

def test_build_manager_passes_update_options_positionally(monkeypatch):
    """UpdateOptions.__new__ takes 2 REQUIRED positional args
    (AllowVersionDowngrade, MaximumDeltasBeforeFallback). Passing them as kwargs
    raises TypeError, which would silently degrade every install to 'not managed'.
    Pin the call shape, and pin that downgrade is ENABLED (that's our rollback story:
    delete a bad release, testers fall back on their next check)."""
    seen = {}

    def _update_options(*args, **kwargs):
        if kwargs:
            raise TypeError("UpdateOptions.__new__() takes no keyword arguments")
        seen["args"] = args
        return object()

    def _github_source(*args, **kwargs):
        seen["source"] = args
        return object()

    fake = types.SimpleNamespace(
        GithubSource=_github_source,
        UpdateOptions=_update_options,
        UpdateManager=lambda source, options: types.SimpleNamespace(_ok=True),
    )
    monkeypatch.setitem(sys.modules, "velopack", fake)

    mgr = updater._build_manager()
    assert mgr._ok is True
    assert seen["args"][0] is True, "AllowVersionDowngrade must be True (rollback)"
    assert seen["args"][1] == 10
    # prerelease=True so a beta-channel install can see `vX.Y.Z-betaN` releases.
    assert seen["source"][0] == f"https://github.com/{config.UPDATE_REPO}"
    assert seen["source"][2] is True


# ── restart argv preservation ─────────────────────────────────────────────────

@pytest.mark.parametrize("argv,expected", [
    ([], []),                                        # frozen bare -> desktop default
    (["--web"], ["--web"]),                          # browser tester stays in browser
    (["--classic"], []),                             # retired flag dropped on relaunch
    (["--desktop"], ["--desktop"]),
    (["--daily"], []),                               # never resurrect a scheduled run
    (["--daily", "--project", "eng"], []),           # ...nor its project pin
    (["--daily", "--project=eng"], []),
    (["--veloapp-install", "1.0.3"], ["1.0.3"]),     # hook flag dropped
    (["--web", "--veloapp-updated"], ["--web"]),
])
def test_restart_args_for_current_process(argv, expected):
    """A tester who launched --web must not be silently bounced into desktop mode by
    an update; a scheduled --daily process must not be relaunched as a window."""
    assert updater.restart_args_for_current_process(argv) == expected


def test_restart_args_defaults_to_sys_argv(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["JobProgram.exe", "--web"])
    assert updater.restart_args_for_current_process() == ["--web"]


# ── the --daily interlock ─────────────────────────────────────────────────────

def test_daily_lock_absent_is_not_active(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "USER_DATA_DIR", tmp_path)
    assert updater.daily_run_active() is False


def test_daily_lock_fresh_blocks_apply(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "USER_DATA_DIR", tmp_path)
    (tmp_path / updater.DAILY_LOCK_NAME).write_text("1234", encoding="ascii")
    assert updater.daily_run_active() is True

    monkeypatch.setattr(updater, "is_managed", lambda: True)
    res = updater.apply_and_restart([])
    assert res == {"ok": False, "exiting": False, "error": "daily-run-active"}


def test_daily_lock_stale_is_ignored(monkeypatch, tmp_path):
    """A crashed daily run must not wedge updates forever."""
    monkeypatch.setattr(config, "USER_DATA_DIR", tmp_path)
    lock = tmp_path / updater.DAILY_LOCK_NAME
    lock.write_text("1234", encoding="ascii")
    import os
    stale = time.time() - (7 * 60 * 60)
    os.utime(lock, (stale, stale))
    assert updater.daily_run_active() is False


# ── apply preconditions ───────────────────────────────────────────────────────

def test_apply_refuses_when_nothing_downloaded(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "USER_DATA_DIR", tmp_path)
    monkeypatch.setattr(updater, "is_managed", lambda: True)
    monkeypatch.setattr(updater, "_manager",
                        lambda: types.SimpleNamespace(
                            get_update_pending_restart=lambda: None))
    res = updater.apply_and_restart([])
    assert res["ok"] is False and res["error"] == "nothing-downloaded"


def test_apply_uses_wait_exit_and_forwards_restart_args(monkeypatch, tmp_path):
    """apply must call wait_exit_then_apply_updates (which RETURNS, letting the HTTP
    response flush) — never apply_updates_and_restart, which would kill us mid-reply."""
    monkeypatch.setattr(config, "USER_DATA_DIR", tmp_path)
    monkeypatch.setattr(updater, "is_managed", lambda: True)
    sentinel = object()
    monkeypatch.setattr(updater, "_pending", sentinel, raising=False)
    seen = {}

    def _wait_exit(update, silent, restart, restart_args):
        seen.update(update=update, silent=silent, restart=restart, args=restart_args)

    def _boom(*a, **k):
        raise AssertionError("apply_updates_and_restart would kill the HTTP response")

    monkeypatch.setattr(updater, "_manager",
                        lambda: types.SimpleNamespace(
                            wait_exit_then_apply_updates=_wait_exit,
                            apply_updates_and_restart=_boom))
    res = updater.apply_and_restart(["--web"])
    assert res == {"ok": True, "exiting": True}
    assert seen["update"] is sentinel
    assert seen["restart"] is True and seen["silent"] is False
    assert seen["args"] == ["--web"]


def test_apply_falls_back_to_previously_staged_update(monkeypatch, tmp_path):
    """Velopack persists a downloaded-but-unapplied update across app restarts."""
    monkeypatch.setattr(config, "USER_DATA_DIR", tmp_path)
    monkeypatch.setattr(updater, "is_managed", lambda: True)
    monkeypatch.setattr(updater, "_pending", None, raising=False)
    staged = object()
    seen = {}
    monkeypatch.setattr(updater, "_manager",
                        lambda: types.SimpleNamespace(
                            get_update_pending_restart=lambda: staged,
                            wait_exit_then_apply_updates=lambda u, s, r, a: seen.update(u=u)))
    assert updater.apply_and_restart([])["ok"] is True
    assert seen["u"] is staged


def test_apply_swallows_sdk_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "USER_DATA_DIR", tmp_path)
    monkeypatch.setattr(updater, "is_managed", lambda: True)
    monkeypatch.setattr(updater, "_pending", object(), raising=False)

    def _raise(*a, **k):
        raise OSError("Update.exe missing")

    monkeypatch.setattr(updater, "_manager",
                        lambda: types.SimpleNamespace(wait_exit_then_apply_updates=_raise))
    res = updater.apply_and_restart([])
    assert res["ok"] is False and "OSError" in res["error"]


# ── check() ───────────────────────────────────────────────────────────────────

def test_check_reports_newer_from_the_sdk(monkeypatch):
    monkeypatch.setattr(updater, "is_managed", lambda: True)
    info = types.SimpleNamespace(
        TargetFullRelease=types.SimpleNamespace(Version="1.0.3"))
    monkeypatch.setattr(updater, "_manager",
                        lambda: types.SimpleNamespace(check_for_updates=lambda: info))
    res = updater.check()
    assert res == {"managed": True, "newer": True, "latest": "1.0.3",
                   "current": config.APP_VERSION}


def test_check_none_means_up_to_date(monkeypatch):
    monkeypatch.setattr(updater, "is_managed", lambda: True)
    monkeypatch.setattr(updater, "_manager",
                        lambda: types.SimpleNamespace(check_for_updates=lambda: None))
    res = updater.check()
    assert res["newer"] is False and res["latest"] is None


def test_check_network_failure_is_not_an_error_envelope(monkeypatch):
    """Offline must read as 'couldn't check', never as a 500 or ok:false."""
    monkeypatch.setattr(updater, "is_managed", lambda: True)

    def _raise():
        raise OSError("offline")

    monkeypatch.setattr(updater, "_manager",
                        lambda: types.SimpleNamespace(check_for_updates=_raise))
    res = updater.check()
    assert res["managed"] is True and res["newer"] is False
    assert res["latest"] is None and res["failure"] == "check-failed"


# ── download state machine ────────────────────────────────────────────────────

def _wait_for(pred, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred():
            return True
        time.sleep(0.01)
    return False


def test_download_async_drives_progress_to_ready(monkeypatch):
    monkeypatch.setattr(updater, "is_managed", lambda: True)
    info = types.SimpleNamespace(
        TargetFullRelease=types.SimpleNamespace(Version="1.0.3"))

    def _download(update_info, cb):
        for pct in (0, 50, 100):
            cb(pct)

    monkeypatch.setattr(updater, "_manager",
                        lambda: types.SimpleNamespace(check_for_updates=lambda: info,
                                                      download_updates=_download))
    updater.download_async()
    assert _wait_for(lambda: updater.progress()["phase"] == "ready")
    st = updater.progress()
    assert st["percent"] == 100 and st["version"] == "1.0.3"
    assert updater._pending is info


def test_download_percent_is_clamped(monkeypatch):
    monkeypatch.setattr(updater, "is_managed", lambda: True)
    info = types.SimpleNamespace(
        TargetFullRelease=types.SimpleNamespace(Version="1.0.3"))
    monkeypatch.setattr(updater, "_manager",
                        lambda: types.SimpleNamespace(
                            check_for_updates=lambda: info,
                            download_updates=lambda i, cb: [cb(-5), cb(1000)]))
    updater.download_async()
    assert _wait_for(lambda: updater.progress()["phase"] == "ready")
    assert 0 <= updater.progress()["percent"] <= 100


def test_download_failure_sets_error_phase_not_exception(monkeypatch):
    monkeypatch.setattr(updater, "is_managed", lambda: True)
    info = types.SimpleNamespace(
        TargetFullRelease=types.SimpleNamespace(Version="1.0.3"))

    def _boom(i, cb):
        raise OSError("disk full")

    monkeypatch.setattr(updater, "_manager",
                        lambda: types.SimpleNamespace(check_for_updates=lambda: info,
                                                      download_updates=_boom))
    updater.download_async()
    assert _wait_for(lambda: updater.progress()["phase"] == "error")
    assert "OSError" in updater.progress()["failure"]


def test_download_when_already_downloading_is_a_noop(monkeypatch):
    monkeypatch.setattr(updater, "is_managed", lambda: True)
    updater._state.update(phase="downloading", percent=42)
    res = updater.download_async()
    assert res["phase"] == "downloading" and res["percent"] == 42
