# WS-1 Coverage Foundations + Benchmark — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the job-search app an entity-resolution engine (stable `job_key`) and a 3-leg coverage-rating benchmark, so coverage can be measured/verified before WS-2 improves it.

**Architecture:** A new `coverage/` package (sibling of `search/`, `scrape/`, `match/`, `tracker/`) holds canonicalization (`entity.py`), geography (`geography.py`), near-duplicate clustering (`resolve.py`), capture-recapture estimators (`estimators.py`), the reference-proxy leg (`reference.py`), the JOLTS sanity gate (`jolts.py`), the report dataclass + persistence (`report.py`), and the orchestrator (`benchmark.py`). Bundled public-domain lookup data lives in `data_static/`. `job_key` becomes the canonical cross-source identity and is wired into existing dedup behind the `normalize_url` fast-path.

**Tech Stack:** Python 3.11, pytest (`py -m pytest`), `cleanco` + `rapidfuzz` + `datasketch` (required, light), `statsmodels`/`splink` (optional, capability-probed), stdlib `hashlib`/`csv`/`json`/`unicodedata`.

## Global Constraints

- **Test runner:** `py -m pytest <path> -v` (Windows `py` launcher). Suite must stay green; add ~30–40 tests. Current suite ≈ 269 test functions across 39 files — recount at build time; do not hard-code a target.
- **New required deps (add to `requirements.txt`):** `cleanco`, `rapidfuzz`, `datasketch`. Heavy estimators (`statsmodels`, `splink`) stay OUT of requirements and are `try/except ImportError` capability-probed with a documented fallback — never required for the frozen build.
- **PyInstaller:** add `rapidfuzz`, `datasketch` to `hiddenimports` in `app.spec` (C-extensions).
- **Path model (from `config.py`):** bundled read-only data resolves under `DATA_DIR/data_static/`; all writes go under `USER_DATA_DIR` (coverage runs → `USER_DATA_DIR/coverage/`). Never write under `DATA_DIR`/`_MEIPASS`.
- **`models.py` stays import-light:** do NOT import `coverage` at module top. `JobResult.job_key` does a _local_ import inside the property and falls back to `self.identity_key` on `ImportError`.
- **`job_key` is pinned (the join key for WS-1 dedup, WS-2 freshness, WS-3 import):** `sha1("\x1f".join([company_canon, soc_code, loc_token, title_core])).hexdigest()[:16]`. New SHA1 identity, independent of the existing MD5 `identity_key`/`fit_token` (which stay for back-compat). Exposed via `functools.cached_property`.
- **Composite formula is pinned:** `CoverageScore = 100 * (Σ wᵢ·legᵢ over present legs / Σ wᵢ over present legs)`, weights `cov_cr=0.5, cov_proxy_weighted=0.3, c_hat=0.2`; `None` legs dropped and weights renormalized. Always report `cov_cr` CI, `cov_upper` (Chao1 ceiling), and the JOLTS verdict **separately** — never collapse to one number.
- **Don't delete `normalize_url`:** URL stays the dedup fast path; `job_key` only _adds_ cross-source collapsing.
- **TDD + frequent commits:** each task = failing test → run-to-fail → minimal impl → run-to-pass → conventional-commit.

## Frozen Shared Interfaces

Every task uses these EXACT names/signatures. Internal helpers/tests are task-local.

```
# models.py (MODIFY)
JobResult.job_key -> str          # functools.cached_property; local import of coverage.entity;
                                  # try/except ImportError -> self.identity_key

# coverage/entity.py
canonicalize_company(name: str) -> str
@dataclass NormalizedTitle: soc_code: str; soc_title: str; seniority: str | None; confidence: float
normalize_title(title: str) -> NormalizedTitle
@dataclass NormalizedLocation: city: str | None; state: str | None; cbsa: str | None; is_remote: bool
normalize_location(loc: str) -> NormalizedLocation
title_core(title: str) -> str
location_token(nl: NormalizedLocation) -> str        # "remote" or f"{city}|{state}"
compute_job_key(company_canon: str, soc_code: str, loc_token: str, title_core_str: str) -> str
job_key_for(job) -> str

# coverage/geography.py
resolve_cbsa(city: str | None, state: str | None) -> str | None
metro_variants(area: str) -> set[str]

# coverage/resolve.py
@dataclass Cluster: job_key: str; canonical: JobResult; members: list; source_ids: set
resolve(jobs: list) -> list[Cluster]                 # source id = job.source_api or job.source_keyword

# coverage/estimators.py
@dataclass ChapmanResult: n_hat: float; var: float; ci95: tuple
chapman(n1: int, n2: int, m: int) -> ChapmanResult
chao1(f1: int, f2: int, s_obs: int) -> float
good_turing(f1: int, n: int) -> float
loglinear(membership: list) -> float                 # list[frozenset[str]]; statsmodels optional

# coverage/reference.py
ReferenceProvider = Callable[[str, list], list]      # (area, soc_groups) -> list[JobResult]
@dataclass ReferenceResult: per_soc: dict; cov_proxy_weighted: float | None
reference_coverage(area, soc_groups, our_clusters, provider, weights: dict | None) -> ReferenceResult

# coverage/jolts.py
@dataclass JoltsResult: expected_openings: int | None; ratio: float | None; verdict: str  # pass|fail|skip
jolts_gate(area, naics: str | None, our_count: int, *, api_key: str | None = None) -> JoltsResult

# coverage/report.py
@dataclass CoverageReport: scope_hash, area, window, soc_grouping, source_ids, composite_score,
    cov_cr, cov_cr_ci, cov_upper, c_hat, cov_proxy_weighted, jolts_verdict, dedup_f1, per_soc,
    n_clusters, n_raw, paths_used
CoverageReport.to_dict() -> dict ; CoverageReport.from_dict(d) -> CoverageReport (classmethod)
scope_hash(area, window, soc_grouping, source_ids) -> str       # sha1("|".join)[:12]
human_summary(report) -> str
persist(report, base_dir) -> Path                                # <base>/runs/<scope_hash>/<ts>.json + <base>/runs.jsonl

# coverage/benchmark.py
run_benchmark(jobs, area, soc_groups, *, window="", provider=None, jolts_key=None,
              weights=None, out_dir=None) -> CoverageReport
```

## File Structure

```
data_static/                         # NEW — bundled, read-only (ships in DATA_DIR)
  onet_soc_alt_titles.tsv            #   alt_title<TAB>soc_code<TAB>soc_title (+ "# onet_version=" header)
  cbsa_delineation.csv               #   cbsa_code,cbsa_title,principal_city,state
  company_aliases.json               #   {"optum":"unitedhealth", ...}
  README.md
coverage/                            # NEW package
  __init__.py · _paths.py · geography.py · entity.py · resolve.py
  estimators.py · jolts.py · report.py · reference.py · benchmark.py
models.py                            # MODIFY — add JobResult.job_key
search/search_engine.py              # MODIFY — _deduplicate uses job_key behind URL fast-path
requirements.txt · app.spec          # MODIFY — deps + hiddenimports
tests/coverage/                      # NEW — one test module per coverage module
tests/fixtures/coverage/             # NEW — labeled_pairs.jsonl, cached_run.jsonl, baseline.json
```

