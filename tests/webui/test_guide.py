"""Guide + backup/restore API (Phase 5).

Covers: the guide shape, backup-download zip content, restore confirm-gate + origin
gate + rollback snapshot, and — the security-critical case — ZIP-SLIP DEFENSE: a
hostile zip whose members traverse out of the data root (../, absolute path, or a
symlink) is refused with a 400 and NOTHING is written outside the data folder.
"""
import io
import os
import zipfile
from pathlib import Path

import pytest

import config


_LOOPBACK = "http://127.0.0.1:5002"


@pytest.fixture
def tmp_data(tmp_path, monkeypatch):
    """Point config.USER_DATA_DIR at a tmp data dir with some content, so backup
    zips it and restore extracts into it (never real user data)."""
    data = tmp_path / "data"
    data.mkdir()
    (data / "preferences.md").write_text("my profile", encoding="utf-8")
    (data / "ui_settings.json").write_text('{"theme":"dark"}', encoding="utf-8")
    monkeypatch.setattr(config, "USER_DATA_DIR", data)
    return data


# ── guide ─────────────────────────────────────────────────────────────────────
def test_guide_shape(client):
    body = client.get("/api/guide").get_json()
    assert body["ok"] is True
    sections = body["sections"]
    assert isinstance(sections, list) and len(sections) > 5
    for s in sections:
        assert set(s.keys()) == {"heading", "level", "body"}
        assert s["level"] in (1, 2)
    # The Welcome h1 is the first section and carries body text.
    assert sections[0]["heading"].startswith("Welcome")
    assert sections[0]["level"] == 1
    assert sections[0]["body"]
    # A known h2 appears somewhere with a level of 2.
    assert any(s["level"] == 2 and "Search" == s["heading"] for s in sections)


# ── backup download ───────────────────────────────────────────────────────────
def test_backup_download_returns_zip(client, tmp_data):
    resp = client.get("/api/backup/download")
    assert resp.status_code == 200
    assert resp.headers["Content-Type"] in ("application/zip",
                                             "application/zip; charset=utf-8")
    assert "attachment" in resp.headers.get("Content-Disposition", "")
    # The payload is a real zip containing the data files.
    zf = zipfile.ZipFile(io.BytesIO(resp.get_data()))
    names = zf.namelist()
    assert "preferences.md" in names
    assert "ui_settings.json" in names
    assert zf.read("preferences.md").decode() == "my profile"


def test_backup_download_leaves_no_artifact_in_data(client, tmp_data):
    before = set(os.listdir(tmp_data))
    client.get("/api/backup/download")
    after = set(os.listdir(tmp_data))
    # The zip is built in a temp dir and cleaned up — nothing new lands in data/.
    assert after == before


