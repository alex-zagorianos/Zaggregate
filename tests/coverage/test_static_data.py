import json, re
from pathlib import Path

DATA_STATIC = Path(__file__).resolve().parents[2] / "data_static"
SOC_RE = re.compile(r"^\d{2}-\d{4}(\.\d{2})?$")

def _onet_rows():
    p = DATA_STATIC / "onet_soc_alt_titles.tsv"
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        yield line.split("\t")

def test_onet_file_parses():
    rows = list(_onet_rows())
    assert rows, "no O*NET rows"
    for r in rows:
        assert len(r) == 3, r
        assert SOC_RE.match(r[1]), r[1]

def test_onet_has_known_titles():
    hits = [r for r in _onet_rows() if r[0].casefold() == "software developer"]
    assert hits and hits[0][1].startswith("15-1252")

def test_cbsa_file_parses():
    p = DATA_STATIC / "cbsa_delineation.csv"
    lines = p.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "cbsa_code,cbsa_title,principal_city,state"
    assert len(lines) > 1

def test_aliases_json_loads():
    d = json.loads((DATA_STATIC / "company_aliases.json").read_text(encoding="utf-8"))
    assert isinstance(d, dict)
    assert all(isinstance(k, str) and isinstance(v, str) for k, v in d.items())
