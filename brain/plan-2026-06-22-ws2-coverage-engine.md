# WS-2 Generic Coverage Engine — Implementation Plan (4 phases)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Raise the WS-1 CoverageScore for the user's `(area, target_roles)` for free: replace registry-as-seed with a generic discovery funnel, add 4 Tier-1 ATS scrapers + a JSON-LD extractor + a Workday CSRF fix, add 3 free aggregators + LinkedIn guest + a BYO SerpApi backend, and add geo/remote filtering, title+body matching, freshness deltas, and `target_roles` config. Every source group is gated by a **lift test** that re-runs WS-1's `coverage.benchmark.run_benchmark` on a before/after fixture and asserts the score rose.

**Architecture:** Extends the existing `scrape/` (ATS scrapers, all following the `scrape/careers_client.py` dispatcher + the greenhouse/lever/ashby/smartrecruiters scraper shape) and `search/` (aggregators inheriting `search/base_client.py` / `search/single_feed_client.py`, registered in `search/cli.py` `ALL_SOURCES` + `build_clients`) packages, plus a NEW `discover/` package (the generic denominator builder) and a NEW `geo/` package (metro filter built on WS-1's `coverage.geography`). The cross-source join key is WS-1's `JobResult.job_key` (sha1, 16-hex, `functools.cached_property`).

**Tech Stack:** Python 3.11, pytest (`py -m pytest <path> -v`). stdlib `json`/`re`/`xml.etree.ElementTree`/`hashlib`/`html`. `requests` + `beautifulsoup4` (already in `requirements.txt`). Optional heavy deps behind `try/except ImportError` with a documented fallback. No live network in any test — every network-touching test uses a recorded fixture via `monkeypatch.setattr(requests, "get"/"post", ...)` (the existing `tests/test_careers_fixes.py` `_Resp` pattern).

## Global Constraints

- **Test runner:** `py -m pytest <path> -v` (Windows `py` launcher). The suite must stay green; each phase adds tests. Current suite ≈ 269 test functions across 39 files — recount at build time; do not hard-code a target.
- **Depends on WS-1:** the `coverage/` package (`coverage.entity.job_key_for`, `coverage.geography.metro_variants`, `coverage.resolve.resolve`, `coverage.benchmark.run_benchmark`) and `JobResult.job_key` MUST already exist (WS-1 plan). If `coverage/` is absent, STOP and surface it — do not stub WS-1 here.
- **`job_key` is the join key** (WS-1, pinned): `sha1("\x1f".join([company_canon, soc_code, loc_token, title_core])).hexdigest()[:16]`, exposed via `JobResult.job_key` (`functools.cached_property`, local import, `ImportError`→`self.identity_key`). WS-2 only _consumes_ it (dedup, freshness, lift) — never redefines it.
- **`JobResult` fields are frozen** (from `models.py`): `title, company, location, salary_min, salary_max, description, url, source_keyword, created, job_id="", source_api="", score=-1, score_notes="", board_count=-1`. Every new scraper/client emits these and only these. `salary_min`/`salary_max` are `Optional[float]`; `created` is a string (ISO preferred). Use `to_float` (`search/http_util.py`) for numeric salary coercion.
- **Optional heavy deps behind `try/except ImportError`** with a documented fallback (mirrors WS-1's `cleanco`/`rapidfuzz` handling). No new _required_ deps beyond what `requirements.txt` already lists (`beautifulsoup4`, `requests`). `lxml` stays OUT — `BeautifulSoup(html, "html.parser")` (stdlib parser) is the documented fallback already used by `scrape/direct_scraper.py`.
- **XML safety (XXE / billion-laughs):** Personio feeds and arbitrary third-party sitemaps are UNTRUSTED XML. Stdlib `xml.etree.ElementTree` is vulnerable to external-entity (XXE) and entity-expansion (billion-laughs) attacks, so every XML parse goes through a shared hardened helper `_safe_fromstring(data)` that prefers `defusedxml.ElementTree.fromstring` and falls back to stdlib **only after stripping DOCTYPE/DTD** (entity attacks require a DTD). `defusedxml` is an OPTIONAL dep (`try/except ImportError`), added to `requirements.txt` in Setup but never hard-required — the DTD-stripping stdlib fallback keeps the parse safe when it is absent. This helper lives in `scrape/xml_safe.py` (Task 2b.0) and is reused by `scrape/personio_scraper.py` and `discover/career_link.py`.
- **Path model (`config.py`):** bundled read-only data resolves under `DATA_DIR`; ALL writes go under `USER_DATA_DIR`. Discovered boards merge into `config.COMPANIES_JSON` (= `USER_DATA_DIR/companies.json`); freshness per-source `job_key` sets persist under `USER_DATA_DIR/freshness/`. Never write under `DATA_DIR`/`_MEIPASS`. `CACHE_DIR = USER_DATA_DIR/cache`.
- **HTTP plumbing reuse:** new aggregators use `search/http_util.py` (`FileCache`, `RateLimiter(int).acquire()`, `cache_key`, `make_session`, `to_float`, `MonthlyQuota`). New ATS scrapers use `scrape/cache_helpers.py` (`read_cache`/`write_cache`/`slug_safe`/`is_failed`/`mark_failed`) + `config.CAREERS_REQUEST_TIMEOUT` + `config.CAREERS_MAX_WORKERS`, exactly like the existing scrapers.
- **Title+body match, not title-only:** existing scrapers gate on TITLE only via `scrape.text_match.keyword_matches`. WS-2 adds `keyword_matches_deep(keyword, title, body)` (title OR body) WITHOUT changing `keyword_matches`; new scrapers and the JSON-LD extractor gate with the deep matcher, and existing scrapers are migrated in WS-2d's task.
- **Legal posture (spec §2, §3, §7):** public/unauthenticated sources only by default; LinkedIn = logged-out **guest endpoints** only (no auth, no cookies, no accounts), off by default. BYO-paid backends (SerpApi) are key-gated and quota-conserving like `jsearch_client.py`. Any source down / rate-limited / key-missing → degrade to `[]` **with a logged warning** (never silent).
- **Fix the silent-empty discovery failure (spec §5.1):** discovery with no reachability must **log loudly** (a `WARNING`/print), not return `[]` silently — implemented in `discover/registry.py` `merge_discovered` and `discover/cc_harvest.harvest_slugs`.
- **TDD + frequent commits:** each task = failing test → run-to-fail → minimal impl → run-to-pass → conventional commit. The executor commits; commits are conventional-commit (`feat(...)`, `test(...)`, `fix(...)`).

## Setup (deps to pip install)

No new _required_ runtime deps. Confirm the existing ones are importable from the repo root, and install the one OPTIONAL hardening dep (`defusedxml`, for safe XML parsing — see XML safety constraint):

```bash
py -m pip install requests beautifulsoup4 defusedxml
```

`requests==2.32.3` and `beautifulsoup4==4.12.3` are already pinned in `requirements.txt`. `defusedxml` is optional: add it to `requirements.txt` in Task 2b.0, but the code degrades to a DTD-stripping stdlib fallback when it is absent, so the suite passes either way. No `lxml`, no `responses`, no `vcrpy` — tests mock `requests.get`/`requests.post` directly. WS-1's deps (`cleanco`, `rapidfuzz`, `datasketch`) must already be installed from the WS-1 build; if `py -c "import coverage.benchmark"` fails, finish WS-1 first.

## Out of scope for the executor (do NOT touch)

- The entire `coverage/` package and `data_static/` (owned by WS-1 — read-only here; consume, never edit).
- `gui.py`, `mcp_server.py`, `claude_bridge.py`, `ranker.py`, `tracker/`, `match/`, `resume/`, the resume generator, and any `brain/` doc.
- Coverage math / estimators / the composite formula (WS-1). WS-2 only feeds more jobs into `run_benchmark`.
- AI ranking / round-trip (that is WS-3).
- Do NOT add Tier-3 official ATS API integrations (Teamtailor/BambooHR/Breezy/iCIMS/Jobvite/ADP/Paycom) — JSON-LD/HTML fallback only.
- Do NOT bundle any paid API key; do NOT scrape behind a login or with cookies; do NOT scrape Google Jobs directly.
- Do NOT make live network calls in tests; do NOT `git push`, change git config, or merge branches.

## Frozen Shared Interfaces

Every task uses these EXACT names/signatures. Internal helpers/tests are task-local.

```
# discover/cc_harvest.py
harvest_slugs(ats_hosts: list, *, crawl_id: str | None = None, limit: int | None = None) -> dict[str, set]
    # {ats_type: {slug, ...}}; queries Common Crawl CDX per host, regexes slugs, dedupes.

# discover/career_link.py
find_career_url(domain: str) -> str | None        # robots/sitemap/homepage-anchor -> careers URL
sitemap_job_urls(domain: str) -> list             # job-ish URLs harvested from sitemap(s)

# discover/detect.py  (thin wrapper around the existing scrape.ats_detect)
detect_ats(url_or_domain: str) -> tuple[str, str] | None   # (ats_type, slug); host-inspect -> embed-fingerprint -> brute-probe; None if undetectable

# discover/registry.py
merge_discovered(boards: dict, companies_json_path) -> int  # user-wins merge into companies.json; loud on empty/unreachable; returns count added

# scrape/workable_scraper.py
fetch(slug: str) -> list[JobResult]               # apply.workable.com/api/v1/widget/accounts/{slug}
# scrape/recruitee_scraper.py
fetch(slug: str) -> list[JobResult]               # {slug}.recruitee.com/api/offers/
# scrape/rippling_scraper.py
fetch(slug: str) -> list[JobResult]               # api.rippling.com/platform/api/ats/v1/board/{slug}/jobs
# scrape/personio_scraper.py
fetch(slug: str) -> list[JobResult]               # {slug}.jobs.personio.de/xml  (XML)
# scrape/jsonld_scraper.py
extract_jobs(html: str, base_url: str) -> list[JobResult]   # schema.org JobPosting / ItemList

# scrape/xml_safe.py  (NEW — XXE/billion-laughs-safe XML)
_safe_fromstring(data) -> xml.etree.ElementTree.Element     # defusedxml if present, else DTD-stripped stdlib

# scrape/text_match.py  (EXTEND — keep keyword_matches unchanged)
keyword_matches_deep(keyword: str, title: str, body: str) -> bool   # match title OR body

# search/ aggregators (inherit JobAPIClient / SingleFeedClient; register in cli.ALL_SOURCES + build_clients)
ArbeitnowClient · JoobleClient · CareerjetClient · LinkedInGuestClient · SerpApiClient
# each implements search(keyword, location, salary_min, page) -> dict and parse_results(raw, source_keyword) -> list[JobResult]

# geo/filter.py
filter_to_metro(jobs: list, area: str, *, remote_region: str | None = None) -> list
    # keep a job if its location matches coverage.geography.metro_variants(area), OR it's remote and passes remote_region.

# search/freshness.py
new_since_last(jobs: list, source_id: str, prev_keys: set) -> list   # jobs whose job_key not in prev_keys
load_prev_keys(source_id: str, base_dir=None) -> set                 # read USER_DATA_DIR/freshness/<source_id>.json
save_keys(source_id: str, keys: set, base_dir=None) -> None          # persist the per-source job_key set

# preferences.py  (EXTEND _DEFAULT_HARD + migrate_from_user_config)
hard["target_roles"]: list[str]   # seeded on migration from user_config.json["keywords"] + parsed from preferences.md
```

## File Structure

```
discover/                    # NEW package (WS-2a)
  __init__.py · cc_harvest.py · career_link.py · detect.py · registry.py
scrape/                      # NEW scrapers (WS-2b) — siblings of greenhouse/lever/...
  workable_scraper.py · recruitee_scraper.py · rippling_scraper.py · personio_scraper.py
  jsonld_scraper.py
  xml_safe.py                # NEW — XXE/billion-laughs-safe XML parse (WS-2a Task 2a.0)
  careers_client.py          # MODIFY — dispatch new ATS types (WS-2b)
  ats_detect.py              # MODIFY — recognize new ATS hosts (WS-2b)
  text_match.py              # MODIFY — add keyword_matches_deep (WS-2d)
  discoverer.py              # MODIFY — loud-failure fix wiring (WS-2a)
  workday_scraper.py         # MODIFY — CSRF prime + faceted paging (WS-2b)
geo/                         # NEW package (WS-2d)
  __init__.py · filter.py
search/
  arbeitnow_client.py · jooble_client.py · careerjet_client.py        # NEW (WS-2c)
  linkedin_guest_client.py · serpapi_client.py                        # NEW (WS-2c)
  freshness.py               # NEW (WS-2d)
  cli.py                     # MODIFY — register new sources (WS-2c)
preferences.py               # MODIFY — target_roles (WS-2d)
config.py                    # MODIFY — new source consts (WS-2c)
tests/discover/              # NEW (WS-2a)
tests/scrape/                # NEW (WS-2b)
tests/search/                # NEW (WS-2c)
tests/geo/                   # NEW (WS-2d)
tests/fixtures/ws2/          # NEW — recorded CDX/ATS/HTML/before-after fixtures
```

---

# PHASE WS-2a — Generic discovery layer + loud-failure fix

**Scope:** the new `discover/` package (`cc_harvest`, `career_link`, `detect`, `registry`), the shared XXE-safe XML helper (used by `career_link` here and by `personio_scraper` in WS-2b), and the loud-failure fix. Replaces registry-as-seed with a generic denominator builder. No scrapers, no aggregators here.
**Verify:** `py -m pytest tests/discover -q`

### Task 2a.0 — `scrape/xml_safe._safe_fromstring` (XXE-hardened XML parse)

**Files:** Create `scrape/xml_safe.py`, `tests/scrape/__init__.py`, `tests/scrape/test_xml_safe.py`; Modify `requirements.txt`

**Interfaces — Produces:** `_safe_fromstring(data) -> xml.etree.ElementTree.Element`. **Consumed by:** `discover/career_link.py` (Task 2a.3, this phase) and `scrape/personio_scraper.py` (Task 2b.4, WS-2b). Built FIRST so both phases can `from scrape.xml_safe import _safe_fromstring`. (WS-2b's Task 2b.0 is a reuse-guard that re-runs this test and does NOT recreate the file — if WS-2b is dispatched independently of WS-2a, run this task there instead; whichever phase runs first owns the file, the other only verifies it exists.)

Personio feeds and arbitrary third-party sitemaps are untrusted XML. This helper prefers `defusedxml` (which rejects DTDs/entities outright) and, when it is absent, falls back to stdlib `ElementTree` **after stripping any DOCTYPE/DTD** so XXE and billion-laughs payloads (both of which require a DTD) cannot execute. It accepts `str` or `bytes` and returns a normal `Element`, so callers are unchanged.

- [ ] **Step 1:** Create `tests/scrape/__init__.py` (empty).
- [ ] **Step 2: Write the failing test** `tests/scrape/test_xml_safe.py`:

```python
from scrape.xml_safe import _safe_fromstring

def test_parses_benign_xml():
    root = _safe_fromstring("<root><a>hi</a></root>")
    assert root.find("a").text == "hi"

def test_accepts_bytes():
    root = _safe_fromstring(b"<root><a>hi</a></root>")
    assert root.tag == "root"

def test_billion_laughs_is_neutralized():
    # Classic entity-expansion bomb. Either the parser refuses the DTD/entity
    # (defusedxml raises) or the DTD is stripped so &lol; never expands.
    bomb = (
        '<?xml version="1.0"?>'
        '<!DOCTYPE lolz [<!ENTITY lol "lol">'
        '<!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;">]>'
        '<lolz>&lol2;</lolz>'
    )
    try:
        root = _safe_fromstring(bomb)
    except Exception:
        return  # defusedxml refused it — safe
    assert "lollollol" not in (root.text or "")  # stdlib path: DTD stripped, unexpanded

def test_external_entity_not_resolved():
    xxe = (
        '<?xml version="1.0"?>'
        '<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
        '<foo>&xxe;</foo>'
    )
    try:
        root = _safe_fromstring(xxe)
    except Exception:
        return  # refused — safe
    assert "root:" not in (root.text or "")  # file contents never injected
```

- [ ] **Step 3: Run to fail** `py -m pytest tests/scrape/test_xml_safe.py -v` → FAIL (module missing).
- [ ] **Step 4: Implement** `scrape/xml_safe.py`:

```python
"""XXE / billion-laughs-safe XML parsing for untrusted feeds (Personio, sitemaps).

Prefers defusedxml (rejects DTDs + entity expansion). When defusedxml is not
installed, falls back to stdlib ElementTree AFTER stripping any DOCTYPE/DTD —
both XXE and entity-expansion attacks require a DTD, so a DTD-free document is
safe to parse with the stdlib. Returns a normal ElementTree.Element either way.
"""
from __future__ import annotations
import re
import xml.etree.ElementTree as _ET

try:
    from defusedxml.ElementTree import fromstring as _defused_fromstring
    _HAVE_DEFUSED = True
except ImportError:
    _HAVE_DEFUSED = False

# Matches a leading <!DOCTYPE ...> declaration (incl. an internal [...] subset).
_DOCTYPE_RE = re.compile(rb"<!DOCTYPE[^>\[]*(\[[^\]]*\])?[^>]*>", re.IGNORECASE | re.DOTALL)


def _to_bytes(data) -> bytes:
    return data.encode("utf-8") if isinstance(data, str) else data


def _safe_fromstring(data):
    """Parse untrusted XML safely. Accepts str or bytes; returns an Element."""
    raw = _to_bytes(data)
    if _HAVE_DEFUSED:
        return _defused_fromstring(raw)
    # No defusedxml: strip the DTD so entity/XXE payloads cannot execute.
    stripped = _DOCTYPE_RE.sub(b"", raw)
    parser = _ET.XMLParser()
    try:  # belt-and-suspenders: disable entity handling on the expat parser
        parser.parser.DefaultHandler = lambda data: None
        parser.parser.EntityDeclHandler = None
    except (AttributeError, TypeError):
        pass
    return _ET.fromstring(stripped, parser=parser)
```

- [ ] **Step 5: Run** `py -m pytest tests/scrape/test_xml_safe.py -v` → PASS (with or without `defusedxml` installed).
- [ ] **Step 6:** Append `defusedxml==0.7.1` to `requirements.txt` (optional-but-recommended; import-guarded, so a build without it still passes).
- [ ] **Step 7: Commit** `git add scrape/xml_safe.py tests/scrape/__init__.py tests/scrape/test_xml_safe.py requirements.txt && git commit -m "feat(scrape): XXE/billion-laughs-safe XML parse helper (defusedxml + DTD-stripping fallback)"`

### Task 2a.1 — `discover/` package skeleton + `detect.detect_ats`

**Files:** Create `discover/__init__.py`, `discover/detect.py`, `tests/discover/__init__.py`, `tests/discover/test_detect.py`

**Interfaces — Produces:** `detect.detect_ats(url_or_domain) -> tuple[str,str] | None`. **Consumes:** `scrape.ats_detect.detect_ats` (existing; returns `(ats_type, slug)` with `"direct"` fallback).

The existing `scrape/ats_detect.detect_ats` returns `("direct", url)` for anything it can't classify and `("direct", "")` for empty host. The discovery wrapper tightens that to `None` (undetectable) and adds the host-inspect → embed-fingerprint → brute-probe order described in spec §5.1.

- [ ] **Step 1:** Create `discover/__init__.py` (empty package marker) and `tests/discover/__init__.py` (empty).
- [ ] **Step 2: Write the failing test** `tests/discover/test_detect.py`:

```python
from discover.detect import detect_ats

def test_greenhouse_url():
    assert detect_ats("https://boards.greenhouse.io/acme") == ("greenhouse", "acme")

def test_workable_host_inspect():
    assert detect_ats("https://apply.workable.com/acme/") == ("workable", "acme")

def test_recruitee_subdomain():
    assert detect_ats("https://acme.recruitee.com/") == ("recruitee", "acme")

def test_personio_subdomain():
    assert detect_ats("https://acme.jobs.personio.de/") == ("personio", "acme")

def test_unknown_returns_none():
    assert detect_ats("https://example.com/about") is None

def test_empty_returns_none():
    assert detect_ats("") is None
```

- [ ] **Step 3: Run to fail** `py -m pytest tests/discover/test_detect.py -v` → FAIL (module missing).
- [ ] **Step 4: Implement** `discover/detect.py`:

```python
"""Discovery-grade ATS detection.

Wraps the existing scrape.ats_detect (greenhouse/lever/ashby/smartrecruiters/
workday) and adds host-inspection for the WS-2 Tier-1 scrapers
(workable/recruitee/rippling/personio). Returns None when nothing is
recognized (the existing detector's 'direct' fallback is noise for discovery).
Order: cheap host inspection first; embed-fingerprint + brute-probe are layered
on by callers that have a fetched page / candidate slugs.
"""
from __future__ import annotations
from urllib.parse import urlsplit

from scrape.ats_detect import detect_ats as _legacy_detect


def _split(url_or_domain: str):
    u = (url_or_domain or "").strip()
    if not u:
        return "", []
    if "://" not in u:
        u = "https://" + u
    parts = urlsplit(u)
    host = (parts.netloc or "").lower().split(":")[0]
    segs = [s for s in parts.path.split("/") if s]
    return host, segs


def _detect_new_ats(host: str, segs: list) -> tuple[str, str] | None:
    # workable: apply.workable.com/{slug}
    if host == "apply.workable.com" and segs:
        return ("workable", segs[0])
    # recruitee: {slug}.recruitee.com
    if host.endswith(".recruitee.com"):
        sub = host[: -len(".recruitee.com")]
        if sub and sub not in ("www", "api"):
            return ("recruitee", sub)
    # personio: {slug}.jobs.personio.de  (also .com)
    for suffix in (".jobs.personio.de", ".jobs.personio.com"):
        if host.endswith(suffix):
            sub = host[: -len(suffix)]
            if sub and sub not in ("www", "api"):
                return ("personio", sub)
    return None


def detect_ats(url_or_domain: str) -> tuple[str, str] | None:
    """Return (ats_type, slug) or None if undetectable."""
    host, segs = _split(url_or_domain)
    if not host:
        return None
    new = _detect_new_ats(host, segs)
    if new is not None:
        return new
    ats, slug = _legacy_detect(url_or_domain)
    if ats == "direct" or not slug:
        return None
    return (ats, slug)
```

- [ ] **Step 5: Run** `py -m pytest tests/discover/test_detect.py -v` → PASS.
- [ ] **Step 6: Commit** `git add discover/__init__.py discover/detect.py tests/discover/__init__.py tests/discover/test_detect.py && git commit -m "feat(discover): package skeleton + detect_ats wrapper (new Tier-1 hosts, None on unknown)"`

### Task 2a.2 — `discover/cc_harvest.harvest_slugs`

**Files:** Create `discover/cc_harvest.py`, `tests/fixtures/ws2/cdx_greenhouse.jsonl`, `tests/discover/test_cc_harvest.py`

**Interfaces — Produces:** `harvest_slugs(ats_hosts, *, crawl_id=None, limit=None) -> dict[str,set]`. **Consumes:** `discover.detect.detect_ats`, `search.http_util.make_session`, `scrape.cache_helpers.read_cache/write_cache`.

Common Crawl CDX returns one JSON object per line (NDJSON). Each line has a `url`. We regex the ATS slug out of each URL via `detect_ats`. Loud-failure: zero reachable hosts → log a warning, return an empty dict (callers decide whether to fall back). The unit test feeds captured CDX lines through a mocked session (no live call).

- [ ] **Step 1:** Create the fixture `tests/fixtures/ws2/cdx_greenhouse.jsonl` (captured-shape CDX NDJSON, public URLs only):

```
{"urlkey":"io,greenhouse,boards)/acme","timestamp":"20250101000000","url":"https://boards.greenhouse.io/acme/jobs/123","status":"200"}
{"urlkey":"io,greenhouse,boards)/acme","timestamp":"20250102000000","url":"https://boards.greenhouse.io/acme/jobs/456","status":"200"}
{"urlkey":"io,greenhouse,boards)/beta","timestamp":"20250101000000","url":"https://boards.greenhouse.io/beta","status":"200"}
{"urlkey":"io,greenhouse,boards)/robots","timestamp":"20250101000000","url":"https://boards.greenhouse.io/robots.txt","status":"200"}
```

- [ ] **Step 2: Write the failing test** `tests/discover/test_cc_harvest.py`:

```python
from pathlib import Path
import discover.cc_harvest as H

FX = Path(__file__).resolve().parents[1] / "fixtures" / "ws2"

class _Resp:
    def __init__(self, text, status=200):
        self.text = text
        self.status_code = status
    def raise_for_status(self):
        pass

def _cdx_text():
    return (FX / "cdx_greenhouse.jsonl").read_text(encoding="utf-8")

def test_harvest_dedupes_slugs(monkeypatch):
    monkeypatch.setattr(H, "_cdx_fetch", lambda host, crawl_id, limit: _cdx_text().splitlines())
    out = H.harvest_slugs(["boards.greenhouse.io"])
    assert out.get("greenhouse") == {"acme", "beta"}  # robots.txt -> no slug, deduped

def test_harvest_unreachable_logs_and_empties(monkeypatch, capsys):
    monkeypatch.setattr(H, "_cdx_fetch", lambda host, crawl_id, limit: (_ for _ in ()).throw(RuntimeError("net")))
    out = H.harvest_slugs(["boards.greenhouse.io"])
    assert out == {}
    assert "WARNING" in capsys.readouterr().out  # loud, not silent

def test_empty_hosts_returns_empty():
    assert H.harvest_slugs([]) == {}
```

- [ ] **Step 3: Run to fail** → FAIL (module missing).
- [ ] **Step 4: Implement** `discover/cc_harvest.py`:

```python
"""Common Crawl CDX -> ATS slugs per host (the generic denominator winner,
spec §5.1). Bounded + cached: a full harvest runs occasionally, not per search.
Loud on unreachability — never returns empty silently when a host blew up.
"""
from __future__ import annotations
import json

from discover.detect import detect_ats
from search.http_util import make_session

_CDX_INDEX = "https://index.commoncrawl.org/CC-MAIN-2025-05-index"


def _cdx_fetch(host: str, crawl_id: str | None, limit: int | None) -> list:
    """Return CDX NDJSON lines for `host`. Isolated so tests mock it."""
    index = f"https://index.commoncrawl.org/CC-MAIN-{crawl_id}-index" if crawl_id else _CDX_INDEX
    session = make_session()
    params = {"url": f"{host}/*", "output": "json"}
    if limit:
        params["limit"] = str(limit)
    resp = session.get(index, params=params, timeout=30)
    resp.raise_for_status()
    return [ln for ln in resp.text.splitlines() if ln.strip()]


def harvest_slugs(ats_hosts: list, *, crawl_id: str | None = None,
                  limit: int | None = None) -> dict[str, set]:
    """{ats_type: {slug,...}} harvested from Common Crawl for each host."""
    if not ats_hosts:
        return {}
    out: dict[str, set] = {}
    reachable = 0
    for host in ats_hosts:
        try:
            lines = _cdx_fetch(host, crawl_id, limit)
            reachable += 1
        except Exception as e:
            print(f"  [cc_harvest] WARNING: {host} unreachable — {e}")
            continue
        for line in lines:
            try:
                url = json.loads(line).get("url", "")
            except (ValueError, TypeError):
                continue
            det = detect_ats(url)
            if det is None:
                continue
            ats_type, slug = det
            out.setdefault(ats_type, set()).add(slug)
    if reachable == 0:
        print("  [cc_harvest] WARNING: no ATS hosts reachable — discovery degraded; "
              "falling back to existing registry (spec §7).")
        return {}
    return out
```

- [ ] **Step 5: Run** `py -m pytest tests/discover/test_cc_harvest.py -v` → PASS.
- [ ] **Step 6: Commit** `git add discover/cc_harvest.py tests/fixtures/ws2/cdx_greenhouse.jsonl tests/discover/test_cc_harvest.py && git commit -m "feat(discover): cc_harvest — Common Crawl CDX slug harvest, deduped, loud on unreachable"`

### Task 2a.3 — `discover/career_link` (robots/sitemap/anchor → careers URL)

**Files:** Create `discover/career_link.py`, `tests/fixtures/ws2/sitemap.xml`, `tests/fixtures/ws2/homepage.html`, `tests/discover/test_career_link.py`

**Interfaces — Produces:** `find_career_url(domain) -> str | None`, `sitemap_job_urls(domain) -> list`. **Consumes:** `search.http_util.make_session`, `bs4.BeautifulSoup`.

Spec §5.1: fetch `robots.txt` (harvest `Sitemap:`), `sitemap.xml` (filter `job|career|position|opening|vacanc`), homepage careers-anchor regex. All HTTP isolated behind `_get(url) -> str | None` so the test mocks it.

- [ ] **Step 1:** Create `tests/fixtures/ws2/sitemap.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/about</loc></url>
  <url><loc>https://example.com/careers/open-positions</loc></url>
  <url><loc>https://example.com/jobs/controls-engineer</loc></url>
  <url><loc>https://example.com/blog/hello</loc></url>
</urlset>
```

- [ ] **Step 2:** Create `tests/fixtures/ws2/homepage.html`:

```html
<html>
  <body>
    <a href="/about">About</a>
    <a href="/careers">Careers</a>
    <a href="https://boards.greenhouse.io/acme">Open roles</a>
  </body>
</html>
```

- [ ] **Step 3: Write the failing test** `tests/discover/test_career_link.py`:

```python
from pathlib import Path
import discover.career_link as C

FX = Path(__file__).resolve().parents[1] / "fixtures" / "ws2"

def _sitemap():
    return (FX / "sitemap.xml").read_text(encoding="utf-8")

def _homepage():
    return (FX / "homepage.html").read_text(encoding="utf-8")

def test_sitemap_job_urls_filters(monkeypatch):
    monkeypatch.setattr(C, "_get", lambda url: _sitemap() if "sitemap" in url else None)
    urls = C.sitemap_job_urls("example.com")
    assert "https://example.com/careers/open-positions" in urls
    assert "https://example.com/jobs/controls-engineer" in urls
    assert all("/blog/" not in u and "/about" not in u for u in urls)

def test_find_career_url_from_anchor(monkeypatch):
    def fake_get(url):
        if url.rstrip("/").endswith("sitemap.xml") or "robots.txt" in url:
            return None
        return _homepage()
    monkeypatch.setattr(C, "_get", fake_get)
    assert C.find_career_url("example.com") == "https://example.com/careers"

def test_find_career_url_none_when_unreachable(monkeypatch):
    monkeypatch.setattr(C, "_get", lambda url: None)
    assert C.find_career_url("example.com") is None
```

- [ ] **Step 4: Run to fail** → FAIL.
- [ ] **Step 5: Implement** `discover/career_link.py`:

```python
"""Company domain -> careers URL (spec §5.1).

robots.txt (harvest Sitemap:) -> sitemap.xml (filter job-ish locs) ->
homepage careers-anchor regex (one-hop). All HTTP behind _get() so tests mock
one seam. Fail-soft: every step returns None/[] on error, never raises.
"""
from __future__ import annotations
import re
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from search.http_util import make_session
from scrape.xml_safe import _safe_fromstring   # XXE/billion-laughs-safe sitemap parse

_JOB_RE = re.compile(r"job|career|position|opening|vacanc", re.I)
_HEADERS = {"User-Agent": "JobSearchTool/1.0 (personal use)"}


def _get(url: str) -> str | None:
    try:
        resp = make_session().get(url, headers=_HEADERS, timeout=20)
        resp.raise_for_status()
        return resp.text
    except Exception:
        return None


def _origin(domain: str) -> str:
    d = (domain or "").strip()
    if not d:
        return ""
    if "://" not in d:
        d = "https://" + d
    parts = urlsplit(d)
    return f"{parts.scheme}://{parts.netloc}"


def _sitemap_urls_from_robots(origin: str) -> list[str]:
    txt = _get(f"{origin}/robots.txt")
    if not txt:
        return []
    return [line.split(":", 1)[1].strip()
            for line in txt.splitlines()
            if line.lower().startswith("sitemap:")]


def sitemap_job_urls(domain: str) -> list:
    origin = _origin(domain)
    if not origin:
        return []
    candidates = _sitemap_urls_from_robots(origin) or [f"{origin}/sitemap.xml"]
    found: list[str] = []
    for sm in candidates:
        xml = _get(sm)
        if not xml:
            continue
        try:
            root = _safe_fromstring(xml)
        except Exception:
            continue
        for loc in root.iter():
            if loc.tag.endswith("loc") and loc.text and _JOB_RE.search(loc.text):
                found.append(loc.text.strip())
    # dedupe, preserve order
    seen: set[str] = set()
    return [u for u in found if not (u in seen or seen.add(u))]


def find_career_url(domain: str) -> str | None:
    origin = _origin(domain)
    if not origin:
        return None
    job_urls = sitemap_job_urls(domain)
    if job_urls:
        return job_urls[0]
    html = _get(origin) or _get(f"{origin}/")
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True)
        if _JOB_RE.search(href) or _JOB_RE.search(text):
            return urljoin(origin + "/", href)
    return None
```

- [ ] **Step 6: Run** `py -m pytest tests/discover/test_career_link.py -v` → PASS.
- [ ] **Step 7: Commit** `git add discover/career_link.py tests/fixtures/ws2/sitemap.xml tests/fixtures/ws2/homepage.html tests/discover/test_career_link.py && git commit -m "feat(discover): career_link — robots/sitemap/anchor -> careers URL, fail-soft"`

### Task 2a.4 — `discover/registry.merge_discovered` (user-wins + loud-failure fix)

**Files:** Create `discover/registry.py`, `tests/discover/test_registry.py`

**Interfaces — Produces:** `merge_discovered(boards, companies_json_path) -> int`. **Consumes:** `scrape.company_registry.save_companies`, `scrape.company_registry.CompanyEntry`.

The existing `scrape.company_registry.save_companies(new_entries, json_path)` already does an atomic, comment-preserving, dedup-by-`(ats_type,slug)`-or-name append and returns the count added (verified in `company_registry.py:179`). `merge_discovered` converts a `{ats_type: {slug,...}}` dict into `CompanyEntry` objects and delegates — and fixes the silent-empty failure: an empty `boards` dict logs loudly and returns 0 (spec §5.1).

- [ ] **Step 1: Write the failing test** `tests/discover/test_registry.py`:

```python
import json
from discover.registry import merge_discovered

def test_merge_adds_new_boards(tmp_path):
    p = tmp_path / "companies.json"
    n = merge_discovered({"greenhouse": {"acme", "beta"}, "lever": {"gamma"}}, p)
    assert n == 3
    saved = json.loads(p.read_text(encoding="utf-8"))["companies"]
    slugs = {c["slug"] for c in saved}
    assert {"acme", "beta", "gamma"} <= slugs

def test_user_wins_existing_not_overwritten(tmp_path):
    p = tmp_path / "companies.json"
    p.write_text(json.dumps({"_comment": "mine", "companies": [
        {"name": "Acme", "ats_type": "greenhouse", "slug": "acme", "industries": ["mine"]}]}),
        encoding="utf-8")
    n = merge_discovered({"greenhouse": {"acme", "beta"}}, p)
    assert n == 1  # acme already present (user wins), only beta added
    raw = json.loads(p.read_text(encoding="utf-8"))
    assert raw["_comment"] == "mine"
    acme = [c for c in raw["companies"] if c["slug"] == "acme"][0]
    assert acme["industries"] == ["mine"]

def test_empty_boards_logs_and_returns_zero(tmp_path, capsys):
    p = tmp_path / "companies.json"
    n = merge_discovered({}, p)
    assert n == 0
    assert "WARNING" in capsys.readouterr().out
```

- [ ] **Step 2: Run to fail** → FAIL.
- [ ] **Step 3: Implement** `discover/registry.py`:

```python
"""Merge discovered boards into companies.json (spec §5.1).

User-wins: delegates to scrape.company_registry.save_companies, which preserves
comments/examples and skips any (ats_type, slug) or name already present.
Fixes the silent-empty discovery failure: an empty harvest logs loudly and
returns 0 instead of pretending success.
"""
from __future__ import annotations

from scrape.company_registry import CompanyEntry, save_companies


def _name_from_slug(ats_type: str, slug: str) -> str:
    core = slug.split(":")[0] if ats_type == "workday" else slug
    return core.replace("-", " ").replace("_", " ").title()


def merge_discovered(boards: dict, companies_json_path) -> int:
    """boards = {ats_type: {slug,...}}. Returns the count actually added."""
    if not boards or not any(slugs for slugs in boards.values()):
        print("  [discover] WARNING: nothing discovered to merge — discovery may "
              "be degraded (no reachability); companies.json left unchanged (spec §5.1).")
        return 0
    entries: list[CompanyEntry] = []
    for ats_type, slugs in boards.items():
        for slug in sorted(slugs):
            if not slug:
                continue
            entries.append(CompanyEntry(
                name=_name_from_slug(ats_type, slug),
                ats_type=ats_type, slug=slug, industries=["discovered"]))
    return save_companies(entries, companies_json_path)
```

- [ ] **Step 4: Run** `py -m pytest tests/discover/test_registry.py -v` → PASS.
- [ ] **Step 5: Commit** `git add discover/registry.py tests/discover/test_registry.py && git commit -m "feat(discover): registry.merge_discovered — user-wins merge + loud-empty failure fix"`

### Task 2a.5 — Wire the loud-failure fix into `scrape/discoverer.py`

**Files:** Modify `scrape/discoverer.py`; Test `tests/discover/test_discoverer_loud.py`

Spec §5.1 + §7: `discover_companies` currently returns `[]` silently when `BRAVE_SEARCH_API_KEY` is unset (`discoverer.py:30-31`). That silent-empty is the bug — it must log loudly so the user knows discovery is degraded, not just "no companies found". Keep the early return (no key = no Brave discovery) but make it loud.

- [ ] **Step 1: Write the failing test** `tests/discover/test_discoverer_loud.py`:

```python
import scrape.discoverer as D

def test_no_brave_key_logs_loudly(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(D, "BRAVE_SEARCH_API_KEY", "")
    out = D.discover_companies("controls engineer", tmp_path, False, set())
    assert out == []
    assert "WARNING" in capsys.readouterr().out  # was silent before
```

- [ ] **Step 2: Run to fail** `py -m pytest tests/discover/test_discoverer_loud.py -v` → FAIL (no warning printed).
- [ ] **Step 3: Implement** — in `scrape/discoverer.py`, replace the current silent guard:

```python
    if not BRAVE_SEARCH_API_KEY:
        return []
```

with a loud one:

```python
    if not BRAVE_SEARCH_API_KEY:
        print("  [discover] WARNING: BRAVE_SEARCH_API_KEY unset — Brave company "
              "discovery skipped; relying on the existing registry only (spec §7).")
        return []
```

- [ ] **Step 4: Run** `py -m pytest tests/discover/test_discoverer_loud.py -v` → PASS; then `py -m pytest tests/test_careers_fixes.py -q` to confirm no discovery-related regression.
- [ ] **Step 5: Commit** `git add scrape/discoverer.py tests/discover/test_discoverer_loud.py && git commit -m "fix(discover): log loudly when Brave key is unset instead of silent-empty (spec §5.1)"`

### Task 2a.6 — Discovery lift gate (denominator grows the run)

**Files:** Create `tests/fixtures/ws2/discovery_before.jsonl`, `tests/fixtures/ws2/discovery_after.jsonl`, `tests/discover/test_discovery_lift.py`

The phase's proof: discovery adds a new source/company so the `run_benchmark` CoverageScore on the after-fixture is **≥** the before-fixture (spec §8, §10). Both fixtures are `list[JobResult]` dicts for `Cincinnati, OH`; "after" adds a cross-source dupe + a net-new cluster from a discovered board.

- [ ] **Step 1:** Create `tests/fixtures/ws2/discovery_before.jsonl` — 2 sources, ~4 jobs (a cross-source pair + singles), each a full `JobResult` dict:

```
{"title":"Software Developer","company":"Acme, Inc.","location":"Cincinnati, OH","salary_min":null,"salary_max":null,"description":"","url":"","source_keyword":"kw","created":"2026-06-22","source_api":"adzuna"}
{"title":"Software Developer","company":"Acme Inc","location":"Cincinnati","salary_min":null,"salary_max":null,"description":"","url":"","source_keyword":"kw","created":"2026-06-22","source_api":"themuse"}
{"title":"Mechanical Engineer","company":"Beta","location":"Cincinnati, OH","salary_min":null,"salary_max":null,"description":"","url":"","source_keyword":"kw","created":"2026-06-22","source_api":"adzuna"}
{"title":"Data Scientist","company":"Gamma","location":"Cincinnati, OH","salary_min":null,"salary_max":null,"description":"","url":"","source_keyword":"kw","created":"2026-06-22","source_api":"themuse"}
```

- [ ] **Step 2:** Create `tests/fixtures/ws2/discovery_after.jsonl` — the same 4 lines PLUS a discovered-board source (`careers`) contributing a cross-source dupe of an existing cluster AND a net-new cluster, so both `n_clusters` and source overlap rise:

```
{"title":"Software Developer","company":"Acme, Inc.","location":"Cincinnati, OH","salary_min":null,"salary_max":null,"description":"","url":"","source_keyword":"kw","created":"2026-06-22","source_api":"adzuna"}
{"title":"Software Developer","company":"Acme Inc","location":"Cincinnati","salary_min":null,"salary_max":null,"description":"","url":"","source_keyword":"kw","created":"2026-06-22","source_api":"themuse"}
{"title":"Mechanical Engineer","company":"Beta","location":"Cincinnati, OH","salary_min":null,"salary_max":null,"description":"","url":"","source_keyword":"kw","created":"2026-06-22","source_api":"adzuna"}
{"title":"Data Scientist","company":"Gamma","location":"Cincinnati, OH","salary_min":null,"salary_max":null,"description":"","url":"","source_keyword":"kw","created":"2026-06-22","source_api":"themuse"}
{"title":"Software Developer","company":"Acme","location":"Cincinnati, OH","salary_min":null,"salary_max":null,"description":"","url":"","source_keyword":"kw","created":"2026-06-22","source_api":"careers"}
{"title":"Controls Engineer","company":"Delta Robotics","location":"Cincinnati, OH","salary_min":null,"salary_max":null,"description":"","url":"","source_keyword":"kw","created":"2026-06-22","source_api":"careers"}
```

- [ ] **Step 3: Write the lift test** `tests/discover/test_discovery_lift.py`:

```python
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
```

- [ ] **Step 4: Run** `py -m pytest tests/discover/test_discovery_lift.py -v` → PASS. (If `coverage.benchmark` is missing, WS-1 is incomplete — STOP and surface it.)
- [ ] **Step 5: Commit** `git add tests/fixtures/ws2/discovery_before.jsonl tests/fixtures/ws2/discovery_after.jsonl tests/discover/test_discovery_lift.py && git commit -m "test(discover): coverage-lift gate — discovered boards do not lower the WS-1 score"`

**Phase WS-2a Verify:** `py -m pytest tests/discover -q` → all green.

---

# PHASE WS-2b — Tier-1 ATS scrapers + JSON-LD extractor + Workday CSRF fix

**Scope:** 4 new Tier-1 scrapers (`workable`, `recruitee`, `rippling`, `personio`), the generic `jsonld_scraper`, the `careers_client` dispatcher + `ats_detect` registration, and the Workday CSRF/faceted-paging upgrade. Each scraper exposes `fetch(slug) -> list[JobResult]`, normalizes to `JobResult`, and is unit-tested against a recorded fixture via the `monkeypatch.setattr(requests, "get"/"post", ...)` pattern.
**Verify:** `py -m pytest tests/scrape -q`

> All scrapers in this phase follow the existing shape (`scrape/greenhouse_scraper.py`, `scrape/lever_scraper.py`): a module-level `_BASE_URL`, a `fetch(slug)` entry, `requests.get/post(..., timeout=CAREERS_REQUEST_TIMEOUT)`, `raise_for_status()`, fail-soft `except` returning `[]` with a printed warning, and a `_map(...)` that emits `JobResult(..., source_api="careers")`. They use the deep matcher only after WS-2d adds it; in WS-2b they map all postings and rely on the run-level filters (the frozen `fetch(slug)` signature takes no keyword — matching is the caller's job here, matching the Tier-1 JSON pattern where the whole board is pulled).

### Task 2b.0 — Ensure the XXE-safe XML helper exists (reuse guard)

**Files:** `scrape/xml_safe.py`, `tests/scrape/__init__.py`, `tests/scrape/test_xml_safe.py`, `requirements.txt` (created by WS-2a Task 2a.0 — do NOT recreate if present)

`scrape/personio_scraper.py` (Task 2b.4) imports `from scrape.xml_safe import _safe_fromstring`. That helper is authored in **WS-2a Task 2a.0**. This guard keeps WS-2b runnable when dispatched independently of WS-2a.

- [ ] **Step 1: Check** `py -c "from scrape.xml_safe import _safe_fromstring; print('ok')"`.
  - If it prints `ok` → the helper already exists (WS-2a built it). Skip to Step 3.
  - If it raises `ModuleNotFoundError` → WS-2a has not run; build the helper now by executing **WS-2a Task 2a.0 Steps 1–7 verbatim** (same file, same test, same commit). Also create `tests/scrape/__init__.py` if missing.
- [ ] **Step 2:** (only if you just built it) `py -m pytest tests/scrape/test_xml_safe.py -v` → PASS.
- [ ] **Step 3:** Proceed to Task 2b.1. (No commit here if the file already existed.)

### Task 2b.1 — `scrape/workable_scraper.fetch`

**Files:** Create `scrape/workable_scraper.py`, `tests/fixtures/ws2/workable.json`, `tests/scrape/test_workable.py` (`tests/scrape/__init__.py` already created in Task 2b.0/2a.0)

**Interfaces — Produces:** `fetch(slug) -> list[JobResult]`. Endpoint: `https://apply.workable.com/api/v1/widget/accounts/{slug}` (returns `{"jobs": [...]}`).

- [ ] **Step 1:** Create `tests/fixtures/ws2/workable.json`:

```json
{
  "name": "Acme",
  "jobs": [
    {
      "title": "Controls Engineer",
      "shortcode": "ABC123",
      "location": {
        "city": "Cincinnati",
        "region": "Ohio",
        "country": "United States"
      },
      "department": "Engineering",
      "description": "<p>Build PLC systems.</p>",
      "url": "https://apply.workable.com/acme/j/ABC123/",
      "published_on": "2026-06-01"
    },
    {
      "title": "Recruiter",
      "shortcode": "DEF456",
      "location": {
        "city": "Remote",
        "region": "",
        "country": "United States"
      },
      "department": "People",
      "description": "Hire people.",
      "url": "https://apply.workable.com/acme/j/DEF456/",
      "published_on": "2026-06-02"
    }
  ]
}
```

- [ ] **Step 2: Write the failing test** `tests/scrape/test_workable.py`:

```python
import json
from pathlib import Path
import requests
import scrape.workable_scraper as W

FX = Path(__file__).resolve().parents[1] / "fixtures" / "ws2"

class _Resp:
    def __init__(self, payload):
        self._p = payload
    def raise_for_status(self):
        pass
    def json(self):
        return self._p

def _payload():
    return json.loads((FX / "workable.json").read_text(encoding="utf-8"))

def test_fetch_maps_jobresults(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp(_payload()))
    jobs = W.fetch("acme")
    assert len(jobs) == 2
    j = jobs[0]
    assert j.title == "Controls Engineer"
    assert j.company == "Acme"
    assert "Cincinnati" in j.location
    assert j.source_api == "careers"
    assert j.url.endswith("/ABC123/")
    assert "PLC" in j.description  # HTML stripped, text kept

def test_fetch_http_error_returns_empty(monkeypatch):
    def boom(*a, **k):
        raise requests.RequestException("down")
    monkeypatch.setattr(requests, "get", boom)
    assert W.fetch("acme") == []
```

- [ ] **Step 3: Run to fail** → FAIL.
- [ ] **Step 4: Implement** `scrape/workable_scraper.py`:

```python
import html
import re
from typing import Optional

import requests

from config import CAREERS_REQUEST_TIMEOUT
from models import JobResult

_BASE_URL = "https://apply.workable.com/api/v1/widget/accounts/{slug}"
_TAG_RE = re.compile(r"<[^>]+>")
_HEADERS = {"Accept": "application/json", "User-Agent": "JobSearchTool/1.0 (personal use)"}


def _clean(raw: str) -> str:
    if not raw:
        return ""
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", html.unescape(raw))).strip()[:3000]


def _location(loc: dict) -> str:
    parts = [loc.get("city"), loc.get("region"), loc.get("country")]
    return ", ".join(p for p in parts if p)


def fetch(slug: str) -> list[JobResult]:
    try:
        resp = requests.get(_BASE_URL.format(slug=slug), headers=_HEADERS,
                            timeout=CAREERS_REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  [workable] {slug}: error — {e}")
        return []
    company = data.get("name") or slug.replace("-", " ").title()
    jobs = data.get("jobs", []) or []
    out: list[JobResult] = []
    for job in jobs:
        out.append(JobResult(
            title=job.get("title", "") or "",
            company=company,
            location=_location(job.get("location") or {}),
            salary_min=None,
            salary_max=None,
            description=_clean(job.get("description", "")),
            url=job.get("url") or "",
            source_keyword="",
            created=job.get("published_on") or "",
            job_id=f"workable_{job.get('shortcode', '')}",
            source_api="careers",
            board_count=len(jobs),
        ))
    return out
```

- [ ] **Step 5: Run** `py -m pytest tests/scrape/test_workable.py -v` → PASS.
- [ ] **Step 6: Commit** `git add scrape/workable_scraper.py tests/fixtures/ws2/workable.json tests/scrape/__init__.py tests/scrape/test_workable.py && git commit -m "feat(scrape): workable Tier-1 scraper (apply.workable.com widget API)"`

### Task 2b.2 — `scrape/recruitee_scraper.fetch`

**Files:** Create `scrape/recruitee_scraper.py`, `tests/fixtures/ws2/recruitee.json`, `tests/scrape/test_recruitee.py`

**Interfaces — Produces:** `fetch(slug) -> list[JobResult]`. Endpoint: `https://{slug}.recruitee.com/api/offers/` (returns `{"offers": [...]}`).

- [ ] **Step 1:** Create `tests/fixtures/ws2/recruitee.json`:

```json
{
  "offers": [
    {
      "title": "Automation Engineer",
      "id": 111,
      "company_name": "Beta Co",
      "city": "Cincinnati",
      "country": "US",
      "description": "<p>Automate lines.</p>",
      "careers_url": "https://beta.recruitee.com/o/automation-engineer",
      "published_at": "2026-06-03",
      "department": "Engineering"
    },
    {
      "title": "Office Manager",
      "id": 222,
      "company_name": "Beta Co",
      "city": "Remote",
      "country": "US",
      "description": "Run the office.",
      "careers_url": "https://beta.recruitee.com/o/office-manager",
      "published_at": "2026-06-04",
      "department": "Ops"
    }
  ]
}
```

- [ ] **Step 2: Write the failing test** `tests/scrape/test_recruitee.py`:

```python
import json
from pathlib import Path
import requests
import scrape.recruitee_scraper as R

FX = Path(__file__).resolve().parents[1] / "fixtures" / "ws2"

class _Resp:
    def __init__(self, payload):
        self._p = payload
    def raise_for_status(self):
        pass
    def json(self):
        return self._p

def _payload():
    return json.loads((FX / "recruitee.json").read_text(encoding="utf-8"))

def test_fetch_maps(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp(_payload()))
    jobs = R.fetch("beta")
    assert len(jobs) == 2
    assert jobs[0].title == "Automation Engineer"
    assert jobs[0].company == "Beta Co"
    assert "Cincinnati" in jobs[0].location
    assert jobs[0].source_api == "careers"
    assert "Automate" in jobs[0].description

def test_fetch_error_empty(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: (_ for _ in ()).throw(requests.RequestException()))
    assert R.fetch("beta") == []
```

- [ ] **Step 3: Run to fail** → FAIL.
- [ ] **Step 4: Implement** `scrape/recruitee_scraper.py`:

```python
import html
import re

import requests

from config import CAREERS_REQUEST_TIMEOUT
from models import JobResult

_BASE_URL = "https://{slug}.recruitee.com/api/offers/"
_TAG_RE = re.compile(r"<[^>]+>")
_HEADERS = {"Accept": "application/json", "User-Agent": "JobSearchTool/1.0 (personal use)"}


def _clean(raw: str) -> str:
    if not raw:
        return ""
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", html.unescape(raw))).strip()[:3000]


def fetch(slug: str) -> list[JobResult]:
    try:
        resp = requests.get(_BASE_URL.format(slug=slug), headers=_HEADERS,
                            timeout=CAREERS_REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  [recruitee] {slug}: error — {e}")
        return []
    offers = data.get("offers", []) or []
    out: list[JobResult] = []
    for o in offers:
        loc = ", ".join(p for p in (o.get("city"), o.get("country")) if p)
        out.append(JobResult(
            title=o.get("title", "") or "",
            company=o.get("company_name") or slug.replace("-", " ").title(),
            location=loc,
            salary_min=None,
            salary_max=None,
            description=_clean(o.get("description", "")),
            url=o.get("careers_url") or "",
            source_keyword="",
            created=o.get("published_at") or "",
            job_id=f"recruitee_{o.get('id', '')}",
            source_api="careers",
            board_count=len(offers),
        ))
    return out
```

- [ ] **Step 5: Run** `py -m pytest tests/scrape/test_recruitee.py -v` → PASS.
- [ ] **Step 6: Commit** `git add scrape/recruitee_scraper.py tests/fixtures/ws2/recruitee.json tests/scrape/test_recruitee.py && git commit -m "feat(scrape): recruitee Tier-1 scraper (offers API)"`

### Task 2b.3 — `scrape/rippling_scraper.fetch`

**Files:** Create `scrape/rippling_scraper.py`, `tests/fixtures/ws2/rippling.json`, `tests/scrape/test_rippling.py`

**Interfaces — Produces:** `fetch(slug) -> list[JobResult]`. Endpoint: `https://api.rippling.com/platform/api/ats/v1/board/{slug}/jobs` (returns a JSON list of job objects).

- [ ] **Step 1:** Create `tests/fixtures/ws2/rippling.json`:

```json
[
  {
    "id": "r1",
    "name": "Test Engineer",
    "workLocation": { "label": "Cincinnati, OH" },
    "url": "https://app.rippling.com/jobs/r1",
    "department": { "label": "QA" }
  },
  {
    "id": "r2",
    "name": "Sales Lead",
    "workLocation": { "label": "Remote - US" },
    "url": "https://app.rippling.com/jobs/r2",
    "department": { "label": "Sales" }
  }
]
```

- [ ] **Step 2: Write the failing test** `tests/scrape/test_rippling.py`:

```python
import json
from pathlib import Path
import requests
import scrape.rippling_scraper as R

FX = Path(__file__).resolve().parents[1] / "fixtures" / "ws2"

class _Resp:
    def __init__(self, payload):
        self._p = payload
    def raise_for_status(self):
        pass
    def json(self):
        return self._p

def _payload():
    return json.loads((FX / "rippling.json").read_text(encoding="utf-8"))

def test_fetch_maps(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp(_payload()))
    jobs = R.fetch("acme")
    assert len(jobs) == 2
    assert jobs[0].title == "Test Engineer"
    assert "Cincinnati" in jobs[0].location
    assert jobs[0].source_api == "careers"
    assert jobs[0].url.endswith("/r1")

def test_fetch_error_empty(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: (_ for _ in ()).throw(requests.RequestException()))
    assert R.fetch("acme") == []
```

- [ ] **Step 3: Run to fail** → FAIL.
- [ ] **Step 4: Implement** `scrape/rippling_scraper.py`:

```python
import requests

from config import CAREERS_REQUEST_TIMEOUT
from models import JobResult

_BASE_URL = "https://api.rippling.com/platform/api/ats/v1/board/{slug}/jobs"
_HEADERS = {"Accept": "application/json", "User-Agent": "JobSearchTool/1.0 (personal use)"}


def fetch(slug: str) -> list[JobResult]:
    try:
        resp = requests.get(_BASE_URL.format(slug=slug), headers=_HEADERS,
                            timeout=CAREERS_REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  [rippling] {slug}: error — {e}")
        return []
    jobs = data if isinstance(data, list) else data.get("items", []) or []
    out: list[JobResult] = []
    for j in jobs:
        loc = (j.get("workLocation") or {}).get("label") or ""
        dept = (j.get("department") or {}).get("label") or ""
        desc = (j.get("description") or "")[:3000]
        if dept:
            desc = (desc + " " + dept).strip()
        out.append(JobResult(
            title=j.get("name", "") or "",
            company=slug.replace("-", " ").title(),
            location=loc,
            salary_min=None,
            salary_max=None,
            description=desc,
            url=j.get("url") or "",
            source_keyword="",
            created=j.get("createdAt") or j.get("postedDate") or "",
            job_id=f"rippling_{j.get('id', '')}",
            source_api="careers",
            board_count=len(jobs),
        ))
    return out
```

- [ ] **Step 5: Run** `py -m pytest tests/scrape/test_rippling.py -v` → PASS.
- [ ] **Step 6: Commit** `git add scrape/rippling_scraper.py tests/fixtures/ws2/rippling.json tests/scrape/test_rippling.py && git commit -m "feat(scrape): rippling Tier-1 scraper (ATS board jobs API)"`

### Task 2b.4 — `scrape/personio_scraper.fetch` (XML)

**Files:** Create `scrape/personio_scraper.py`, `tests/fixtures/ws2/personio.xml`, `tests/scrape/test_personio.py`

**Interfaces — Produces:** `fetch(slug) -> list[JobResult]`. Endpoint: `https://{slug}.jobs.personio.de/xml` (XML; `<position>` elements under `<workzag-jobs>`). Parse with stdlib `xml.etree.ElementTree`.

- [ ] **Step 1:** Create `tests/fixtures/ws2/personio.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<workzag-jobs>
  <position>
    <id>9001</id>
    <name>Embedded Engineer</name>
    <office>Cincinnati</office>
    <department>R&amp;D</department>
    <jobDescriptions>
      <jobDescription><name>Role</name><value>&lt;p&gt;Write firmware.&lt;/p&gt;</value></jobDescription>
    </jobDescriptions>
    <createdAt>2026-06-05</createdAt>
  </position>
  <position>
    <id>9002</id>
    <name>HR Generalist</name>
    <office>Remote</office>
    <department>People</department>
    <jobDescriptions>
      <jobDescription><name>Role</name><value>Manage HR.</value></jobDescription>
    </jobDescriptions>
    <createdAt>2026-06-06</createdAt>
  </position>
</workzag-jobs>
```

- [ ] **Step 2: Write the failing test** `tests/scrape/test_personio.py`:

```python
from pathlib import Path
import requests
import scrape.personio_scraper as P

FX = Path(__file__).resolve().parents[1] / "fixtures" / "ws2"

class _Resp:
    def __init__(self, text):
        self.text = text
        self.content = text.encode("utf-8")
    def raise_for_status(self):
        pass

def _xml():
    return (FX / "personio.xml").read_text(encoding="utf-8")

def test_fetch_parses_xml(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp(_xml()))
    jobs = P.fetch("acme")
    assert len(jobs) == 2
    assert jobs[0].title == "Embedded Engineer"
    assert jobs[0].location == "Cincinnati"
    assert jobs[0].source_api == "careers"
    assert "firmware" in jobs[0].description.lower()
    assert jobs[0].job_id == "personio_9001"

def test_fetch_bad_xml_empty(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp("<not-xml"))
    assert P.fetch("acme") == []
```

- [ ] **Step 3: Run to fail** → FAIL.
- [ ] **Step 4: Implement** `scrape/personio_scraper.py`:

```python
import html
import re
import xml.etree.ElementTree as ET

import requests

from config import CAREERS_REQUEST_TIMEOUT
from models import JobResult
from scrape.xml_safe import _safe_fromstring

_BASE_URL = "https://{slug}.jobs.personio.de/xml"
_TAG_RE = re.compile(r"<[^>]+>")
_HEADERS = {"Accept": "application/xml", "User-Agent": "JobSearchTool/1.0 (personal use)"}


def _clean(raw: str) -> str:
    if not raw:
        return ""
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", html.unescape(raw))).strip()[:3000]


def _descr(pos: ET.Element) -> str:
    parts = []
    for jd in pos.iter():
        if jd.tag == "value" and jd.text:
            parts.append(jd.text)
    return _clean(" ".join(parts))


def fetch(slug: str) -> list[JobResult]:
    try:
        resp = requests.get(_BASE_URL.format(slug=slug), headers=_HEADERS,
                            timeout=CAREERS_REQUEST_TIMEOUT)
        resp.raise_for_status()
        root = _safe_fromstring(resp.content)   # XXE/billion-laughs-safe (Task 2a.0)
    except Exception as e:
        print(f"  [personio] {slug}: error — {e}")
        return []
    positions = [el for el in root.iter() if el.tag == "position"]
    out: list[JobResult] = []
    for pos in positions:
        def _text(tag):
            el = pos.find(tag)
            return (el.text or "").strip() if el is not None and el.text else ""
        out.append(JobResult(
            title=_text("name"),
            company=slug.replace("-", " ").title(),
            location=_text("office"),
            salary_min=None,
            salary_max=None,
            description=_descr(pos),
            url=f"https://{slug}.jobs.personio.de/job/{_text('id')}" if _text("id") else "",
            source_keyword="",
            created=_text("createdAt"),
            job_id=f"personio_{_text('id')}",
            source_api="careers",
            board_count=len(positions),
        ))
    return out
```

- [ ] **Step 5: Run** `py -m pytest tests/scrape/test_personio.py -v` → PASS.
- [ ] **Step 6: Commit** `git add scrape/personio_scraper.py tests/fixtures/ws2/personio.xml tests/scrape/test_personio.py && git commit -m "feat(scrape): personio Tier-1 scraper (XML feed, stdlib ElementTree)"`

### Task 2b.5 — `scrape/jsonld_scraper.extract_jobs`

**Files:** Create `scrape/jsonld_scraper.py`, `tests/fixtures/ws2/jsonld_page.html`, `tests/scrape/test_jsonld.py`

**Interfaces — Produces:** `extract_jobs(html, base_url) -> list[JobResult]`. Parses `<script type="application/ld+json">` for `@type=JobPosting` (and `ItemList` of them); maps `hiringOrganization`/`jobLocation`/`datePosted`/`validThrough`/`baseSalary` → `JobResult`. Uses `bs4.BeautifulSoup(html, "html.parser")` (already a dep). Malformed/partial → best-effort, skip unparseable (spec §7).

- [ ] **Step 1:** Create `tests/fixtures/ws2/jsonld_page.html`:

```html
<html>
  <head>
    <script type="application/ld+json">
      {
        "@context": "https://schema.org/",
        "@type": "JobPosting",
        "title": "Mechatronics Engineer",
        "description": "<p>Design mechatronic systems.</p>",
        "datePosted": "2026-06-07",
        "validThrough": "2026-09-07",
        "hiringOrganization": {
          "@type": "Organization",
          "name": "Gamma Industries"
        },
        "jobLocation": {
          "@type": "Place",
          "address": {
            "@type": "PostalAddress",
            "addressLocality": "Cincinnati",
            "addressRegion": "OH"
          }
        },
        "baseSalary": {
          "@type": "MonetaryValue",
          "currency": "USD",
          "value": {
            "@type": "QuantitativeValue",
            "minValue": 95000,
            "maxValue": 130000
          }
        },
        "url": "https://gamma.example/jobs/mechatronics"
      }
    </script>
    <script type="application/ld+json">
      { "@type": "WebSite", "name": "not a job" }
    </script>
  </head>
  <body>
    ignored
  </body>
</html>
```

- [ ] **Step 2: Write the failing test** `tests/scrape/test_jsonld.py`:

```python
from pathlib import Path
from scrape.jsonld_scraper import extract_jobs

FX = Path(__file__).resolve().parents[1] / "fixtures" / "ws2"

def _html():
    return (FX / "jsonld_page.html").read_text(encoding="utf-8")

def test_extracts_jobposting():
    jobs = extract_jobs(_html(), "https://gamma.example")
    assert len(jobs) == 1
    j = jobs[0]
    assert j.title == "Mechatronics Engineer"
    assert j.company == "Gamma Industries"
    assert "Cincinnati" in j.location and "OH" in j.location
    assert j.salary_min == 95000 and j.salary_max == 130000
    assert j.created == "2026-06-07"
    assert "mechatronic" in j.description.lower()  # HTML stripped

def test_no_jsonld_returns_empty():
    assert extract_jobs("<html><body>nothing</body></html>", "https://x") == []

def test_malformed_jsonld_skipped():
    bad = '<script type="application/ld+json">{not json}</script>'
    assert extract_jobs(bad, "https://x") == []
```

- [ ] **Step 3: Run to fail** → FAIL.
- [ ] **Step 4: Implement** `scrape/jsonld_scraper.py`:

```python
"""Generic schema.org/JobPosting extractor (spec §5.3).

One parser, thousands of sites: scan <script type="application/ld+json"> for
JobPosting objects (directly, in @graph, or inside an ItemList) and map to
JobResult. Best-effort; malformed/partial entries are skipped, not raised.
Uses the stdlib html.parser via BeautifulSoup (no lxml dependency).
"""
from __future__ import annotations
import html as _html
import json
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from models import JobResult
from search.http_util import to_float

_TAG_RE = re.compile(r"<[^>]+>")


def _clean(raw: str) -> str:
    if not raw:
        return ""
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", _html.unescape(str(raw)))).strip()[:3000]


def _org_name(org) -> str:
    if isinstance(org, dict):
        return org.get("name") or ""
    if isinstance(org, str):
        return org
    return ""


def _location(loc) -> str:
    if isinstance(loc, list):
        return "; ".join(_location(x) for x in loc if _location(x))
    if isinstance(loc, dict):
        addr = loc.get("address")
        if isinstance(addr, dict):
            parts = [addr.get("addressLocality"), addr.get("addressRegion"),
                     addr.get("addressCountry")]
            parts = [p if isinstance(p, str) else (p or {}).get("name", "") for p in parts]
            return ", ".join(p for p in parts if p)
        if isinstance(addr, str):
            return addr
    if isinstance(loc, str):
        return loc
    return ""


def _salary(base) -> tuple:
    if not isinstance(base, dict):
        return (None, None)
    val = base.get("value")
    if isinstance(val, dict):
        lo, hi = val.get("minValue"), val.get("maxValue")
        if lo is None and hi is None:
            single = to_float(val.get("value"))
            return (single, single)
        return (to_float(lo), to_float(hi))
    single = to_float(val)
    return (single, single)


def _iter_objects(obj):
    """Yield every dict in a JSON-LD blob (handles @graph + ItemList)."""
    if isinstance(obj, list):
        for x in obj:
            yield from _iter_objects(x)
    elif isinstance(obj, dict):
        yield obj
        for key in ("@graph", "itemListElement"):
            if key in obj:
                yield from _iter_objects(obj[key])
        if "item" in obj and isinstance(obj["item"], dict):
            yield from _iter_objects(obj["item"])


def _is_jobposting(obj: dict) -> bool:
    t = obj.get("@type")
    if isinstance(t, list):
        return "JobPosting" in t
    return t == "JobPosting"


def _to_jobresult(obj: dict, base_url: str) -> JobResult | None:
    title = obj.get("title") or obj.get("name") or ""
    if not title:
        return None
    lo, hi = _salary(obj.get("baseSalary"))
    url = obj.get("url") or ""
    if url and base_url and "://" not in url:
        url = urljoin(base_url, url)
    return JobResult(
        title=_clean(title) or title,
        company=_org_name(obj.get("hiringOrganization")),
        location=_location(obj.get("jobLocation")),
        salary_min=lo,
        salary_max=hi,
        description=_clean(obj.get("description", "")),
        url=url,
        source_keyword="",
        created=obj.get("datePosted") or "",
        job_id="",
        source_api="careers",
    )


def extract_jobs(html: str, base_url: str) -> list[JobResult]:
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    out: list[JobResult] = []
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = tag.string or tag.get_text() or ""
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            continue
        for obj in _iter_objects(data):
            if _is_jobposting(obj):
                jr = _to_jobresult(obj, base_url)
                if jr is not None:
                    out.append(jr)
    return out
```

- [ ] **Step 5: Run** `py -m pytest tests/scrape/test_jsonld.py -v` → PASS.
- [ ] **Step 6: Commit** `git add scrape/jsonld_scraper.py tests/fixtures/ws2/jsonld_page.html tests/scrape/test_jsonld.py && git commit -m "feat(scrape): generic schema.org JobPosting/ItemList extractor (html.parser)"`

### Task 2b.6 — Register new ATS types in `careers_client` + `ats_detect`

**Files:** Modify `scrape/careers_client.py`, `scrape/ats_detect.py`; Test `tests/scrape/test_careers_dispatch.py`

**Interfaces — Consumes:** `workable_scraper.fetch`, `recruitee_scraper.fetch`, `rippling_scraper.fetch`, `personio_scraper.fetch`. The dispatcher (`CareersClient._scrape_one`, `careers_client.py:106`) routes by `company.ats_type`; the new `fetch(slug)` scrapers take only a slug, so the dispatcher passes `company.slug`. `scrape/ats_detect.detect_ats` (the source-of-truth used by `discoverer` + paste-a-URL) gets the same 4 hosts the discovery wrapper already knows.

- [ ] **Step 1: Write the failing test** `tests/scrape/test_careers_dispatch.py`:

```python
from scrape.ats_detect import detect_ats
from scrape.company_registry import CompanyEntry
from scrape.careers_client import CareersClient

def test_ats_detect_workable():
    assert detect_ats("https://apply.workable.com/acme/") == ("workable", "acme")

def test_ats_detect_recruitee():
    assert detect_ats("https://beta.recruitee.com/") == ("recruitee", "beta")

def test_ats_detect_personio():
    assert detect_ats("https://acme.jobs.personio.de/") == ("personio", "acme")

def test_dispatch_routes_workable(tmp_path, monkeypatch):
    import scrape.careers_client as cc
    called = {}
    monkeypatch.setattr(cc, "scrape_workable", lambda slug: called.setdefault("slug", slug) or [])
    client = CareersClient(cache_dir=tmp_path, cache_enabled=False, discovery_enabled=False)
    company = CompanyEntry("Acme", "workable", "acme", [])
    client._scrape_one(company, "engineer")
    assert called["slug"] == "acme"
```

- [ ] **Step 2: Run to fail** → FAIL (`scrape_workable` not imported; `detect_ats` doesn't know the hosts).
- [ ] **Step 3: Implement (a)** — in `scrape/ats_detect.py`, add detection for the 4 new hosts inside `detect_ats`, BEFORE the final `return ("direct", u)`:

```python
    if host == "apply.workable.com" and segs:
        return ("workable", segs[0])

    if host.endswith(".recruitee.com"):
        sub = host[: -len(".recruitee.com")]
        if sub and sub not in ("www", "api"):
            return ("recruitee", sub)

    for _suffix in (".jobs.personio.de", ".jobs.personio.com"):
        if host.endswith(_suffix):
            sub = host[: -len(_suffix)]
            if sub and sub not in ("www", "api"):
                return ("personio", sub)
```

- [ ] **Step 4: Implement (b)** — in `scrape/careers_client.py`, add imports near the other scraper imports:

```python
from scrape.workable_scraper import fetch as scrape_workable
from scrape.recruitee_scraper import fetch as scrape_recruitee
from scrape.rippling_scraper import fetch as scrape_rippling
from scrape.personio_scraper import fetch as scrape_personio
```

and extend `_scrape_one` (the new scrapers take only `slug`; they have no keyword/cache args, so call them with `company.slug` — the dispatcher's existing per-company timeout/parallelism still applies) by inserting before the `else:` branch:

```python
        elif company.ats_type == "workable":
            return scrape_workable(company.slug)
        elif company.ats_type == "recruitee":
            return scrape_recruitee(company.slug)
        elif company.ats_type == "rippling":
            return scrape_rippling(company.slug)
        elif company.ats_type == "personio":
            return scrape_personio(company.slug)
```

- [ ] **Step 5: Run** `py -m pytest tests/scrape/test_careers_dispatch.py -v` → PASS; then `py -m pytest tests/test_ats_detect.py tests/test_careers_fixes.py -q` → no regression.
- [ ] **Step 6: Commit** `git add scrape/ats_detect.py scrape/careers_client.py tests/scrape/test_careers_dispatch.py && git commit -m "feat(scrape): register workable/recruitee/rippling/personio in ats_detect + careers dispatcher"`

### Task 2b.7 — Workday CSRF session-prime + faceted paging

**Files:** Modify `scrape/workday_scraper.py`; Test `tests/scrape/test_workday_csrf.py`

Spec §5.4: GET the careers page in-session to prime a CSRF cookie/token, then POST `wday/cxs` with faceted paging to work around the 10k cap. The existing `scrape_workday` (in `scrape/workday_scraper.py`) does a bare `requests.post` with `limit=20, offset=0`. Add a `_prime_session(tenant, n, site) -> requests.Session` that GETs the public careers page first (Workday sets the CSRF cookie on that GET), and a `_paged_post` that walks `offset` until `total` is reached or a page is empty (capped). Keep the bare-POST path as the fallback when priming fails, and keep all current behavior (slug parse, URL build, board_count, negative-cache) intact.

- [ ] **Step 1: Write the failing test** `tests/scrape/test_workday_csrf.py`:

```python
import requests
import scrape.workday_scraper as W
from scrape.company_registry import CompanyEntry

class _Resp:
    def __init__(self, payload=None, *, cookies=None, text=""):
        self._p = payload or {}
        self.text = text
        self.cookies = cookies or {}
        self.status_code = 200
    def raise_for_status(self):
        pass
    def json(self):
        return self._p

def _company():
    return CompanyEntry("Cat", "workday", "cat:5:CaterpillarCareers", [])

def test_prime_session_then_paged(tmp_path, monkeypatch):
    gets, posts = [], []

    class _Sess:
        def __init__(self):
            self.headers = {}
            self.cookies = {}
        def get(self, url, **k):
            gets.append(url)
            return _Resp(text="<html>careers</html>", cookies={"CALYPSO_CSRF_TOKEN": "tok"})
        def post(self, url, **k):
            posts.append(k.get("json", {}))
            offset = k.get("json", {}).get("offset", 0)
            if offset == 0:
                return _Resp({"total": 3,
                              "jobPostings": [{"title": "Controls Engineer", "externalPath": "/job/A_R1",
                                               "locationsText": "Cincinnati, OH", "reqId": "R1"},
                                              {"title": "Tech II", "externalPath": "/job/B_R2",
                                               "locationsText": "Peoria, IL", "reqId": "R2"}]})
            return _Resp({"total": 3,
                          "jobPostings": [{"title": "Welder", "externalPath": "/job/C_R3",
                                           "locationsText": "Peoria, IL", "reqId": "R3"}]})

    monkeypatch.setattr(W, "_make_session", lambda: _Sess())
    jobs = W.scrape_workday(_company(), "engineer", tmp_path, cache_enabled=False)
    assert len(gets) >= 1                 # primed the careers page (CSRF GET)
    assert len(jobs) == 3                 # faceted/offset paging pulled all 3
    assert any(j.title == "Controls Engineer" for j in jobs)
    assert all(j.source_api == "careers" for j in jobs)

def test_prime_failure_falls_back_to_bare_post(tmp_path, monkeypatch):
    class _Sess:
        def __init__(self):
            self.headers = {}
            self.cookies = {}
        def get(self, url, **k):
            raise requests.RequestException("blocked")
        def post(self, url, **k):
            return _Resp({"total": 1,
                          "jobPostings": [{"title": "Controls Engineer", "externalPath": "/job/A_R1",
                                           "locationsText": "Cincinnati, OH", "reqId": "R1"}]})
    monkeypatch.setattr(W, "_make_session", lambda: _Sess())
    jobs = W.scrape_workday(_company(), "engineer", tmp_path, cache_enabled=False)
    assert len(jobs) == 1                 # degraded gracefully to a single bare POST
```

- [ ] **Step 2: Run to fail** → FAIL (`_make_session` absent; no priming/paging).
- [ ] **Step 3: Implement** — in `scrape/workday_scraper.py`, add imports + helpers and rewrite the fetch body to prime then page. Add near the top:

```python
from search.http_util import make_session as _make_session

_PAGE_LIMIT = 20          # Workday CXS hard per-response cap
_MAX_PAGES = 50           # offset paging ceiling (1000 postings) to bound a run
```

Add a priming helper:

```python
def _prime_session(tenant: str, n: str, site: str):
    """GET the public careers page so Workday sets its CSRF cookie/token on the
    session; mirror the token into a header. Returns a primed session, or a
    fresh un-primed one if the GET fails (caller falls back to a bare POST)."""
    session = _make_session()
    session.headers.update({"Content-Type": "application/json", "Accept": "application/json"})
    careers_url = f"https://{tenant}.wd{n}.myworkdayjobs.com/{site}"
    try:
        resp = session.get(careers_url, timeout=CAREERS_REQUEST_TIMEOUT)
        resp.raise_for_status()
        token = None
        for name in ("CALYPSO_CSRF_TOKEN", "wd-browser-id", "PLAY_SESSION"):
            token = (getattr(resp, "cookies", {}) or {}).get(name) or session.cookies.get(name)
            if token:
                break
        if token:
            session.headers["X-CALYPSO-CSRF-TOKEN"] = token
    except Exception:
        pass
    return session
```

Replace the fetch/POST section (everything from `url = _WD_BASE.format(...)` through the `write_cache(cache_file, data)` block) with a primed, faceted/offset-paged fetch:

```python
    url = _WD_BASE.format(tenant=tenant, n=n, site=site)
    session = _prime_session(tenant, n, site)

    def _post(offset: int) -> dict | None:
        payload = {"appliedFacets": {}, "limit": _PAGE_LIMIT, "offset": offset, "searchText": keyword}
        try:
            resp = session.post(url, json=payload, timeout=CAREERS_REQUEST_TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"  [workday] {company.name}: HTTP error at offset {offset} — {e}")
            return None

    first = _post(0)
    if first is None:
        if cache_enabled:
            mark_failed(failed_file)
        return []

    postings = list(first.get("jobPostings", []) or [])
    total = first.get("total")
    if isinstance(total, int) and total > _PAGE_LIMIT:
        offset = _PAGE_LIMIT
        pages = 1
        while offset < total and pages < _MAX_PAGES:
            page = _post(offset)
            if not page:
                break
            chunk = page.get("jobPostings", []) or []
            if not chunk:
                break
            postings.extend(chunk)
            offset += _PAGE_LIMIT
            pages += 1
    data = {"total": total, "jobPostings": postings}

    if cache_enabled:
        write_cache(cache_file, data)
```

(The `_map_results(...)` call after this block, the slug parse, the negative-cache markers, and the cache read path all stay unchanged.)

- [ ] **Step 4: Run** `py -m pytest tests/scrape/test_workday_csrf.py -v` → PASS; then `py -m pytest tests/test_workday_url.py -q` → no regression in URL construction.
- [ ] **Step 5: Commit** `git add scrape/workday_scraper.py tests/scrape/test_workday_csrf.py && git commit -m "feat(scrape): workday CSRF session-prime + offset paging (work around 10k cap), bare-POST fallback"`

### Task 2b.8 — Scraper lift gate (new ATS sources raise coverage)

**Files:** Create `tests/fixtures/ws2/scrapers_before.jsonl`, `tests/fixtures/ws2/scrapers_after.jsonl`, `tests/scrape/test_scraper_lift.py`

Proof for the phase: the new Tier-1 scrapers contribute clusters so `run_benchmark` does not drop (spec §8). Same structure as 2a.6.

- [ ] **Step 1:** Create `tests/fixtures/ws2/scrapers_before.jsonl` (2 sources, ~4 jobs — copy the 2a.6 `discovery_before.jsonl` content).
- [ ] **Step 2:** Create `tests/fixtures/ws2/scrapers_after.jsonl` (same 4 lines + two `careers`-source lines: a cross-source dupe of the Acme Software Developer cluster and a net-new "Embedded Engineer / Personio Co" cluster):

```
{"title":"Software Developer","company":"Acme, Inc.","location":"Cincinnati, OH","salary_min":null,"salary_max":null,"description":"","url":"","source_keyword":"kw","created":"2026-06-22","source_api":"adzuna"}
{"title":"Software Developer","company":"Acme Inc","location":"Cincinnati","salary_min":null,"salary_max":null,"description":"","url":"","source_keyword":"kw","created":"2026-06-22","source_api":"themuse"}
{"title":"Mechanical Engineer","company":"Beta","location":"Cincinnati, OH","salary_min":null,"salary_max":null,"description":"","url":"","source_keyword":"kw","created":"2026-06-22","source_api":"adzuna"}
{"title":"Data Scientist","company":"Gamma","location":"Cincinnati, OH","salary_min":null,"salary_max":null,"description":"","url":"","source_keyword":"kw","created":"2026-06-22","source_api":"themuse"}
{"title":"Software Developer","company":"Acme","location":"Cincinnati, OH","salary_min":null,"salary_max":null,"description":"","url":"","source_keyword":"kw","created":"2026-06-22","source_api":"careers"}
{"title":"Embedded Engineer","company":"Personio Co","location":"Cincinnati, OH","salary_min":null,"salary_max":null,"description":"","url":"","source_keyword":"kw","created":"2026-06-22","source_api":"careers"}
```

- [ ] **Step 3: Write the lift test** `tests/scrape/test_scraper_lift.py`:

```python
import json
from pathlib import Path
from models import JobResult
from coverage.benchmark import run_benchmark

FX = Path(__file__).resolve().parents[1] / "fixtures" / "ws2"

def _jobs(name):
    return [JobResult(**json.loads(l))
            for l in (FX / name).read_text(encoding="utf-8").splitlines() if l.strip()]

def test_new_scrapers_do_not_lower_coverage(tmp_path):
    before = run_benchmark(_jobs("scrapers_before.jsonl"), "Cincinnati, OH", ["15-1252.00"], out_dir=tmp_path / "b")
    after = run_benchmark(_jobs("scrapers_after.jsonl"), "Cincinnati, OH", ["15-1252.00"], out_dir=tmp_path / "a")
    assert after.n_clusters >= before.n_clusters
    assert after.composite_score >= before.composite_score
```

- [ ] **Step 4: Run** `py -m pytest tests/scrape/test_scraper_lift.py -v` → PASS.
- [ ] **Step 5: Commit** `git add tests/fixtures/ws2/scrapers_before.jsonl tests/fixtures/ws2/scrapers_after.jsonl tests/scrape/test_scraper_lift.py && git commit -m "test(scrape): coverage-lift gate — new Tier-1 scrapers do not lower the WS-1 score"`

**Phase WS-2b Verify:** `py -m pytest tests/scrape -q` → all green.

---

# PHASE WS-2c — Aggregators (arbeitnow/jooble/careerjet), LinkedIn guest, SerpApi BYO

**Scope:** 3 free aggregators + LinkedIn logged-out guest + the key-gated SerpApi backend, each inheriting the base client and registered in `search/cli.py` `ALL_SOURCES` + `build_clients`. Config constants in `config.py`. SerpApi is key-gated + quota-conserving like `jsearch_client.py`.
**Verify:** `py -m pytest tests/search -q`

> Free, keyless aggregators (`arbeitnow`, `jooble*`, `careerjet*`, `linkedin_guest`) extend `search/single_feed_client.SingleFeedClient` (sets `cache_subdir` + `rate_limit`, gets `__init__`/`strip_html`/`_cached` for free; `__init__(cache_dir=None, cache_enabled=True)` matches `build_clients`). SerpApi carries a key + monthly quota, so it subclasses `JobAPIClient` directly like `jsearch_client.py`. (\*Jooble/Careerjet technically want a free API key; both are modeled key-optional — if the env key is unset the client logs a warning and degrades to `[]`, never raising.)

### Task 2c.1 — `search/config` constants for the new sources

**Files:** Modify `config.py`; Test `tests/search/__init__.py`, `tests/search/test_ws2_config.py`

- [ ] **Step 1: Write the failing test** `tests/search/test_ws2_config.py`:

```python
import config

def test_new_source_consts_present():
    assert config.ARBEITNOW_URL.startswith("https://")
    assert config.JOOBLE_URL.startswith("https://")
    assert config.CAREERJET_URL.startswith("https://")
    assert config.LINKEDIN_GUEST_URL.startswith("https://")
    assert config.SERPAPI_URL.startswith("https://")
    assert isinstance(config.SERPAPI_MONTHLY_LIMIT, int)
    assert isinstance(config.ARBEITNOW_RATE_LIMIT, int)
```

- [ ] **Step 2: Run to fail** → FAIL.
- [ ] **Step 3: Implement** — append to `config.py` (after the existing source blocks; insert before the `# Match scoring (match/scorer.py)` comment at config.py:161, or simply append at end of file — both are safe):

```python
# Arbeitnow — free public job-board API, no key. Remote + EU/US listings.
ARBEITNOW_URL = "https://www.arbeitnow.com/api/job-board-api"
ARBEITNOW_RATE_LIMIT = 5

# Jooble — aggregator; free API key (env JOOBLE_API_KEY) unlocks POST search.
JOOBLE_URL = "https://jooble.org/api/"
JOOBLE_API_KEY = os.getenv("JOOBLE_API_KEY")
JOOBLE_RATE_LIMIT = 10

# Careerjet — aggregator; free affiliate key (env CAREERJET_AFFID) for the public search API.
CAREERJET_URL = "https://public.api.careerjet.net/search"
CAREERJET_AFFID = os.getenv("CAREERJET_AFFID")
CAREERJET_RATE_LIMIT = 10

# LinkedIn — logged-out GUEST endpoint only (public; no auth/cookies/accounts).
# Off by default; the user opts in by adding 'linkedin_guest' to --sources.
LINKEDIN_GUEST_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
LINKEDIN_GUEST_RATE_LIMIT = 3      # conservative; public guest surface
LINKEDIN_GUEST_PAGE_SIZE = 25      # guest endpoint pages by 25

# SerpApi — BYO-paid Google-Jobs backend (env SERPAPI_KEY or secrets/serpapi_key).
SERPAPI_URL = "https://serpapi.com/search"
SERPAPI_KEY = os.getenv("SERPAPI_KEY")
SERPAPI_RATE_LIMIT = 5
SERPAPI_MONTHLY_LIMIT = 100        # free tier; tracked in cache/serpapi_usage.json
```

- [ ] **Step 4: Run** `py -m pytest tests/search/test_ws2_config.py -v` → PASS.
- [ ] **Step 5: Commit** `git add config.py tests/search/__init__.py tests/search/test_ws2_config.py && git commit -m "feat(config): constants for arbeitnow/jooble/careerjet/linkedin-guest/serpapi sources"`

### Task 2c.2 — `search/arbeitnow_client.ArbeitnowClient`

**Files:** Create `search/arbeitnow_client.py`, `tests/fixtures/ws2/arbeitnow.json`, `tests/search/test_arbeitnow.py`

**Interfaces — Produces:** `ArbeitnowClient(SingleFeedClient)`. Single-document feed, filtered client-side per keyword (like `remotive_client`).

- [ ] **Step 1:** Create `tests/fixtures/ws2/arbeitnow.json`:

```json
{
  "data": [
    {
      "title": "Controls Engineer",
      "company_name": "Acme",
      "location": "Cincinnati, OH",
      "url": "https://arbeitnow.com/view/controls-engineer",
      "description": "<p>PLC work.</p>",
      "tags": ["engineering"],
      "created_at": 1717200000,
      "remote": false,
      "slug": "controls-engineer"
    },
    {
      "title": "Barista",
      "company_name": "Cafe",
      "location": "Remote",
      "url": "https://arbeitnow.com/view/barista",
      "description": "Make coffee.",
      "tags": ["food"],
      "created_at": 1717300000,
      "remote": true,
      "slug": "barista"
    }
  ]
}
```

- [ ] **Step 2: Write the failing test** `tests/search/test_arbeitnow.py`:

```python
import json
from pathlib import Path
from search.arbeitnow_client import ArbeitnowClient

FX = Path(__file__).resolve().parents[1] / "fixtures" / "ws2"

def _payload():
    return json.loads((FX / "arbeitnow.json").read_text(encoding="utf-8"))

def _client(tmp_path):
    return ArbeitnowClient(cache_dir=tmp_path, cache_enabled=False)

def test_parse_filters_by_keyword(tmp_path):
    jobs = _client(tmp_path).parse_results(_payload(), "controls engineer")
    assert len(jobs) == 1
    assert jobs[0].title == "Controls Engineer"
    assert jobs[0].source_api == "arbeitnow"
    assert "PLC" in jobs[0].description

def test_parse_no_match(tmp_path):
    assert _client(tmp_path).parse_results(_payload(), "neurosurgeon") == []

def test_page_two_empty(tmp_path, monkeypatch):
    c = _client(tmp_path)
    monkeypatch.setattr(c, "_cached", lambda *a, **k: _payload())
    assert c.search("controls engineer", page=2) == {"data": []}
```

- [ ] **Step 3: Run to fail** → FAIL.
- [ ] **Step 4: Implement** `search/arbeitnow_client.py`:

```python
"""Arbeitnow public job-board API — free, no key. Single-document feed fetched
once per cache cycle and filtered client-side per keyword (like Remotive)."""
from datetime import datetime, timezone
from typing import Optional

from config import ARBEITNOW_RATE_LIMIT, ARBEITNOW_URL
from models import JobResult
from search.single_feed_client import SingleFeedClient


class ArbeitnowClient(SingleFeedClient):
    cache_subdir = "arbeitnow"
    rate_limit = ARBEITNOW_RATE_LIMIT

    def search(self, keyword: str, location: str = "", salary_min: Optional[int] = None,
               page: int = 1) -> dict:
        if page > 1:
            return {"data": []}

        def fetch():
            self.limiter.acquire()
            resp = self.session.get(ARBEITNOW_URL, timeout=30)
            resp.raise_for_status()
            return {"data": resp.json().get("data", [])}

        return self._cached("feed", fetch)

    def parse_results(self, raw: dict, source_keyword: str) -> list[JobResult]:
        from scrape.text_match import keyword_matches
        results = []
        for item in raw.get("data", []):
            title = item.get("title", "") or ""
            blob = f"{title} {' '.join(item.get('tags') or [])}"
            if not keyword_matches(source_keyword, blob):
                continue
            created = item.get("created_at")
            created_iso = ""
            if isinstance(created, (int, float)):
                created_iso = datetime.fromtimestamp(created, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
            results.append(JobResult(
                title=title,
                company=item.get("company_name", "Unknown") or "Unknown",
                location=item.get("location") or ("Remote" if item.get("remote") else ""),
                salary_min=None,
                salary_max=None,
                description=self.strip_html(item.get("description", "") or "")[:3000],
                url=item.get("url", "") or "",
                source_keyword=source_keyword,
                created=created_iso,
                job_id=f"arbeitnow_{item.get('slug', '')}",
                source_api="arbeitnow",
            ))
        return results
```

- [ ] **Step 5: Run** `py -m pytest tests/search/test_arbeitnow.py -v` → PASS.
- [ ] **Step 6: Commit** `git add search/arbeitnow_client.py tests/fixtures/ws2/arbeitnow.json tests/search/test_arbeitnow.py && git commit -m "feat(search): arbeitnow client (free public feed, client-side keyword filter)"`

### Task 2c.3 — `search/jooble_client.JoobleClient` (key-optional POST)

**Files:** Create `search/jooble_client.py`, `tests/fixtures/ws2/jooble.json`, `tests/search/test_jooble.py`

**Interfaces — Produces:** `JoobleClient(SingleFeedClient)`. Jooble's API is `POST {JOOBLE_URL}{key}` with `{"keywords","location"}`; response `{"jobs":[...]}`. Key-optional: no key → loud warning + `{"jobs": []}`.

- [ ] **Step 1:** Create `tests/fixtures/ws2/jooble.json`:

```json
{
  "totalCount": 1,
  "jobs": [
    {
      "title": "Automation Engineer",
      "company": "Beta",
      "location": "Cincinnati, OH",
      "link": "https://jooble.org/jdp/123",
      "snippet": "Automate <b>lines</b>.",
      "updated": "2026-06-08T00:00:00",
      "id": 123,
      "salary": "$90,000"
    }
  ]
}
```

- [ ] **Step 2: Write the failing test** `tests/search/test_jooble.py`:

```python
import json
from pathlib import Path
import search.jooble_client as JC
from search.jooble_client import JoobleClient

FX = Path(__file__).resolve().parents[1] / "fixtures" / "ws2"

def _payload():
    return json.loads((FX / "jooble.json").read_text(encoding="utf-8"))

def test_parse_maps(tmp_path):
    c = JoobleClient(cache_dir=tmp_path, cache_enabled=False)
    jobs = c.parse_results(_payload(), "automation engineer")
    assert len(jobs) == 1
    assert jobs[0].title == "Automation Engineer"
    assert jobs[0].source_api == "jooble"
    assert "lines" in jobs[0].description  # html stripped
    assert jobs[0].url.endswith("/123")

def test_no_key_warns_and_empty(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(JC, "JOOBLE_API_KEY", "")
    c = JoobleClient(cache_dir=tmp_path, cache_enabled=False)
    assert c.search("automation engineer", "Cincinnati") == {"jobs": []}
    assert "WARNING" in capsys.readouterr().out
```

- [ ] **Step 3: Run to fail** → FAIL.
- [ ] **Step 4: Implement** `search/jooble_client.py`:

```python
"""Jooble aggregator — free API key (JOOBLE_API_KEY) unlocks POST search.
Key-optional: without a key the client logs loudly and degrades to empty,
never raising (spec §7)."""
from typing import Optional

from config import JOOBLE_API_KEY, JOOBLE_RATE_LIMIT, JOOBLE_URL
from models import JobResult
from search.http_util import cache_key
from search.single_feed_client import SingleFeedClient


class JoobleClient(SingleFeedClient):
    cache_subdir = "jooble"
    rate_limit = JOOBLE_RATE_LIMIT

    def search(self, keyword: str, location: str = "", salary_min: Optional[int] = None,
               page: int = 1) -> dict:
        if page > 1:
            return {"jobs": []}
        if not JOOBLE_API_KEY:
            print("  [jooble] WARNING: JOOBLE_API_KEY unset — Jooble skipped "
                  "(free key at jooble.org/api/about).")
            return {"jobs": []}
        key = cache_key("jooble", keyword, location)

        def fetch():
            self.limiter.acquire()
            resp = self.session.post(
                f"{JOOBLE_URL}{JOOBLE_API_KEY}",
                json={"keywords": keyword, "location": location},
                timeout=30)
            resp.raise_for_status()
            return {"jobs": resp.json().get("jobs", [])}

        return self._cached(key, fetch)

    def parse_results(self, raw: dict, source_keyword: str) -> list[JobResult]:
        results = []
        for item in raw.get("jobs", []):
            snippet = self.strip_html(item.get("snippet", "") or "")
            salary = (item.get("salary") or "").strip()
            if salary:
                snippet = f"Salary: {salary}\n{snippet}"
            results.append(JobResult(
                title=item.get("title", "") or "",
                company=item.get("company", "Unknown") or "Unknown",
                location=item.get("location", "") or "",
                salary_min=None,
                salary_max=None,
                description=snippet[:3000],
                url=item.get("link", "") or "",
                source_keyword=source_keyword,
                created=item.get("updated", "") or "",
                job_id=f"jooble_{item.get('id', '')}",
                source_api="jooble",
            ))
        return results
```

- [ ] **Step 5: Run** `py -m pytest tests/search/test_jooble.py -v` → PASS.
- [ ] **Step 6: Commit** `git add search/jooble_client.py tests/fixtures/ws2/jooble.json tests/search/test_jooble.py && git commit -m "feat(search): jooble client (key-optional POST search, loud degrade)"`

### Task 2c.4 — `search/careerjet_client.CareerjetClient` (key-optional GET)

**Files:** Create `search/careerjet_client.py`, `tests/fixtures/ws2/careerjet.json`, `tests/search/test_careerjet.py`

**Interfaces — Produces:** `CareerjetClient(SingleFeedClient)`. GET `{CAREERJET_URL}` with `keywords`/`location`/`affid`/`pagesize`; response `{"jobs":[...]}`. Key-optional like Jooble.

- [ ] **Step 1:** Create `tests/fixtures/ws2/careerjet.json`:

```json
{
  "type": "JOBS",
  "hits": 1,
  "jobs": [
    {
      "title": "Test Engineer",
      "company": "Gamma",
      "locations": "Cincinnati, OH",
      "url": "https://www.careerjet.com/jobad/abc",
      "description": "Run <b>tests</b>.",
      "date": "Sun, 08 Jun 2026 00:00:00 GMT",
      "salary_min": 80000,
      "salary_max": 100000
    }
  ]
}
```

- [ ] **Step 2: Write the failing test** `tests/search/test_careerjet.py`:

```python
import json
from pathlib import Path
import search.careerjet_client as CC
from search.careerjet_client import CareerjetClient

FX = Path(__file__).resolve().parents[1] / "fixtures" / "ws2"

def _payload():
    return json.loads((FX / "careerjet.json").read_text(encoding="utf-8"))

def test_parse_maps(tmp_path):
    c = CareerjetClient(cache_dir=tmp_path, cache_enabled=False)
    jobs = c.parse_results(_payload(), "test engineer")
    assert len(jobs) == 1
    assert jobs[0].title == "Test Engineer"
    assert jobs[0].source_api == "careerjet"
    assert jobs[0].salary_min == 80000 and jobs[0].salary_max == 100000
    assert "tests" in jobs[0].description

def test_no_affid_warns_and_empty(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(CC, "CAREERJET_AFFID", "")
    c = CareerjetClient(cache_dir=tmp_path, cache_enabled=False)
    assert c.search("test engineer", "Cincinnati") == {"jobs": []}
    assert "WARNING" in capsys.readouterr().out
```

- [ ] **Step 3: Run to fail** → FAIL.
- [ ] **Step 4: Implement** `search/careerjet_client.py`:

```python
"""Careerjet public search API — free affiliate id (CAREERJET_AFFID) required.
Key-optional: without an affid the client logs loudly and degrades to empty."""
from typing import Optional

from config import CAREERJET_AFFID, CAREERJET_RATE_LIMIT, CAREERJET_URL
from models import JobResult
from search.http_util import cache_key, to_float
from search.single_feed_client import SingleFeedClient


class CareerjetClient(SingleFeedClient):
    cache_subdir = "careerjet"
    rate_limit = CAREERJET_RATE_LIMIT

    def search(self, keyword: str, location: str = "", salary_min: Optional[int] = None,
               page: int = 1) -> dict:
        if page > 1:
            return {"jobs": []}
        if not CAREERJET_AFFID:
            print("  [careerjet] WARNING: CAREERJET_AFFID unset — Careerjet skipped "
                  "(free affiliate id at careerjet.com/partners/).")
            return {"jobs": []}
        key = cache_key("careerjet", keyword, location)

        def fetch():
            self.limiter.acquire()
            resp = self.session.get(CAREERJET_URL, params={
                "keywords": keyword, "location": location, "affid": CAREERJET_AFFID,
                "pagesize": 50, "user_ip": "11.22.33.44", "user_agent": self.user_agent,
            }, timeout=30)
            resp.raise_for_status()
            return {"jobs": resp.json().get("jobs", [])}

        return self._cached(key, fetch)

    def parse_results(self, raw: dict, source_keyword: str) -> list[JobResult]:
        results = []
        for item in raw.get("jobs", []):
            results.append(JobResult(
                title=item.get("title", "") or "",
                company=item.get("company", "Unknown") or "Unknown",
                location=item.get("locations", "") or "",
                salary_min=to_float(item.get("salary_min")),
                salary_max=to_float(item.get("salary_max")),
                description=self.strip_html(item.get("description", "") or "")[:3000],
                url=item.get("url", "") or "",
                source_keyword=source_keyword,
                created=item.get("date", "") or "",
                job_id=f"careerjet_{abs(hash(item.get('url', '')))}",
                source_api="careerjet",
            ))
        return results
```

- [ ] **Step 5: Run** `py -m pytest tests/search/test_careerjet.py -v` → PASS.
- [ ] **Step 6: Commit** `git add search/careerjet_client.py tests/fixtures/ws2/careerjet.json tests/search/test_careerjet.py && git commit -m "feat(search): careerjet client (key-optional GET search, loud degrade)"`

### Task 2c.5 — `search/linkedin_guest_client.LinkedInGuestClient`

**Files:** Create `search/linkedin_guest_client.py`, `tests/fixtures/ws2/linkedin_guest.html`, `tests/search/test_linkedin_guest.py`

**Interfaces — Produces:** `LinkedInGuestClient(SingleFeedClient)`. Logged-out guest endpoint returns an HTML fragment of `<li>` job cards (no JSON, no auth). Parse with `BeautifulSoup`. Spec §2/§3: no auth, no cookies, no accounts; off by default (only runs if `linkedin_guest` is in `--sources`).

- [ ] **Step 1:** Create `tests/fixtures/ws2/linkedin_guest.html`:

```html
<ul>
  <li>
    <div class="base-card">
      <h3 class="base-search-card__title">Controls Engineer</h3>
      <h4 class="base-search-card__subtitle">Acme Industries</h4>
      <span class="job-search-card__location">Cincinnati, OH</span>
      <a
        class="base-card__full-link"
        href="https://www.linkedin.com/jobs/view/123456"
      ></a>
      <time class="job-search-card__listdate" datetime="2026-06-09"></time>
    </div>
  </li>
  <li>
    <div class="base-card">
      <h3 class="base-search-card__title">Sales Director</h3>
      <h4 class="base-search-card__subtitle">Beta LLC</h4>
      <span class="job-search-card__location">Remote</span>
      <a
        class="base-card__full-link"
        href="https://www.linkedin.com/jobs/view/789012"
      ></a>
      <time class="job-search-card__listdate" datetime="2026-06-10"></time>
    </div>
  </li>
</ul>
```

- [ ] **Step 2: Write the failing test** `tests/search/test_linkedin_guest.py`:

```python
from pathlib import Path
from search.linkedin_guest_client import LinkedInGuestClient

FX = Path(__file__).resolve().parents[1] / "fixtures" / "ws2"

def _html():
    return (FX / "linkedin_guest.html").read_text(encoding="utf-8")

def _client(tmp_path):
    return LinkedInGuestClient(cache_dir=tmp_path, cache_enabled=False)

def test_parse_cards(tmp_path):
    jobs = _client(tmp_path).parse_results({"html": _html()}, "controls engineer")
    assert len(jobs) == 2
    j = jobs[0]
    assert j.title == "Controls Engineer"
    assert j.company == "Acme Industries"
    assert "Cincinnati" in j.location
    assert j.url.endswith("/123456")
    assert j.source_api == "linkedin_guest"
    assert j.created == "2026-06-09"

def test_empty_html(tmp_path):
    assert _client(tmp_path).parse_results({"html": ""}, "x") == []
```

- [ ] **Step 3: Run to fail** → FAIL.
- [ ] **Step 4: Implement** `search/linkedin_guest_client.py`:

```python
"""LinkedIn LOGGED-OUT GUEST endpoint only (spec §2/§3).

Public, unauthenticated job-card fragment — NO login, NO cookies, NO accounts.
Off by default; the user opts in via --sources linkedin_guest. Conservative
rate limit. The guest endpoint returns an HTML fragment of job cards, parsed
with BeautifulSoup (html.parser).
"""
from typing import Optional

from bs4 import BeautifulSoup

from config import LINKEDIN_GUEST_PAGE_SIZE, LINKEDIN_GUEST_RATE_LIMIT, LINKEDIN_GUEST_URL
from models import JobResult
from search.http_util import cache_key
from search.single_feed_client import SingleFeedClient


class LinkedInGuestClient(SingleFeedClient):
    cache_subdir = "linkedin_guest"
    rate_limit = LINKEDIN_GUEST_RATE_LIMIT
    user_agent = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")

    def search(self, keyword: str, location: str = "", salary_min: Optional[int] = None,
               page: int = 1) -> dict:
        start = (page - 1) * LINKEDIN_GUEST_PAGE_SIZE
        key = cache_key("linkedin_guest", keyword, location, start)

        def fetch():
            self.limiter.acquire()
            resp = self.session.get(LINKEDIN_GUEST_URL, params={
                "keywords": keyword, "location": location, "start": start,
            }, timeout=30)
            resp.raise_for_status()
            return {"html": resp.text}

        return self._cached(key, fetch)

    def parse_results(self, raw: dict, source_keyword: str) -> list[JobResult]:
        html = raw.get("html") or ""
        if not html:
            return []
        soup = BeautifulSoup(html, "html.parser")
        results = []
        for card in soup.select("li div.base-card, div.base-card"):
            def _txt(sel):
                el = card.select_one(sel)
                return el.get_text(strip=True) if el else ""
            title = _txt("h3.base-search-card__title")
            if not title:
                continue
            link_el = card.select_one("a.base-card__full-link")
            url = (link_el.get("href") if link_el else "") or ""
            time_el = card.select_one("time.job-search-card__listdate")
            created = (time_el.get("datetime") if time_el else "") or ""
            results.append(JobResult(
                title=title,
                company=_txt("h4.base-search-card__subtitle") or "Unknown",
                location=_txt("span.job-search-card__location"),
                salary_min=None,
                salary_max=None,
                description="",
                url=url.split("?")[0],
                source_keyword=source_keyword,
                created=created,
                job_id=f"linkedin_{url.rstrip('/').split('/')[-1]}" if url else "",
                source_api="linkedin_guest",
            ))
        return results
```

- [ ] **Step 5: Run** `py -m pytest tests/search/test_linkedin_guest.py -v` → PASS.
- [ ] **Step 6: Commit** `git add search/linkedin_guest_client.py tests/fixtures/ws2/linkedin_guest.html tests/search/test_linkedin_guest.py && git commit -m "feat(search): linkedin guest client (logged-out public cards only, off by default)"`

### Task 2c.6 — `search/serpapi_client.SerpApiClient` (BYO key + monthly quota)

**Files:** Create `search/serpapi_client.py`, `tests/fixtures/ws2/serpapi.json`, `tests/search/test_serpapi.py`

**Interfaces — Produces:** `SerpApiClient(JobAPIClient)`. Mirrors `jsearch_client.py`: key from `SERPAPI_KEY` env or `secrets/serpapi_key` file; raises `ValueError` in `__init__` when no key (so `build_clients` skips it like jsearch/adzuna); `MonthlyQuota` reservation + refund on failure; `FileCache`. SerpApi Google-Jobs response: `{"jobs_results":[...]}`.

- [ ] **Step 1:** Create `tests/fixtures/ws2/serpapi.json`:

```json
{
  "jobs_results": [
    {
      "title": "Mechatronics Engineer",
      "company_name": "Delta",
      "location": "Cincinnati, OH",
      "description": "Design systems.",
      "job_id": "xyz",
      "detected_extensions": { "posted_at": "2 days ago" },
      "apply_options": [{ "link": "https://jobs.example/delta/mechatronics" }]
    }
  ]
}
```

- [ ] **Step 2: Write the failing test** `tests/search/test_serpapi.py`:

```python
import json
from pathlib import Path
import pytest
import search.serpapi_client as SC
from search.serpapi_client import SerpApiClient

FX = Path(__file__).resolve().parents[1] / "fixtures" / "ws2"

def _payload():
    return json.loads((FX / "serpapi.json").read_text(encoding="utf-8"))

def test_init_no_key_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(SC, "SERPAPI_KEY", "")
    monkeypatch.setattr(SC.config, "SECRETS_DIR", tmp_path)  # no key file
    with pytest.raises(ValueError):
        SerpApiClient(cache_dir=tmp_path, cache_enabled=False)

def test_parse_maps(tmp_path, monkeypatch):
    monkeypatch.setattr(SC, "SERPAPI_KEY", "k")
    c = SerpApiClient(cache_dir=tmp_path, cache_enabled=False)
    jobs = c.parse_results(_payload(), "mechatronics engineer")
    assert len(jobs) == 1
    assert jobs[0].title == "Mechatronics Engineer"
    assert jobs[0].source_api == "serpapi"
    assert jobs[0].url.endswith("/mechatronics")

def test_quota_exhausted_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(SC, "SERPAPI_KEY", "k")
    c = SerpApiClient(cache_dir=tmp_path, cache_enabled=False)
    monkeypatch.setattr(c.quota, "try_increment", lambda n=1: False)
    assert c.search("x", "Cincinnati") == {"jobs_results": []}
```

- [ ] **Step 3: Run to fail** → FAIL.
- [ ] **Step 4: Implement** `search/serpapi_client.py`:

```python
"""SerpApi Google-Jobs backend — BYO-paid, key-gated, quota-conserving
(mirrors jsearch_client.py). Key from SERPAPI_KEY env or secrets/serpapi_key.
Covers Indeed/LinkedIn/Glassdoor/ZipRecruiter via Google Jobs aggregation."""
from pathlib import Path
from typing import Optional

import config
from config import (
    CACHE_DIR,
    SERPAPI_KEY,
    SERPAPI_MONTHLY_LIMIT,
    SERPAPI_RATE_LIMIT,
    SERPAPI_URL,
)
from models import JobResult
from search.base_client import JobAPIClient
from search.http_util import FileCache, MonthlyQuota, RateLimiter, cache_key, make_session


def _resolve_key(explicit: Optional[str]) -> Optional[str]:
    if explicit:
        return explicit
    if SERPAPI_KEY:
        return SERPAPI_KEY
    try:
        return (config.SECRETS_DIR / "serpapi_key").read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


class SerpApiClient(JobAPIClient):
    def __init__(self, api_key: Optional[str] = None, cache_dir: Optional[Path] = None,
                 cache_enabled: bool = True):
        self.api_key = _resolve_key(api_key)
        if not self.api_key:
            raise ValueError(
                "SerpApi key missing. Set SERPAPI_KEY in .env or put it in secrets/serpapi_key")
        self.cache = FileCache("serpapi", cache_dir)
        self.cache_enabled = cache_enabled
        self.session = make_session()
        self.limiter = RateLimiter(SERPAPI_RATE_LIMIT)
        self.quota = MonthlyQuota((cache_dir or CACHE_DIR) / "serpapi_usage.json", SERPAPI_MONTHLY_LIMIT)
        self._quota_warned = False

    def search(self, keyword: str, location: str = "Cincinnati, OH",
               salary_min: Optional[int] = None, page: int = 1) -> dict:
        key = cache_key("serpapi", keyword, location, page)
        if self.cache_enabled:
            cached = self.cache.get(key)
            if cached is not None:
                return cached
        if not self.quota.try_increment():
            if not self._quota_warned:
                print(f"  [serpapi] Monthly cap ({SERPAPI_MONTHLY_LIMIT}) reached — skipping this month.")
                self._quota_warned = True
            return {"jobs_results": []}
        self.limiter.acquire()
        params = {
            "engine": "google_jobs", "q": f"{keyword} {location}".strip(),
            "api_key": self.api_key,
        }
        try:
            resp = self.session.get(SERPAPI_URL, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            self.quota.decrement()
            raise
        if self.cache_enabled:
            self.cache.put(key, data)
        return data

    def parse_results(self, raw: dict, source_keyword: str) -> list[JobResult]:
        results = []
        for item in raw.get("jobs_results", []):
            opts = item.get("apply_options") or []
            url = (opts[0].get("link") if opts else "") or item.get("share_link", "") or ""
            posted = (item.get("detected_extensions") or {}).get("posted_at", "") or ""
            results.append(JobResult(
                title=item.get("title", "") or "",
                company=item.get("company_name", "Unknown") or "Unknown",
                location=item.get("location", "") or "",
                salary_min=None,
                salary_max=None,
                description=(item.get("description", "") or "")[:3000],
                url=url,
                source_keyword=source_keyword,
                created=posted,
                job_id=f"serpapi_{item.get('job_id', '')}",
                source_api="serpapi",
            ))
        return results
```

- [ ] **Step 5: Run** `py -m pytest tests/search/test_serpapi.py -v` → PASS.
- [ ] **Step 6: Commit** `git add search/serpapi_client.py tests/fixtures/ws2/serpapi.json tests/search/test_serpapi.py && git commit -m "feat(search): serpapi BYO Google-Jobs client (key-gated + monthly quota, jsearch pattern)"`

### Task 2c.7 — Register all 5 sources in `search/cli.py`

**Files:** Modify `search/cli.py`; Test `tests/search/test_cli_registration.py`

**Interfaces — Consumes:** all 5 new clients. Add their names to `ALL_SOURCES` and a `build_clients` branch each (free ones unconditional; serpapi key-gated with the `ValueError`-skip pattern; `linkedin_guest` runs only when explicitly requested — keep it in `ALL_SOURCES` but the user gates it via `--sources`, matching how jsearch is excluded from `DAILY_SOURCES`).

- [ ] **Step 1: Write the failing test** `tests/search/test_cli_registration.py`:

```python
from search import cli

def test_all_sources_includes_new():
    for s in ("arbeitnow", "jooble", "careerjet", "linkedin_guest", "serpapi"):
        assert s in cli.ALL_SOURCES

def test_build_clients_arbeitnow(tmp_path):
    clients = cli.build_clients(["arbeitnow"], cache_enabled=False)
    assert [type(c).__name__ for c in clients] == ["ArbeitnowClient"]

def test_build_clients_serpapi_skipped_without_key(monkeypatch, capsys):
    import search.serpapi_client as SC
    monkeypatch.setattr(SC, "SERPAPI_KEY", "")
    import config
    monkeypatch.setattr(SC.config, "SECRETS_DIR", config.USER_DATA_DIR / "nonexistent")
    clients = cli.build_clients(["serpapi"], cache_enabled=False)
    assert clients == []
    assert "Skipping" in capsys.readouterr().out
```

- [ ] **Step 2: Run to fail** → FAIL (names not registered).
- [ ] **Step 3: Implement (a)** — in `search/cli.py`, extend `ALL_SOURCES`:

```python
ALL_SOURCES = ["adzuna", "jsearch", "usajobs", "careers", "themuse", "remoteok",
               "remotive", "jobicy", "himalayas", "hn",
               "arbeitnow", "jooble", "careerjet", "linkedin_guest", "serpapi"]
```

- [ ] **Step 4: Implement (b)** — in `build_clients`, add branches before the final `else:` (mirror the existing lazy-import style):

```python
        elif source == "arbeitnow":
            from search.arbeitnow_client import ArbeitnowClient
            clients.append(ArbeitnowClient(cache_enabled=cache_enabled))

        elif source == "jooble":
            from search.jooble_client import JoobleClient
            clients.append(JoobleClient(cache_enabled=cache_enabled))

        elif source == "careerjet":
            from search.careerjet_client import CareerjetClient
            clients.append(CareerjetClient(cache_enabled=cache_enabled))

        elif source == "linkedin_guest":
            from search.linkedin_guest_client import LinkedInGuestClient
            print("  [linkedin_guest] NOTE: logged-out PUBLIC guest endpoint only — "
                  "no login/cookies. Review LinkedIn ToS before enabling.")
            clients.append(LinkedInGuestClient(cache_enabled=cache_enabled))

        elif source == "serpapi":
            from search.serpapi_client import SerpApiClient
            try:
                clients.append(SerpApiClient(cache_enabled=cache_enabled))
                print(f"  [serpapi] BYO Google-Jobs backend active "
                      f"(free tier {__import__('config').SERPAPI_MONTHLY_LIMIT}/month).")
            except ValueError as e:
                print(f"  [serpapi] Skipping — {e}")
```

- [ ] **Step 5: Run** `py -m pytest tests/search/test_cli_registration.py -v` → PASS; then `py -m pytest tests/test_search_engine.py -q` → no regression.
- [ ] **Step 6: Commit** `git add search/cli.py tests/search/test_cli_registration.py && git commit -m "feat(search): register arbeitnow/jooble/careerjet/linkedin-guest/serpapi in cli ALL_SOURCES + build_clients"`

### Task 2c.8 — Aggregator lift gate

**Files:** Create `tests/fixtures/ws2/aggregators_before.jsonl`, `tests/fixtures/ws2/aggregators_after.jsonl`, `tests/search/test_aggregator_lift.py`

Proof: a new aggregator source adds a third `source_api` (so capture-recapture has ≥3 sources or more cross-source overlap) and net-new clusters → `run_benchmark` does not drop.

- [ ] **Step 1:** Create `tests/fixtures/ws2/aggregators_before.jsonl` (copy `discovery_before.jsonl` from 2a.6 — 2 sources).
- [ ] **Step 2:** Create `tests/fixtures/ws2/aggregators_after.jsonl` (same 4 lines + 2 `arbeitnow`-source lines: one cross-source dupe + one net-new cluster):

```
{"title":"Software Developer","company":"Acme, Inc.","location":"Cincinnati, OH","salary_min":null,"salary_max":null,"description":"","url":"","source_keyword":"kw","created":"2026-06-22","source_api":"adzuna"}
{"title":"Software Developer","company":"Acme Inc","location":"Cincinnati","salary_min":null,"salary_max":null,"description":"","url":"","source_keyword":"kw","created":"2026-06-22","source_api":"themuse"}
{"title":"Mechanical Engineer","company":"Beta","location":"Cincinnati, OH","salary_min":null,"salary_max":null,"description":"","url":"","source_keyword":"kw","created":"2026-06-22","source_api":"adzuna"}
{"title":"Data Scientist","company":"Gamma","location":"Cincinnati, OH","salary_min":null,"salary_max":null,"description":"","url":"","source_keyword":"kw","created":"2026-06-22","source_api":"themuse"}
{"title":"Software Developer","company":"Acme","location":"Cincinnati, OH","salary_min":null,"salary_max":null,"description":"","url":"","source_keyword":"kw","created":"2026-06-22","source_api":"arbeitnow"}
{"title":"Automation Engineer","company":"Epsilon","location":"Cincinnati, OH","salary_min":null,"salary_max":null,"description":"","url":"","source_keyword":"kw","created":"2026-06-22","source_api":"arbeitnow"}
```

- [ ] **Step 3: Write the lift test** `tests/search/test_aggregator_lift.py`:

```python
import json
from pathlib import Path
from models import JobResult
from coverage.benchmark import run_benchmark

FX = Path(__file__).resolve().parents[1] / "fixtures" / "ws2"

def _jobs(name):
    return [JobResult(**json.loads(l))
            for l in (FX / name).read_text(encoding="utf-8").splitlines() if l.strip()]

def test_aggregators_do_not_lower_coverage(tmp_path):
    before = run_benchmark(_jobs("aggregators_before.jsonl"), "Cincinnati, OH", ["15-1252.00"], out_dir=tmp_path / "b")
    after = run_benchmark(_jobs("aggregators_after.jsonl"), "Cincinnati, OH", ["15-1252.00"], out_dir=tmp_path / "a")
    assert after.n_clusters >= before.n_clusters
    assert after.composite_score >= before.composite_score
```

- [ ] **Step 4: Run** `py -m pytest tests/search/test_aggregator_lift.py -v` → PASS.
- [ ] **Step 5: Commit** `git add tests/fixtures/ws2/aggregators_before.jsonl tests/fixtures/ws2/aggregators_after.jsonl tests/search/test_aggregator_lift.py && git commit -m "test(search): coverage-lift gate — new aggregators do not lower the WS-1 score"`

**Phase WS-2c Verify:** `py -m pytest tests/search -q` → all green.

---

# PHASE WS-2d — Geo/remote filter + title+body match + freshness + target_roles + lift gates

**Scope:** the `geo/` package metro filter, the `keyword_matches_deep` title+body matcher (wired into the new scrapers + JSON-LD), per-source freshness deltas, the `preferences.json` `target_roles` migration, and the consolidating lift tests.
**Verify:** `py -m pytest tests/geo -q`

### Task 2d.1 — `scrape/text_match.keyword_matches_deep`

**Files:** Modify `scrape/text_match.py`; Test `tests/scrape/test_text_match_deep.py`

**Interfaces — Produces:** `keyword_matches_deep(keyword, title, body) -> bool` (match TITLE OR BODY). **Consumes:** `search.query.parse` (already used by `keyword_matches`). Spec §5.6: recover generically-titled reqs by also matching the description/department. `keyword_matches` stays unchanged (title-only) for back-compat.

- [ ] **Step 1: Write the failing test** `tests/scrape/test_text_match_deep.py`:

```python
from scrape.text_match import keyword_matches, keyword_matches_deep

def test_title_only_still_works():
    assert keyword_matches("controls engineer", "Senior Controls Engineer")
    assert not keyword_matches("controls engineer", "Software Developer")

def test_deep_matches_body_when_title_misses():
    # generic title, but the body mentions the role
    assert keyword_matches_deep("controls engineer",
                                "Engineer II",
                                "You will own PLC controls engineer duties on the line.")

def test_deep_matches_title():
    assert keyword_matches_deep("controls engineer", "Controls Engineer", "")

def test_deep_no_match_anywhere():
    assert not keyword_matches_deep("controls engineer", "Barista", "Make coffee.")
```

- [ ] **Step 2: Run to fail** → FAIL (`keyword_matches_deep` missing).
- [ ] **Step 3: Implement** — append to `scrape/text_match.py`:

```python
def keyword_matches_deep(keyword: str, title: str, body: str) -> bool:
    """True if the boolean `keyword` query matches the TITLE or the BODY
    (description/department). Recovers generically-titled reqs whose role only
    shows up in the body. `keyword_matches` (title-only) is unchanged."""
    q = parse(keyword)
    haystack = f"{title or ''} {body or ''}"
    return q.matches(title or "") or q.matches(haystack)
```

- [ ] **Step 4: Run** `py -m pytest tests/scrape/test_text_match_deep.py -v` → PASS.
- [ ] **Step 5: Commit** `git add scrape/text_match.py tests/scrape/test_text_match_deep.py && git commit -m "feat(scrape): keyword_matches_deep — title+body boolean matching (keyword_matches unchanged)"`

### Task 2d.2 — `geo/filter.filter_to_metro`

**Files:** Create `geo/__init__.py`, `geo/filter.py`, `tests/geo/__init__.py`, `tests/geo/test_filter.py`

**Interfaces — Produces:** `filter_to_metro(jobs, area, *, remote_region=None) -> list`. **Consumes:** `coverage.geography.metro_variants` (WS-1). Spec §5.5: keep a job whose location matches any metro variant; keep remote postings gated by `remote_region` (`"us"` keeps US/anywhere-remote, drops global-only). Unknown/empty location is KEPT (don't over-cut, mirrors `preferences.hard_gate`).

- [ ] **Step 1: Write the failing test** `tests/geo/test_filter.py`:

```python
from models import JobResult
from geo.filter import filter_to_metro

def _j(location, title="Engineer"):
    return JobResult(title=title, company="C", location=location, salary_min=None, salary_max=None,
                     description="", url="", source_keyword="kw", created="2026-06-22", source_api="s")

def test_keeps_metro_match():
    jobs = [_j("Cincinnati, OH"), _j("San Francisco, CA")]
    out = filter_to_metro(jobs, "Cincinnati, OH")
    assert [j.location for j in out] == ["Cincinnati, OH"]

def test_keeps_unknown_location():
    out = filter_to_metro([_j("")], "Cincinnati, OH")
    assert len(out) == 1  # empty location kept (don't over-cut)

def test_remote_region_us_keeps_us_remote_drops_global():
    jobs = [_j("Remote - US"), _j("Remote - Worldwide")]
    out = filter_to_metro(jobs, "Cincinnati, OH", remote_region="us")
    locs = [j.location for j in out]
    assert "Remote - US" in locs
    assert "Remote - Worldwide" not in locs

def test_no_remote_region_keeps_all_remote():
    jobs = [_j("Remote - Worldwide")]
    assert len(filter_to_metro(jobs, "Cincinnati, OH")) == 1
```

- [ ] **Step 2: Run to fail** → FAIL.
- [ ] **Step 3: Implement** `geo/filter.py` (and empty `geo/__init__.py`, `tests/geo/__init__.py`):

```python
"""Metro radius + remote-region filter (spec §5.5).

Built on coverage.geography.metro_variants (WS-1): keep a job whose location
matches any variant of the target metro, keep remote postings gated by region,
and keep unknown/empty locations (don't over-cut the wide net).
"""
from __future__ import annotations

from coverage.geography import metro_variants

# Tokens that signal a US-acceptable remote posting.
_US_OK = ("us", "u.s", "united states", "usa", "anywhere", "remote")
_GLOBAL_ONLY = ("worldwide", "global", "anywhere in the world", "international")


def _is_remote(loc: str, title: str) -> bool:
    return "remote" in loc or "remote" in title


def _remote_region_ok(loc: str, remote_region: str | None) -> bool:
    if not remote_region:
        return True
    region = remote_region.strip().lower()
    if region == "us":
        if any(g in loc for g in _GLOBAL_ONLY):
            return False
        return any(tok in loc for tok in _US_OK)
    return region in loc


def filter_to_metro(jobs: list, area: str, *, remote_region: str | None = None) -> list:
    variants = {v for v in metro_variants(area) if v}
    out = []
    for j in jobs:
        loc = (getattr(j, "location", "") or "").strip().lower()
        title = (getattr(j, "title", "") or "").lower()
        if not loc:
            out.append(j)          # unknown location: keep (don't over-cut)
            continue
        if _is_remote(loc, title):
            if _remote_region_ok(loc, remote_region):
                out.append(j)
            continue
        if any(v in loc for v in variants):
            out.append(j)
    return out
```

- [ ] **Step 4: Run** `py -m pytest tests/geo/test_filter.py -v` → PASS.
- [ ] **Step 5: Commit** `git add geo/__init__.py geo/filter.py tests/geo/__init__.py tests/geo/test_filter.py && git commit -m "feat(geo): filter_to_metro — metro-variant + remote-region post-fetch filter (WS-1 geography)"`

### Task 2d.3 — `search/freshness` — per-source new-since-last delta

**Files:** Create `search/freshness.py`, `tests/search/test_freshness.py`

**Interfaces — Produces:** `new_since_last(jobs, source_id, prev_keys) -> list`, `load_prev_keys(source_id, base_dir=None) -> set`, `save_keys(source_id, keys, base_dir=None) -> None`. **Consumes:** `JobResult.job_key` (WS-1), `config.USER_DATA_DIR`. Spec §5.6: compare `job_key` set vs the previous run; persist per-source sets under `USER_DATA_DIR/freshness/`.

- [ ] **Step 1: Write the failing test** `tests/search/test_freshness.py`:

```python
from models import JobResult
import search.freshness as F

def _j(title, company="Acme", location="Cincinnati, OH"):
    return JobResult(title=title, company=company, location=location, salary_min=None, salary_max=None,
                     description="", url="", source_keyword="kw", created="2026-06-22", source_api="adzuna")

def test_new_since_last_filters_seen():
    a, b = _j("Software Developer"), _j("Mechanical Engineer")
    prev = {a.job_key}
    out = F.new_since_last([a, b], "adzuna", prev)
    assert out == [b]

def test_persist_roundtrip(tmp_path):
    a = _j("Software Developer")
    F.save_keys("adzuna", {a.job_key}, base_dir=tmp_path)
    assert F.load_prev_keys("adzuna", base_dir=tmp_path) == {a.job_key}

def test_load_missing_returns_empty(tmp_path):
    assert F.load_prev_keys("never_run", base_dir=tmp_path) == set()
```

- [ ] **Step 2: Run to fail** → FAIL.
- [ ] **Step 3: Implement** `search/freshness.py`:

```python
"""Per-source freshness delta (spec §5.6).

Persist each source's set of job_keys under USER_DATA_DIR/freshness/, so the
next run can surface only postings new since last time. job_key is WS-1's
stable cross-source identity.
"""
from __future__ import annotations
import json
from pathlib import Path

import config


def _dir(base_dir=None) -> Path:
    base = Path(base_dir) if base_dir is not None else Path(config.USER_DATA_DIR) / "freshness"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _path(source_id: str, base_dir=None) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in source_id)
    return _dir(base_dir) / f"{safe}.json"


def load_prev_keys(source_id: str, base_dir=None) -> set:
    p = _path(source_id, base_dir)
    if not p.exists():
        return set()
    try:
        return set(json.loads(p.read_text(encoding="utf-8")))
    except (ValueError, OSError):
        return set()


def save_keys(source_id: str, keys: set, base_dir=None) -> None:
    p = _path(source_id, base_dir)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(sorted(keys)), encoding="utf-8")
    tmp.replace(p)


def new_since_last(jobs: list, source_id: str, prev_keys: set) -> list:
    """Jobs whose job_key was not in the previous run's set for this source."""
    return [j for j in jobs if j.job_key not in prev_keys]
```

- [ ] **Step 4: Run** `py -m pytest tests/search/test_freshness.py -v` → PASS.
- [ ] **Step 5: Commit** `git add search/freshness.py tests/search/test_freshness.py && git commit -m "feat(search): freshness — per-source job_key delta + persistence under USER_DATA_DIR"`

### Task 2d.4 — `preferences.target_roles` (seed on migration)

**Files:** Modify `preferences.py`; Test `tests/search/test_target_roles.py`

**Interfaces — Consumes/Produces:** `preferences._DEFAULT_HARD` gains `target_roles: []`; `migrate_from_user_config` seeds it from `cfg["keywords"]`; `load` carries it through. Spec §2: area comes from `locations[]` (already present), field/target-roles from the new `target_roles[]` key. (The `preferences.md` parse mentioned in the spec is best-effort: the migration line already writes keywords into `profile_md`; the JSON `target_roles` is the machine-readable seed.)

- [ ] **Step 1: Write the failing test** `tests/search/test_target_roles.py`:

```python
import json
import preferences

def test_default_hard_has_target_roles():
    assert "target_roles" in preferences._DEFAULT_HARD
    assert preferences._DEFAULT_HARD["target_roles"] == []

def test_migrate_seeds_target_roles_from_keywords():
    cfg = {"keywords": ["controls engineer", "automation engineer"], "location": "Cincinnati"}
    out = preferences.migrate_from_user_config(cfg)
    assert out["hard"]["target_roles"] == ["controls engineer", "automation engineer"]

def test_load_carries_target_roles(tmp_path):
    pj = tmp_path / "preferences.json"
    pj.write_text(json.dumps({"target_roles": ["mechatronics engineer"], "locations": ["Cincinnati"]}),
                  encoding="utf-8")
    loaded = preferences.load(prefs_md=tmp_path / "missing.md", prefs_json=pj)
    assert loaded["hard"]["target_roles"] == ["mechatronics engineer"]
```

- [ ] **Step 2: Run to fail** → FAIL (`target_roles` absent).
- [ ] **Step 3: Implement** — in `preferences.py`, add the key to `_DEFAULT_HARD` (after `seniority_exclude`):

```python
    "seniority_exclude": [],   # title substrings to exclude (e.g. "principal")
    "target_roles": [],        # WS-2: field/role seeds for generic discovery (area = locations[])
```

and in `migrate_from_user_config`, seed it from keywords (after the `keywords = cfg.get("keywords") or []` line, before building `lines`):

```python
    keywords = cfg.get("keywords") or []
    hard["target_roles"] = list(keywords)
```

(`load()` already copies every key in `_DEFAULT_HARD` from the JSON file, so `target_roles` is carried through automatically — no change needed there.)

- [ ] **Step 4: Run** `py -m pytest tests/search/test_target_roles.py -v` → PASS; then `py -m pytest tests/test_preferences.py -q` → no regression.
- [ ] **Step 5: Commit** `git add preferences.py tests/search/test_target_roles.py && git commit -m "feat(preferences): add target_roles[] seeded from user_config keywords (WS-2 generic discovery field)"`

### Task 2d.5 — Wire deep matching into the new Tier-1 scrapers + JSON-LD

**Files:** Modify `scrape/workable_scraper.py`, `scrape/recruitee_scraper.py`, `scrape/rippling_scraper.py`, `scrape/personio_scraper.py`, `scrape/jsonld_scraper.py`; Test `tests/scrape/test_scraper_deep_match.py`

Spec §5.6: the new scrapers currently map ALL postings (no keyword gate). Add an OPTIONAL `keyword` param so the run can title+body filter via `keyword_matches_deep`, defaulting to `""` (no filtering — preserves the WS-2b `fetch(slug)` contract and tests). The frozen signature is `fetch(slug)`; add `*, keyword: str = ""` keyword-only so existing one-arg calls and the dispatcher are unaffected.

- [ ] **Step 1: Write the failing test** `tests/scrape/test_scraper_deep_match.py`:

```python
import json
from pathlib import Path
import requests
import scrape.workable_scraper as W
from scrape.jsonld_scraper import extract_jobs

FX = Path(__file__).resolve().parents[1] / "fixtures" / "ws2"

class _Resp:
    def __init__(self, payload):
        self._p = payload
    def raise_for_status(self):
        pass
    def json(self):
        return self._p

def _workable_payload():
    return json.loads((FX / "workable.json").read_text(encoding="utf-8"))

def test_workable_keyword_filters(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp(_workable_payload()))
    # keyword that hits the Controls Engineer title/desc but not the Recruiter
    jobs = W.fetch("acme", keyword="controls engineer")
    assert [j.title for j in jobs] == ["Controls Engineer"]

def test_workable_no_keyword_keeps_all(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp(_workable_payload()))
    assert len(W.fetch("acme")) == 2  # default keyword="" -> no filtering

def test_jsonld_keyword_filters():
    html = (FX / "jsonld_page.html").read_text(encoding="utf-8")
    assert len(extract_jobs(html, "https://x", keyword="mechatronics")) == 1
    assert extract_jobs(html, "https://x", keyword="neurosurgeon") == []
```

- [ ] **Step 2: Run to fail** → FAIL (no `keyword` param).
- [ ] **Step 3: Implement** — for EACH of the four Tier-1 scrapers, change the signature and add a gate. Example for `scrape/workable_scraper.py` (apply the analogous change to recruitee/rippling/personio — gate each posting on title+body before appending):

```python
def fetch(slug: str, *, keyword: str = "") -> list[JobResult]:
```

and inside the per-posting loop, before `out.append(...)`, add:

```python
        title = job.get("title", "") or ""
        body = _clean(job.get("description", ""))
        if keyword:
            from scrape.text_match import keyword_matches_deep
            if not keyword_matches_deep(keyword, title, body):
                continue
```

(reuse the already-computed `title`/`description` where the scraper already builds them; for recruitee the body is the cleaned `description`, for rippling it's `desc`, for personio it's `_descr(pos)`). For `scrape/jsonld_scraper.py`, change:

```python
def extract_jobs(html: str, base_url: str, *, keyword: str = "") -> list[JobResult]:
```

and gate each built `JobResult` before appending:

```python
                if jr is not None:
                    if keyword:
                        from scrape.text_match import keyword_matches_deep
                        if not keyword_matches_deep(keyword, jr.title, jr.description):
                            continue
                    out.append(jr)
```

- [ ] **Step 4: Run** `py -m pytest tests/scrape/test_scraper_deep_match.py -v` → PASS; then re-run the WS-2b scraper tests `py -m pytest tests/scrape/test_workable.py tests/scrape/test_recruitee.py tests/scrape/test_rippling.py tests/scrape/test_personio.py tests/scrape/test_jsonld.py -q` → all still green (default `keyword=""` keeps them passing).
- [ ] **Step 5: Commit** `git add scrape/workable_scraper.py scrape/recruitee_scraper.py scrape/rippling_scraper.py scrape/personio_scraper.py scrape/jsonld_scraper.py tests/scrape/test_scraper_deep_match.py && git commit -m "feat(scrape): optional title+body keyword gate on Tier-1 + JSON-LD scrapers (keyword_matches_deep)"`

### Task 2d.6 — Match-depth + geo + freshness lift gate (consolidated)

**Files:** Create `tests/fixtures/ws2/depth_before.jsonl`, `tests/fixtures/ws2/depth_after.jsonl`, `tests/geo/test_depth_lift.py`

The phase's proof (spec §8): (1) the geo filter trims off-metro noise without dropping in-metro clusters, and (2) title+body matching recovers a generically-titled in-metro req that title-only missed — so the after-fixture's in-metro coverage rises. The "before" run is the raw fetch (off-metro noise + a generically-titled SOC-15 req excluded by title-only); the "after" run is geo-filtered + deep-matched, recovering the req.

- [ ] **Step 1:** Create `tests/fixtures/ws2/depth_before.jsonl` — the raw, unfiltered set: in-metro clusters + an off-metro job + a generically-titled SOC-15 req. (4 lines: 2 in-metro across sources, 1 off-metro San Francisco, 1 generically-titled.)

```
{"title":"Software Developer","company":"Acme, Inc.","location":"Cincinnati, OH","salary_min":null,"salary_max":null,"description":"","url":"","source_keyword":"kw","created":"2026-06-22","source_api":"adzuna"}
{"title":"Software Developer","company":"Acme Inc","location":"Cincinnati","salary_min":null,"salary_max":null,"description":"","url":"","source_keyword":"kw","created":"2026-06-22","source_api":"themuse"}
{"title":"Engineer II","company":"Beta","location":"San Francisco, CA","salary_min":null,"salary_max":null,"description":"Frontend work.","url":"","source_keyword":"kw","created":"2026-06-22","source_api":"adzuna"}
{"title":"Engineer II","company":"Gamma","location":"Cincinnati, OH","salary_min":null,"salary_max":null,"description":"You will own software developer duties.","url":"","source_keyword":"kw","created":"2026-06-22","source_api":"themuse"}
```

- [ ] **Step 2: Write the lift test** `tests/geo/test_depth_lift.py` (computes the "after" set IN the test by applying the real geo filter + deep matcher, then asserts coverage rises vs the off-metro-noisy raw set restricted to SOC-15 recall):

```python
import json
from pathlib import Path
from models import JobResult
from coverage.benchmark import run_benchmark
from geo.filter import filter_to_metro
from scrape.text_match import keyword_matches_deep

FX = Path(__file__).resolve().parents[1] / "fixtures" / "ws2"
AREA = "Cincinnati, OH"

def _raw():
    return [JobResult(**json.loads(l))
            for l in (FX / "depth_before.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]

def test_geo_trims_offmetro_without_losing_inmetro(tmp_path):
    raw = _raw()
    filtered = filter_to_metro(raw, AREA)
    assert all("san francisco" not in (j.location or "").lower() for j in filtered)
    # in-metro Acme cross-source pair survives
    assert any(j.company.startswith("Acme") for j in filtered)

def test_deep_match_recovers_generic_title():
    # title-only ("software developer" not in "Engineer II") would drop the Gamma req;
    # deep match recovers it via the body.
    gamma = [j for j in _raw() if j.company == "Gamma"][0]
    assert not keyword_matches_deep("software developer", gamma.title, "")  # title alone misses
    assert keyword_matches_deep("software developer", gamma.title, gamma.description)  # body recovers

def test_coverage_not_lower_after_geo_and_depth(tmp_path):
    raw = _raw()
    after = filter_to_metro(raw, AREA)  # drop off-metro noise; deep-matched reqs already in-set
    rb = run_benchmark(raw, AREA, ["15-1252.00"], out_dir=tmp_path / "b")
    ra = run_benchmark(after, AREA, ["15-1252.00"], out_dir=tmp_path / "a")
    # removing off-metro noise must not lower the in-metro coverage score
    assert ra.composite_score >= rb.composite_score
```

- [ ] **Step 3: Run** `py -m pytest tests/geo/test_depth_lift.py -v` → PASS.
- [ ] **Step 4: Commit** `git add tests/fixtures/ws2/depth_before.jsonl tests/geo/test_depth_lift.py && git commit -m "test(geo): lift gate — geo trim + title+body recovery do not lower the WS-1 score"`

### Task 2d.7 — Full-suite green check

**Files:** none (verification task)

- [ ] **Step 1: Run the whole suite** `py -m pytest -q` → all green (WS-1 + WS-2a/b/c/d). If anything is red, fix it in the owning task's file and re-commit before proceeding.
- [ ] **Step 2: Commit (only if a fix was needed)** `git commit -am "fix(ws2): resolve full-suite regression surfaced by the consolidated run"` (skip if nothing changed).

**Phase WS-2d Verify:** `py -m pytest tests/geo -q` → all green. (Full WS-2 verify: `py -m pytest tests/discover tests/scrape tests/search tests/geo -q`.)

---

## Self-Review

- **Spec coverage:** discovery (WS-2a: cc_harvest §5.1, career_link §5.1, detect §5.1, registry user-wins §5.1, loud-failure fix §5.1/§7) ✓; Tier-1 scrapers (WS-2b: workable/recruitee/rippling/personio §5.2, jsonld §5.3, workday CSRF + faceted paging §5.4) ✓; hard targets (WS-2c: arbeitnow/jooble/careerjet §4, linkedin guest §5.4, serpapi BYO §5.4) ✓; geo+remote (WS-2d §5.5), title+body match (§5.6), freshness (§5.6), target_roles (§2) ✓; lift gates per group (§8/§10) in 2a.6, 2b.8, 2c.8, 2d.6 ✓.
- **Frozen contract:** every signature in the prompt is reproduced verbatim in Frozen Shared Interfaces and each task (`harvest_slugs`, `find_career_url`/`sitemap_job_urls`, `detect_ats`, `merge_discovered`, the four `fetch(slug)`, `extract_jobs(html, base_url)`, `keyword_matches_deep`, the 5 clients, `filter_to_metro(jobs, area, *, remote_region=None)`, `new_since_last(jobs, source_id, prev_keys)`, `target_roles[]`). `job_key` is consumed only (WS-1), never redefined.
- **Grounded in real code:** `JobResult` field list and `identity_key` (`models.py`); scraper shape + `_with_*`/`_matches` + `is_failed`/`mark_failed`/`slug_safe` (`greenhouse_scraper.py`, `cache_helpers.py`); dispatcher `_scrape_one` (`careers_client.py:106`); `detect_ats` host parsing (`ats_detect.py`); `save_companies` user-wins dedup returning a count (`company_registry.py:179`); `SingleFeedClient` `__init__`/`_cached`/`strip_html` (`single_feed_client.py`); `JobAPIClient`+`FileCache`/`RateLimiter(int).acquire()`/`MonthlyQuota`/`cache_key`/`to_float` (`base_client.py`, `http_util.py`); jsearch key-gate + quota refund pattern (`jsearch_client.py`); `cli.ALL_SOURCES`/`build_clients` lazy-import branches (`cli.py`); `preferences._DEFAULT_HARD`/`migrate_from_user_config`/`load` (`preferences.py`); `secrets/<name>` key-file pattern (`ranker.py:66`); workday bare-POST + slug parse + `_map_results` (`workday_scraper.py`); the `_Resp` + `monkeypatch.setattr(requests, ...)` test pattern (`tests/test_careers_fixes.py`).
- **Optional-dep posture:** no new _required_ deps; `lxml` deliberately avoided — `BeautifulSoup(html, "html.parser")` (already used by `direct_scraper.py`) is the HTML parser. Jooble/Careerjet free keys and the SerpApi key are env/secrets-gated with loud degrade, never hard-required.
- **XML safety (raised by the security hook):** untrusted XML (Personio feeds, third-party sitemaps) is parsed via `scrape/xml_safe._safe_fromstring`, which prefers `defusedxml` and falls back to DTD-stripped stdlib `ElementTree` — closing the XXE / billion-laughs hole the stock `ET.fromstring` would have left. `defusedxml` is the one new (optional, import-guarded) dependency. The helper is authored once in WS-2a Task 2a.0 and reuse-guarded in WS-2b Task 2b.0 so the two phases stay independently dispatchable without both writing the same file.
- **Could not fully ground (flagged for the executor):** (1) the **exact live JSON shapes** of the workable/recruitee/rippling/serpapi endpoints and the LinkedIn-guest card classes are modeled from the spec's documented URLs and common public response shapes — the recorded fixtures encode the assumed schema; if a live response differs at build time, the executor must re-capture the fixture and adjust the field map (spec §9 R1, "re-verify at build time"). (2) The **Workday CSRF cookie name** (`CALYPSO_CSRF_TOKEN`) and header (`X-CALYPSO-CSRF-TOKEN`) are the commonly observed pair; the prime step is fail-soft (falls back to a bare POST) so a wrong cookie name degrades gracefully rather than breaking. (3) The **Common Crawl CDX index id** (`CC-MAIN-2025-05`) is a placeholder default overridable via `crawl_id=`; the harvest test mocks `_cdx_fetch`, so the default index id is not load-bearing for the suite.
