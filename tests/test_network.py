"""network.py — CSV parsers, canonical matching, and the user-level store (B4).

Storage isolation: every test repoints ``config.USER_DATA_DIR`` at a tmp dir so
network.json never touches real user data.
"""
import json

import pytest

import config
import network


@pytest.fixture(autouse=True)
def _tmp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "USER_DATA_DIR", tmp_path)
    return tmp_path


# ── LinkedIn parser (preamble + tolerant columns) ─────────────────────────────

_LINKEDIN_WITH_PREAMBLE = """\
Notes:
"When exporting your connection data, you may notice that some of the fields are
empty. Please try again in a few hours."

First Name,Last Name,URL,Email Address,Company,Position,Connected On
Jane,Doe,https://www.linkedin.com/in/janedoe,jane@example.com,Acme Inc.,Staff Engineer,01 Jan 2024
John,Roe,https://www.linkedin.com/in/johnroe,,Acme,Recruiter,02 Feb 2024
Sam,Poe,https://www.linkedin.com/in/sampoe,,,Consultant,03 Mar 2024
"""


def test_linkedin_preamble_is_stripped_and_columns_parsed():
    rows = network.parse_connections_csv(_LINKEDIN_WITH_PREAMBLE, "linkedin")
    assert [r["name"] for r in rows] == ["Jane Doe", "John Roe", "Sam Poe"]
    assert rows[0]["company"] == "Acme Inc." and rows[0]["position"] == "Staff Engineer"
    # Row with no company is KEPT (unmatchable), never dropped.
    assert rows[2]["name"] == "Sam Poe" and rows[2]["company"] == ""
    assert rows[2]["company_key"] == ""
    # Acme Inc. and Acme canonicalize to the same key (suffix stripped).
    assert rows[0]["company_key"] == rows[1]["company_key"] != ""


def test_linkedin_without_preamble_still_parses():
    text = ("First Name,Last Name,Company,Position\n"
            "Amy,Ling,Globex,PM\n")
    rows = network.parse_connections_csv(text, "linkedin")
    assert rows == [{"name": "Amy Ling", "company": "Globex", "position": "PM",
                     "source": "linkedin", "company_key": network.company_key("Globex")}]


def test_weird_column_order_and_case():
    # Columns out of order, mixed case, extra column, BOM on the first header.
    text = ("﻿POSITION,company,Last Name,First Name,Connected On\n"
            "VP Eng,Initech LLC,Waddams,Milton,05 May 2024\n")
    rows = network.parse_connections_csv(text, "linkedin")
    assert rows[0]["name"] == "Milton Waddams"
    assert rows[0]["company"] == "Initech LLC"
    assert rows[0]["position"] == "VP Eng"


# ── Google Contacts parser ─────────────────────────────────────────────────────

def test_google_contacts_organization_columns():
    text = ("Name,Given Name,Family Name,Organization 1 - Name,Organization 1 - Title\n"
            "Grace Hopper,Grace,Hopper,Umbrella Corp,Rear Admiral\n"
            ",Ada,Lovelace,Analytical Engines,Programmer\n")
    rows = network.parse_connections_csv(text, "google")
    assert rows[0]["name"] == "Grace Hopper"          # explicit Name column wins
    assert rows[0]["company"] == "Umbrella Corp"
    assert rows[0]["position"] == "Rear Admiral"
    assert rows[0]["source"] == "google"
    # No 'Name' value -> First+Last fallback.
    assert rows[1]["name"] == "Ada Lovelace"


def test_google_organization_name_variant():
    text = ("Name,Organization Name,Organization Title\n"
            "Alan Kay,Xerox PARC,Fellow\n")
    rows = network.parse_connections_csv(text, "google")
    assert rows[0]["company"] == "Xerox PARC" and rows[0]["position"] == "Fellow"


def test_empty_and_blank_text_return_empty():
    assert network.parse_connections_csv("", "linkedin") == []
    assert network.parse_connections_csv("   \n  \n", "google") == []


# ── canonical matching (suffix/case + no false positives) ─────────────────────

def test_company_key_normalizes_suffix_and_case():
    assert network.company_key("Acme, Inc.") == network.company_key("ACME")
    assert network.company_key("Globex LLC") == network.company_key("globex")
    assert network.company_key("") == ""
    assert network.company_key("   ") == ""


def test_matches_for_suffix_and_case_variants():
    network.import_text(
        "First Name,Last Name,Company,Position\n"
        "Jane,Doe,Acme Inc.,Staff Engineer\n"
        "John,Roe,ACME,Recruiter\n"
        "Sue,Kim,Globex Corporation,Analyst\n", "linkedin")
    acme = network.matches_for("acme")
    assert {c["name"] for c in acme} == {"Jane Doe", "John Roe"}
    # Distinct company -> no false positive.
    assert [c["name"] for c in network.matches_for("Globex")] == ["Sue Kim"]
    assert network.matches_for("Nonexistent Co") == []
    # A blank company never matches unmatchable (no-company) contacts.
    assert network.matches_for("") == []


def test_match_counts_bulk():
    network.import_text(
        "First Name,Last Name,Company\n"
        "A,A,Acme\nB,B,Acme Inc.\nC,C,Globex\n", "linkedin")
    counts = network.match_counts(["Acme", "Globex", "Unknown"])
    assert counts == {"Acme": 2, "Globex": 1}   # Unknown omitted (0 matches)


# ── storage: merge-dedup + clear ───────────────────────────────────────────────

def test_import_merges_and_dedups(_tmp_store):
    first = network.import_text(
        "First Name,Last Name,Company\nJane,Doe,Acme\nJohn,Roe,Acme\n", "linkedin")
    assert first == {"added": 2, "total": 2}
    # Re-import the same Jane (same name+company) + a new person -> only 1 added.
    second = network.import_text(
        "First Name,Last Name,Company\nJane,Doe,Acme Inc.\nSue,Kim,Globex\n", "linkedin")
    assert second == {"added": 1, "total": 3}    # Jane deduped by (name, canon company)
    # The store file lives under the tmp USER_DATA_DIR, not elsewhere.
    assert (_tmp_store / "network.json").exists()
    saved = json.loads((_tmp_store / "network.json").read_text(encoding="utf-8"))
    assert len(saved["contacts"]) == 3
    assert saved["last_import"]["source"] == "linkedin"


def test_clear_empties_store():
    network.import_text("First Name,Company\nJane,Acme\n", "linkedin")
    assert network.summary()["total"] == 1
    assert network.clear() == 1
    assert network.summary()["total"] == 0
    assert network.clear() == 0                  # idempotent


def test_summary_counts_distinct_companies():
    network.import_text(
        "First Name,Company\nA,Acme\nB,Acme Inc.\nC,Globex\nD,\n", "linkedin")
    s = network.summary()
    assert s["total"] == 4                        # no-company row kept
    assert s["companies"] == 2                     # Acme (2 rows) + Globex, blank excluded


def test_store_isolation_across_user_data_dirs(tmp_path, monkeypatch):
    a = tmp_path / "a"; b = tmp_path / "b"
    a.mkdir(); b.mkdir()
    monkeypatch.setattr(config, "USER_DATA_DIR", a)
    network.import_text("First Name,Company\nJane,Acme\n", "linkedin")
    monkeypatch.setattr(config, "USER_DATA_DIR", b)
    assert network.summary()["total"] == 0        # separate store, no leak
    assert (a / "network.json").exists()
    assert not (b / "network.json").exists()
