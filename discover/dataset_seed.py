"""Bulk-seed the company registry from an open ATS-slug dataset (plan P1).

The discovery funnel resolves a domain -> careers URL -> ATS board, but its
careers-link resolver misses JS-SPA boards (~1/10 hit rate). The far bigger,
$0 win is a *deterministic bulk seed*: open datasets (jobhive MIT ~86k/47 ATS,
OpenJobs MIT) already list (ats_type, slug) pairs directly. Feed those straight
through the same probe-verify gate that makes LLM enumeration safe — no resolver,
no hallucination, no staleness (every slug is live-probed before it is kept).

    boards = load_ats_dataset("jobhive.csv")         # {ats_type: {slug, ...}}
    result = seed_from_dataset("jobhive.csv", industry="health_informatics")

Parsing is stdlib-only (csv / json) — NO pyarrow/pandas, so the frozen .exe stays
lean. A parquet source is converted to CSV/NDJSON offline once (documented in the
CLI). Column names differ per dataset, so the importer auto-detects the common
shapes and accepts an explicit `column_map` override.
"""
from __future__ import annotations

import csv
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from discover.registry import _name_from_slug
from scrape.ats_detect import detect_ats
from scrape.ats_detect import probe_count as _probe_count
from scrape.company_registry import CompanyEntry, get_registry, save_companies

# Dataset ATS names -> our internal vocab (scrape.company_registry ats_type).
# Datasets label the same platform many ways; normalize to what probe_count knows.
_ATS_VOCAB = {
    "greenhouse": "greenhouse", "greenhouse.io": "greenhouse", "gh": "greenhouse",
    "lever": "lever", "lever.co": "lever",
    "ashby": "ashby", "ashbyhq": "ashby", "ashby_hq": "ashby",
    "smartrecruiters": "smartrecruiters", "smart_recruiters": "smartrecruiters",
    "workday": "workday", "workdayjobs": "workday", "myworkdayjobs": "workday",
    "workable": "workable",
    "recruitee": "recruitee",
    "personio": "personio",
    "icims": "icims",
    "taleo": "taleo",
    "successfactors": "successfactors", "sapsf": "successfactors", "sap": "successfactors",
    "jsonld": "jsonld", "direct": "direct",
}

# The ATS types probe_count can actually count (so the verify gate is meaningful).
PROBEABLE = {"greenhouse", "lever", "ashby", "smartrecruiters", "workday",
             "icims", "taleo", "successfactors", "jsonld"}

# Column-name candidates for auto-detection (lowercased match). Order = priority.
_COLS = {
    "ats":      ("ats", "ats_type", "ats_platform", "platform", "board_type",
                 "provider", "source", "system"),
    "slug":     ("slug", "company_slug", "board", "board_slug", "board_token",
                 "token", "handle", "identifier", "id"),
    "name":     ("name", "company", "company_name", "employer", "org", "organization"),
    "industry": ("industry", "industry_category", "sector", "category"),
    "url":      ("url", "board_url", "careers_url", "career_url", "job_board_url",
                 "link", "website"),
}


def normalize_ats(value: str) -> str:
    """Map a dataset's ATS label to our internal ats_type vocab ('' if unknown)."""
    v = (value or "").strip().lower().replace("-", "").replace(" ", "")
    return _ATS_VOCAB.get(v, _ATS_VOCAB.get(value.strip().lower(), ""))


def _pick_columns(fieldnames, column_map=None) -> dict:
    """Resolve which source columns map to ats/slug/name/industry/url."""
    lowered = {(f or "").strip().lower(): f for f in (fieldnames or [])}
    picked: dict[str, str | None] = {}
    override = {k: v for k, v in (column_map or {}).items()}
    for role, candidates in _COLS.items():
        if role in override:
            picked[role] = override[role]
            continue
        picked[role] = next((lowered[c] for c in candidates if c in lowered), None)
    return picked


def _iter_rows(path: Path):
    """Yield dict rows from a CSV or NDJSON/JSON file (stdlib only)."""
    suffix = path.suffix.lower()
    text_first = ""
    with path.open("r", encoding="utf-8", newline="") as fh:
        # Peek to disambiguate .txt / extensionless files.
        pos = fh.tell()
        text_first = fh.read(1)
        fh.seek(pos)
        if suffix in (".ndjson", ".jsonl") or (suffix == "" and text_first == "{"):
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict):
                    yield obj
            return
        if suffix == ".json" or text_first == "[":
            try:
                payload = json.load(fh)
            except json.JSONDecodeError:
                return
            rows = payload
            if isinstance(payload, dict):
                rows = next((v for v in payload.values() if isinstance(v, list)), [])
            for obj in rows or []:
                if isinstance(obj, dict):
                    yield obj
            return
        # Default: CSV/TSV
        dialect_delim = "\t" if suffix == ".tsv" else ","
        reader = csv.DictReader(fh, delimiter=dialect_delim)
        for row in reader:
            yield row


def _row_to_board(row: dict, cols: dict):
    """One dataset row -> (ats_type, slug, name) in our vocab, or None if unusable.
    `name` is the dataset's real company name ('' when the dataset has no name
    column) — carried so distinct boards that share a slug across ATS platforms
    don't collapse under an identical slug-derived name in save_companies."""
    ats_raw = (row.get(cols["ats"]) if cols["ats"] else "") or ""
    slug = (row.get(cols["slug"]) if cols["slug"] else "") or ""
    name = (row.get(cols["name"]) if cols["name"] else "") or ""
    ats = normalize_ats(str(ats_raw))
    slug = str(slug).strip()

    # Fall back to a board/careers URL column when ats/slug are absent or unmapped.
    if (not ats or not slug) and cols["url"]:
        url = str(row.get(cols["url"]) or "").strip()
        if url:
            d_ats, d_slug = detect_ats(url)
            ats = ats or d_ats
            slug = slug or d_slug
    if not ats or not slug:
        return None
    if ats not in _ATS_VOCAB.values():
        return None
    return (ats, slug, str(name).strip())


