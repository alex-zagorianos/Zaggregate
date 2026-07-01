import functools
import hashlib
import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlsplit, parse_qsl, urlencode

# Query params that carry no identity (tracking/analytics) -> dropped.
_TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term",
                    "utm_content", "gh_src", "fbclid", "gclid", "ref", "se"}
# Query params that DO identify a specific posting -> kept.
_IDENTITY_PARAMS = {"gh_jid", "jobid", "id", "lever"}
# Query params that carry a WRAPPED destination URL on redirect/click endpoints.
_REDIRECT_PARAMS = ("url", "target", "destination", "redirect", "redirect_url", "r_url")
# Only treat a generic ?url=/?target= as a redirect wrapper when the URL itself
# LOOKS like a click/redirect endpoint — otherwise a direct ATS/apply URL that
# happens to carry a `target=`/`redirect=` marketing param (e.g. a ZipRecruiter
# apply link) would be wrongly replaced by that unrelated destination and collapse
# two distinct postings in dedup.
_REDIRECT_HOST_RE = re.compile(
    r"^(l|lnk|link|links|click|clicks|clk|track|tracking|redirect|redir|r|rd|out|go|away)\.",
    re.I)
_REDIRECT_PATH_RE = re.compile(
    r"/(click|clk|redirect|redir|out|go|away|track|rd)(/|$)", re.I)


def _unwrap_redirect(url: str, _depth: int = 0) -> str:
    """Follow aggregator/redirect wrappers to the canonical destination so two
    links to the SAME posting (a Google/Indeed click-redirect vs the direct ATS
    URL) don't look distinct and inflate the inbox. Bounded recursion; returns the
    input unchanged when there's nothing to unwrap."""
    if not url or _depth > 3:
        return url
    parts = urlsplit(url.strip())
    host = parts.netloc.lower()
    q = dict(parse_qsl(parts.query, keep_blank_values=True))
    # Google redirect wrappers: google.com/url?q=… or /aclk?…&url=…
    if "google." in host and parts.path in ("/url", "/aclk"):
        for pname in ("q", "url"):
            val = q.get(pname, "")
            if val.startswith(("http://", "https://")):
                return _unwrap_redirect(val, _depth + 1)
    # Generic redirect params — ONLY on hosts/paths that look like a click/redirect
    # endpoint, so a direct posting URL carrying such a param is left alone.
    if _REDIRECT_HOST_RE.match(host) or _REDIRECT_PATH_RE.search(parts.path):
        for pname in _REDIRECT_PARAMS:
            val = q.get(pname, "")
            if val.startswith(("http://", "https://")):
                return _unwrap_redirect(val, _depth + 1)
    return url


def normalize_url(url: str) -> str:
    """Canonicalize a posting URL for identity comparison.

    Unwraps redirect/click wrappers (Google/aggregator), collapses any Indeed job
    URL to its `jk` identity, lowercases the host, drops scheme + fragment +
    trailing slash, and removes tracking query params (utm_*, gh_src, fbclid,
    gclid, ref) while keeping identity params (gh_jid, jobId, jobid, id, lever).
    Returns '' for falsy input.
    """
    if not url:
        return ""
    url = _unwrap_redirect(url)
    parts = urlsplit(url.strip())
    host = parts.netloc.lower()
    # Indeed: rc/clk, viewjob, m/viewjob and country subdomains all identify the
    # same posting by its `jk` job key -> one canonical form.
    if host.endswith("indeed.com"):
        jk = dict(parse_qsl(parts.query, keep_blank_values=True)).get("jk")
        if jk:
            return f"indeed.com/viewjob?jk={jk}"
    path = parts.path.rstrip("/")
    kept = [
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in _TRACKING_PARAMS
    ]
    query = urlencode(kept)
    base = f"{host}{path}"
    return f"{base}?{query}" if query else base


@dataclass
class JobResult:
    title: str
    company: str
    location: str
    salary_min: Optional[float]
    salary_max: Optional[float]
    description: str
    url: str
    source_keyword: str
    created: str
    job_id: str = ""
    source_api: str = ""
    # Filled in by match.scorer after dedup; -1 = not scored.
    score: int = -1
    score_notes: str = ""
    # Total postings on the company's careers board (careers scrapers only);
    # cheap company-size proxy: 12 openings = small shop, 300+ = mega board.
    # -1 = unknown (API sources don't see the whole board).
    board_count: int = -1
    # Transient (set by daily_run's freshness pass): True when this job_key was
    # not in the previous run's baseline for its source. Carried into the inbox
    # row's extras (new_batch) at insert; surfaced by the GUI "New only" filter.
    is_new: bool = False

    @property
    def dedup_key(self) -> str:
        raw = f"{(self.title or '').lower().strip()}|{(self.company or '').lower().strip()}|{(self.location or '').lower().strip()}"
        return hashlib.md5(raw.encode()).hexdigest()

    @property
    def identity_key(self) -> str:
        """Cross-source identity hash.

        Prefer the normalized URL (collapses location/tracking variants of the
        same posting). With no URL, fall back to title|company WITHOUT location,
        since location formatting varies across sources.
        """
        if self.url:
            raw = normalize_url(self.url)
        else:
            raw = f"{(self.title or '').lower().strip()}|{(self.company or '').lower().strip()}"
        return hashlib.md5(raw.encode()).hexdigest()

    @functools.cached_property
    def job_key(self) -> str:
        """Stable cross-source identity (SHA1 of company_canon|soc|loc|title_core).

        Delegates to coverage.entity.job_key_for with a local import so models.py
        stays import-light; falls back to the MD5 identity_key if coverage is
        unavailable (e.g. a stripped frozen build without the data bundle)."""
        try:
            from coverage import entity
            return entity.job_key_for(self)
        except ImportError:
            return self.identity_key

    def salary_display(self) -> str:
        if self.salary_min and self.salary_max:
            return f"${self.salary_min:,.0f} - ${self.salary_max:,.0f}"
        if self.salary_min:
            return f"${self.salary_min:,.0f}+"
        return "Not listed"
