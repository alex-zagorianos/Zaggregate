import json
from pathlib import Path
import pytest
from models import JobResult
from coverage.benchmark import run_benchmark

FX = Path(__file__).resolve().parents[1] / "fixtures" / "coverage"
TOL = 2.0

def _jobs():
    return [JobResult(**json.loads(l)) for l in (FX / "cached_run.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]

def _baseline():
    return json.loads((FX / "baseline.json").read_text(encoding="utf-8"))

@pytest.fixture
def report(tmp_path):
    return run_benchmark(_jobs(), area="Cincinnati, OH", soc_groups=["15-1252.00"], out_dir=tmp_path)

def test_score_within_tolerance(report):
    base = _baseline()["composite_score"]
    assert abs(report.composite_score - base) <= TOL
    assert report.composite_score >= base - TOL  # no silent regression

def test_expected_legs_and_path_match(report):
    base = _baseline()
    assert report.cov_cr is not None and report.c_hat is not None
    assert report.paths_used["cr"] == base["paths_used"]["cr"]
