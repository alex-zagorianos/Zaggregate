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
