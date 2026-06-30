"""Backup/restore round-trip over the data folder (pure core; the dialog wrappers
just pick paths)."""
import config
from ui import help as uihelp


def test_backup_then_restore_roundtrip(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    (data / "preferences.md").write_text("my profile", encoding="utf-8")
    (data / "ui_settings.json").write_text('{"theme":"dark"}', encoding="utf-8")
    monkeypatch.setattr(config, "USER_DATA_DIR", data)

    zip_path = uihelp.make_backup(str(tmp_path / "backup"))
    assert zip_path.endswith(".zip")

    # wipe a file, then restore brings it back
    (data / "preferences.md").write_text("CLOBBERED", encoding="utf-8")
    uihelp.restore_backup(zip_path)
    assert (data / "preferences.md").read_text(encoding="utf-8") == "my profile"
    assert (data / "ui_settings.json").read_text(encoding="utf-8") == '{"theme":"dark"}'