# ── restore: confirm gate + origin gate ───────────────────────────────────────
def _make_zip(members: dict[str, bytes]) -> bytes:
    """A well-formed backup zip from {name: bytes}."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in members.items():
            z.writestr(name, data)
    return buf.getvalue()


def test_restore_requires_confirm(client, tmp_data):
    zbytes = _make_zip({"preferences.md": b"restored!"})
    resp = client.post(
        "/api/backup/restore",
        data={"file": (io.BytesIO(zbytes), "backup.zip")},
        headers={"Origin": _LOOPBACK},
        content_type="multipart/form-data")
    assert resp.status_code == 400
    assert "confirm" in resp.get_json()["error"]
    # Nothing was overwritten.
    assert (tmp_data / "preferences.md").read_text() == "my profile"


def test_restore_headerless_403(client, tmp_data):
    zbytes = _make_zip({"preferences.md": b"x"})
    resp = client.post(
        "/api/backup/restore",
        data={"file": (io.BytesIO(zbytes), "backup.zip"), "confirm": "true"},
        content_type="multipart/form-data")   # no Origin
    assert resp.status_code == 403
    assert (tmp_data / "preferences.md").read_text() == "my profile"


def test_restore_no_file_400(client, tmp_data):
    resp = client.post(
        "/api/backup/restore",
        data={"confirm": "true"},
        headers={"Origin": _LOOPBACK},
        content_type="multipart/form-data")
    assert resp.status_code == 400
    assert "no backup file" in resp.get_json()["error"]


def test_restore_happy_overwrites_and_snapshots(client, tmp_data):
    zbytes = _make_zip({"preferences.md": b"RESTORED", "new_file.txt": b"hi"})
    resp = client.post(
        "/api/backup/restore",
        data={"file": (io.BytesIO(zbytes), "backup.zip"), "confirm": "true"},
        headers={"Origin": _LOOPBACK},
        content_type="multipart/form-data")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["members"] == 2
    # Data was overwritten + the new file landed.
    assert (tmp_data / "preferences.md").read_text() == "RESTORED"
    assert (tmp_data / "new_file.txt").read_text() == "hi"
    # A pre-restore rollback snapshot was taken under backups/.
    assert body["rollback"] and Path(body["rollback"]).exists()
    assert Path(body["rollback"]).name.startswith("pre-restore-")


# ── large-upload: the app-wide 8 MB cap must not break a real backup restore ──
def test_restore_accepts_upload_over_receiver_8mb_cap(client, tmp_data):
    """The receiver app sets MAX_CONTENT_LENGTH=8 MB (sized for extension capture
    POSTs). A real data-folder backup zip routinely exceeds 8 MB, so the blanket
    cap used to reject the restore with a raw HTML 413 before the route ran. The
    route now lifts the cap per-request; a >8 MB restore must succeed (200) and
    honor the JSON envelope, not 413."""
    # A zip whose stored payload is comfortably over 8 MB. Use incompressible
    # random bytes so the on-the-wire multipart body actually exceeds the cap.
    big_payload = os.urandom(9 * 1024 * 1024)  # 9 MiB, > the 8 MiB cap
    zbytes = _make_zip({"preferences.md": b"BIG_RESTORE",
                        "blob.bin": big_payload})
    assert len(zbytes) > 8 * 1024 * 1024  # the upload really is over the cap
    resp = client.post(
        "/api/backup/restore",
        data={"file": (io.BytesIO(zbytes), "backup.zip"), "confirm": "true"},
        headers={"Origin": _LOOPBACK},
        content_type="multipart/form-data")
    assert resp.status_code == 200, (
        f"large restore rejected ({resp.status_code}); the 8 MB cap still gates it")
    body = resp.get_json()
    assert body["ok"] is True
    assert body["members"] == 2
    assert (tmp_data / "preferences.md").read_text() == "BIG_RESTORE"
    assert (tmp_data / "blob.bin").read_bytes() == big_payload


# ── JOB-SAFE: restore must not clobber an in-flight engine job ────────────────
def test_restore_refused_while_exclusive_job_running(client, tmp_data):
    # A restore extracts over the whole data folder; running it while a daily-run/
    # search/build-list/seed-metro exclusive engine job is mid-flight would
    # overwrite tracker.db / companies.json out from under it. The restore must
    # refuse with a 409 (same shape as the engine jobs) and write NOTHING.
    import threading
    from webui.jobs import runner

    release = threading.Event()
    started = threading.Event()

    def _blocking(handle):
        started.set()
        release.wait(timeout=10)      # hold the exclusive mutex until released
        return {"held": True}

    job_id = runner.start("build_list", "slug-x", _blocking, exclusive=True)
    try:
        assert started.wait(timeout=5)          # the job is running + holds the mutex
        zbytes = _make_zip({"preferences.md": b"SHOULD_NOT_LAND"})
        resp = client.post(
            "/api/backup/restore",
            data={"file": (io.BytesIO(zbytes), "backup.zip"), "confirm": "true"},
            headers={"Origin": _LOOPBACK},
            content_type="multipart/form-data")
        assert resp.status_code == 409
        body = resp.get_json()
        assert body["ok"] is False
        assert body["job_id"] == job_id
        assert "another run is in progress" in body["error"]
        # CRITICAL: the in-flight job's data folder was NOT touched.
        assert (tmp_data / "preferences.md").read_text() == "my profile"
    finally:
        release.set()

    # Once the exclusive job releases, a restore is allowed again.
    import time
    for _ in range(50):
        if runner.exclusive_active() is None:
            break
        time.sleep(0.05)
    assert runner.exclusive_active() is None
    zbytes = _make_zip({"preferences.md": b"NOW_ALLOWED"})
    resp = client.post(
        "/api/backup/restore",
        data={"file": (io.BytesIO(zbytes), "backup.zip"), "confirm": "true"},
        headers={"Origin": _LOOPBACK},
        content_type="multipart/form-data")
    assert resp.status_code == 200
    assert (tmp_data / "preferences.md").read_text() == "NOW_ALLOWED"


# ── ZIP-SLIP DEFENSE (security-critical) ──────────────────────────────────────
def _hostile_zip(member_name: str, payload: bytes = b"pwned") -> bytes:
    """A zip carrying a single member with a traversal/absolute name."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(member_name, payload)
    return buf.getvalue()