---

### Task 1 — Source, license-check, and validate bundled static data

**Files:** Create `data_static/onet_soc_alt_titles.tsv`, `data_static/cbsa_delineation.csv`, `data_static/company_aliases.json`, `data_static/README.md`; Test `tests/coverage/test_static_data.py`

Prerequisite (spec §10): these files do not exist yet and must be acquired before any code that reads them.

- [ ] **Step 1:** Acquire O\*NET **Alternate Titles** (O\*NET Resource Center, public domain). Keep only: alternate title, O\*NET-SOC code, reported title. Add a header line `# onet_version=<v>` and write `data_static/onet_soc_alt_titles.tsv` (tab-separated: `alt_title<TAB>soc_code<TAB>soc_title`). For the committed CI subset, include at minimum a `software developer` → `15-1252.00` row plus ~30 common engineering/software/health titles.
- [ ] **Step 2:** Acquire the Census **CBSA delineation** file (public domain). Reduce to `data_static/cbsa_delineation.csv` with header exactly `cbsa_code,cbsa_title,principal_city,state` and ~15 top metros incl. a `Cincinnati, OH` row.
- [ ] **Step 3:** Create `data_static/company_aliases.json` = `{"optum": "unitedhealth"}` (editable map). Add `data_static/README.md` noting these are curated subsets and pointing to the full O\*NET/Census fetch as a follow-up.
- [ ] **Step 4: Write the failing test** `tests/coverage/test_static_data.py`:

```python
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
```

- [ ] **Step 5: Run to verify** `py -m pytest tests/coverage/test_static_data.py -v` → PASS once the files exist.
- [ ] **Step 6: Commit** `git add data_static/ tests/coverage/test_static_data.py && git commit -m "feat(coverage): bundle O*NET alt-titles + CBSA delineation + company aliases static data"`

### Task 2 — `coverage/` package skeleton + static-data path resolution

**Files:** Create `coverage/__init__.py`, `coverage/_paths.py`, `tests/coverage/__init__.py`, `tests/coverage/test_paths.py`

- [ ] **Step 1:** Create `coverage/__init__.py` (empty package marker; do **not** import submodules at package top — keeps `models` import light).
- [ ] **Step 2:** Create `coverage/_paths.py`:

```python
from pathlib import Path
from config import DATA_DIR  # bundled, read-only

DATA_STATIC = Path(DATA_DIR) / "data_static"

def static_path(name: str) -> Path:
    return DATA_STATIC / name
```

- [ ] **Step 3: Write the test** `tests/coverage/test_paths.py`:

```python
from coverage._paths import static_path

def test_static_path_points_into_bundle():
    p = static_path("onet_soc_alt_titles.tsv")
    assert p.name == "onet_soc_alt_titles.tsv"
    assert p.parent.name == "data_static"
```

- [ ] **Step 4: Run** `py -m pytest tests/coverage/test_paths.py -v` → PASS.
- [ ] **Step 5: Commit** `git add coverage/__init__.py coverage/_paths.py tests/coverage/__init__.py tests/coverage/test_paths.py && git commit -m "feat(coverage): package skeleton + bundled static-data path resolution"`

### Task 3 — `coverage/geography.py` — CBSA resolution + metro variants

**Files:** Create `coverage/geography.py`, `tests/coverage/test_geography.py`

**Interfaces — Produces:** `resolve_cbsa(city, state) -> str | None`, `metro_variants(area) -> set[str]` (consumed by `entity.normalize_location` Task 4, `reference.py` Task 10).

- [ ] **Step 1: Write the failing test** `tests/coverage/test_geography.py`:

```python
from coverage.geography import resolve_cbsa, metro_variants

def test_resolve_cbsa_known_pair():
    assert resolve_cbsa("Cincinnati", "OH") is not None

def test_resolve_cbsa_none_inputs():
    assert resolve_cbsa(None, None) is None
    assert resolve_cbsa("Cincinnati", None) is None

def test_metro_variants_includes_input():
    assert "cincinnati" in metro_variants("Cincinnati")

def test_metro_variants_known_metro():
    v = metro_variants("Cincinnati, OH")
    assert any("cincinnati" in x for x in v)
```

- [ ] **Step 2: Run to fail** `py -m pytest tests/coverage/test_geography.py -v` → FAIL (module missing).
- [ ] **Step 3: Implement** `coverage/geography.py`:

```python
import csv, functools
from coverage._paths import static_path

@functools.lru_cache(maxsize=1)
def _rows() -> list[dict]:
    with static_path("cbsa_delineation.csv").open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))

def resolve_cbsa(city: str | None, state: str | None) -> str | None:
    if not city or not state:
        return None
    c, s = city.strip().casefold(), state.strip().casefold()
    for r in _rows():
        if r["principal_city"].casefold() == c and r["state"].casefold() == s:
            return r["cbsa_code"]
    return None

def metro_variants(area: str) -> set[str]:
    out = {area.strip().casefold()}
    a = area.strip().casefold()
    for r in _rows():
        title = r["cbsa_title"].casefold()
        if a in title or title in a:
            out.add(title)
            out.add(r["principal_city"].casefold())
            bare = title.split(",")[0].replace(" metro area", "").strip()
            out.add(bare)
    return {v for v in out if v}
```

- [ ] **Step 4: Run** `py -m pytest tests/coverage/test_geography.py -v` → PASS.
- [ ] **Step 5: Commit** `git add coverage/geography.py tests/coverage/test_geography.py && git commit -m "feat(coverage): geography — CBSA resolution + metro variant expansion"`

### Task 4 — `coverage/entity.py` — canonicalization, normalization, `job_key`

**Files:** Create `coverage/entity.py`, `tests/coverage/test_entity.py`

**Interfaces — Produces:** `canonicalize_company`, `NormalizedTitle`, `normalize_title`, `NormalizedLocation`, `normalize_location`, `title_core`, `location_token`, `compute_job_key`, `job_key_for` (consumed by `resolve.py`, `reference.py`, `models.py`). **Consumes:** `geography.resolve_cbsa`.

- [ ] **Step 1: Write the failing test** `tests/coverage/test_entity.py`:

