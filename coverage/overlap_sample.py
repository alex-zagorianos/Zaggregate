"""Independent OVERLAP sampling for reach measurement (E2 / review P1 Tier A).

Capture-recapture certifies reach only when independent source families OVERLAP.
The daily SerpApi probe (daily_run._reach_probe) supplies one cross-family overlap
inline. THIS module is a second, MEASUREMENT-ONLY path: it pulls a small random
sample of postings for the project's field+metro from an INDEPENDENT commercial
board and measures how many of that sample the run already captured (the overlap
count, f2). A high overlap corroborates high reach; a low overlap says the run is
missing a real slice. It writes a tiny JSON snapshot coverage/reach can surface as
an extra "family" line — it never fetches into or mutates the scored pipeline.

Two free-tier samplers (key-gated, opt-in, NOT in DAILY_SOURCES):

  * TheirStack  — POST https://api.theirstack.com/v1/jobs/search
      Auth: Authorization: Bearer <THEIRSTACK_API_KEY>. FREE tier ~200 credits/mo
      (1 credit ~= 1 returned job), so a sample of a few dozen is a handful of
      credits. Response: {"data": [{job_title, company, url, location, ...}]}.
      Field mapping verified 2026-07-01 against the live OpenAPI spec
      (api.theirstack.com/openapi.json).

  * Techmap jobdatafeeds via RapidAPI (PROVISIONAL) — GET the RapidAPI endpoint
      with X-RapidAPI-Key: <TECHMAP_RAPIDAPI_KEY>. FREE tier ~1,000 jobs/mo. The
      exact per-job field names are NOT verifiable from the public RapidAPI
      listing (marketing page, no open schema), so the parser reads several
      plausible aliases per field (name/title, company/orgName, url/apply_url,
      locality/region/orgAddress) — mark PROVISIONAL until checked against a live
      response. See deviations.

Config keys (env-then-secret): THEIRSTACK_API_KEY / TECHMAP_RAPIDAPI_KEY.

Design invariants: read-only, best-effort (never raises into a run), stdlib +
requests + the existing coverage/entity dedup identity. Opt-in: nothing here runs
unless its key is set AND the caller invokes it.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import config
from coverage import entity

THEIRSTACK_URL = "https://api.theirstack.com/v1/jobs/search"
# Techmap: the RapidAPI host + path are set at call time from config so a user can
# point at whichever Techmap jobdatafeeds product they subscribed to. Sensible
# default = the international daily-postings feed host.
TECHMAP_RAPIDAPI_HOST = "daily-international-job-postings.p.rapidapi.com"
TECHMAP_RAPIDAPI_PATH = "/api/v2/jobs/search"

_DEFAULT_SAMPLE = 40          # postings to pull per sampler (small, free-tier-safe)
_DEFAULT_MAX_AGE_DAYS = 30    # only recent postings, to match a fresh run


@dataclass
class _Posting:
    """A minimal posting for overlap math (mirrors the attrs entity.job_key_for
    reads: title / company / location)."""
    title: str = ""
    company: str = ""
    location: str = ""
    url: str = ""


@dataclass
class OverlapSample:
    source: str                    # 'theirstack' | 'techmap'
    area: str
    industry: str
    n_sample: int                  # postings pulled from the external source
    n_captured: int                # distinct captured job_keys we compared against
    overlap: int                   # sample postings ALSO in the captured set (f2)
    overlap_pct: Optional[float]   # overlap / n_sample * 100 (None if n_sample==0)
    method: str                    # 'job_key' | 'job_key+fuzzy'
    message: str = ""
    ts: str = ""

    def to_dict(self) -> dict:
        return {
            "source": self.source, "area": self.area, "industry": self.industry,
            "n_sample": self.n_sample, "n_captured": self.n_captured,
            "overlap": self.overlap, "overlap_pct": self.overlap_pct,
            "method": self.method, "message": self.message, "ts": self.ts,
        }


# ── dedup identity ────────────────────────────────────────────────────────────
def _key(p) -> str:
    """The run's dedup identity (coverage.entity.job_key_for) for any object with
    title/company/location attrs."""
    return entity.job_key_for(p)


def _captured_keys(captured) -> set:
    """Build the set of job_keys for the run's captured postings. `captured` is an
    iterable of JobResult-like objects OR an iterable of pre-computed key strings."""
    keys: set = set()
    for c in captured or ():
        if isinstance(c, str):
            keys.add(c)
        else:
            try:
                keys.add(_key(c))
            except Exception:
                continue
    return keys


def compute_overlap(sample, captured, *, fuzzy: bool = True) -> tuple[int, str]:
    """Overlap count between an external `sample` (list of _Posting/JobResult-like)
    and the run's `captured` set (JobResult-like objects OR key strings).

    Primary match is the exact job_key (company+SOC+location+title identity). When
    `fuzzy` and rapidfuzz is available, a sample posting whose exact key misses is
    given a second chance via the SAME company+title fuzzy rule coverage.resolve
    uses (so cross-source formatting differences don't undercount overlap).

    Returns (overlap_count, method)."""
    cap_keys = _captured_keys(captured)
    method = "job_key"
    overlap = 0
    # Fuzzy fallback needs the captured objects (not just keys) to compare titles.
    cap_objs = [c for c in (captured or ()) if not isinstance(c, str)]
    use_fuzzy = fuzzy and bool(cap_objs)
    try:
        from rapidfuzz import fuzz as _rf
    except Exception:
        _rf = None
        use_fuzzy = False
    if use_fuzzy:
        method = "job_key+fuzzy"

    for s in sample or ():
        try:
            sk = _key(s)
        except Exception:
            continue
        if sk in cap_keys:
            overlap += 1
            continue
        if not use_fuzzy:
            continue
        # Second chance: same canonical company AND fuzzy title match, mirroring
        # coverage.resolve._pair_matches (0.6 title + 0.4 company, threshold 85).
        sc = entity.canonicalize_company(getattr(s, "company", "") or "")
        st = getattr(s, "title", "") or ""
        for c in cap_objs:
            cc = entity.canonicalize_company(getattr(c, "company", "") or "")
            if sc != cc:
                continue
            ct = getattr(c, "title", "") or ""
            combined = 0.6 * _rf.token_set_ratio(st, ct) + 0.4 * _rf.WRatio(sc, cc)
            if combined >= 85.0:
                overlap += 1
                break
    return overlap, method


# ── samplers ──────────────────────────────────────────────────────────────────
def _theirstack_key() -> Optional[str]:
    return config.resolve_secret("THEIRSTACK_API_KEY", "theirstack_api_key")


def _techmap_key() -> Optional[str]:
    return config.resolve_secret("TECHMAP_RAPIDAPI_KEY", "techmap_rapidapi_key")


def _parse_theirstack(data) -> list[_Posting]:
    """Parse a TheirStack /v1/jobs/search response into _Postings. Field names
    verified against the live OpenAPI spec (2026-07-01)."""
    out: list[_Posting] = []
    items = (data or {}).get("data") if isinstance(data, dict) else None
    for it in items or []:
        if not isinstance(it, dict):
            continue
        loc = (it.get("location") or it.get("short_location")
               or it.get("long_location") or "")
        out.append(_Posting(
            title=(it.get("job_title") or "").strip(),
            company=(it.get("company") or "").strip(),
            location=(loc or "").strip(),
            url=(it.get("url") or it.get("final_url") or it.get("source_url") or ""),
        ))
    return out


def sample_theirstack(keyword: str, location: str = "", *, sample: int = _DEFAULT_SAMPLE,
                      country_code: str = "us", session=None,
                      max_age_days: int = _DEFAULT_MAX_AGE_DAYS) -> list[_Posting]:
    """Pull a small sample from TheirStack for `keyword`+`location`. [] if no key,
    an error, or no results (never raises)."""
    key = _theirstack_key()
    if not key:
        return []
    try:
        import requests
        sess = session or requests
        body = {
            "page": 0,
            "limit": max(1, min(int(sample), 50)),
            "job_title_or": [keyword] if keyword else [],
            "job_country_code_or": [country_code] if country_code else [],
            "posted_at_max_age_days": int(max_age_days),
            "order_by": [{"field": "date_posted", "desc": True}],
            "include_total_results": False,
        }
        if location:
            body["job_location_pattern_or"] = [location]
        resp = sess.post(THEIRSTACK_URL, json=body, timeout=30, headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        resp.raise_for_status()
        return _parse_theirstack(resp.json())
    except Exception:
        return []


def _parse_techmap(data) -> list[_Posting]:
    """Parse a Techmap jobdatafeeds response into _Postings (PROVISIONAL field
    mapping — reads several plausible aliases; see module docstring)."""
    if isinstance(data, dict):
        items = (data.get("data") or data.get("jobs") or data.get("results")
                 or data.get("hits") or [])
    elif isinstance(data, list):
        items = data
    else:
        items = []
    out: list[_Posting] = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        title = (it.get("name") or it.get("title") or it.get("jobTitle")
                 or it.get("position") or "")
        company = (it.get("company") or it.get("orgName") or it.get("companyName")
                   or it.get("hiringOrganization") or "")
        location = (it.get("locality") or it.get("city") or it.get("region")
                    or it.get("orgAddress") or it.get("location") or "")
        url = (it.get("url") or it.get("apply_url") or it.get("applyUrl")
               or it.get("jobUrl") or "")
        out.append(_Posting(title=str(title).strip(), company=str(company).strip(),
                            location=str(location).strip(), url=str(url)))
    return out


def sample_techmap(keyword: str, location: str = "", *, sample: int = _DEFAULT_SAMPLE,
                   session=None, host: str = TECHMAP_RAPIDAPI_HOST,
                   path: str = TECHMAP_RAPIDAPI_PATH) -> list[_Posting]:
    """Pull a small sample from Techmap jobdatafeeds via RapidAPI. [] if no key,
    an error, or no results (never raises). PROVISIONAL endpoint/params."""
    key = _techmap_key()
    if not key:
        return []
    try:
        import requests
        sess = session or requests
        url = f"https://{host}{path}"
        params = {"title": keyword, "location": location,
                  "size": max(1, min(int(sample), 100))}
        resp = sess.get(url, params=params, timeout=30, headers={
            "X-RapidAPI-Key": key,
            "X-RapidAPI-Host": host,
            "Accept": "application/json",
        })
        resp.raise_for_status()
        return _parse_techmap(resp.json())
    except Exception:
        return []


_SAMPLERS = {
    "theirstack": sample_theirstack,
    "techmap": sample_techmap,
}


def key_present(source: str) -> bool:
    """True if `source`'s free-tier key is configured (env or secret)."""
    s = (source or "").strip().lower()
    if s == "theirstack":
        return bool(_theirstack_key())
    if s == "techmap":
        return bool(_techmap_key())
    return False


def run_overlap_sample(source: str, captured, keyword: str, *, location: str = "",
                       industry: str = "", sample: int = _DEFAULT_SAMPLE,
                       persist: bool = True, project: str = "",
                       sampler=None) -> OverlapSample:
    """Measure how much of an independent `source` sample the run already captured.

    `captured`: the run's captured postings (JobResult-like) or their job_keys.
    `keyword`/`location`/`industry`: what to sample for. `sampler`: inject a fake
    in tests (a callable(keyword, location, sample=) -> list of postings); else the
    registered real sampler for `source` is used (which self-skips without a key).

    Returns an OverlapSample. Best-effort — never raises. When `persist`, writes a
    per-project JSON snapshot coverage/reach can surface as an extra family line."""
    src = (source or "").strip().lower()
    fn = sampler or _SAMPLERS.get(src)
    ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    if fn is None:
        return OverlapSample(source=src, area=location, industry=industry,
                             n_sample=0, n_captured=0, overlap=0, overlap_pct=None,
                             method="job_key", message=f"unknown source {src!r}", ts=ts)
    try:
        postings = fn(keyword, location, sample=sample) or []
    except Exception as e:
        return OverlapSample(source=src, area=location, industry=industry,
                             n_sample=0, n_captured=0, overlap=0, overlap_pct=None,
                             method="job_key",
                             message=f"sampler error: {type(e).__name__}", ts=ts)

    cap_list = list(captured or ())
    n_cap = len({c if isinstance(c, str) else _key(c) for c in cap_list}) if cap_list else 0
    overlap, method = compute_overlap(postings, cap_list)
    n_sample = len(postings)
    pct = (overlap / n_sample * 100.0) if n_sample else None
    if not key_present(src) and sampler is None and n_sample == 0:
        msg = f"{src}: no key configured — measurement skipped"
    elif n_sample == 0:
        msg = f"{src}: sample returned no postings"
    else:
        msg = (f"{src}: {overlap}/{n_sample} sampled postings already captured "
               f"(the run overlaps ~{pct:.0f}% of an independent {src} sample)")
    est = OverlapSample(source=src, area=location, industry=industry,
                        n_sample=n_sample, n_captured=n_cap, overlap=overlap,
                        overlap_pct=pct, method=method, message=msg, ts=ts)
    if persist:
        try:
            persist_sample(est, project=project)
        except Exception:
            pass
    return est


# ── persistence ───────────────────────────────────────────────────────────────
def _sample_dir() -> Path:
    return Path(config.USER_DATA_DIR) / "coverage" / "overlap"


def persist_sample(est: OverlapSample, *, project: str = "") -> Path:
    """Append to a per-project JSONL history + write a 'latest' snapshot. Returns
    the latest path. Best-effort."""
    base = _sample_dir()
    base.mkdir(parents=True, exist_ok=True)
    slug = (project or "root").replace("/", "_").replace("\\", "_")
    payload = {**est.to_dict(), "project": slug}
    with (base / f"{slug}.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload) + "\n")
    latest = base / f"{slug}.{est.source}.latest.json"
    latest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return latest


def load_latest(source: str, project: str = "") -> Optional[dict]:
    """Most recent persisted overlap snapshot for a project+source, or None."""
    slug = (project or "root").replace("/", "_").replace("\\", "_")
    p = _sample_dir() / f"{slug}.{(source or '').strip().lower()}.latest.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
