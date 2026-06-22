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


def _slug_valid(slug: str) -> bool:
    """Reject slugs that are clearly not ATS board identifiers (file names, deep paths)."""
    if not slug:
        return False
    # Reject slugs containing a dot (e.g. "robots.txt", "sitemap.xml") or slashes
    if "." in slug or "/" in slug:
        return False
    # Reject numeric-only slugs that look like job IDs, not board slugs
    if slug.isdigit():
        return False
    return True


def detect_ats(url_or_domain: str) -> tuple[str, str] | None:
    """Return (ats_type, slug) or None if undetectable."""
    host, segs = _split(url_or_domain)
    if not host:
        return None
    new = _detect_new_ats(host, segs)
    if new is not None:
        if _slug_valid(new[1]):
            return new
        return None
    ats, slug = _legacy_detect(url_or_domain)
    if ats == "direct" or not slug:
        return None
    if not _slug_valid(slug):
        return None
    return (ats, slug)