```python
from coverage import entity as E

def test_canonicalize_company_strips_suffix_and_punct():
    assert E.canonicalize_company("Acme, Inc.") == "acme"

def test_canonicalize_company_alias():
    assert E.canonicalize_company("Optum") == "unitedhealth"

def test_normalize_title_known_soc_and_seniority():
    nt = E.normalize_title("Senior Software Developer")
    assert nt.soc_code.startswith("15-1252")
    assert nt.seniority and "senior" in nt.seniority

def test_normalize_title_unmapped():
    assert E.normalize_title("zxqw blorp").soc_code == "00-0000"

def test_normalize_location_remote_and_city():
    assert E.normalize_location("Remote").is_remote is True
    nl = E.normalize_location("Cincinnati, OH")
    assert nl.city == "Cincinnati" and nl.state == "OH"

def test_job_key_cross_source_collision():
    a = type("J", (), {"company": "Acme, Inc.", "title": "Senior Software Developer", "location": "Cincinnati, OH"})()
    b = type("J", (), {"company": "Acme Inc",   "title": "Software Developer",         "location": "Cincinnati"})()
    assert E.job_key_for(a) == E.job_key_for(b)
    assert len(E.job_key_for(a)) == 16

def test_job_key_distinct_role_differs():
    a = type("J", (), {"company": "Acme", "title": "Software Developer", "location": "Cincinnati, OH"})()
    b = type("J", (), {"company": "Acme", "title": "Mechanical Engineer", "location": "Cincinnati, OH"})()
    assert E.job_key_for(a) != E.job_key_for(b)
```

- [ ] **Step 2: Run to fail** → FAIL (module missing).
- [ ] **Step 3: Implement** `coverage/entity.py`:

```python
from __future__ import annotations
import functools, hashlib, json, re, unicodedata
from dataclasses import dataclass
from coverage._paths import static_path
from coverage.geography import resolve_cbsa

try:
    from cleanco import basename as _cc_basename
except ImportError:
    _SUFFIX = re.compile(r"\b(inc|llc|ltd|gmbh|corp|co)\b\.?", re.I)
    def _cc_basename(n: str) -> str:
        return _SUFFIX.sub("", n)

try:
    from rapidfuzz import process as _rf_process, fuzz as _rf_fuzz
    _HAVE_RAPIDFUZZ = True
except ImportError:
    _HAVE_RAPIDFUZZ = False

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s]")
_SENIORITY = re.compile(r"\b(sr|senior|jr|junior|i{1,3}|iv|lead|principal|staff)\b\.?", re.I)
_REMOTE = re.compile(r"\bremote\b|\banywhere\b", re.I)
_CONF_FLOOR = 0.6

@functools.lru_cache(maxsize=1)
def _aliases() -> dict[str, str]:
    return json.loads(static_path("company_aliases.json").read_text(encoding="utf-8"))

@functools.lru_cache(maxsize=1)
def _onet() -> dict[str, tuple[str, str]]:
    out: dict[str, tuple[str, str]] = {}
    for line in static_path("onet_soc_alt_titles.tsv").read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        alt, soc, soc_title = line.split("\t")
        out[alt.casefold()] = (soc, soc_title)
    return out

def canonicalize_company(name: str) -> str:
    if not name:
        return ""
    s = _cc_basename(name)
    s = unicodedata.normalize("NFKD", s).casefold()
    s = _PUNCT.sub(" ", s)
    s = _WS.sub(" ", s).strip()
    return _aliases().get(s, s)

@dataclass
class NormalizedTitle:
    soc_code: str
    soc_title: str
    seniority: str | None
    confidence: float

def title_core(title: str) -> str:
    s = _SENIORITY.sub("", title or "")
    return _WS.sub(" ", s).strip().casefold()

def _seniority_of(title: str) -> str | None:
    m = _SENIORITY.search(title or "")
    return m.group(0).strip().casefold() if m else None

def normalize_title(title: str) -> NormalizedTitle:
    core = title_core(title)
    seniority = _seniority_of(title)
    table = _onet()
    if core in table:
        soc, soc_title = table[core]
        return NormalizedTitle(soc, soc_title, seniority, 1.0)
    if _HAVE_RAPIDFUZZ and table:
        match = _rf_process.extractOne(core, list(table.keys()), scorer=_rf_fuzz.token_set_ratio)
        if match:
            cand, score, _ = match
            conf = score / 100.0
            if conf >= _CONF_FLOOR:
                soc, soc_title = table[cand]
                return NormalizedTitle(soc, soc_title, seniority, conf)
    return NormalizedTitle("00-0000", core, seniority, 0.0)

@dataclass
class NormalizedLocation:
    city: str | None
    state: str | None
    cbsa: str | None
    is_remote: bool

def normalize_location(loc: str) -> NormalizedLocation:
    if not loc:
        return NormalizedLocation(None, None, None, False)
    if _REMOTE.search(loc):
        return NormalizedLocation(None, None, None, True)
    parts = [p.strip() for p in loc.split(",")]
    city = parts[0] or None
    state = parts[1].split()[0] if len(parts) > 1 and parts[1] else None
    return NormalizedLocation(city, state, resolve_cbsa(city, state), False)

def location_token(nl: NormalizedLocation) -> str:
    return "remote" if nl.is_remote else f"{nl.city}|{nl.state}"

def compute_job_key(company_canon: str, soc_code: str, loc_token: str, title_core_str: str) -> str:
    payload = "\x1f".join([company_canon, soc_code, loc_token, title_core_str])
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]

def job_key_for(job) -> str:
    company = canonicalize_company(getattr(job, "company", "") or "")
    nt = normalize_title(getattr(job, "title", "") or "")
    nl = normalize_location(getattr(job, "location", "") or "")
    return compute_job_key(company, nt.soc_code, location_token(nl), title_core(getattr(job, "title", "") or ""))
```

- [ ] **Step 4: Run** `py -m pytest tests/coverage/test_entity.py -v` → PASS.
- [ ] **Step 5: Commit** `git add coverage/entity.py tests/coverage/test_entity.py && git commit -m "feat(coverage): entity resolution — company/title/location canonicalization + stable job_key"`

### Task 5 — Wire `JobResult.job_key` into `models.py`

**Files:** Modify `models.py`; Test `tests/coverage/test_models_job_key.py`

**Interfaces — Consumes:** `coverage.entity.job_key_for`. **Produces:** `JobResult.job_key`.

- [ ] **Step 1: Write the failing test** `tests/coverage/test_models_job_key.py`:

```python
from models import JobResult
from coverage import entity

def _job():
    return JobResult(title="Software Developer", company="Acme, Inc.", location="Cincinnati, OH",
                     salary_min=None, salary_max=None, description="", url="", source_keyword="kw",
                     created="2026-06-22", source_api="adzuna")

def test_job_key_matches_entity():
    j = _job()
    assert j.job_key == entity.job_key_for(j)

def test_job_key_is_cached():
    j = _job()
    assert j.job_key is j.job_key  # cached_property memoizes the same object
```

- [ ] **Step 2: Run to fail** → FAIL (no `job_key`).
- [ ] **Step 3: Implement** — add `import functools` at the top of `models.py`, and inside `JobResult`:

