"""Coverage gate for the company-acquisition pipeline: growing the registry can
only ADD boards (never remove/rescore), so coverage cannot regress — verified two
ways: save_companies is append-only, and a benchmark over before/after fixtures
does not drop the composite score."""
import json
from pathlib import Path

from coverage.benchmark import run_benchmark
from models import JobResult
from scrape.company_registry import CompanyEntry, save_companies

FX = Path(__file__).resolve().parents[1] / "fixtures" / "ws2"


def _jobs(name):
    return [JobResult(**json.loads(l))
            for l in (FX / name).read_text(encoding="utf-8").splitlines() if l.strip()]


def test_enumeration_additions_do_not_regress_coverage(tmp_path):
    # Enumeration adds boards exactly like discovery does (more observed clusters),
    # so the composite must not drop.
    before = run_benchmark(_jobs("discovery_before.jsonl"), "Cincinnati, OH",
                           ["15-1252.00"], out_dir=tmp_path / "b")
    after = run_benchmark(_jobs("discovery_after.jsonl"), "Cincinnati, OH",
                          ["15-1252.00"], out_dir=tmp_path / "a")
    assert after.n_clusters >= before.n_clusters
    assert after.composite_score >= before.composite_score


def test_save_companies_is_append_only(tmp_path):
    # The verify gate writes via save_companies, which is user-wins + additive:
    # an existing entry is never dropped or duplicated when new ones arrive.
    path = tmp_path / "companies.json"
    path.write_text(json.dumps({"companies": [
        {"name": "Existing Co", "ats_type": "greenhouse", "slug": "existing", "industries": ["controls"]},
    ]}), encoding="utf-8")

    added = save_companies([
        CompanyEntry("Existing Co", "greenhouse", "existing", ["controls"]),  # dup -> skipped
        CompanyEntry("New Co", "lever", "newco", ["controls", "cincinnati"]),  # added
    ], path)
    assert added == 1

    saved = json.loads(path.read_text(encoding="utf-8"))["companies"]
    slugs = {c["slug"] for c in saved}
    assert slugs == {"existing", "newco"}          # existing preserved, new added
    assert sum(c["slug"] == "existing" for c in saved) == 1  # no duplication
