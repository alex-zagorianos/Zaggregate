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


def test_gui_verified_readd_upgrades_unverified_board(tmp_path):
    # The GUI '+ Add Companies' save contract: a board first kept-anyway
    # (unverified), then re-added after it probes live, is partitioned as
    # 'verified' and save_companies (the same call _do_gated_add makes) upgrades
    # the stored record in place — clearing the flag so it scrapes again. This is
    # the registry-level equivalent of the dialog's _do_gated_add save, without a
    # Tk display.
    import json
    from scrape.company_registry import (UNVERIFIED_FLAG, get_registry,
                                         is_unverified, save_companies)
    p = tmp_path / "companies.json"

    # 1) Kept-anyway unreachable board (what _do_gated_add flags + saves).
    dead = CompanyEntry("Flaky Co", "greenhouse", "flakyco",
                        ["controls_engineering"], {UNVERIFIED_FLAG: True})
    assert save_companies([dead], p) == 1
    assert "Flaky Co" not in {c.name for c in get_registry("controls_engineering", user_json=p)}

    # 2) Re-add after it verifies: partition_add_entries -> 'verified' (no flag),
    #    the exact list _do_gated_add hands to save_companies.
    fresh = CompanyEntry("Flaky Co", "greenhouse", "flakyco", ["controls_engineering"])
    verified, unreachable = partition_add_entries([fresh], {0: "live"})
    assert [e.name for e in verified] == ["Flaky Co"] and unreachable == []
    assert save_companies(verified, p) == 1        # counted as an upgrade

    entries = get_registry(include_unverified=True, user_json=p)
    flaky = next(e for e in entries if e.name == "Flaky Co")
    assert not is_unverified(flaky)
    assert "Flaky Co" in {c.name for c in get_registry("controls_engineering", user_json=p)}
    # Still one record — upgraded in place, not duplicated.
    raw = json.loads(p.read_text(encoding="utf-8"))
    assert sum(1 for c in raw["companies"] if c.get("slug") == "flakyco") == 1
