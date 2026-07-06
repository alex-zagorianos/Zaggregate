"""Seed-My-Area: turn a metro + field into a VERIFIED local employer registry,
with zero AI, from the CareerOneStop Business Finder directory.

This is the "supply side" the held plan (Leg B) named as its missing half. The
DISCOVERY half is CareerOneStop Business Finder (discover.business_finder); the
IMPORT half already existed and is reused verbatim:

    employer {name, domain} -> career_link.find_career_url(domain)
                            -> ats_detect.detect_ats(url) -> (ats_type, slug)
                            -> ats_detect.probe_count(entry)  [live verify]
                            -> save VERIFIED boards only (P0-6 gate honored)

Only boards whose live probe returns >0 open jobs are saved; a dead/hallucinated
directory row fails the probe and is dropped, never written. Every save is tagged
with the user's field (token-aware normalized, so multi-word fields like
"warehouse logistics" match their own seeds — P0-1) plus a metro tag.

Bounded + polite: a per-run employer cap (default 40) and the shared careers
rate limiter (via probe_count's per-host limiter) keep it gentle. Best-effort:
no key, no employers, or a probe error each degrade to an honest empty result,
never a raised exception into a GUI or a daily run.

Success metric (held plan): a non-Cincinnati persona seeds a verified local
registry in <20 min unassisted — the whole flow is one call / one CLI flag / one
Tools-menu item, and needs only a free CareerOneStop key.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Optional

from discover.business_finder import BusinessFinderClient
from enumerate_companies import resolve_and_verify
from scrape.company_registry import get_registry, save_companies

# Default employer cap per run — enough to seed a metro's marquee employers
# without a long probe storm. Overridable by callers (CLI --limit / GUI).
DEFAULT_MAX_EMPLOYERS = 40


@dataclass
class SeedResult:
    """Outcome of one Seed-My-Area run — the honest report the plan wants."""
    industry: str = ""
    metro: str = ""
    has_key: bool = False
    discovered: int = 0            # employers returned by Business Finder
    with_domain: int = 0           # of those, ones that carried a website
    already_known: int = 0         # dropped: already in the registry by name
    verified: int = 0              # live boards (probe > 0)
    added: int = 0                 # actually written to companies.json
    dropped: list = field(default_factory=list)   # [(name, reason)]
    entries: list = field(default_factory=list)    # [(CompanyEntry, count)] verified
    note: str = ""                 # a one-line human explanation when empty

    def as_dict(self) -> dict:
        from collections import Counter
        return {
            "industry": self.industry, "metro": self.metro, "has_key": self.has_key,
            "discovered": self.discovered, "with_domain": self.with_domain,
            "already_known": self.already_known, "verified": self.verified,
            "added": self.added,
            "drop_reasons": dict(Counter(r for _, r in self.dropped)),
            "note": self.note,
        }


def _metro_tag(metro: str) -> str:
    """A generic slug tag derived from the metro string itself (never a hardcoded
    metro). Mirrors build_company_list._metro_tag."""
    try:
        import workspace
        tag = workspace.slugify(metro or "")
        if tag:
            return tag
    except Exception:
        pass
    return re.sub(r"[^a-z0-9]+", "-", (metro or "").strip().lower()).strip("-") or "local"


def _industry_tags(industry: str) -> list[str]:
    """Tags stamped on saved boards. The raw field (spaces preserved) is what the
    registry's token-aware matcher normalizes on both sides (P0-1), so store it
    verbatim; drop an empty field to avoid an untagged catch-all row."""
    ind = (industry or "").strip()
    return [ind] if ind else []


def seed_my_metro(
    *,
    industry: str = "",
    metro: str = "",
    keyword: str = "",
    limit: int = DEFAULT_MAX_EMPLOYERS,
    dry_run: bool = False,
    client: Optional[BusinessFinderClient] = None,
    resolve_and_verify_fn: Callable = resolve_and_verify,
    save_fn: Callable = save_companies,
    log: Callable[[str], None] = print,
    user_json=None,
) -> SeedResult:
    """Discover local employers via CareerOneStop Business Finder, verify each has
    a live ATS board, and save the verified ones (P0-6 honored), tagged for this
    field + metro.

    `client`, `resolve_and_verify_fn`, and `save_fn` are injectable for tests.
    Returns a SeedResult (never raises for the ordinary no-key / no-match cases).
    """
    res = SeedResult(industry=(industry or "").strip(), metro=(metro or "").strip())
    bf = client or BusinessFinderClient()
    res.has_key = bf.has_key()

    if not res.has_key:
        res.note = ("No CareerOneStop key — employer discovery is off. Add a free "
                    "CAREERONESTOP_USER_ID + CAREERONESTOP_TOKEN "
                    "(Tools > Connect job sources) to seed your area.")
        log(f"[seed-metro] {res.note}")
        return res

    if not res.industry and not (keyword or "").strip():
        res.note = "No field or keyword to search — nothing to seed."
        log(f"[seed-metro] {res.note}")
        return res

    log(f"[seed-metro] Looking up employers for "
        f"{res.industry or keyword!r} near {res.metro or '(no location)'}…")
    employers = bf.find_employers(industry=res.industry, keyword=keyword,
                                  location=res.metro, limit=limit)
    res.discovered = len(employers)
    if not employers:
        res.note = ("Business Finder returned no employers for this field + area "
                    "(or the key/endpoint needs verifying). Nothing seeded.")
        log(f"[seed-metro] {res.note}")
        return res

    # Only rows with a resolvable website can be turned into an ATS board; the
    # rest are directory contacts we can't verify. Cap for politeness.
    with_domain = [e for e in employers if e.get("domain")]
    res.with_domain = len(with_domain)
    candidates = [{"name": e["name"], "domain": e["domain"]} for e in with_domain[:limit]]
    log(f"[seed-metro] {res.discovered} employer(s) found, {res.with_domain} with a "
        f"website to resolve; probing for live ATS boards…")
    if not candidates:
        res.note = ("Found employers but none carried a website to resolve into a "
                    "careers board. Nothing to verify.")
        log(f"[seed-metro] {res.note}")
        return res

    try:
        existing = [e.name for e in get_registry(user_json=user_json)]
    except Exception:
        existing = []

    tag = _metro_tag(res.metro)
    tags = _industry_tags(res.industry) + [tag]
    verified, dropped = resolve_and_verify_fn(
        candidates, tags, metro_tag=tag, existing_names=existing)

    res.verified = len(verified)
    res.dropped = list(dropped)
    res.entries = list(verified)
    res.already_known = sum(1 for _, r in dropped if r == "already known")

    if not verified:
        res.note = ("No employer resolved to a live ATS board (dead/unreachable "
                    "boards are dropped, not saved — nothing bad is written).")
        log(f"[seed-metro] verified 0, dropped {len(dropped)}. {res.note}")
        return res

    if dry_run:
        log(f"[seed-metro] [dry-run] {res.verified} verified board(s); nothing written.")
        return res

    res.added = save_fn([e for e, _ in verified], user_json) if user_json is not None \
        else save_fn([e for e, _ in verified])
    log(f"[seed-metro] verified {res.verified}, added {res.added} verified local "
        f"board(s) for '{res.industry or keyword}' near {res.metro or '(no location)'}.")
    return res
