"""A3 concurrency/robustness: atomic registry writes, loud corruption (no silent
root-reroute), and the advisory cross-process registry lock."""
import json
import os
from pathlib import Path

import pytest

import workspace


@pytest.fixture
def tmp_base(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace, "BASE_DIR", tmp_path)
    workspace.unpin_active()
    yield tmp_path
    workspace.unpin_active()


# ── atomic writes ─────────────────────────────────────────────────────────────
def test_write_registry_is_atomic_no_partial_on_failure(tmp_base, monkeypatch):
    """A failure during os.replace must leave NO corrupt projects.json: the real
    file is written only by the atomic rename, so a crash mid-write can at worst
    orphan a .tmp, never truncate the live registry."""
    workspace.create_project("Seed", make_active=True)          # good baseline
    good = json.loads(workspace._registry_path().read_text(encoding="utf-8"))

    def boom(*_a, **_k):
        raise OSError("simulated crash during rename")

    monkeypatch.setattr(workspace.os, "replace", boom)
    with pytest.raises(OSError):
        workspace._write_registry({"active": "x", "projects": [{"slug": "x"}]})

    # Live registry is byte-identical to before the failed write (not partial).
    assert json.loads(workspace._registry_path().read_text(encoding="utf-8")) == good


def test_write_registry_uses_tmp_then_replace(tmp_base, monkeypatch):
    seen = {}

    real_replace = os.replace

    def spy(src, dst):
        seen["src"] = str(src)
        seen["dst"] = str(dst)
        return real_replace(src, dst)

    monkeypatch.setattr(workspace.os, "replace", spy)
    workspace._write_registry({"active": None, "projects": []})
    assert seen["src"].endswith(".tmp")
    assert seen["dst"].endswith("projects.json")
    assert not Path(seen["src"]).exists()          # tmp consumed by the rename


# ── loud corruption (no silent reroute to root) ───────────────────────────────
def test_corrupt_registry_raises_not_reroutes_on_write(tmp_base):
    """A corrupt projects.json must make set_active REFUSE (raise), not silently
    fall back to an empty registry (which would reroute writes to the root)."""
    workspace.create_project("Real", make_active=True)
    workspace._registry_path().write_text("{ this is not json", encoding="utf-8")

    with pytest.raises(workspace.RegistryCorruptError):
        workspace.set_active("real")


def test_corrupt_registry_raises_on_read_path(tmp_base):
    """Read-only resolvers surface a clear error too (not a silent empty reg)."""
    workspace.create_project("Real", make_active=True)
    workspace._registry_path().write_text("<<<garbage>>>", encoding="utf-8")

    with pytest.raises(workspace.RegistryCorruptError):
        workspace.list_projects()
    with pytest.raises(workspace.RegistryCorruptError):
        workspace.db_path()          # write-target resolution refuses


def test_corrupt_registry_does_not_silently_reroute_db_to_root(tmp_base):
    """The bug being fixed: an empty-registry fallback made db_path() resolve to
    the ROOT tracker.db. After the fix it raises instead of returning root."""
    slug = workspace.create_project("Proj", make_active=True)
    per_project_db = workspace.db_path(slug)
    workspace._registry_path().write_text("not json at all", encoding="utf-8")

    with pytest.raises(workspace.RegistryCorruptError):
        workspace.db_path()
    # And it certainly must NOT silently resolve to the root db.
    assert per_project_db != tmp_base / "tracker.db"


def test_pinned_process_immune_to_corruption_for_reads(tmp_base):
    """A process that pinned its slug resolves paths WITHOUT touching projects.json,
    so mid-session corruption cannot redirect its already-pinned writes."""
    slug = workspace.create_project("Pinned", make_active=True)
    workspace.pin_active(slug)
    try:
        workspace._registry_path().write_text("corrupt!!!", encoding="utf-8")
        # active_slug short-circuits on the pin -> never reads the corrupt file.
        assert workspace.active_slug() == slug
        assert workspace.db_path().parent.name == slug
    finally:
        workspace.unpin_active()


def test_fresh_install_no_file_still_empty_not_corrupt(tmp_base):
    """No projects.json at all is a fresh install, NOT corruption: resolution
    must keep working (root fallback), never raise."""
    assert not workspace.has_projects()
    assert workspace.active_slug() is None
    assert workspace.db_path() == tmp_base / "tracker.db"     # root fallback intact
    assert workspace.list_projects() == []


# ── advisory registry lock ────────────────────────────────────────────────────
def test_lock_acquire_and_release_removes_file(tmp_base):
    lp = workspace._lock_path()
    assert not lp.exists()
    with workspace._registry_lock():
        assert lp.exists()                       # held -> file present
    assert not lp.exists()                       # released -> gone


def test_lock_contention_warns_and_proceeds(tmp_base, monkeypatch):
    """A second acquirer must NOT deadlock: on timeout it warns and proceeds
    unlocked (a crashed holder must never wedge the app)."""
    warned = {}
    import logging
    monkeypatch.setattr(logging.Logger, "warning",
                        lambda self, *a, **k: warned.setdefault("hit", (a, k)))

    with workspace._registry_lock():             # first holder keeps the file
        # Force a fast timeout and a NON-stale existing lock so it can't reclaim.
        monkeypatch.setattr(workspace, "_LOCK_STALE_S", 10_000.0)
        inner = workspace._registry_lock(timeout=0.15)
        with inner:                              # contended -> warn+proceed
            pass
        assert not inner._held                   # proceeded WITHOUT the lock
    assert "hit" in warned


def test_lock_reclaims_stale_lockfile(tmp_base, monkeypatch):
    """A lockfile older than _LOCK_STALE_S (crashed holder) is reclaimed so the
    next acquirer really takes the lock rather than warn-and-proceeding."""
    lp = workspace._lock_path()
    lp.parent.mkdir(parents=True, exist_ok=True)
    lp.write_text("99999", encoding="utf-8")     # orphaned lock from a dead pid
    old = os.stat(lp).st_mtime - 10_000
    os.utime(lp, (old, old))                     # make it ancient

    monkeypatch.setattr(workspace, "_LOCK_STALE_S", 60.0)
    lock = workspace._registry_lock(timeout=0.3)
    with lock:
        assert lock._held                        # reclaimed the stale lock
    assert not lp.exists()


def test_set_active_and_create_project_hold_lock(tmp_base, monkeypatch):
    """Registry mutations acquire the advisory lock around their read-modify-write."""
    calls = {"n": 0}
    real = workspace._registry_lock

    def counting(*a, **k):
        calls["n"] += 1
        return real(*a, **k)

    monkeypatch.setattr(workspace, "_registry_lock", counting)
    workspace.create_project("A", make_active=True)
    workspace.create_project("B")
    workspace.set_active("a")
    assert calls["n"] == 3                        # each mutation locked once
