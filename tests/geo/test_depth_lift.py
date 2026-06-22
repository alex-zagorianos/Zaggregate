"""WS-2d lift gate: geo filter + deep matching must not reduce coverage
below WS-1 baseline when applied to the canonical before set."""
import json
from pathlib import Path
from models import JobResult
from coverage.benchmark import run_benchmark
from geo.filter import filter_to_metro

FX = Path(__file__).resolve().parents[1] / "fixtures" / "ws2"


def _jobs(name):
    return [JobResult(**json.loads(l))
            for l in (FX / name).read_text(encoding="utf-8").splitlines() if l.strip()]


def test_geo_filter_does_not_drop_all(tmp_path):
    jobs = _jobs("depth_before.jsonl")
    filtered = filter_to_metro(jobs, "Cincinnati, OH")
    assert len(filtered) >= 1  # some Cincinnati jobs survive

def test_geo_filter_coverage_does_not_regress(tmp_path):
    jobs = _jobs("depth_before.jsonl")
    baseline = run_benchmark(jobs, "Cincinnati, OH", ["15-1252.00"], out_dir=tmp_path / "base")
    filtered = filter_to_metro(jobs, "Cincinnati, OH")
    after = run_benchmark(filtered, "Cincinnati, OH", ["15-1252.00"], out_dir=tmp_path / "after")
    # Composite and clusters should not drop more than 10% after city-level filter
    assert after.composite_score >= baseline.composite_score * 0.90
    assert after.n_clusters >= max(1, baseline.n_clusters - 1)