```python
    @functools.cached_property
    def job_key(self) -> str:
        try:
            from coverage import entity
            return entity.job_key_for(self)
        except ImportError:
            return self.identity_key
```

- [ ] **Step 4: Run** `py -m pytest tests/coverage/test_models_job_key.py -v` → PASS.
- [ ] **Step 5: Commit** `git add models.py tests/coverage/test_models_job_key.py && git commit -m "feat(models): JobResult.job_key cached_property delegating to coverage.entity (ImportError-safe)"`

### Task 6 — `coverage/resolve.py` — near-duplicate clustering

**Files:** Create `coverage/resolve.py`, `tests/coverage/test_resolve.py`

**Interfaces — Produces:** `Cluster`, `resolve(jobs) -> list[Cluster]` (consumed by `estimators`/`reference`/`benchmark`). **Consumes:** `coverage.entity`, `JobResult.job_key`.

- [ ] **Step 1: Write the failing test** `tests/coverage/test_resolve.py`:

```python
from models import JobResult
from coverage.resolve import resolve

def _j(title, company, location, source):
    return JobResult(title=title, company=company, location=location, salary_min=None, salary_max=None,
                     description="", url="", source_keyword="kw", created="2026-06-22", source_api=source)

def test_identical_postings_collapse():
    jobs = [_j("Software Developer", "Acme, Inc.", "Cincinnati, OH", "adzuna"),
            _j("Software Developer", "Acme Inc",   "Cincinnati",     "themuse")]
    clusters = resolve(jobs)
    assert len(clusters) == 1
    assert clusters[0].source_ids == {"adzuna", "themuse"}

def test_distinct_jobs_separate():
    jobs = [_j("Software Developer", "Acme", "Cincinnati, OH", "adzuna"),
            _j("Mechanical Engineer", "Acme", "Cincinnati, OH", "adzuna")]
    assert len(resolve(jobs)) == 2

def test_empty_input_returns_empty():
    assert resolve([]) == []
```

- [ ] **Step 2: Run to fail** → FAIL.
- [ ] **Step 3: Implement** `coverage/resolve.py`:

```python
from __future__ import annotations
from dataclasses import dataclass
from coverage import entity

try:
    from rapidfuzz import fuzz as _rf_fuzz
    _HAVE_RF = True
except ImportError:
    _HAVE_RF = False

_MATCH_THRESHOLD = 85.0

@dataclass
class Cluster:
    job_key: str
    canonical: "JobResult"  # noqa: F821
    members: list
    source_ids: set

def _source_id(job) -> str:
    return getattr(job, "source_api", None) or getattr(job, "source_keyword", None) or ""

def _block_key(job) -> tuple:
    nt = entity.normalize_title(getattr(job, "title", "") or "")
    nl = entity.normalize_location(getattr(job, "location", "") or "")
    return (entity.canonicalize_company(getattr(job, "company", "") or ""), nt.soc_code, entity.location_token(nl))

def _pair_matches(a, b) -> bool:
    ta, tb = (getattr(a, "title", "") or ""), (getattr(b, "title", "") or "")
    ca, cb = (getattr(a, "company", "") or ""), (getattr(b, "company", "") or "")
    if not _HAVE_RF:
        return entity.title_core(ta) == entity.title_core(tb) and \
            entity.canonicalize_company(ca) == entity.canonicalize_company(cb)
    combined = 0.6 * _rf_fuzz.token_set_ratio(ta, tb) + 0.4 * _rf_fuzz.WRatio(ca, cb)
    return combined >= _MATCH_THRESHOLD

class _UnionFind:
    def __init__(self, n: int):
        self.p = list(range(n))
    def find(self, x: int) -> int:
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x
    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)

def resolve(jobs: list) -> list[Cluster]:
    if not jobs:
        return []
    blocks: dict[tuple, list[int]] = {}
    for i, j in enumerate(jobs):
        blocks.setdefault(_block_key(j), []).append(i)
    uf = _UnionFind(len(jobs))
    for idxs in blocks.values():
        for a in range(len(idxs)):
            for b in range(a + 1, len(idxs)):
                if _pair_matches(jobs[idxs[a]], jobs[idxs[b]]):
                    uf.union(idxs[a], idxs[b])
    groups: dict[int, list[int]] = {}
    for i in range(len(jobs)):
        groups.setdefault(uf.find(i), []).append(i)
    clusters: list[Cluster] = []
    for members_idx in groups.values():
        members = [jobs[i] for i in sorted(members_idx)]
        canonical = members[0]
        clusters.append(Cluster(job_key=canonical.job_key, canonical=canonical,
                                 members=members, source_ids={_source_id(m) for m in members}))
    clusters.sort(key=lambda c: c.job_key)
    return clusters
```

- [ ] **Step 4: Run** `py -m pytest tests/coverage/test_resolve.py -v` → PASS.
- [ ] **Step 5: Commit** `git add coverage/resolve.py tests/coverage/test_resolve.py && git commit -m "feat(coverage): resolve — block/score/union-find clustering into Clusters"`

### Task 7 — `coverage/estimators.py` — capture-recapture estimators

**Files:** Create `coverage/estimators.py`, `tests/coverage/test_estimators.py`

**Interfaces — Produces:** `ChapmanResult`, `chapman`, `chao1`, `good_turing`, `loglinear` (consumed by `benchmark`).

- [ ] **Step 1: Write the failing test** `tests/coverage/test_estimators.py`:

```python
import math
from coverage.estimators import chapman, chao1, good_turing, loglinear

def test_chapman_known_value():
    r = chapman(100, 100, 20)
    assert abs(r.n_hat - 480.0476190476191) < 1e-6
    assert r.ci95[0] < r.n_hat < r.ci95[1]

def test_chao1_known_value():
    assert chao1(10, 5, 50) == 50 + (10 * 9) / (2 * 6)

def test_chao1_f2_zero_no_div_error():
    assert chao1(4, 0, 10) == 10 + (4 * 3) / 2

def test_good_turing():
    assert good_turing(10, 100) == 0.9

def test_good_turing_zero_n():
    assert good_turing(0, 0) == 0.0

def test_loglinear_two_sources_falls_back():
    membership = [frozenset({"a"})] * 80 + [frozenset({"b"})] * 80 + [frozenset({"a", "b"})] * 20
    assert loglinear(membership) > 0
```

- [ ] **Step 2: Run to fail** → FAIL.
- [ ] **Step 3: Implement** `coverage/estimators.py`:

