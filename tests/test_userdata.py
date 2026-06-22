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
