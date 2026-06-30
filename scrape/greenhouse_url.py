"""Canonical Greenhouse job URLs.

Greenhouse hands each job an `absolute_url`, but for many tenants that points at
the company's OWN careers site. Some of those sites (Nuro, Tulip, Aurora,
Zipline, Agility, Stoke, Saildrone, …) are JavaScript single-page apps that
never render the specific job server-side — the saved link opens a generic
"Work at X" page and looks dead, even though the posting is live.

Greenhouse's hosted application endpoint —
`https://job-boards.greenhouse.io/embed/job_app?for={slug}&token={id}` — renders
the full job description + apply form server-side for EVERY board, regardless of
how the company configured its own site. So we build links from the board slug +
numeric job id instead of trusting `absolute_url`. The link stays unique per job
(the token differs), so inbox de-duplication is unaffected.
"""
import re
from typing import Optional
from urllib.parse import urlsplit, parse_qs

_EMBED = "https://job-boards.greenhouse.io/embed/job_app?for={slug}&token={token}"
# Greenhouse-hosted job path, e.g. boards.greenhouse.io/acme/jobs/123
_PATH_RE = re.compile(r"/(?P<slug>[^/]+)/jobs/(?P<token>\d+)\b")


def embed_url(slug: str, token) -> str:
    """The server-rendered Greenhouse application URL for a job."""
    return _EMBED.format(slug=slug, token=token)


def parse(url: str) -> Optional[tuple[Optional[str], str]]:
    """Pull (slug, token) out of any Greenhouse job URL.

    Handles three shapes:
      * embed/job_app?for={slug}&token={id}                  -> (slug, id)
      * {greenhouse-host}/{slug}/jobs/{id}                   -> (slug, id)
      * {any-host}?gh_jid={id}   (a company-embed deep link) -> (None, id)

    Returns None when no Greenhouse job id can be found. `slug` is None when the
    URL carries the job id but not the board slug (a company-embed gh_jid link);
    callers resolve the slug from the company name in that case.
    """
    if not url:
        return None
    parts = urlsplit(url)
    host = parts.netloc.lower()
    q = parse_qs(parts.query)

    # 1. Already the hosted application endpoint.
    if "/embed/job_app" in parts.path:
        token = (q.get("token") or [None])[0]
        if token:
            return ((q.get("for") or [None])[0], token)

    # 2. Greenhouse-hosted board path /{slug}/jobs/{id}.
    if "greenhouse.io" in host:
        m = _PATH_RE.search(parts.path)
        if m:
            return (m["slug"], m["token"])

    # 3. Company-embed deep link ...?gh_jid={id} (slug unknown).
    gh = (q.get("gh_jid") or [None])[0]
    if gh:
        return (None, gh)

    return None