```python
from __future__ import annotations
import itertools, math
from dataclasses import dataclass

try:
    import statsmodels.api as _sm  # noqa: F401
    _HAVE_SM = True
except ImportError:
    _HAVE_SM = False

@dataclass
class ChapmanResult:
    n_hat: float
    var: float
    ci95: tuple

def chapman(n1: int, n2: int, m: int) -> ChapmanResult:
    n_hat = (n1 + 1) * (n2 + 1) / (m + 1) - 1
    var = ((n1 + 1) * (n2 + 1) * (n1 - m) * (n2 - m)) / ((m + 1) ** 2 * (m + 2))
    half = 1.96 * math.sqrt(var) if var > 0 else 0.0
    return ChapmanResult(n_hat=n_hat, var=var, ci95=(n_hat - half, n_hat + half))

def chao1(f1: int, f2: int, s_obs: int) -> float:
    return s_obs + (f1 * (f1 - 1)) / (2 * (f2 + 1))

def good_turing(f1: int, n: int) -> float:
    if n <= 0:
        return 0.0
    return 1.0 - (f1 / n)

def loglinear(membership: list) -> float:
    sources = sorted({s for fs in membership for s in fs})
    if _HAVE_SM and len(sources) >= 3:
        return _loglinear_glm(membership, sources)
    estimates: list[float] = []
    for a, b in itertools.combinations(sources, 2):
        n1 = sum(1 for fs in membership if a in fs)
        n2 = sum(1 for fs in membership if b in fs)
        m = sum(1 for fs in membership if a in fs and b in fs)
        if m > 0:
            estimates.append(chapman(n1, n2, m).n_hat)
    return sum(estimates) / len(estimates) if estimates else float(len(membership))

def _loglinear_glm(membership: list, sources: list) -> float:
    import numpy as np
    import statsmodels.api as sm
    cells: dict[tuple, int] = {}
    for fs in membership:
        pattern = tuple(1 if s in fs else 0 for s in sources)
        cells[pattern] = cells.get(pattern, 0) + 1
    rows = [p for p in cells if any(p)]
    y = np.array([cells[p] for p in rows], dtype=float)
    X = sm.add_constant(np.array(rows, dtype=float), has_constant="add")
    model = sm.GLM(y, X, family=sm.families.Poisson()).fit()
    zero = sm.add_constant(np.zeros((1, len(sources))), has_constant="add")
    return len(membership) + float(model.predict(zero)[0])
```

- [ ] **Step 4: Run** `py -m pytest tests/coverage/test_estimators.py -v` → PASS.
- [ ] **Step 5: Commit** `git add coverage/estimators.py tests/coverage/test_estimators.py && git commit -m "feat(coverage): estimators — chapman/chao1/good_turing/loglinear (statsmodels optional)"`

### Task 8 — `coverage/jolts.py` — JOLTS macro sanity gate

**Files:** Create `coverage/jolts.py`, `tests/coverage/test_jolts.py`

**Interfaces — Produces:** `JoltsResult`, `jolts_gate(...)` (consumed by `benchmark`). **Consumes:** `search/http_util.py` (`FileCache.put/get`, `cache_key`, `RateLimiter(int).acquire()`).

- [ ] **Step 1: Write the failing test** `tests/coverage/test_jolts.py`:

```python
import coverage.jolts as J

def test_no_key_returns_skip():
    assert J.jolts_gate("Cincinnati, OH", None, 100).verdict == "skip"

def test_network_error_returns_skip(monkeypatch):
    monkeypatch.setattr(J, "_fetch_expected_openings", lambda *a, **k: (_ for _ in ()).throw(RuntimeError()))
    assert J.jolts_gate("X", None, 100, api_key="k").verdict == "skip"

def test_ratio_in_band_pass(monkeypatch):
    monkeypatch.setattr(J, "_fetch_expected_openings", lambda *a, **k: 1000)
    r = J.jolts_gate("X", None, 100, api_key="k")
    assert r.verdict == "pass" and r.expected_openings == 1000

def test_ratio_out_of_band_fail(monkeypatch):
    monkeypatch.setattr(J, "_fetch_expected_openings", lambda *a, **k: 10)
    assert J.jolts_gate("X", None, 100000, api_key="k").verdict == "fail"

def test_zero_expected_returns_skip(monkeypatch):
    monkeypatch.setattr(J, "_fetch_expected_openings", lambda *a, **k: 0)
    assert J.jolts_gate("X", None, 100, api_key="k").verdict == "skip"
```

- [ ] **Step 2: Run to fail** → FAIL.
- [ ] **Step 3: Implement** `coverage/jolts.py` (note: `RateLimiter(int).acquire()` and `FileCache.put/get` — the real `http_util` API):

```python
from __future__ import annotations
from dataclasses import dataclass

_PASS_LO, _PASS_HI = 0.05, 5.0

@dataclass
class JoltsResult:
    expected_openings: int | None
    ratio: float | None
    verdict: str  # "pass" | "fail" | "skip"

def jolts_gate(area: str, naics: str | None, our_count: int, *, api_key: str | None = None) -> JoltsResult:
    if not api_key:
        return JoltsResult(None, None, "skip")
    try:
        expected = _fetch_expected_openings(area, naics, api_key)
    except Exception:
        return JoltsResult(None, None, "skip")
    if not expected:
        return JoltsResult(None, None, "skip")
    ratio = our_count / expected
    verdict = "pass" if _PASS_LO <= ratio <= _PASS_HI else "fail"
    return JoltsResult(expected_openings=expected, ratio=ratio, verdict=verdict)

def _fetch_expected_openings(area: str, naics: str | None, api_key: str) -> int | None:
    import requests
    from search.http_util import FileCache, cache_key, RateLimiter
    cache = FileCache("jolts")
    key = cache_key("jolts", area, naics or "")
    cached = cache.get(key)
    if cached is not None:
        return cached.get("openings")
    RateLimiter(50).acquire()
    resp = requests.post(
        "https://api.bls.gov/publicAPI/v2/timeseries/data/",
        json={"seriesid": [_series_id(area, naics)], "registrationkey": api_key},
        timeout=30,
    )
    resp.raise_for_status()
    series = resp.json().get("Results", {}).get("series", [])
    if not series or not series[0].get("data"):
        return None
    openings = int(float(series[0]["data"][0]["value"])) * 1000
    cache.put(key, {"openings": openings})
    return openings

def _series_id(area: str, naics: str | None) -> str:
    # JTU national total-nonfarm job openings, level (NSA) — safe default series.
    return "JTU000000000000000JOL"
```

- [ ] **Step 4: Run** `py -m pytest tests/coverage/test_jolts.py -v` → PASS.
- [ ] **Step 5: Commit** `git add coverage/jolts.py tests/coverage/test_jolts.py && git commit -m "feat(coverage): JOLTS macro sanity gate (optional key, skip/pass/fail)"`

### Task 9 — `coverage/report.py` — `CoverageReport` + scope hash + persistence

**Files:** Create `coverage/report.py`, `tests/coverage/test_report.py`

**Interfaces — Produces:** `CoverageReport`, `scope_hash`, `human_summary`, `persist` (consumed by `benchmark`).

