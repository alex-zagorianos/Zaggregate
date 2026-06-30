"""Wave 0 ship-blocker regressions."""
import importlib
from pathlib import Path


def test_geography_missing_data_does_not_crash(monkeypatch):
    import coverage._paths as paths
    import coverage.geography as g
    monkeypatch.setattr(paths, "DATA_STATIC", Path(r"C:\__nonexistent__\data_static"))
    g._rows.cache_clear()
    # Must NOT raise even though the CBSA file is absent.
    assert g.metro_variants("Cincinnati")  # at least the bare area token
    from geo.filter import location_visible
    assert location_visible("San Francisco, CA", "ML Engineer", "Cincinnati",
                            "Local + remote") in (True, False)
    g._rows.cache_clear()


def test_scaffold_seeds_companies_json(tmp_path, monkeypatch):
    import config, userdata
    bundle = tmp_path / "bundle"
    (bundle / "data_templates").mkdir(parents=True)
    (bundle / "companies.json").write_text('{"companies": []}', encoding="utf-8")
    monkeypatch.setattr(config, "DATA_DIR", bundle)
    data_dir = tmp_path / "data"
    created = userdata.scaffold(data_dir)
    assert (data_dir / "companies.json").exists()
    assert "companies.json" in created
    # idempotent
    assert "companies.json" not in userdata.scaffold(data_dir)


def test_gui_log_fatal_writes_log(tmp_path, monkeypatch):
    import config
    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path)
    import gui
    tb = gui._log_fatal(ValueError("boom"))
    assert "boom" in tb
    assert (tmp_path / "gui_error.log").exists()
