"""jobhive bulk seed — streaming, field-targeted, byte/candidate-bounded.

The manifest + per-ATS CSV slices are mocked with an in-memory bytes blob fed
through a fake requests-shaped session (small, DELIBERATELY odd chunk sizes,
so every test exercises the partial-trailing-line-across-chunks path). No
real network in any test below except the one tiny, hard-capped live smoke
test at the bottom (per plan)."""
import csv
import io
import json

import pytest

from discover import jobhive_seed as jhs
from discover.jobhive_seed import FieldSpec
from scrape.company_registry import CompanyEntry

MANIFEST_URL = "https://fake.test/manifest.json"

_HEADER = ["url", "title", "company", "ats_type", "ats_id", "location", "is_remote",
          "salary_min", "salary_max", "salary_currency", "salary_period",
          "salary_summary", "employment_type", "department", "team", "description",
          "posted_at", "requisition_id", "apply_url", "commitment", "raw", "country_iso"]


def _row(**kw) -> list:
    return [kw.get(c, "") for c in _HEADER]


def _csv_bytes(rows: list[list]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(_HEADER)
    for r in rows:
        w.writerow(r)
    return buf.getvalue().encode("utf-8")


def _manifest_bytes(ats_urls: dict) -> bytes:
    return json.dumps({"by_ats": {ats: {"csv": url} for ats, url in ats_urls.items()}}).encode("utf-8")


class _FakeResponse:
    def __init__(self, data: bytes, chunk_size: int = 37):
        self._data = data
        self._chunk_size = chunk_size
        self.closed = False

    def raise_for_status(self):
        pass

    def json(self):
        return json.loads(self._data.decode("utf-8"))

    def iter_content(self, chunk_size=8192):
        cs = self._chunk_size  # deliberately ignore the caller's hint (stress chunking)
        for i in range(0, len(self._data), cs):
            yield self._data[i:i + cs]

    def close(self):
        self.closed = True


class _FakeSession:
    def __init__(self, routes: dict, chunk_size: int = 37):
        self._routes = routes
        self._chunk_size = chunk_size
        self.calls: list[str] = []

    def get(self, url, headers=None, stream=False, timeout=None):
        self.calls.append(url)
        assert headers and "User-Agent" in headers  # jobhive 403s without one
        if url not in self._routes:
            raise AssertionError(f"unexpected URL requested: {url}")
        return _FakeResponse(self._routes[url], chunk_size=self._chunk_size)


def _make_session(rows: list[list], ats: str = "greenhouse", chunk_size: int = 37):
    csv_url = f"https://fake.test/{ats}/jobs.csv"
    routes = {MANIFEST_URL: _manifest_bytes({ats: csv_url}), csv_url: _csv_bytes(rows)}
    return _FakeSession(routes, chunk_size=chunk_size)


def _gh(slug: str, n: int) -> str:
    return f"https://job-boards.greenhouse.io/{slug}/jobs/{n}"


# ── relevance filtering ──────────────────────────────────────────────────────

def test_relevance_filtering_keeps_only_matching_rows():
    rows = [
        _row(url=_gh("acme", 1), title="Controls Engineer", company="Acme", location="Columbus, OH"),
        _row(url=_gh("globex", 2), title="Marketing Manager", company="Globex", location="Dayton, OH"),
    ]
    sess = _make_session(rows)
    fields = [FieldSpec("controls", ["engineer"])]
    result = jhs.seed_from_jobhive(fields, ["greenhouse"], session=sess, manifest_url=MANIFEST_URL,
                                   probe=lambda e: 5, dry_run=True, existing=set())
    assert result["fields"]["controls"]["candidates"] == 1
    assert result["ats"]["greenhouse"]["rows_scanned"] == 2
    assert [e.slug for e in result["entries"]] == ["acme"]


# ── multi-field bucketing ────────────────────────────────────────────────────

def test_multi_field_row_gets_both_tags():
    rows = [_row(url=_gh("dualco", 1), title="Robotics Controls Engineer", company="DualCo",
                location="Cincinnati, OH")]
    sess = _make_session(rows)
    fields = [FieldSpec("controls", ["engineer"]), FieldSpec("robotics", ["robot"])]
    result = jhs.seed_from_jobhive(fields, ["greenhouse"], session=sess, manifest_url=MANIFEST_URL,
                                   probe=lambda e: 5, dry_run=True, existing=set())
    assert result["fields"]["controls"]["candidates"] == 1
    assert result["fields"]["robotics"]["candidates"] == 1
    assert len(result["entries"]) == 1
    assert result["entries"][0].industries == ["controls", "robotics"]


# ── byte cap ──────────────────────────────────────────────────────────────────

def test_byte_cap_stops_the_stream_early():
    rows = [_row(url=_gh(f"co{i}", i), title="Controls Engineer", company=f"Company {i}",
                location="Cincinnati, OH, United States of America")
            for i in range(60)]
    sess = _make_session(rows)
    fields = [FieldSpec("controls", ["engineer"])]
    result = jhs.seed_from_jobhive(fields, ["greenhouse"], session=sess, manifest_url=MANIFEST_URL,
                                   probe=lambda e: 5, dry_run=True, existing=set(),
                                   max_bytes_per_ats=1200, limit_per_field=1000)
    s = result["ats"]["greenhouse"]
    assert 0 < s["rows_scanned"] < 60
    assert s["streamed_bytes"] >= 1200


# ── per-field candidate cap ──────────────────────────────────────────────────

def test_limit_per_field_stops_the_stream_early():
    rows = [_row(url=_gh(f"co{i}", i), title="Controls Engineer", company=f"Company {i}")
            for i in range(50)]
    sess = _make_session(rows)
    fields = [FieldSpec("controls", ["engineer"])]
    result = jhs.seed_from_jobhive(fields, ["greenhouse"], session=sess, manifest_url=MANIFEST_URL,
                                   probe=lambda e: 5, dry_run=True, existing=set(),
                                   max_bytes_per_ats=60_000_000, limit_per_field=3)
    s = result["ats"]["greenhouse"]
    assert result["fields"]["controls"]["candidates"] == 3
    assert s["rows_scanned"] < 50


# ── dedup vs the existing registry (BEFORE probing) ──────────────────────────

def test_dedup_skips_slug_already_in_registry_via_existing_param():
    rows = [
        _row(url=_gh("knownco", 1), title="Controls Engineer", company="KnownCo"),
        _row(url=_gh("newco", 2), title="Controls Engineer", company="NewCo"),
    ]
    sess = _make_session(rows)
    fields = [FieldSpec("controls", ["engineer"])]
    result = jhs.seed_from_jobhive(fields, ["greenhouse"], session=sess, manifest_url=MANIFEST_URL,
                                   probe=lambda e: 5, dry_run=True,
                                   existing={("greenhouse", "knownco")})
    assert result["fields"]["controls"]["candidates"] == 1
    assert [e.slug for e in result["entries"]] == ["newco"]


def test_dedup_uses_get_registry_when_existing_not_given(monkeypatch):
    rows = [
        _row(url=_gh("knownco", 1), title="Controls Engineer", company="KnownCo"),
        _row(url=_gh("newco", 2), title="Controls Engineer", company="NewCo"),
    ]
    sess = _make_session(rows)
    monkeypatch.setattr(
        jhs, "get_registry",
        lambda **kw: [CompanyEntry("KnownCo", "greenhouse", "knownco", ["x"])])
    fields = [FieldSpec("controls", ["engineer"])]
    result = jhs.seed_from_jobhive(fields, ["greenhouse"], session=sess, manifest_url=MANIFEST_URL,
                                   probe=lambda e: 5, dry_run=True)
    assert result["fields"]["controls"]["candidates"] == 1
    assert [e.slug for e in result["entries"]] == ["newco"]


# ── dry_run never saves ──────────────────────────────────────────────────────

def test_dry_run_does_not_call_save_companies(monkeypatch):
    rows = [_row(url=_gh("acme", 1), title="Controls Engineer", company="Acme")]
    sess = _make_session(rows)
    called = []
    monkeypatch.setattr(jhs, "save_companies", lambda *a, **k: called.append(1) or 0)
    fields = [FieldSpec("controls", ["engineer"])]
    result = jhs.seed_from_jobhive(fields, ["greenhouse"], session=sess, manifest_url=MANIFEST_URL,
                                   probe=lambda e: 5, dry_run=True, existing=set())
    assert called == []
    assert result["added"] == 0
    assert result["fields"]["controls"]["added"] == 0
    assert result["verified"] == 1


def test_not_dry_run_calls_save_companies_with_merged_entries(monkeypatch):
    rows = [_row(url=_gh("dualco", 1), title="Robotics Controls Engineer", company="DualCo")]
    sess = _make_session(rows)
    saved: list = []

    def _fake_save(entries, path=None):
        saved.extend(entries)
        return len(entries)

    monkeypatch.setattr(jhs, "save_companies", _fake_save)
    fields = [FieldSpec("controls", ["engineer"]), FieldSpec("robotics", ["robot"])]
    result = jhs.seed_from_jobhive(fields, ["greenhouse"], session=sess, manifest_url=MANIFEST_URL,
                                   probe=lambda e: 5, existing=set())
    assert result["added"] == 1
    assert [e.slug for e in saved] == ["dualco"]
    assert saved[0].industries == ["controls", "robotics"]
    assert result["fields"]["controls"]["added"] == 1
    assert result["fields"]["robotics"]["added"] == 1


# ── slug derived from url ────────────────────────────────────────────────────

def test_slug_derived_from_url():
    rows = [_row(url="https://job-boards.greenhouse.io/1800contacts/jobs/7974903",
                title="Controls Engineer", company="Whatever Inc", ats_type="")]
    sess = _make_session(rows)
    fields = [FieldSpec("controls", ["engineer"])]
    result = jhs.seed_from_jobhive(fields, ["greenhouse"], session=sess, manifest_url=MANIFEST_URL,
                                   probe=lambda e: 1, dry_run=True, existing=set())
    assert [e.slug for e in result["entries"]] == ["1800contacts"]
    assert result["entries"][0].ats_type == "greenhouse"


def test_fallback_to_ats_type_and_company_when_url_unresolvable():
    # No url column value at all -> detect_ats("") returns ("direct", "") -> the
    # ats_type + company columns are the fallback.
    rows = [_row(url="", title="Controls Engineer", company="Some Company Inc.",
                ats_type="Lever")]
    sess = _make_session(rows)
    fields = [FieldSpec("controls", ["engineer"])]
    result = jhs.seed_from_jobhive(fields, ["greenhouse"], session=sess, manifest_url=MANIFEST_URL,
                                   probe=lambda e: 1, dry_run=True, existing=set())
    assert len(result["entries"]) == 1
    entry = result["entries"][0]
    assert entry.ats_type == "lever"
    assert entry.slug == "some-company-inc"


# ── probe-0 boards are dropped ───────────────────────────────────────────────

def test_probe_zero_board_is_dropped():
    rows = [
        _row(url=_gh("deadco", 1), title="Controls Engineer", company="DeadCo"),
        _row(url=_gh("liveco", 2), title="Controls Engineer", company="LiveCo"),
    ]
    sess = _make_session(rows)

    def probe(e):
        return {"deadco": 0, "liveco": 4}.get(e.slug, 0)

    fields = [FieldSpec("controls", ["engineer"])]
    result = jhs.seed_from_jobhive(fields, ["greenhouse"], session=sess, manifest_url=MANIFEST_URL,
                                   probe=probe, dry_run=True, existing=set())
    assert [e.slug for e in result["entries"]] == ["liveco"]
    assert any(ats == "greenhouse" and slug == "deadco" and reason == "no live jobs"
              for ats, slug, reason in result["dropped"])


# ── embedded newline inside a quoted field doesn't corrupt row parsing ───────

def test_embedded_newline_in_description_does_not_corrupt_parsing():
    rows = [
        _row(url=_gh("wraps", 1), title="Controls Engineer", company="Wraps Inc",
            description="Line one.\nLine two.\nLine three."),
        _row(url=_gh("after", 2), title="Controls Engineer", company="After Inc"),
    ]
    sess = _make_session(rows, chunk_size=13)  # tiny + odd, forces mid-field chunk splits
    fields = [FieldSpec("controls", ["engineer"])]
    result = jhs.seed_from_jobhive(fields, ["greenhouse"], session=sess, manifest_url=MANIFEST_URL,
                                   probe=lambda e: 1, dry_run=True, existing=set())
    assert result["ats"]["greenhouse"]["rows_scanned"] == 2
    assert sorted(e.slug for e in result["entries"]) == ["after", "wraps"]


# ── non-seedable / unknown ATS is skipped, not crashed on ───────────────────

def test_unknown_ats_in_ats_list_is_skipped():
    rows = [_row(url=_gh("acme", 1), title="Controls Engineer", company="Acme")]
    sess = _make_session(rows)
    fields = [FieldSpec("controls", ["engineer"])]
    result = jhs.seed_from_jobhive(fields, ["icims", "greenhouse"], session=sess,
                                   manifest_url=MANIFEST_URL, probe=lambda e: 1,
                                   dry_run=True, existing=set())
    assert "icims" not in result["ats"]
    assert result["fields"]["controls"]["candidates"] == 1


# ── _probe_board delegation (workable/recruitee/personio have no count API,
#    so the default probe reuses their own careers-scraper fetch()) ─────────

def test_probe_board_delegates_to_workable_scraper(monkeypatch):
    import scrape.workable_scraper as ws
    monkeypatch.setattr(ws, "fetch", lambda slug, **kw: [object(), object(), object()])
    entry = CompanyEntry("Acme", "workable", "acme", [])
    assert jhs._probe_board(entry) == 3


def test_probe_board_delegates_to_recruitee_scraper(monkeypatch):
    import scrape.recruitee_scraper as rs
    monkeypatch.setattr(rs, "fetch", lambda slug, **kw: [object()])
    entry = CompanyEntry("Acme", "recruitee", "acme", [])
    assert jhs._probe_board(entry) == 1


def test_probe_board_delegates_to_personio_scraper(monkeypatch):
    import scrape.personio_scraper as ps
    monkeypatch.setattr(ps, "fetch", lambda slug, **kw: [])
    entry = CompanyEntry("Acme", "personio", "acme", [])
    assert jhs._probe_board(entry) == 0


def test_probe_board_falls_back_to_probe_count_for_other_ats(monkeypatch):
    monkeypatch.setattr(jhs, "_probe_count", lambda entry: 42)
    entry = CompanyEntry("Acme", "greenhouse", "acme", [])
    assert jhs._probe_board(entry) == 42


# ── keywords_for_industry ────────────────────────────────────────────────────

def test_keywords_for_industry_is_deduped_and_lowercased():
    kw = jhs.keywords_for_industry("controls engineering")
    assert kw == list(dict.fromkeys(kw))          # no duplicates
    assert all(k == k.lower() for k in kw)         # all lowercase
    assert "controls" in kw and "engineering" in kw


# ── ONE tiny live smoke test (per plan) — real manifest + a small real slice,
#    hard-capped at 64 KB, skips (never fails) if the sandbox has no network. ──

def test_live_smoke_reads_small_real_slice():
    fields = [FieldSpec("smoke", ["engineer", "manager", "specialist", "coordinator",
                                  "director", "analyst"])]
    try:
        # chunk_size well under the byte cap (real jobhive rows carry a raw/
        # description column that can run several KB) so the cap is hit only
        # after a few rows are actually readable, not on the very first pull.
        result = jhs.seed_from_jobhive(fields, ["bamboohr"], max_bytes_per_ats=50_000,
                                       chunk_size=8_192, limit_per_field=5, dry_run=True,
                                       probe=lambda e: 0)  # never hit a real probe endpoint
    except Exception as e:
        pytest.skip(f"jobhive unreachable from this sandbox: {type(e).__name__}: {e}")
    if result.get("error"):
        pytest.skip(f"jobhive manifest fetch failed: {result['error']}")
    s = result["ats"].get("bamboohr", {})
    if s.get("error"):
        pytest.skip(f"jobhive slice fetch failed: {s['error']}")
    assert s["streamed_bytes"] > 0
    assert s["streamed_bytes"] < 150_000           # well under "large"
    assert s["rows_scanned"] >= 1