- [ ] **Step 1: Write the failing test** `tests/coverage/test_report.py`:

```python
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
```

- [ ] **Step 2: Run to fail** → FAIL.
- [ ] **Step 3: Implement** `coverage/report.py`:

```python
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
```

- [ ] **Step 4: Run** `py -m pytest tests/coverage/test_report.py -v` → PASS.
- [ ] **Step 5: Commit** `git add coverage/report.py tests/coverage/test_report.py && git commit -m "feat(coverage): CoverageReport + pinned scope_hash + JSON persistence/rollup"`

### Task 10 — `coverage/reference.py` — reference-proxy leg (primary)

**Files:** Create `coverage/reference.py`, `tests/coverage/test_reference.py`

**Interfaces — Produces:** `ReferenceProvider`, `ReferenceResult`, `reference_coverage(...)` (consumed by `benchmark`). **Consumes:** `entity.normalize_title`, `resolve`.

- [ ] **Step 1: Write the failing test** `tests/coverage/test_reference.py`:

```python
from models import JobResult
from coverage.reference import reference_coverage
from coverage.resolve import resolve

def _j(title, company="Acme", location="Cincinnati, OH", source="ref"):
    return JobResult(title=title, company=company, location=location, salary_min=None, salary_max=None,
                     description="", url="", source_keyword="kw", created="2026-06-22", source_api=source)

def test_none_provider_returns_none():
    assert reference_coverage("A", ["15-1252.00"], [], None, None).cov_proxy_weighted is None

def test_perfect_overlap_proxy_one():
    ours = resolve([_j("Software Developer", source="ours")])
    provider = lambda area, groups: [_j("Software Developer")]
    assert reference_coverage("A", ["15-1252.00"], ours, provider, None).cov_proxy_weighted == 1.0

def test_partial_overlap():
    ours = resolve([_j("Software Developer", source="ours")])
    provider = lambda area, groups: [_j("Software Developer"), _j("Mechanical Engineer")]
    cov = reference_coverage("A", [], ours, provider, None).cov_proxy_weighted
    assert 0 < cov < 1
```

- [ ] **Step 2: Run to fail** → FAIL.
- [ ] **Step 3: Implement** `coverage/reference.py`:

```python
from __future__ import annotations
from collections.abc import Callable
from dataclasses import dataclass
from coverage.entity import normalize_title
from coverage.resolve import resolve

ReferenceProvider = Callable[[str, list], list]

@dataclass
class ReferenceResult:
    per_soc: dict
    cov_proxy_weighted: float | None

def _soc_of_cluster(cluster) -> str:
    return normalize_title(getattr(cluster.canonical, "title", "") or "").soc_code

def reference_coverage(area: str, soc_groups: list, our_clusters: list, provider, weights: dict | None) -> ReferenceResult:
    if provider is None:
        return ReferenceResult(per_soc={}, cov_proxy_weighted=None)
    ref_clusters = resolve(provider(area, soc_groups))
    if not ref_clusters:
        return ReferenceResult(per_soc={}, cov_proxy_weighted=None)
    our_keys = {c.job_key for c in our_clusters}
    ref_by_soc: dict[str, list] = {}
    for rc in ref_clusters:
        ref_by_soc.setdefault(_soc_of_cluster(rc), []).append(rc)
    per_soc: dict[str, dict] = {}
    for g, clusters in ref_by_soc.items():
        d_g = len(clusters)
        n_g = sum(1 for rc in clusters if rc.job_key in our_keys)
        per_soc[g] = {"D_g": d_g, "N_g": n_g, "cov_proxy_g": (n_g / d_g) if d_g else None}
    present = {g: v for g, v in per_soc.items() if v["D_g"] > 0}
    if not present:
        return ReferenceResult(per_soc=per_soc, cov_proxy_weighted=None)
    w = weights or {}
    num = sum(w.get(g, 1.0) * v["cov_proxy_g"] for g, v in present.items())
    den = sum(w.get(g, 1.0) for g in present)
    return ReferenceResult(per_soc=per_soc, cov_proxy_weighted=(num / den) if den else None)
```

- [ ] **Step 4: Run** `py -m pytest tests/coverage/test_reference.py -v` → PASS.
- [ ] **Step 5: Commit** `git add coverage/reference.py tests/coverage/test_reference.py && git commit -m "feat(coverage): reference-proxy leg — per-SOC deduped D/N + employment-share weighting"`

### Task 11 — `coverage/benchmark.py` — orchestration

**Files:** Create `coverage/benchmark.py`, `tests/coverage/test_benchmark.py`

**Interfaces — Produces:** `run_benchmark(...)`. **Consumes:** `resolve`, `estimators`, `reference_coverage`, `jolts_gate`, `report.*`. Note the `out_dir` param (defaults to `config.USER_DATA_DIR/coverage`) so tests need not monkeypatch a module-level constant.

- [ ] **Step 1: Write the failing test** `tests/coverage/test_benchmark.py`:

```python
from models import JobResult
from coverage.benchmark import run_benchmark

def _j(title, company, source):
    return JobResult(title=title, company=company, location="Cincinnati, OH", salary_min=None, salary_max=None,
                     description="", url="", source_keyword="kw", created="2026-06-22", source_api=source)

def _two_source_jobs():
    # one cross-source dupe + singles -> 2 sources present
    return [_j("Software Developer", "Acme", "adzuna"), _j("Software Developer", "Acme", "themuse"),
            _j("Mechanical Engineer", "Beta", "adzuna"), _j("Data Scientist", "Gamma", "themuse")]

def test_two_source_fixture_populates_cr(tmp_path):
    r = run_benchmark(_two_source_jobs(), "Cincinnati, OH", ["15-1252.00"], out_dir=tmp_path)
    assert r.paths_used["cr"] == "chapman"
    assert r.cov_cr is not None

def test_composite_renormalizes_missing_legs(tmp_path):
    r = run_benchmark(_two_source_jobs(), "Cincinnati, OH", [], out_dir=tmp_path)
    assert r.cov_proxy_weighted is None  # no provider
    assert 0 <= r.composite_score <= 100

def test_persists_report(tmp_path):
    run_benchmark(_two_source_jobs(), "Cincinnati, OH", [], out_dir=tmp_path)
    assert (tmp_path / "runs.jsonl").exists()
```

- [ ] **Step 2: Run to fail** → FAIL.
- [ ] **Step 3: Implement** `coverage/benchmark.py`:

