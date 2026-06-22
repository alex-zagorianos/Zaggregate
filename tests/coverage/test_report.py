import json
from coverage.report import CoverageReport, scope_hash, human_summary, persist

def _r(**kw):
    base = dict(scope_hash="abc", area="A", window="W", soc_grouping="g", source_ids=["a", "b"],
               composite_score=42.0, cov_cr=0.5, cov_cr_ci=(0.4, 0.6), cov_upper=120.0, c_hat=0.8,
               cov_proxy_weighted=None, jolts_verdict="skip", dedup_f1=None, per_soc={}, n_clusters=10,
               n_raw=12, paths_used={"cr": "chapman"})
    base.update(kw)
    return CoverageReport(**base)

def test_scope_hash_pinned():
    import hashlib
    expect = hashlib.sha1("A|W|g|a,b".encode()).hexdigest()[:12]
    assert scope_hash("A", "W", "g", ["b", "a"]) == expect  # sorted sources

def test_to_dict_from_dict_roundtrip():
    r = _r()
    assert CoverageReport.from_dict(r.to_dict()) == r

def test_human_summary_handles_none_legs():
    assert "Composite" in human_summary(_r(cov_cr=None, cov_proxy_weighted=None))

def test_persist_writes_run_and_rollup(tmp_path):
    r = _r()
    p = persist(r, tmp_path)
    assert p.exists()
    assert (tmp_path / "runs.jsonl").read_text(encoding="utf-8").strip()