@pytest.mark.parametrize("evil_name", [
    "../escape.txt",
    "../../escape.txt",
    "../../../etc/passwd",
    "sub/../../escape.txt",
])
def test_restore_refuses_traversal_member(client, tmp_data, evil_name):
    zbytes = _hostile_zip(evil_name)
    resp = client.post(
        "/api/backup/restore",
        data={"file": (io.BytesIO(zbytes), "evil.zip"), "confirm": "true"},
        headers={"Origin": _LOOPBACK},
        content_type="multipart/form-data")
    assert resp.status_code == 400
    assert "unsafe backup" in resp.get_json()["error"]
    # CRITICAL: nothing was written outside the data root.
    parent = tmp_data.parent
    assert not (parent / "escape.txt").exists()
    assert not (parent.parent / "escape.txt").exists()
    # The legit file is untouched (validation happens before any write).
    assert (tmp_data / "preferences.md").read_text() == "my profile"


def test_restore_refuses_absolute_path_member(client, tmp_data, tmp_path):
    # A member with an absolute path must not escape the data root.
    outside = tmp_path / "OUTSIDE_ABS.txt"
    # zipfile stores names as-is; craft an absolute-looking name.
    abs_name = str(outside).replace("\\", "/").lstrip("/")
    # Prefix with a drive-absolute form on Windows / leading slash on POSIX so it
    # resolves outside the root when joined.
    zbytes = _hostile_zip("/" + abs_name if os.name != "nt" else abs_name)
    resp = client.post(
        "/api/backup/restore",
        data={"file": (io.BytesIO(zbytes), "evil.zip"), "confirm": "true"},
        headers={"Origin": _LOOPBACK},
        content_type="multipart/form-data")
    # Either refused as unsafe, OR (if the absolute name happened to resolve INSIDE
    # after join) it wrote inside the data root — never outside it.
    assert not outside.exists()
    if resp.status_code == 200:
        # Any extracted member stayed inside the data dir.
        for f in tmp_data.rglob("*"):
            assert tmp_data.resolve() in f.resolve().parents or f.resolve() == tmp_data.resolve()
    else:
        assert resp.status_code == 400


def test_restore_refuses_symlink_member(client, tmp_data, tmp_path):
    # A symlink member (unix external-attr high bits) is refused — the second
    # zip-slip vector (a link out of the tree a later member writes through).
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        info = zipfile.ZipInfo("evil_link")
        # 0xA1FF0000 -> symlink mode (0o120000) in the external attr high bits.
        info.external_attr = (0o120777 << 16)
        z.writestr(info, str(tmp_path))   # link target = outside the data root
    resp = client.post(
        "/api/backup/restore",
        data={"file": (io.BytesIO(buf.getvalue()), "evil.zip"), "confirm": "true"},
        headers={"Origin": _LOOPBACK},
        content_type="multipart/form-data")
    assert resp.status_code == 400
    assert "unsafe backup" in resp.get_json()["error"]
    assert not (tmp_data / "evil_link").exists()


# ── WAL-sidecar restore (Windows-locked-file critical, S36) ───────────────────
# On Windows a restore can't overwrite tracker.db / its -shm/-wal sidecars while
# the server that services the restore holds an open WAL-mode connection to the
# SAME db. Fix (defense in depth): backup checkpoints + drops the sidecars so the
# zipped .db is self-contained; restore checkpoints/releases the live connection,
# ignores any -shm/-wal members inside the upload, and deletes stale on-disk
# sidecars post-extract so the next get_conn() rebuilds them from the restored db.
@pytest.fixture
def live_wal_db(tmp_data, monkeypatch):
    """A live WAL-mode tracker.db INSIDE the tmp data folder, with an open prior
    read so -wal/-shm sidecars exist on disk — the Windows repro. Points
    ``db.DB_PATH`` at it so make_backup/restore's checkpoint targets THIS db."""
    from tracker import db
    db_path = tmp_data / "tracker.db"
    monkeypatch.setattr(db, "DB_PATH", db_path)
    db.init_db()
    db.add_job("Original Role", "OrigCo", url="https://ex.com/orig")
    # Do a read via get_conn() (WAL pragmas applied) and leave the -wal sidecar on
    # disk — simulates the server holding open WAL state at restore time.
    got = db.get_all()
    assert any(r["title"] == "Original Role" for r in got)
    return db_path


