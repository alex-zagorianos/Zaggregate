import hashlib
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlsplit, parse_qsl, urlencode

# Query params that carry no identity (tracking/analytics) -> dropped.
_TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term",
                    "utm_content", "gh_src", "fbclid", "gclid", "ref"}
# Query params that DO identify a specific posting -> kept.
_IDENTITY_PARAMS = {"gh_jid", "jobid", "id", "lever"}


def normalize_url(url: str) -> str:
    """Canonicalize a posting URL for identity comparison.

    Lowercases the host, drops scheme + fragment + trailing slash, and removes
    tracking query params (utm_*, gh_src, fbclid, gclid, ref) while keeping
    identity params (gh_jid, jobId, jobid, id, lever). Returns '' for falsy input.
    """
    if not url:
        return ""
    parts = urlsplit(url.strip())
    host = parts.netloc.lower()
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

    def salary_display(self) -> str:
        if self.salary_min and self.salary_max:
            return f"${self.salary_min:,.0f} - ${self.salary_max:,.0f}"
        if self.salary_min:
            return f"${self.salary_min:,.0f}+"
        return "Not listed"
