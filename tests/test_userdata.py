import sys
from pathlib import Path

import config


def test_user_data_dir_env_override(monkeypatch, tmp_path):
    """JOBPROGRAM_DATA env var overrides the data folder location anywhere."""
    target = tmp_path / "mydata"
    monkeypatch.setenv("JOBPROGRAM_DATA", str(target))
    assert config._get_user_data_dir() == Path(str(target))


def test_user_data_dir_dev_is_repo_root(monkeypatch):
    """Dev (non-frozen) keeps user files at the REPO ROOT — one level above
    src/, where config.py lives since the 2026-07 restructure."""
    monkeypatch.delenv("JOBPROGRAM_DATA", raising=False)
    monkeypatch.setattr(config, "_is_frozen", lambda: False)
    assert config._get_user_data_dir() == Path(config.__file__).resolve().parent.parent


def test_user_data_dir_frozen_is_localappdata(monkeypatch, tmp_path):
    """Frozen: ALWAYS %LOCALAPPDATA%/JobProgram — never beside the exe.

    Velopack swaps the whole `current/` folder that holds the exe on every
    update, so `<exe>/data` (the pre-v1.0.3 anchor) would be destroyed. This is
    the invariant the entire auto-update design rests on."""
    monkeypatch.delenv("JOBPROGRAM_DATA", raising=False)
    monkeypatch.setattr(config, "_is_frozen", lambda: True)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AppData" / "Local"))
    monkeypatch.setattr(sys, "executable", str(tmp_path / "JobProgram.exe"))
    assert config._get_user_data_dir() == tmp_path / "AppData" / "Local" / "JobProgram"


def test_user_data_dir_frozen_ignores_writable_exe_data(monkeypatch, tmp_path):
    """Regression guard for the swap-zone bug: even when a writable `data/` dir
    already sits beside the exe (an old v1.0.2 zip install), the frozen app must
    NOT adopt it — that folder lives inside Velopack's swap zone."""
    monkeypatch.delenv("JOBPROGRAM_DATA", raising=False)
    monkeypatch.setattr(config, "_is_frozen", lambda: True)
    exe_dir = tmp_path / "current"
    (exe_dir / "data").mkdir(parents=True)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AppData" / "Local"))
    monkeypatch.setattr(sys, "executable", str(exe_dir / "JobProgram.exe"))
    resolved = config._get_user_data_dir()
    assert resolved == tmp_path / "AppData" / "Local" / "JobProgram"
    assert (exe_dir / "data") not in resolved.parents and resolved != exe_dir / "data"


def test_user_data_dir_env_override_beats_frozen(monkeypatch, tmp_path):
    """JOBPROGRAM_DATA still wins when frozen (used by the --daily scheduled task
    and by testers relocating their data off a sync folder)."""
    monkeypatch.setattr(config, "_is_frozen", lambda: True)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    monkeypatch.setenv("JOBPROGRAM_DATA", str(tmp_path / "elsewhere"))
    assert config._get_user_data_dir() == tmp_path / "elsewhere"


def test_workspace_roots_under_user_data_dir():
    """workspace.BASE_DIR is the resolved user data folder, so projects/ and the
    tracker.db never land in the read-only _MEIPASS bundle when frozen."""
    import workspace
    assert workspace.BASE_DIR == config.USER_DATA_DIR


def test_scaffold_creates_then_idempotent(tmp_path, monkeypatch):
    import userdata
    tdir = tmp_path / "bundle" / "data_templates"
    tdir.mkdir(parents=True)
    (tdir / "experience.template.md").write_text("# Experience\n## CONTACT\n", encoding="utf-8")
    (tdir / "preferences.template.md").write_text("# My Job Preferences\n", encoding="utf-8")
    (tdir / "preferences.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(userdata, "templates_dir", lambda: tdir)

    data = tmp_path / "data"
    created = userdata.scaffold(data)
    assert set(created) == {"experience.md", "preferences.md", "preferences.json"}
    assert (data / "experience.md").exists()
    assert (data / "preferences.md").exists()
    assert (data / "preferences.json").exists()
    # Idempotent: a second call creates nothing.
    assert userdata.scaffold(data) == []


def test_scaffold_does_not_overwrite_existing(tmp_path, monkeypatch):
    import userdata
    tdir = tmp_path / "bundle" / "data_templates"
    tdir.mkdir(parents=True)
    (tdir / "preferences.template.md").write_text("TEMPLATE", encoding="utf-8")
    monkeypatch.setattr(userdata, "templates_dir", lambda: tdir)

    data = tmp_path / "data"
    data.mkdir()
    (data / "preferences.md").write_text("MY EDITS", encoding="utf-8")
    userdata.scaffold(data)
    assert (data / "preferences.md").read_text(encoding="utf-8") == "MY EDITS"


def test_bootstrap_seeds_and_makes_runtime_dirs(tmp_path, monkeypatch):
    import userdata
    tdir = tmp_path / "bundle" / "data_templates"
    tdir.mkdir(parents=True)
    (tdir / "experience.template.md").write_text("# Experience\n", encoding="utf-8")
    (tdir / "preferences.template.md").write_text("# Prefs\n", encoding="utf-8")
    (tdir / "preferences.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(userdata, "templates_dir", lambda: tdir)

    data = tmp_path / "data"
    monkeypatch.setattr(config, "USER_DATA_DIR", data)
    monkeypatch.setattr(config, "CACHE_DIR", data / "cache")
    monkeypatch.setattr(config, "OUTPUT_DIR", data / "output")

    created = userdata.bootstrap()
    assert "preferences.md" in created
    assert (data / "preferences.md").exists()
    assert (data / "cache").is_dir()
    assert (data / "output").is_dir()