def test_backup_excludes_wal_sidecars(client, live_wal_db, tmp_data):
    # live_wal_db already left REAL -wal/-shm sidecars on disk (via its get_conn()
    # read) — on Windows those are locked, which is the whole point.
    assert (tmp_data / "tracker.db-wal").exists()
    assert (tmp_data / "tracker.db-shm").exists()
    resp = client.get("/api/backup/download")
    assert resp.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(resp.get_data()))
    names = zf.namelist()
    # The .db itself is captured (checkpointed, so it's self-contained), but NO
    # -shm/-wal members ride along.
    assert "tracker.db" in names
    assert not any(n.endswith("-wal") or n.endswith("-shm") for n in names), names


def test_restore_zip_with_sidecars_succeeds_and_leaves_none(client, live_wal_db, tmp_data):
    # An OLDER backup zip that DOES contain -shm/-wal members must restore cleanly
    # and leave no stale sidecars on disk.
    zbytes = _make_zip({
        "tracker.db": b"SQLite format 3\x00restored-db-bytes",
        "tracker.db-wal": b"OLD STALE WAL - must be ignored",
        "tracker.db-shm": b"OLD STALE SHM - must be ignored",
        "preferences.md": b"restored profile",
    })
    resp = client.post(
        "/api/backup/restore",
        data={"file": (io.BytesIO(zbytes), "old-backup.zip"), "confirm": "true"},
        headers={"Origin": _LOOPBACK},
        content_type="multipart/form-data")
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["ok"] is True
    # The .db + non-sidecar members restored; the sidecar members were skipped.
    assert (tmp_data / "tracker.db").read_bytes().startswith(b"SQLite format 3")
    assert (tmp_data / "preferences.md").read_text() == "restored profile"
    # members count excludes the two skipped sidecars (tracker.db + preferences.md).
    assert body["members"] == 2
    # No stale sidecars left behind — not from the zip, not from the pre-restore db.
    assert not (tmp_data / "tracker.db-wal").exists()
    assert not (tmp_data / "tracker.db-shm").exists()


def test_restore_roundtrip_with_open_wal_connection(client, live_wal_db, tmp_data):
    # THE Windows repro: a prior get_conn()-based read (in live_wal_db) left WAL
    # state open on the SAME db; a real backup of that db then restored over it
    # must succeed AND post-restore reads must see the restored data.
    from tracker import db
    # Build a genuine backup zip of the CURRENT (WAL-mode, open-connection) db via
    # the download route, mutate the live db, then restore the snapshot back.
    dl = client.get("/api/backup/download")
    assert dl.status_code == 200
    backup_bytes = dl.get_data()
    # Mutate the live db AFTER the snapshot — the restore must roll this back.
    db.add_job("Post-Snapshot Role", "LaterCo", url="https://ex.com/later")
    assert any(r["title"] == "Post-Snapshot Role" for r in db.get_all())
    # Restore the earlier snapshot over the live (still-open-WAL) data folder.
    resp = client.post(
        "/api/backup/restore",
        data={"file": (io.BytesIO(backup_bytes), "snap.zip"), "confirm": "true"},
        headers={"Origin": _LOOPBACK},
        content_type="multipart/form-data")
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["ok"] is True
    # No stale sidecars survive the restore.
    assert not (tmp_data / "tracker.db-wal").exists()
    assert not (tmp_data / "tracker.db-shm").exists()
    # Post-restore reads (fresh get_conn() handle) see the restored data: the
    # original row is back and the post-snapshot mutation is gone.
    titles = {r["title"] for r in db.get_all()}
    assert "Original Role" in titles
    assert "Post-Snapshot Role" not in titles