```python
from __future__ import annotations
from pathlib import Path
import config
from coverage import report as _report
from coverage.estimators import chao1, chapman, good_turing, loglinear
from coverage.jolts import jolts_gate
from coverage.reference import reference_coverage
from coverage.report import CoverageReport
from coverage.resolve import resolve

_WEIGHTS = {"cov_cr": 0.5, "cov_proxy_weighted": 0.3, "c_hat": 0.2}

def _clamp_fraction(observed: int, n_hat) -> float | None:
    if n_hat is None or n_hat <= 0:
        return None
    return max(0.0, min(1.0, observed / n_hat))

def _composite(cov_cr, cov_proxy_weighted, c_hat) -> float:
    legs = {"cov_cr": cov_cr, "cov_proxy_weighted": cov_proxy_weighted, "c_hat": c_hat}
    present = {k: v for k, v in legs.items() if v is not None}
    if not present:
        return 0.0
    num = sum(_WEIGHTS[k] * v for k, v in present.items())
    den = sum(_WEIGHTS[k] for k in present)
    return 100.0 * (num / den)

def run_benchmark(jobs: list, area: str, soc_groups: list, *, window: str = "", provider=None,
                  jolts_key: str | None = None, weights: dict | None = None, out_dir=None) -> CoverageReport:
    clusters = resolve(jobs)
    n_clusters, n_raw = len(clusters), len(jobs)
    paths_used: dict = {}

    membership = [frozenset(c.source_ids) for c in clusters]
    source_counts: dict[str, int] = {}
    for ms in membership:
        for s in ms:
            source_counts[s] = source_counts.get(s, 0) + 1
    sources = sorted(source_counts, key=lambda s: source_counts[s], reverse=True)
    f1 = sum(1 for ms in membership if len(ms) == 1)
    f2 = sum(1 for ms in membership if len(ms) == 2)

    cov_cr = cov_cr_ci = cov_upper = c_hat = None
    if len(sources) >= 3:
        cov_cr = _clamp_fraction(n_clusters, loglinear(membership))
        paths_used["cr"] = "loglinear"
    elif len(sources) == 2:
        a, b = sources[0], sources[1]
        m = sum(1 for ms in membership if a in ms and b in ms)
        res = chapman(source_counts[a], source_counts[b], m)
        cov_cr = _clamp_fraction(n_clusters, res.n_hat)
        cov_cr_ci = (_clamp_fraction(n_clusters, res.ci95[1]), _clamp_fraction(n_clusters, res.ci95[0]))
        paths_used["cr"] = "chapman"
    else:
        paths_used["cr"] = "insufficient_sources"

    if n_clusters:
        cov_upper = chao1(f1, f2, n_clusters)
        c_hat = good_turing(f1, n_raw)

    ref = reference_coverage(area, soc_groups, clusters, provider, weights)
    paths_used["reference"] = "provider" if provider is not None else "skip"
    jolts = jolts_gate(area, None, n_clusters, api_key=jolts_key)
    paths_used["jolts"] = jolts.verdict

    rpt = CoverageReport(
        scope_hash=_report.scope_hash(area, window, ",".join(soc_groups), sources),
        area=area, window=window, soc_grouping=",".join(soc_groups), source_ids=sources,
        composite_score=_composite(cov_cr, ref.cov_proxy_weighted, c_hat),
        cov_cr=cov_cr, cov_cr_ci=cov_cr_ci, cov_upper=cov_upper, c_hat=c_hat,
        cov_proxy_weighted=ref.cov_proxy_weighted, jolts_verdict=jolts.verdict,
        dedup_f1=None, per_soc=ref.per_soc, n_clusters=n_clusters, n_raw=n_raw, paths_used=paths_used,
    )
    base = Path(out_dir) if out_dir is not None else Path(config.USER_DATA_DIR) / "coverage"
    _report.persist(rpt, base)
    return rpt
```

- [ ] **Step 4: Run** `py -m pytest tests/coverage/test_benchmark.py -v` → PASS.
- [ ] **Step 5: Commit** `git add coverage/benchmark.py tests/coverage/test_benchmark.py && git commit -m "feat(coverage): benchmark orchestration — 3 legs + pinned composite + persist"`

### Task 12 — Wire `job_key` into existing dedup behind the URL fast-path

**Files:** Modify `search/search_engine.py` (`_deduplicate`); the cross-run `seen_urls()` filter lives in `search/cli.py` (extend it too); Test `tests/coverage/test_dedup_wiring.py`

Per spec §4.1 + R5: keep `normalize_url` as the fast path; `job_key` only **adds** cross-source collapsing. Characterize current behavior before swapping.

- [ ] **Step 1: Write the failing test** `tests/coverage/test_dedup_wiring.py`:

```python
from models import JobResult
from search.search_engine import SearchEngine

def _j(title, company, location, url, source):
    return JobResult(title=title, company=company, location=location, salary_min=None, salary_max=None,
                     description="", url=url, source_keyword="kw", created="2026-06-22", source_api=source)

def _dedup(jobs):
    return SearchEngine(clients=[])._deduplicate(jobs)

def test_url_fast_path_still_dedupes():
    jobs = [_j("Eng", "Acme", "Cincinnati, OH", "https://x.co/1?utm_source=a", "s1"),
            _j("Eng", "Acme", "Cincinnati, OH", "https://x.co/1?utm_source=b", "s2")]
    assert len(_dedup(jobs)) == 1  # tracking-variant URLs collapse (characterization parity)

def test_cross_source_dupe_collapsed_by_job_key():
    jobs = [_j("Software Developer", "Acme, Inc.", "Cincinnati, OH", "", "adzuna"),
            _j("Software Developer", "Acme Inc",   "Cincinnati",     "", "themuse")]
    assert len(_dedup(jobs)) == 1  # no URLs, different formatting -> job_key collapses

def test_distinct_jobs_survive():
    jobs = [_j("Software Developer", "Acme", "Cincinnati, OH", "", "adzuna"),
            _j("Mechanical Engineer", "Acme", "Cincinnati, OH", "", "adzuna")]
    assert len(_dedup(jobs)) == 2
```

- [ ] **Step 2: Run to fail** → the cross-source test FAILs under the current URL-only logic.
- [ ] **Step 3: Implement** — replace the body of `_deduplicate` in `search/search_engine.py`:

```python
    def _deduplicate(self, results: list[JobResult]) -> list[JobResult]:
        # URL is the fast path (tracking/location variants collapse); job_key
        # additionally catches keyless cross-source duplicates with differing URLs.
        seen_urls: set[str] = set()
        seen_keys: set[str] = set()
        unique: list[JobResult] = []
        for job in results:
            u = normalize_url(job.url)
            if u and u in seen_urls:
                continue
            k = job.job_key
            if k in seen_keys:
                continue
            if u:
                seen_urls.add(u)
            seen_keys.add(k)
            unique.append(job)
        return unique
```

(`normalize_url` is already imported in `search_engine.py` via `models`; if not, add `from models import normalize_url`.) Then extend the cross-run filter in `search/cli.py` so a previously-seen `job_key` is also treated as seen (mirror the URL check already there ~lines 362–373).

