"""Regression guards for the S36 Tk-free *_core extractions (setup_wizard_core,
help_core): the cores must import WITHOUT tkinter, the tk modules must re-export
the SAME objects (patch/call-target identity preserved), and the new pure helpers
(guide_sections / safe_extract_zip) behave as the web layer needs.
"""
import builtins
import io
import zipfile
from pathlib import Path

import pytest


def _import_without_tkinter(module_names):
    """Import the named modules with tkinter poisoned, proving they're Tk-free.
    Runs in-process (the modules are already import-safe elsewhere; this asserts
    they don't pull tkinter into their OWN import graph)."""
    real = builtins.__import__

    def guard(name, *a, **k):
        if name == "tkinter" or name.startswith("tkinter."):
            raise ImportError(f"tkinter blocked (proving {module_names} Tk-free)")
        return real(name, *a, **k)

    import importlib
    builtins.__import__ = guard
    try:
        return [importlib.import_module(n) for n in module_names]
    finally:
        builtins.__import__ = real


def test_cores_are_tk_free():
    mods = _import_without_tkinter(
        ["ui.setup_wizard_core", "ui.help_core", "ui.ai_setup"])
    swc, hc, ai = mods
    # Exercise the on-disk-contract entry points (no Tk needed).
    assert swc.build_preferences({"roles": ["x"]})["hard"]["target_roles"] == ["x"]
    assert swc.parse_salary_input("90k") == 90000
    assert hc.guide_sections()
    assert ai.build_setup_prompt()


def test_setup_wizard_reexports_core_identity():
    from ui import setup_wizard as sw
    from ui import setup_wizard_core as swc
    for name in ("build_preferences", "parse_salary_input", "structure_resume_text",
                 "_search_config", "apply", "is_onboarded", "mark_onboarded",
                 "prefill_from_existing", "connected_source_labels",
                 "preset_tokens", "_FIELD_PRESETS", "_token_to_preset_label"):
        assert getattr(sw, name) is getattr(swc, name), name


def test_help_reexports_core_identity():
    from ui import help as uihelp
    from ui import help_core as hc
    for name in ("GUIDE", "make_backup", "restore_backup", "auto_backup",
                 "backups_dir", "guide_sections", "safe_extract_zip",
                 "UnsafeZipEntry"):
        assert getattr(uihelp, name) is getattr(hc, name), name


# ── guide_sections ────────────────────────────────────────────────────────────
def test_guide_sections_folds_headings_and_bodies():
    from ui.help_core import guide_sections, GUIDE
    secs = guide_sections()
    # One section per heading (h1/h2).
    n_headings = sum(1 for tag, _ in GUIDE if tag in ("h1", "h2"))
    assert len(secs) == n_headings
    # Every section has a heading + a level; most carry body text.
    assert all(s["level"] in (1, 2) for s in secs)
    assert all("heading" in s and "body" in s for s in secs)
    # The first h1 is "Welcome" and its following body is joined in.
    assert secs[0]["heading"].startswith("Welcome")
    assert "finds jobs" in secs[0]["body"]


# ── safe_extract_zip (unit-level zip-slip defense) ────────────────────────────
def _zip(members):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in members.items():
            z.writestr(name, data)
    return buf.getvalue()


def test_safe_extract_zip_happy(tmp_path):
    from ui.help_core import safe_extract_zip
    src = tmp_path / "a.zip"
    src.write_bytes(_zip({"a.txt": b"1", "sub/b.txt": b"2"}))
    dest = tmp_path / "out"
    members = safe_extract_zip(str(src), dest)
    assert set(members) >= {"a.txt", "sub/b.txt"}
    assert (dest / "a.txt").read_bytes() == b"1"
    assert (dest / "sub" / "b.txt").read_bytes() == b"2"


@pytest.mark.parametrize("evil", ["../x.txt", "../../x.txt", "a/../../x.txt"])
def test_safe_extract_zip_refuses_traversal(tmp_path, evil):
    from ui.help_core import safe_extract_zip, UnsafeZipEntry
    src = tmp_path / "evil.zip"
    src.write_bytes(_zip({evil: b"pwned"}))
    dest = tmp_path / "out"
    with pytest.raises(UnsafeZipEntry):
        safe_extract_zip(str(src), dest)
    # Nothing escaped the dest tree.
    assert not (tmp_path / "x.txt").exists()
    assert not (tmp_path.parent / "x.txt").exists()


def test_safe_extract_zip_refuses_symlink(tmp_path):
    from ui.help_core import safe_extract_zip, UnsafeZipEntry
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        info = zipfile.ZipInfo("link")
        info.external_attr = (0o120777 << 16)   # symlink mode bits
        z.writestr(info, "/etc")
    src = tmp_path / "evil.zip"
    src.write_bytes(buf.getvalue())
    with pytest.raises(UnsafeZipEntry):
        safe_extract_zip(str(src), tmp_path / "out")
