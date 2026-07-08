"""Search Discovery — Tk 'Discover keywords' dialog (Phase 9).

The data logic lives in Tk-free module-level helpers in ``ui.tab_search``
(discovery_tier_rows / discovery_activate / discovery_deactivate /
discovery_format_openings / discovery_pool_rows / discovery_active_or_core_terms)
so it's exercised here without constructing any widget. A couple of
headless-safe smoke tests at the bottom build the real ``DiscoverKeywordsDialog``
under a Tk root (mirrors tests/ui/test_ai_setup_gui.py's ``root`` fixture) and
skip cleanly when no display is available.
"""
import pytest

import workspace
from tracker import db
from search.discovery import pool
from ui.tab_search import (
    DiscoverKeywordsDialog,
    discovery_active_or_core_terms,
    discovery_activate,
    discovery_deactivate,
    discovery_format_openings,
    discovery_pool_rows,
    discovery_tier_rows,
)


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """Standard tracker.db fixture (search-discovery-plan precedent) so
    pool.upsert_terms/set_status/get_pool hit an isolated, disposable DB."""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "tracker.db")
    db.init_db()
    return tmp_path


@pytest.fixture
def cfg_store(monkeypatch):
    """In-memory search config (mirrors tests/webui/test_discovery_api.py's
    fixture) so activate/deactivate config writes never touch a real project."""
    store = {"keywords": []}
    monkeypatch.setattr(workspace, "load_config", lambda slug=None: dict(store))
    monkeypatch.setattr(workspace, "save_config",
                        lambda cfg, slug=None: store.update(cfg))
    monkeypatch.setattr(workspace, "active_slug", lambda: "test")
    monkeypatch.setattr(workspace, "pin_active", lambda slug=None: None)
    monkeypatch.setattr(workspace, "unpin_active", lambda: None)
    return store


# ── discovery_tier_rows: propose()-dict -> Treeview/pool-ready rows ───────────
def test_tier_rows_flattens_all_three_tiers_in_order():
    result = {
        "core": [{"term": "Diesel Mechanic", "source": "onet"}],
        "adjacent": [{"term": "Fleet Technician", "source": "related_soc"}],
        "exploratory": [{"term": "Heavy Equipment Tech", "source": "related_soc"}],
    }
    rows = discovery_tier_rows(result)
    assert [r["tier"] for r in rows] == ["core", "adjacent", "exploratory"]
    assert rows[0] == {"term": "Diesel Mechanic", "tier": "core",
                       "source": "onet", "status": "suggested"}


def test_tier_rows_skips_blank_terms_and_defaults_source():
    result = {"core": [{"term": "  "}, {"term": "Welder"}], "adjacent": [], "exploratory": []}
    rows = discovery_tier_rows(result)
    assert len(rows) == 1
    assert rows[0]["term"] == "Welder"
    assert rows[0]["source"] == "onet"          # default when the item omits it


def test_tier_rows_never_raises_on_missing_or_malformed_input():
    assert discovery_tier_rows(None) == []
    assert discovery_tier_rows({}) == []
    assert discovery_tier_rows({"core": [None, {}]}) == []


# ── discovery_format_openings / discovery_pool_rows ──────────────────────────
def test_format_openings_never_checked_is_em_dash():
    assert discovery_format_openings(None) == "—"
    assert discovery_format_openings({"term": "x", "yield_count": None}) == "—"


def test_format_openings_shows_zero_count_never_hides_it():
    # Inclusion over precision: a zero count is SHOWN, not hidden/dropped.
    assert discovery_format_openings({"term": "x", "yield_count": 0}) == "0"
    assert discovery_format_openings({"term": "x", "yield_count": 42}) == "42"


def test_format_openings_appends_low_activity_nudge_in_plain_english():
    row = {"term": "Diesel Mechanic", "yield_count": 0}
    text = discovery_format_openings(row, low_activity_terms={"Diesel Mechanic"})
    assert "0" in text
    assert "hasn't found much lately" in text
    # No internal jargon ever reaches the label.
    assert "probe" not in text.lower() and "yield" not in text.lower()


def test_pool_rows_shapes_and_preserves_order():
    raw = [
        {"term": "B", "tier": "core", "status": "active", "yield_count": 3},
        {"term": "A", "tier": "adjacent", "status": "suggested", "yield_count": None},
    ]
    shaped = discovery_pool_rows(raw)
    assert [r["term"] for r in shaped] == ["B", "A"]
    assert shaped[0]["openings"] == "3"
    assert shaped[1]["openings"] == "—"
    assert shaped[1]["status"] == "suggested"


# ── discovery_active_or_core_terms ────────────────────────────────────────────
def test_active_or_core_prefers_active_terms():
    tier_rows = [{"term": "Core Title", "tier": "core"}]
    assert discovery_active_or_core_terms(["Active Title"], tier_rows) == ["Active Title"]


