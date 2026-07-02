"""P0-6: the '+ Add Companies' dialog gates saving on the live probe verdict.

The pure classification helper (partition_add_entries) is unit-tested here; the
full dialog is a Tk Toplevel that needs a display, so only the verdict logic —
the part that decides what gets saved as verified vs unreachable — is covered
directly. The registry-side effects (unverified boards excluded from scraping)
live in tests/test_discovery_persist.py.
"""
import gui
from gui import partition_add_entries
from scrape.company_registry import CompanyEntry


def _e(name, ats="greenhouse"):
    return CompanyEntry(name, ats, name.lower())


def test_live_and_direct_are_verified_unreachable_is_not():
    entries = [_e("Live"), _e("Direct", "direct"), _e("Dead")]
    status = {0: "live", 1: "direct", 2: "unreachable"}
    verified, unreachable = partition_add_entries(entries, status)
    assert [e.name for e in verified] == ["Live", "Direct"]
    assert [e.name for e in unreachable] == ["Dead"]


def test_unprobed_entry_is_treated_as_unreachable():
    # unknown-is-unsafe: a board we never confirmed live must not be saved as
    # verified just because the user skipped the Validate button.
    entries = [_e("Probed"), _e("Skipped")]
    status = {0: "live"}                        # index 1 never probed
    verified, unreachable = partition_add_entries(entries, status)
    assert [e.name for e in verified] == ["Probed"]
    assert [e.name for e in unreachable] == ["Skipped"]


def test_all_unreachable_yields_no_verified():
    entries = [_e("A"), _e("B")]
    verified, unreachable = partition_add_entries(entries, {0: "unreachable",
                                                            1: "unreachable"})
    assert verified == []
    assert [e.name for e in unreachable] == ["A", "B"]


def test_all_verified_yields_no_unreachable():
    entries = [_e("A"), _e("B", "direct")]
    verified, unreachable = partition_add_entries(entries, {0: "live", 1: "direct"})
    assert [e.name for e in verified] == ["A", "B"]
    assert unreachable == []


def test_dialog_class_exposes_gated_add_paths():
    # Guard the wiring: the dialog no longer saves the full list blindly; it
    # routes through the gated path.
    assert hasattr(gui.AddCompaniesDialog, "_do_gated_add")
    assert hasattr(gui.AddCompaniesDialog, "_add")