- [ ] **Step 4: Run** `py -m pytest tests/coverage/test_dedup_wiring.py -v` → PASS; then `py -m pytest -q` to confirm no regression in existing dedup tests.
- [ ] **Step 5: Commit** `git add search/search_engine.py search/cli.py tests/coverage/test_dedup_wiring.py && git commit -m "feat(search): cross-source dedup via job_key behind the normalize_url fast-path"`

### Task 13 — Labeled-pair dedup accuracy gate (F1 ≥ 0.85)

**Files:** Create `tests/fixtures/coverage/labeled_pairs.jsonl`, `tests/coverage/test_dedup_accuracy.py`

The "tested for verification" gold check (spec §8).

- [ ] **Step 1:** Commit `tests/fixtures/coverage/labeled_pairs.jsonl` — **~40 hand-written** same/different pairs (expand toward ~200 later; note this inline in the file's first comment is not possible in JSONL, so track it in `data_static/README.md`). Each line: `{"a": {<JobResult fields>}, "b": {<JobResult fields>}, "same": true|false}`. Cover: company-variant=same, location-variant=same, seniority-variant=same, and distinct-role=different. Every job object must include all required `JobResult` fields (`title, company, location, salary_min, salary_max, description, url, source_keyword, created`). Example lines:

```
{"a":{"title":"Senior Software Developer","company":"Acme, Inc.","location":"Cincinnati, OH","salary_min":null,"salary_max":null,"description":"","url":"","source_keyword":"kw","created":"2026-06-22","source_api":"adzuna"},"b":{"title":"Software Developer","company":"Acme Inc","location":"Cincinnati","salary_min":null,"salary_max":null,"description":"","url":"","source_keyword":"kw","created":"2026-06-22","source_api":"themuse"},"same":true}
{"a":{"title":"Software Developer","company":"Acme","location":"Cincinnati, OH","salary_min":null,"salary_max":null,"description":"","url":"","source_keyword":"kw","created":"2026-06-22","source_api":"adzuna"},"b":{"title":"Mechanical Engineer","company":"Acme","location":"Cincinnati, OH","salary_min":null,"salary_max":null,"description":"","url":"","source_keyword":"kw","created":"2026-06-22","source_api":"adzuna"},"same":false}
```

- [ ] **Step 2: Write the test** `tests/coverage/test_dedup_accuracy.py`:

```python
import json
from pathlib import Path
from models import JobResult
from coverage.resolve import resolve

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "coverage" / "labeled_pairs.jsonl"

def _pairs():
    for line in FIXTURE.read_text(encoding="utf-8").splitlines():
        if line.strip():
            yield json.loads(line)

def _predict_same(a: dict, b: dict) -> bool:
    return len(resolve([JobResult(**a), JobResult(**b)])) == 1

def test_dedup_f1_meets_floor():
    tp = fp = fn = tn = 0
    for p in _pairs():
        pred, truth = _predict_same(p["a"], p["b"]), bool(p["same"])
        if pred and truth: tp += 1
        elif pred and not truth: fp += 1
        elif not pred and truth: fn += 1
        else: tn += 1
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    assert f1 >= 0.85, f"F1={f1:.3f} P={precision:.3f} R={recall:.3f}"
    assert precision >= 0.80 and recall >= 0.80
```

- [ ] **Step 3: Run** `py -m pytest tests/coverage/test_dedup_accuracy.py -v` → PASS (tune `resolve` thresholds in Task 6 if needed; record any threshold change).
- [ ] **Step 4: Commit** `git add tests/fixtures/coverage/labeled_pairs.jsonl tests/coverage/test_dedup_accuracy.py && git commit -m "test(coverage): labeled-pair dedup accuracy gate (F1>=0.85)"`

### Task 14 — Benchmark regression gate + recorded baseline + deps

**Files:** Create `tests/fixtures/coverage/cached_run.jsonl`, `tests/fixtures/coverage/baseline.json`, `tests/coverage/test_benchmark_regression.py`; Modify `app.spec`, `requirements.txt`

Records the "before" number WS-2 must beat and locks it as a regression test (spec §8, §10).

- [ ] **Step 1:** Commit `tests/fixtures/coverage/cached_run.jsonl` — a cached multi-source `list[JobResult]` for area `Cincinnati, OH` (~12 jobs, ≥2 `source_api` values incl. a cross-source dupe), each line a full `JobResult` dict (no live network in the test).
- [ ] **Step 2:** Generate the baseline once and commit it: run

```bash
py -c "import json; from pathlib import Path; from models import JobResult; from coverage.benchmark import run_benchmark; \
jobs=[JobResult(**json.loads(l)) for l in Path('tests/fixtures/coverage/cached_run.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]; \
r=run_benchmark(jobs,'Cincinnati, OH',['15-1252.00'],out_dir=Path('tests/fixtures/coverage/_tmp')); \
Path('tests/fixtures/coverage/baseline.json').write_text(json.dumps(r.to_dict(),indent=2),encoding='utf-8')"
```

then delete the throwaway `tests/fixtures/coverage/_tmp/` dir. `baseline.json` is the recorded baseline coverage number.

- [ ] **Step 3: Write the regression test** `tests/coverage/test_benchmark_regression.py`:

```python
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
```

- [ ] **Step 4:** Add `cleanco`, `rapidfuzz`, `datasketch` to `requirements.txt` (light, required; leave `statsmodels`/`splink` out — optional, capability-probed). Add `rapidfuzz`, `datasketch` to `hiddenimports` in `app.spec`.
- [ ] **Step 5: Run the whole suite** `py -m pytest -q` → all green.
- [ ] **Step 6: Commit** `git add tests/fixtures/coverage/cached_run.jsonl tests/fixtures/coverage/baseline.json tests/coverage/test_benchmark_regression.py app.spec requirements.txt && git commit -m "test(coverage): benchmark regression gate + recorded baseline; deps + PyInstaller hiddenimports"`

---

## Self-Review

- **Spec coverage:** entity resolution (Tasks 2–6) ✓; 3-leg benchmark — capture-recapture (7), JOLTS (8), reference-proxy (10), composite/persist (9, 11) ✓; dedup wiring (12) ✓; labeled-pair F1 gold check (13) ✓; regression gate + baseline (14) ✓; bundled static data (1) ✓; deps + PyInstaller (14) ✓.
- **Placeholders:** none — every code step has runnable code; the only acquisition step (Task 1 O\*NET/CBSA) names the public-domain sources and the exact target format.
- **Type consistency:** signatures match the Frozen Shared Interfaces; `job_key`/`scope_hash`/composite are pinned identically in Global Constraints and the tasks; `run_benchmark` carries `out_dir` (used by Tasks 11 & 14 tests).
- **Known follow-ups (not blockers):** labeled-pair set starts at ~40 (expand toward ~200); `_series_id` is a national-total stub (refine when JOLTS keys are wired); a _live_ baseline (real crawler run) is an Alex/Opus step — GLM uses the committed fixture baseline as the CI anchor.
