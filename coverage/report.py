from __future__ import annotations
import dataclasses, hashlib, json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

@dataclass
class CoverageReport:
    scope_hash: str
    area: str
    window: str
    soc_grouping: str
    source_ids: list
    composite_score: float
    cov_cr: float | None
    cov_cr_ci: tuple | None
    cov_upper: float | None
    c_hat: float | None
    cov_proxy_weighted: float | None
    jolts_verdict: str
    dedup_f1: float | None
    per_soc: dict
    n_clusters: int
    n_raw: int
    paths_used: dict

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d["cov_cr_ci"] = list(self.cov_cr_ci) if self.cov_cr_ci is not None else None
        return d

    @classmethod
    def from_dict(cls, d) -> "CoverageReport":
        d = dict(d)
        if d.get("cov_cr_ci") is not None:
            d["cov_cr_ci"] = tuple(d["cov_cr_ci"])
        return cls(**d)

def scope_hash(area: str, window: str, soc_grouping: str, source_ids: list) -> str:
    payload = "|".join([area, window, soc_grouping, ",".join(sorted(source_ids))])
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]

def human_summary(report: CoverageReport) -> str:
    ci = f" CI{tuple(round(x, 1) for x in report.cov_cr_ci)}" if report.cov_cr_ci else ""
    def fmt(v, nd):
        return v if v is None else round(v, nd)
    return "\n".join([
        f"Coverage [{report.area} | {report.window} | {report.soc_grouping}]  scope={report.scope_hash}",
        f"  Composite score : {report.composite_score:.1f} / 100",
        f"  Capture-recapture: {fmt(report.cov_cr, 3)}{ci}",
        f"  Ceiling (Chao1) : {fmt(report.cov_upper, 1)}",
        f"  Completeness    : {fmt(report.c_hat, 3)}",
        f"  Reference proxy : {fmt(report.cov_proxy_weighted, 3)}",
        f"  JOLTS gate      : {report.jolts_verdict}",
        f"  Dedup F1        : {fmt(report.dedup_f1, 3)}",
        f"  Clusters/raw    : {report.n_clusters} / {report.n_raw}",
        f"  Paths used      : {report.paths_used}",
    ])

def persist(report: CoverageReport, base_dir) -> "Path":
    base = Path(base_dir)
    run_dir = base / "runs" / report.scope_hash
    run_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_path = run_dir / f"{ts}.json"
    payload = report.to_dict()
    run_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    with (base / "runs.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({**payload, "ts": ts}) + "\n")
    return run_path
