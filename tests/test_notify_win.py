"""notify_win.py — message assembly/truncation, the notify() contract, the
notify_high_fit setting round-trip, and the daily_run trigger logic."""
from types import SimpleNamespace

import pytest

import config
import daily_run
import notify_win
from ui import settings as ui_settings


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "USER_DATA_DIR", tmp_path)
    return tmp_path


def _row(title="Engineer", company="Acme", score=90, is_new=True):
    return SimpleNamespace(title=title, company=company, score=score, is_new=is_new)


# ── the notify_high_fit setting (ui/settings.py) ──────────────────────────────

def test_notify_high_fit_default_false(isolated):
    assert ui_settings.get_notify_high_fit() is False


def test_notify_high_fit_roundtrip(isolated):
    ui_settings.set_notify_high_fit(True)
    assert ui_settings.get_notify_high_fit() is True
    ui_settings.set_notify_high_fit(False)
    assert ui_settings.get_notify_high_fit() is False


def test_notify_high_fit_coexists_with_theme(isolated):
    ui_settings.set_theme("dark")
    ui_settings.set_notify_high_fit(True)
    assert ui_settings.get_theme() == "dark"
    assert ui_settings.get_notify_high_fit() is True


# ── message assembly + truncation (notify_win.high_fit_message) ──────────────

def test_high_fit_message_none_when_no_qualifying_rows():
    rows = [_row(score=79), _row(score=50)]
    assert notify_win.high_fit_message(rows) is None


def test_high_fit_message_counts_and_picks_top_score():
    rows = [_row(title="Engineer I", company="Acme", score=80),
            _row(title="Staff Engineer", company="Beta Corp", score=95),
            _row(title="Low Fit", company="Gamma", score=60)]
    n, msg = notify_win.high_fit_message(rows)
    assert n == 2  # only the two >= HIGH_FIT_MIN=80 rows qualify
    assert "2 new high-fit matches" in msg
    assert "Staff Engineer" in msg and "Beta Corp" in msg and "(95)" in msg


def test_high_fit_message_singular_wording():
    rows = [_row(title="Solo Match", company="Acme", score=88)]
    n, msg = notify_win.high_fit_message(rows)
    assert n == 1
    assert "1 new high-fit match " in msg or "1 new high-fit match —" in msg
    assert "matches" not in msg


def test_high_fit_message_boundary_score_included():
    # Exactly HIGH_FIT_MIN (80) qualifies (>=, not >).
    rows = [_row(score=notify_win.HIGH_FIT_MIN)]
    built = notify_win.high_fit_message(rows)
    assert built is not None
    assert built[0] == 1


def test_truncate_title_to_63_chars():
    long_title = "T" * 100
    truncated = notify_win._truncate(long_title, notify_win._TITLE_MAX)
    assert len(truncated) == notify_win._TITLE_MAX
    assert truncated.endswith("…")


def test_truncate_body_to_255_chars():
    long_body = "B" * 400
    truncated = notify_win._truncate(long_body, notify_win._BODY_MAX)
    assert len(truncated) == notify_win._BODY_MAX
    assert truncated.endswith("…")


def test_truncate_short_text_unchanged():
    assert notify_win._truncate("short", notify_win._TITLE_MAX) == "short"


# ── notify() never raises / returns False on failure ──────────────────────────

def test_notify_returns_false_when_impl_raises(monkeypatch):
    def _boom(title, body):
        raise RuntimeError("simulated Win32 failure")
    monkeypatch.setattr(notify_win, "_notify_impl", _boom)
    assert notify_win.notify("Zaggregate", "hello") is False


def test_notify_returns_true_when_impl_succeeds(monkeypatch):
    monkeypatch.setattr(notify_win, "_notify_impl", lambda title, body: True)
    assert notify_win.notify("Zaggregate", "hello") is True


def test_notify_impl_off_windows_returns_false(monkeypatch):
    monkeypatch.setattr(notify_win.sys, "platform", "linux")
    assert notify_win._notify_impl("t", "b") is False


# ── notify_high_fit_matches wiring (message -> notify) ────────────────────────