def test_active_or_core_falls_back_to_core_tier():
    tier_rows = [{"term": "Core Title", "tier": "core"},
                 {"term": "Adjacent Title", "tier": "adjacent"}]
    assert discovery_active_or_core_terms([], tier_rows) == ["Core Title"]


def test_active_or_core_empty_input_never_raises():
    assert discovery_active_or_core_terms([], []) == []
    assert discovery_active_or_core_terms(None, None) == []


# ── discovery_activate / discovery_deactivate: cfg + pool in sync ────────────
def test_activate_mirrors_into_cfg_keywords_and_pool(tmp_db):
    cfg = {"keywords": []}
    ok = discovery_activate(cfg, "Diesel Mechanic", tier="core", source="onet")
    assert ok is True
    assert cfg["keywords"] == ["Diesel Mechanic"]
    assert cfg["discovery_enabled"] is True
    assert pool.get_term("Diesel Mechanic")["status"] == "active"


def test_activate_is_idempotent_no_duplicate_keyword(tmp_db):
    cfg = {"keywords": ["Diesel Mechanic"]}
    discovery_activate(cfg, "Diesel Mechanic")
    assert cfg["keywords"] == ["Diesel Mechanic"]      # not duplicated


def test_activate_blank_term_is_a_noop(tmp_db):
    cfg = {"keywords": ["Existing"]}
    ok = discovery_activate(cfg, "   ")
    assert ok is False
    assert cfg == {"keywords": ["Existing"]}           # untouched


def test_deactivate_removes_from_cfg_and_marks_pool_inactive(tmp_db):
    cfg = {"keywords": []}
    discovery_activate(cfg, "Welder")
    assert "Welder" in cfg["keywords"]
    ok = discovery_deactivate(cfg, "Welder")
    assert ok is True
    assert "Welder" not in cfg["keywords"]
    assert pool.get_term("Welder")["status"] == "inactive"


def test_deactivate_blank_term_is_a_noop(tmp_db):
    cfg = {"keywords": ["Existing"]}
    ok = discovery_deactivate(cfg, "")
    assert ok is False
    assert cfg["keywords"] == ["Existing"]


def test_deactivate_unknown_term_still_removes_from_cfg(tmp_db):
    # A term that was never in the pool (e.g. hand-typed then removed before
    # ever being suggested) must still be droppable from cfg['keywords'].
    cfg = {"keywords": ["Ghost Title"]}
    ok = discovery_deactivate(cfg, "Ghost Title")
    assert ok is True
    assert cfg["keywords"] == []


# ── end-to-end pipeline with a real propose() call (still Tk-free) ───────────
def test_propose_to_pool_pipeline_is_tk_free(tmp_db):
    from search.discovery import propose
    result = propose.propose("welder")
    rows = discovery_tier_rows(result)
    assert rows                                        # a resolvable field yields rows
    inserted = pool.upsert_terms(rows)
    assert inserted == len(rows)                        # first pass: all new
    suggested = pool.get_pool(status="suggested")
    assert {r["term"] for r in rows} <= {r["term"] for r in suggested}


# ── headless-safe Tk widget smoke tests (skip cleanly with no display) ───────
@pytest.fixture
def root(tmp_db, monkeypatch):
    import tkinter as tk
    try:
        r = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    from ui import theme
    theme.apply_theme(r)
    yield r
    try:
        r.destroy()
    except tk.TclError:
        pass


def test_dialog_builds_with_empty_pool(root):
    dlg = DiscoverKeywordsDialog(root)
    root.update_idletasks()
    assert dlg._tree["columns"] == ("term", "tier", "status", "openings")
    assert dlg._tree.get_children() == ()
    dlg.destroy()


def test_dialog_suggest_populates_tree(root):
    dlg = DiscoverKeywordsDialog(root)
    root.update_idletasks()
    dlg._field.set("welder")
    dlg._on_suggest()
    root.update_idletasks()
    assert dlg._tree.get_children()
    assert dlg._last_tier_rows
    dlg.destroy()


def test_dialog_activate_updates_cfg_and_is_safe_without_a_searchtab_parent(
        root, cfg_store):
    # `root` here is a bare Tk() (not a SearchTab) -- _sync_parent_cfg's
    # best-effort AttributeError guard must swallow the missing `_kw` widget.
    dlg = DiscoverKeywordsDialog(root)
    root.update_idletasks()
    dlg._field.set("welder")
    dlg._on_suggest()
    root.update_idletasks()
    term = dlg._tree.get_children()[0]
    dlg._tree.selection_set(term)
    dlg._on_activate()
    assert term in cfg_store["keywords"]
    assert pool.get_term(term)["status"] == "active"
    dlg.destroy()
