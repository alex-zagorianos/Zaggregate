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
