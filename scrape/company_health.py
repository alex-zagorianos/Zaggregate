"""Prune dead/empty companies from companies.json.

A company is removed only after it fails a probe `threshold` times in a row
(tracked in cache/company_health.json), so one transient network blip can't
delete a live entry. Only user/discovered entries in companies.json are touched
— the hardcoded registry lives in code and is never pruned.

Probe outcomes:
  True  -> alive (board reachable AND has >=1 posting)  -> streak reset
  False -> definitively dead (HTTP 404) or empty board  -> streak += 1
  None  -> unknown (timeout / connection error / other) -> streak untouched
"""
import json
from pathlib import Path
from typing import Callable, Optional

import requests

from config import CACHE_DIR, COMPANIES_JSON, CAREERS_REQUEST_TIMEOUT
from scrape.cache_helpers import write_cache
from scrape.company_registry import CompanyEntry

_GREENHOUSE_URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
_LEVER_URL = "https://api.lever.co/v0/postings/{slug}?mode=json"
_UA = {"User-Agent": "Mozilla/5.0 (zaggregate company-health probe)"}


def _probe(entry: CompanyEntry) -> Optional[bool]:
    """Return True (alive), False (404/empty), or None (unknown — don't penalize)."""
    try:
        if entry.ats_type == "greenhouse":
            r = requests.get(_GREENHOUSE_URL.format(slug=entry.slug), timeout=CAREERS_REQUEST_TIMEOUT)
            if r.status_code == 404:
                return False
            r.raise_for_status()
            return len(r.json().get("jobs", [])) > 0
        if entry.ats_type == "lever":
            r = requests.get(_LEVER_URL.format(slug=entry.slug), timeout=CAREERS_REQUEST_TIMEOUT)
            if r.status_code == 404:
                return False
            r.raise_for_status()
            data = r.json()
            return isinstance(data, list) and len(data) > 0
        if entry.ats_type == "direct":
            r = requests.get(entry.slug, timeout=CAREERS_REQUEST_TIMEOUT, headers=_UA)
            if r.status_code == 404:
                return False
            return None if r.status_code >= 400 else True
        # workday slugs are "tenant:N:site" (not a fetchable URL here) — skip.
        return None
    except requests.RequestException:
        return None


def _load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def prune_companies(
    threshold: int = 2,
    json_path: Optional[Path] = None,
    health_path: Optional[Path] = None,
    probe: Callable[[CompanyEntry], Optional[bool]] = _probe,
) -> list[str]:
    """Probe every company in companies.json; remove those that have now failed
    `threshold` consecutive probes. Returns the names removed."""
    path = json_path or COMPANIES_JSON
    hpath = health_path or (CACHE_DIR / "company_health.json")
    raw = _load_json(path)
    companies = raw.get("companies", [])
    health = _load_json(hpath)

    removed_keys: set[tuple] = set()
    removed_names: list[str] = []

    for c in companies:
        if "_example" in c or not c.get("name"):
            continue
        # Browser-only boards (S33/S34) are real, live companies the SERVER
        # cannot read — a Cloudflare/CSRF-walled tenant or a browser-verified
        # direct clip. Probing them here is a guaranteed-fail (or, for a
        # clipped direct slug, a fetch we've promised never to make
        # server-side), and letting the fail-streak accumulate would DELETE a
        # board the user explicitly verified from their own browser. Skip:
        # never probed, never penalized, never pruned.
        if (c.get("extra") or {}).get("browser_only"):
            continue
        entry = CompanyEntry(
            name=c["name"], ats_type=c.get("ats_type", "direct"),
            slug=c.get("slug", ""), industries=c.get("industries", []),
        )
        key = f"{entry.ats_type}:{entry.slug}"
        alive = probe(entry)
        if alive is True:
            health[key] = 0
        elif alive is False:
            health[key] = int(health.get(key, 0)) + 1
            if health[key] >= threshold:
                removed_keys.add((entry.ats_type, entry.slug))
                removed_names.append(entry.name)
                health.pop(key, None)
        # alive is None -> leave streak untouched

    if removed_keys:
        raw["companies"] = [
            c for c in companies
            if "_example" in c or (c.get("ats_type"), c.get("slug")) not in removed_keys
        ]
        write_cache(path, raw)
    write_cache(hpath, health)
    return removed_names
