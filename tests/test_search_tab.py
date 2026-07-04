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


# ── S35 finding #19: manual-Search "skipped (no key)" surfacing ──────────────
# Pure static helpers on gui.SearchTab -- importable/callable without a Tk root
# (same pattern as gui.InboxTab._score_cell / _keyless_badge_text in
# tests/ui/test_inbox_surfacing.py).

def test_class_is_keyless_skipped_matches_by_source_prefix():
    import gui
    f = gui.SearchTab._class_is_keyless_skipped
    assert f("JoobleClient", ["jooble"]) is True
    assert f("CareerjetClient", ["careerjet"]) is True
    assert f("AdzunaClient", ["adzuna", "usajobs"]) is True
    assert f("USAJobsClient", ["adzuna", "usajobs"]) is True
    assert f("CareerOneStopClient", ["careeronestop"]) is True
    assert f("TheMuseClient", ["adzuna"]) is False
    assert f("TheMuseClient", []) is False
    assert f("", ["adzuna"]) is False


def test_progress_line_names_skip_reason_not_bare_zero():
    import gui
    f = gui.SearchTab._progress_line
    skipped = f("JoobleClient", 2, 5, 0, True)
    assert "skipped" in skipped.lower()
    assert "free key" in skipped.lower()
    assert "(0)" not in skipped
    normal = f("TheMuseClient", 2, 5, 0, False)
    assert normal == "source 2/5 — TheMuseClient (0)"


def test_health_summary_line_counts_real_skip_flag_not_error_text():
    import gui
    rows = [
        {"source": "TheMuseClient", "count": 5, "ok": True, "error": "",
         "skipped_keyless": False},
        {"source": "JoobleClient", "count": 0, "ok": True, "error": "",
         "skipped_keyless": True},
        {"source": "CareerjetClient", "count": 0, "ok": True, "error": "",
         "skipped_keyless": True},
    ]
    line = gui.SearchTab._health_summary_line(rows)
    assert "1 ok" in line
    assert "2 skipped (no key)" in line


def test_health_summary_line_falls_back_to_error_text_heuristic():
    # A row from an OLDER call site that never set skipped_keyless still gets
    # bucketed via the pre-existing error-string heuristic (backward compat).
    import gui
    rows = [{"source": "AdzunaClient", "count": 0, "ok": False,
             "error": "401 Unauthorized"}]
    line = gui.SearchTab._health_summary_line(rows)
    assert "1 skipped (no key)" in line


def test_health_summary_line_empty_when_no_rows():
    import gui
    assert gui.SearchTab._health_summary_line([]) == ""


def test_health_details_text_names_skip_reason():
    import gui
    rows = [{"source": "JoobleClient", "count": 0, "ok": True, "error": "",
             "skipped_keyless": True}]
    text = gui.SearchTab._health_details_text(rows)
    assert text == "JoobleClient: skipped — needs a free key"
