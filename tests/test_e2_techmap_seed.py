"""E2 Techmap Kaggle registry seed: DatasetSpec wiring + parse a tiny fixture
slice (employer + careers/ATS URL per row) through the same detect_ats ->
probe-verify funnel jobhive uses. Probe is faked (no network)."""
import pytest

from discover import dataset_seed as ds


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


# A tiny Techmap-shaped CSV slice: one row per posting, employer in `company`,
# careers/ATS URL in `url`. Two resolve to real ATS boards; one has no board URL.
_TECHMAP_CSV = (
    "name,company,url,orgAddress,dateCreated\n"
    "Registered Nurse,Acme Health,https://boards.greenhouse.io/acmehealth/jobs/1,Cincinnati OH,2021-09-01\n"
    "Staff Nurse,Beta Care,https://jobs.lever.co/betacare/abc,Dayton OH,2021-09-02\n"
    "Aide,Gamma Home,https://gammahome.example.com/careers,Columbus OH,2021-09-03\n"
)


def test_techmap_spec_registered():
    assert "techmap-intl-2021-09" in ds.TECHMAP_DATASETS
    spec = ds.TECHMAP_DATASETS["techmap-intl-2021-09"]
    assert spec.kaggle_ref.startswith("techmap/")
    assert "license" in spec.license_note.lower()


def test_techmap_column_map_extracts_boards_from_url(tmp_path):
    # load_ats_dataset with the Techmap column map must resolve the greenhouse +
    # lever boards out of the URL column (ats/slug auto-detect -> None -> URL path).
    spec = ds.TECHMAP_DATASETS["techmap-intl-2021-09"]
    cols = ds._spec_column_map(spec)
    path = _write(tmp_path, "techmap.csv", _TECHMAP_CSV)
    boards = ds.load_ats_dataset(path, column_map=cols)
    assert set(boards.get("greenhouse", set())) == {"acmehealth"}
    assert set(boards.get("lever", set())) == {"betacare"}
    # The bare careers URL resolves to a 'direct' board (detect_ats fallback) —
    # captured, but 'direct' is not PROBEABLE so it drops at the verify gate.
    assert "greenhouse" in boards and "lever" in boards


def test_seed_from_techmap_probe_verify(tmp_path):
    path = _write(tmp_path, "techmap.csv", _TECHMAP_CSV)
    companies_json = tmp_path / "companies.json"

    # Fake probe: greenhouse board "live" (5 jobs), lever board "dead" (0).
    def fake_probe(entry):
        return 5 if entry.ats_type == "greenhouse" else 0

    summary = ds.seed_from_techmap(
        path, spec_key="techmap-intl-2021-09", industry="nursing",
        probe=fake_probe, companies_json_path=companies_json,
        existing=set(), dry_run=True)
    verified_ats = {e.ats_type for e, _ in summary["verified"]}
    assert "greenhouse" in verified_ats     # live board kept
    assert "lever" not in verified_ats      # dead board dropped
    # The spec block carries the license-check note.
    assert summary["spec"]["kaggle_ref"] == "techmap/international-job-postings-september-2021"
    assert summary["spec"]["license_note"]


def test_seed_from_techmap_unknown_spec_raises(tmp_path):
    path = _write(tmp_path, "x.csv", _TECHMAP_CSV)
    with pytest.raises(ValueError):
        ds.seed_from_techmap(path, spec_key="does-not-exist")


def test_seed_from_techmap_industry_tag(tmp_path):
    path = _write(tmp_path, "techmap.csv", _TECHMAP_CSV)

    def fake_probe(entry):
        return 3

    summary = ds.seed_from_techmap(
        path, spec_key="techmap-us-2023-05-05", industry="nursing",
        probe=fake_probe, existing=set(), dry_run=True)
    for entry, _ in summary["verified"]:
        assert "nursing" in entry.industries
