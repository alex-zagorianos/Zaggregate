import sys
from pathlib import Path

import config


def test_user_data_dir_env_override(monkeypatch, tmp_path):
    """JOBPROGRAM_DATA env var overrides the data folder location anywhere."""
    target = tmp_path / "mydata"
    monkeypatch.setenv("JOBPROGRAM_DATA", str(target))
    assert config._get_user_data_dir() == Path(str(target))


def test_user_data_dir_dev_is_repo_root(monkeypatch):
    """Dev (non-frozen) keeps the current files-at-repo-root layout."""
    monkeypatch.delenv("JOBPROGRAM_DATA", raising=False)
    monkeypatch.setattr(config, "_is_frozen", lambda: False)
    assert config._get_user_data_dir() == Path(config.__file__).parent


def test_user_data_dir_frozen_prefers_exe_data(monkeypatch, tmp_path):
    """Frozen: ./data beside the exe when that dir is writable."""
    monkeypatch.delenv("JOBPROGRAM_DATA", raising=False)
    monkeypatch.setattr(config, "_is_frozen", lambda: True)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "JobProgram.exe"))
    assert config._get_user_data_dir() == tmp_path / "data"


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
