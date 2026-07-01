"""Relevance classification for discovered/seeded boards (plan P3).

A bulk ATS-slug import (dataset_seed) is *live* (probe-verified) but not
necessarily *on-field*: a health-informatics seeder does not want a marketing
agency's Greenhouse board just because it has open jobs. This gate filters
off-industry boards — deterministic-first (keyword-match the board's own scraped
job titles), and only the genuinely ambiguous long tail goes to an (optional,
batched, cached) AI call. It is conservative by construction:

  * a title matches the field's keywords            -> KEEP (deterministic)
  * the board exposes NO sample titles              -> KEEP (never drop blind)
  * titles exist but none match  -> ambiguous -> AI decides, else KEEP by default

So with no AI configured and no `drop_ambiguous`, nothing is ever dropped — the
query-time `get_registry(industry=)` filter remains the backstop. The gate only
*removes* a board when there is positive evidence (an AI reject, or an explicit
drop_ambiguous request) that it is off-field.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

# Generic title words that carry no field signal (so they don't count as matches).
_GENERIC = {
    "the", "and", "for", "with", "job", "jobs", "role", "roles", "position",
    "positions", "senior", "junior", "staff", "lead", "principal", "of", "in",
    "at", "an", "new", "our", "team", "remote", "hybrid", "onsite", "full", "time",
}


def title_keywords_for(industry: str, keywords=None) -> set:
    """The lowercased tokens whose presence in a job title signals field relevance.
    Drawn from the user's target keywords (primary) + the industry label."""
    toks: set[str] = set()
    for src in list(keywords or []) + [industry or ""]:
        for t in re.split(r"[\s_\-/,()]+", str(src).lower()):
            t = t.strip()
            if len(t) >= 3 and t not in _GENERIC:
                toks.add(t)
    return toks


def is_relevant_deterministic(name, sample_titles, kw):
    """True (a sampled title matches a field keyword) / False (titles present, none
    match — ambiguous) / None (no title sample — unknown, never drop)."""
    if not sample_titles:
        return None
    kw = {k for k in (kw or ()) if k}
    if not kw:
        return None
    for title in sample_titles:
        low = (title or "").lower()
        if any(re.search(r"\b" + re.escape(k) + r"\b", low) for k in kw):
            return True
    return False


def _load_cache(path):
    if not path:
        return {}
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_cache(path, cache):
    if not path:
        return
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    except OSError:
        pass


def classify_boards(boards, industry, keywords=None, *, ai=None, cache_path=None,
                    sample_fn=None, drop_ambiguous=False, batch_size=10) -> set:
    """Return the set of kept (ats_type, slug) identities.

    `boards`: iterable of CompanyEntry-like objects (.name/.ats_type/.slug), which
    may carry `.sample_titles`. `sample_fn(entry) -> [title,...]` overrides that
    (e.g. a live fetch). `ai(items, industry) -> [{relevant, subsector}]` (index-
    aligned) resolves ambiguous boards; results are cached by (ats,slug,industry).
    """
    kw = title_keywords_for(industry, keywords)
    ind_key = (industry or "").strip().lower()
    cache = _load_cache(cache_path)
    kept: set = set()
    ambiguous: list = []  # (entry, titles, cache_key)

    for e in boards:
        ident = (e.ats_type, e.slug)
        if sample_fn is not None:
            titles = list(sample_fn(e) or [])
        else:
            titles = list(getattr(e, "sample_titles", None) or [])
        verdict = is_relevant_deterministic(getattr(e, "name", ""), titles, kw)
        if verdict is True or verdict is None:
            kept.add(ident)                        # match, or no sample -> keep
            continue
        ckey = f"{e.ats_type}|{e.slug}|{ind_key}"  # verdict is False -> ambiguous
        if ckey in cache:
            if cache[ckey].get("relevant", True):
                kept.add(ident)
            continue
        if ai is None:
            if not drop_ambiguous:
                kept.add(ident)
            continue
        ambiguous.append((e, titles, ckey))

    for i in range(0, len(ambiguous), batch_size):
        chunk = ambiguous[i:i + batch_size]
        items = [{"name": getattr(e, "name", ""), "titles": t} for e, t, _ in chunk]
        try:
            results = ai(items, industry) or []
        except Exception:
            results = []
        for (e, _t, ckey), res in zip(chunk, results):
            res = res or {}
            rel = bool(res.get("relevant", True))
            cache[ckey] = {"relevant": rel, "subsector": res.get("subsector", "")}
            if rel:
                kept.add((e.ats_type, e.slug))
        # Any board the AI didn't return a verdict for stays kept (conservative).
        for e, _t, _ckey in chunk[len(results):]:
            kept.add((e.ats_type, e.slug))

    _save_cache(cache_path, cache)
    return kept


def make_classifier(industry, keywords=None, *, ai=None, cache_path=None,
                    sample_fn=None, drop_ambiguous=False):
    """Build the callable(list[CompanyEntry]) -> kept-set that dataset_seed /
    funnel accept as their `classify=` seam. No-op-safe: with no ai/sample_fn it
    keeps everything (probe-verify + query-time industry filter remain the gate)."""
    def _classify(entries):
        return classify_boards(entries, industry, keywords, ai=ai,
                               cache_path=cache_path, sample_fn=sample_fn,
                               drop_ambiguous=drop_ambiguous)
    return _classify


def sample_titles_for(entry, *, timeout=None, limit=8):
    """Fetch a few live job titles for a board (best-effort; [] on any failure).
    Mirrors probe_count's endpoints but returns titles for the relevance gate.
    Network — never called in tests (dataset_seed's classify seam injects instead)."""
    import requests
    if timeout is None:
        from config import CAREERS_REQUEST_TIMEOUT as timeout
    t, slug = entry.ats_type, entry.slug
    try:
        if t == "greenhouse":
            r = requests.get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs", timeout=timeout)
            if r.ok:
                return [j.get("title", "") for j in r.json().get("jobs", [])[:limit]]
        elif t == "lever":
            r = requests.get(f"https://api.lever.co/v0/postings/{slug}?mode=json", timeout=timeout)
            if r.ok:
                return [j.get("text", "") for j in r.json()[:limit]]
        elif t == "ashby":
            r = requests.get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}", timeout=timeout)
            if r.ok:
                return [j.get("title", "") for j in r.json().get("jobs", [])[:limit]]
        elif t == "smartrecruiters":
            r = requests.get(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit={limit}",
                             timeout=timeout)
            if r.ok:
                return [j.get("name", "") for j in r.json().get("content", [])[:limit]]
        elif t == "workday" and slug.count(":") == 2:
            tenant, n, site = slug.split(":")
            r = requests.post(
                f"https://{tenant}.wd{n}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs",
                json={"appliedFacets": {}, "limit": limit, "offset": 0, "searchText": ""},
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                timeout=timeout)
            if r.ok:
                return [j.get("title", "") for j in r.json().get("jobPostings", [])[:limit]]
    except Exception:
        return []
    return []