def test_notify_high_fit_matches_calls_notify_when_qualifying(monkeypatch):
    calls = []
    monkeypatch.setattr(notify_win, "notify",
                        lambda title, body: calls.append((title, body)) or True)
    rows = [_row(score=90, title="Big Fit", company="Acme")]
    result = notify_win.notify_high_fit_matches(rows)
    assert result is True
    assert len(calls) == 1
    title, body = calls[0]
    assert title == "Zaggregate"
    assert "Big Fit" in body and "Acme" in body


def test_notify_high_fit_matches_skips_when_none_qualifying(monkeypatch):
    calls = []
    monkeypatch.setattr(notify_win, "notify",
                        lambda title, body: calls.append((title, body)) or True)
    rows = [_row(score=10)]
    result = notify_win.notify_high_fit_matches(rows)
    assert result is False
    assert calls == []


# ── daily_run trigger logic (daily_run._maybe_notify_high_fit) ────────────────
# Mirrors tests/test_byoai_auto_rank.py's pattern: call the extracted gated
# helper directly (rather than driving the whole main() pipeline), monkeypatching
# ui.settings.get_notify_high_fit and notify_win.notify_high_fit_matches so the
# gate can be observed in isolation.

def test_trigger_off_never_calls_notify(monkeypatch):
    monkeypatch.setattr(ui_settings, "get_notify_high_fit", lambda: False)
    calls = []
    monkeypatch.setattr(notify_win, "notify_high_fit_matches",
                        lambda rows: calls.append(rows) or True)
    qualified = [_row(score=95, is_new=True)]
    daily_run._maybe_notify_high_fit(qualified, added=1)
    assert calls == []


def test_trigger_on_with_qualifying_rows_calls_once_with_correct_set(monkeypatch):
    monkeypatch.setattr(ui_settings, "get_notify_high_fit", lambda: True)
    calls = []
    monkeypatch.setattr(notify_win, "notify_high_fit_matches",
                        lambda rows: calls.append(rows) or True)
    new_high = _row(title="New High Fit", company="Acme", score=90, is_new=True)
    old_high = _row(title="Old High Fit", company="Beta", score=90, is_new=False)
    new_low = _row(title="New Low Fit", company="Gamma", score=40, is_new=True)
    qualified = [new_high, old_high, new_low]
    daily_run._maybe_notify_high_fit(qualified, added=1)
    assert len(calls) == 1
    # Only the is_new rows are passed through (old_high is filtered out here;
    # the score threshold itself is notify_win.high_fit_message's job).
    passed = calls[0]
    assert new_high in passed and new_low in passed
    assert old_high not in passed


def test_trigger_on_with_no_qualifying_rows_not_called(monkeypatch):
    monkeypatch.setattr(ui_settings, "get_notify_high_fit", lambda: True)
    calls = []
    monkeypatch.setattr(notify_win, "notify_high_fit_matches",
                        lambda rows: calls.append(rows) or False)
    # No is_new rows at all -> the filtered set passed to notify_high_fit_matches
    # is empty; notify_high_fit_matches itself would find nothing qualifying.
    qualified = [_row(score=95, is_new=False)]
    daily_run._maybe_notify_high_fit(qualified, added=1)
    # The helper is still invoked (with an empty list) since added>=1 and the
    # setting is on; notify_high_fit_matches is what decides nothing qualifies.
    assert calls == [[]]


def test_trigger_zero_added_never_calls_even_when_on(monkeypatch):
    monkeypatch.setattr(ui_settings, "get_notify_high_fit", lambda: True)
    calls = []
    monkeypatch.setattr(notify_win, "notify_high_fit_matches",
                        lambda rows: calls.append(rows) or True)
    qualified = [_row(score=95, is_new=True)]
    daily_run._maybe_notify_high_fit(qualified, added=0)
    assert calls == []


def test_trigger_never_raises_on_notify_failure(monkeypatch):
    """A notify_win hiccup must never propagate out of the daily run."""
    monkeypatch.setattr(ui_settings, "get_notify_high_fit", lambda: True)

    def boom(rows):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(notify_win, "notify_high_fit_matches", boom)
    qualified = [_row(score=95, is_new=True)]
    daily_run._maybe_notify_high_fit(qualified, added=1)  # must not raise
