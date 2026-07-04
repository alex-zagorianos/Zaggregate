"""Shared traversal-locked download helper (webui.downloads) — unit level.

The queue + resume download routes both go through ``send_locked`` / ``is_contained``
locked to ``workspace.output_dir()``. These tests assert the containment gate at the
function level (independent of any route) so the traversal defense is covered once,
centrally.
"""
import os

import pytest

import workspace
from webui import downloads


@pytest.fixture
def out_base(tmp_path, monkeypatch):
    # NB: the webui conftest's autouse _isolate_output_dir already points
    # workspace.output_dir at tmp_path/ws_output and creates it; re-point here
    # explicitly (belt-and-suspenders) with exist_ok so the two never collide.
    out = tmp_path / "ws_output"
    out.mkdir(exist_ok=True)
    monkeypatch.setattr(workspace, "output_dir", lambda slug=None: out)
    return out


def test_output_subtree_creates_and_resolves(out_base):
    sub = downloads.output_subtree("resumes")
    assert sub.exists() and sub.is_dir()
    assert sub == (out_base / "resumes").resolve()


def test_is_contained_real_file(out_base):
    (out_base / "r.docx").write_text("x")
    base = downloads.output_subtree()
    assert downloads.is_contained(base, "r.docx") == (base / "r.docx").resolve()


def test_is_contained_rejects_parent_traversal(out_base, tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("s")
    base = downloads.output_subtree()
    # ../secret.txt escapes the base -> None
    assert downloads.is_contained(base, f"..{os.sep}secret.txt") is None


def test_is_contained_rejects_absolute_escape(out_base, tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("s")
    base = downloads.output_subtree()
    assert downloads.is_contained(base, str(secret)) is None


def test_is_contained_rejects_directory(out_base):
    (out_base / "sub").mkdir()
    base = downloads.output_subtree()
    # a directory is not a file -> not served
    assert downloads.is_contained(base, "sub") is None


def test_is_contained_missing_file(out_base):
    base = downloads.output_subtree()
    assert downloads.is_contained(base, "nope.docx") is None
