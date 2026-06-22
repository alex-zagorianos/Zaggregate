import json
from pathlib import Path
from models import JobResult
from coverage.benchmark import run_benchmark

FX = Path(__file__).resolve().parents[1] / "fixtures" / "ws2"

def _jobs(name):
    return [JobResult(**json.loads(l))
            for l in (FX / name).read_text(encoding="utf-8").splitlines() if l.strip()]

def test_discovery_increases_coverage(tmp_path):
    before = run_benchmark(_jobs("discovery_before.jsonl"), "Cincinnati, OH",
                           ["15-1252.00"], out_dir=tmp_path / "b")
    after = run_benchmark(_jobs("discovery_after.jsonl"), "Cincinnati, OH",
                          ["15-1252.00"], out_dir=tmp_path / "a")
    # More observed clusters from the discovered board -> coverage must not drop.
    assert after.n_clusters >= before.n_clusters
    assert after.composite_score >= before.composite_score
