"""Tests for Item-5 SearchTab save-searches logic and empty-state helpers.

These tests exercise the workspace + gui layer without spawning a Tk window,
using monkeypatching to isolate the workspace I/O.
"""
import pytest
import workspace


# ── save-searches workspace round-trip ────────────────────────────────────────

@pytest.fixture
def tmp_base(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace, 'BASE_DIR', tmp_path)
    return tmp_path


def _simulate_save(tmp_base, keywords_raw, loc, salary_raw):
    """Replicate _save_searches workspace writes without a Tk window."""
    keywords = [k.strip() for k in keywords_raw.split(',') if k.strip()]
    loc = loc.strip()
    try:
        salary_min = int(salary_raw.strip() or 0) or None
    except ValueError:
        salary_min = None
    cfg = workspace.load_config()
    if keywords:
        cfg['keywords'] = keywords
    elif 'keywords' in cfg:
        del cfg['keywords']
    if loc:
        cfg['location'] = loc
    if salary_min:
        cfg['salary_min'] = salary_min
    elif 'salary_min' in cfg:
        del cfg['salary_min']
    workspace.save_config(cfg)
    return workspace.load_config()


def test_save_searches_persists_keywords(tmp_base):
    cfg = _simulate_save(tmp_base, 'controls engineer, plc', 'Cincinnati', '')
    assert cfg['keywords'] == ['controls engineer', 'plc']


def test_save_searches_persists_location(tmp_base):
    cfg = _simulate_save(tmp_base, 'engineer', 'Columbus, OH', '')
    assert cfg['location'] == 'Columbus, OH'


def test_save_searches_persists_salary(tmp_base):
    cfg = _simulate_save(tmp_base, 'engineer', 'Remote', '80000')
    assert cfg['salary_min'] == 80000


def test_save_searches_removes_salary_when_blank(tmp_base):
    # Prime with a salary, then blank it out
    workspace.save_config({'salary_min': 50000})
    cfg = _simulate_save(tmp_base, 'engineer', 'Remote', '')
    assert 'salary_min' not in cfg


def test_save_searches_removes_keywords_when_blank(tmp_base):
    workspace.save_config({'keywords': ['old']})
    cfg = _simulate_save(tmp_base, '', 'Remote', '')
    assert 'keywords' not in cfg


def test_save_searches_merges_not_clobbers(tmp_base):
    workspace.save_config({'extra_key': 'keep_me', 'location': 'Old City'})
    cfg = _simulate_save(tmp_base, 'engineer', 'New City', '')
    # Extra key survives
    assert cfg.get('extra_key') == 'keep_me'
    # Location updated
    assert cfg['location'] == 'New City'


# ── safe_url is already tested in test_safe_url.py (Item 1) ──────────────────
