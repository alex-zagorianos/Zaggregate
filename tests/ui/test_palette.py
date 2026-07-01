"""Command palette: pure filter logic + module/app import smoke."""
import gui  # must import cleanly (also covered by test_smoke)
from ui import palette


def test_filter_empty_returns_all():
    labels = ["Go to Inbox", "Go to Search", "Open the Guide"]
    assert palette.filter_commands(labels, "") == labels
    assert palette.filter_commands(labels, "   ") == labels


def test_filter_substring():
    labels = ["Go to Inbox", "Go to Search", "Open the Guide"]
    assert palette.filter_commands(labels, "search") == ["Go to Search"]
    assert "Go to Inbox" in palette.filter_commands(labels, "inbox")


def test_filter_subsequence_and_ranking():
    labels = ["Apply Queue", "Job Tracker"]
    r = palette.filter_commands(labels, "aqu")   # subsequence of "Apply Queue"
    assert "Apply Queue" in r
    # substring match ranks before a pure-subsequence match
    labels2 = ["Job Tracker", "Jab Trkr"]
    assert palette.filter_commands(labels2, "job")[0] == "Job Tracker"


def test_filter_no_match():
    assert palette.filter_commands(["Inbox"], "zzz") == []


def test_gui_imports():
    assert gui is not None
    assert hasattr(palette, "open_palette")