def load_ats_dataset(path, *, ats_filter=None, column_map=None, limit=None,
                     names_out=None) -> dict:
    """Parse an ATS-slug dataset into ``{ats_type: {slug, ...}}``.

    - `ats_filter`: keep only these ats_types (iterable, our vocab).
    - `column_map`: override column detection, e.g. {"ats": "platform", "slug": "token"}.
    - `limit`: stop after this many *rows* read (for --dry-run sampling).
    - `names_out`: optional dict; when supplied, populated with {(ats,slug): name}
      from the dataset's real name column (first non-empty wins).
    Bad/unmapped rows are silently skipped; the return value is dedup-by-set.
    """
    path = Path(path)
    keep = {normalize_ats(a) or a for a in ats_filter} if ats_filter else None
    boards: dict[str, set] = {}
    cols = None
    n = 0
    for row in _iter_rows(path):
        if cols is None:
            cols = _pick_columns(list(row.keys()), column_map)
        n += 1
        if limit is not None and n > limit:
            break
        board = _row_to_board(row, cols)
        if not board:
            continue
        ats, slug, name = board
        if keep is not None and ats not in keep:
            continue
        boards.setdefault(ats, set()).add(slug)
        if names_out is not None and name and (ats, slug) not in names_out:
            names_out[(ats, slug)] = name
    return boards


def _existing_keys(companies_json_path=None) -> set:
    """(ats_type, slug) pairs already in the registry (hardcoded ∪ companies.json)."""
    try:
        reg = get_registry(user_json=companies_json_path)
    except Exception:
        return set()
    return {(e.ats_type, e.slug) for e in reg}


def verify_boards(boards: dict, industry="", *, probe=_probe_count, max_workers=12,
                  existing=None, classify=None, names=None):
    """Probe-verify {ats:{slug}} boards → (verified, dropped).

    verified = [(CompanyEntry, open_job_count)] best-first; dropped = [(ats,slug,reason)].
    `existing` (a set of (ats,slug)) is skipped without probing. `names` maps
    (ats,slug)->the dataset's real company name (falls back to a slug-derived name).
    `classify`, when given, is a callable(list[CompanyEntry]) -> set of kept
    (ats,slug) applied AFTER verification (the P3 relevance gate seam).
    """
    existing = existing or set()
    names = names or {}
    tag = (industry or "").strip().lower().replace(" ", "_")
    industries = [tag] if tag else ["discovered"]

    work: list[tuple[str, str]] = []
    dropped: list[tuple[str, str, str]] = []
    for ats, slugs in boards.items():
        for slug in slugs:
            if not slug:
                continue
            if (ats, slug) in existing:
                dropped.append((ats, slug, "already known"))
                continue
            if ats not in PROBEABLE:
                dropped.append((ats, slug, f"unprobeable ats ({ats})"))
                continue
            work.append((ats, slug))

    def _one(pair):
        ats, slug = pair
        name = names.get((ats, slug)) or _name_from_slug(ats, slug)
        entry = CompanyEntry(name, ats, slug, list(industries))
        try:
            n = probe(entry)
        except Exception as e:  # network/parse — treat as unverifiable, don't crash
            return (pair, f"probe error: {type(e).__name__}", None)
        if n is None:
            return (pair, f"unverifiable board ({ats})", None)
        if n <= 0:
            return (pair, "no live jobs", None)
        return (pair, "ok", (entry, n))

    verified: list[tuple[CompanyEntry, int]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = [ex.submit(_one, p) for p in work]
        for fut in as_completed(futs):
            pair, reason, payload = fut.result()
            if payload is not None:
                verified.append(payload)
            else:
                dropped.append((pair[0], pair[1], reason))

    if classify is not None and verified:
        kept = classify([e for e, _ in verified])
        keep_pairs = set(kept or set())
        filtered = []
        for entry, n in verified:
            if (entry.ats_type, entry.slug) in keep_pairs:
                filtered.append((entry, n))
            else:
                dropped.append((entry.ats_type, entry.slug, "off-industry (classify)"))
        verified = filtered

    verified.sort(key=lambda t: t[1], reverse=True)
    return verified, dropped


def seed_from_dataset(path, industry="", *, probe=_probe_count, max_workers=12,
                      limit=None, ats_filter=None, column_map=None, classify=None,
                      companies_json_path=None, dry_run=False, existing=None) -> dict:
    """Load a dataset, probe-verify, and merge live boards into companies.json.

    Returns a summary dict {loaded, candidates, skipped_known, verified, dropped,
    added}. Idempotent: `save_companies` dedups, so re-running only adds new lives.
    """
    names: dict = {}
    boards = load_ats_dataset(path, ats_filter=ats_filter, column_map=column_map,
                              limit=limit, names_out=names)
    loaded = sum(len(s) for s in boards.values())
    if existing is None:
        existing = _existing_keys(companies_json_path)
    verified, dropped = verify_boards(boards, industry, probe=probe,
                                      max_workers=max_workers, existing=existing,
                                      classify=classify, names=names)
    skipped_known = sum(1 for _, _, r in dropped if r == "already known")
    added = 0
    if not dry_run and verified:
        added = save_companies([e for e, _ in verified], companies_json_path)
    return {
        "loaded": loaded,
        "candidates": loaded - skipped_known,
        "skipped_known": skipped_known,
        "verified": verified,
        "dropped": dropped,
        "added": added,
    }
