import tkinter as tk
import pytest
import gui


@pytest.fixture
def root(monkeypatch):
    try:
        r = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    r.withdraw()
    gui.theme.apply_theme(r)
    yield r
    r.destroy()


def _picks():
    return [
        {"id": 1, "rank": 1, "title": "Software Developer", "company": "Acme",
         "location": "Cincinnati, OH", "fit": 92, "fit_why": "strong",
         "score": 70, "source": "adzuna", "url": "https://x/1"},
        {"id": 2, "rank": 2, "title": "Controls Eng", "company": "Beta",
         "location": "Remote", "fit": 85, "fit_why": "good",
         "score": 66, "source": "muse", "url": "https://x/2"},
    ]


def test_top_picks_renders_in_rank_order(root, monkeypatch):
    monkeypatch.setattr(gui.tracker_service, "top_picks", lambda n: _picks())
    tab = gui.TopPicksTab(root, on_change=None)
    assert list(tab._tree.get_children()) == ["1", "2"]
    assert tab._tree.set("1", "title") == "Software Developer"
    assert tab._showing_empty is False


def test_top_picks_empty_state(root, monkeypatch):
    monkeypatch.setattr(gui.tracker_service, "top_picks", lambda n: [])
    tab = gui.TopPicksTab(root, on_change=None)
    assert not tab._tree.get_children()
    assert tab._showing_empty is True


def test_top_picks_n_reads_all(root, monkeypatch):
    captured = {}
    monkeypatch.setattr(gui.tracker_service, "top_picks",
                        lambda n: captured.update(n=n) or [])
    tab = gui.TopPicksTab(root, on_change=None)
    tab._topn.set("All")
    tab.refresh()
    assert captured["n"] == 0
