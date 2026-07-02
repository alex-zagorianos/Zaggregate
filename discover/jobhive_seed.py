"""Bulk-seed the company registry from the jobhive open ATS dataset (MIT,
storage.stapply.ai) — streamed, field-targeted, and probe-verified.

discover.dataset_seed already turns a LOCAL ats-slug file into verified
registry entries. jobhive is a much bigger win but a much bigger dataset (the
manifest lists per-ATS CSV slices from ~13k rows to ~172k rows, some nearly a
GB) — downloading a slice to disk before filtering would blow right through
the "FREE + EFFICIENT" mandate. This module never does that: each ATS's CSV
slice is opened as an HTTP stream and parsed row-by-row; a row only becomes a
candidate once it (a) resolves to a real (ats_type, slug) board and (b) its
title/department/location — NEVER the free-text description — matches at
least one target field's keywords. ONE stream pass per ATS serves every
field passed in; two hard caps (a byte budget and a per-field candidate cap)
guarantee a run can never balloon into an unbounded download regardless of
how large the upstream dataset grows.

    fields = [FieldSpec("health_informatics", keywords_for_industry("health informatics")),
              FieldSpec("controls", keywords_for_industry("controls engineering"))]
    result = seed_from_jobhive(fields, ["greenhouse", "lever", "ashby"])

Only the union of surviving candidates is ever probe-verified (in parallel,
once each, even if a board matched several fields) — the same live-board gate
discover.dataset_seed uses, so a board that lands in companies.json here is
provably scrapable today, not just present in an open dataset.

Examples:
  py -3.12 discover/jobhive_seed.py --industry "health informatics" --dry-run
  py -3.12 discover/jobhive_seed.py --industry controls --ats greenhouse,lever,ashby --json
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import requests

# Mirrors discover/inbox_harvest.py's bootstrap so `py discover/jobhive_seed.py`
# works standalone too (this file sits one level deeper, hence parent.parent).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import CAREERS_REQUEST_TIMEOUT
from discover.dataset_seed import normalize_ats
from discover.registry import _name_from_slug
from scrape.ats_detect import detect_ats
from scrape.ats_detect import probe_count as _probe_count
from scrape.company_registry import CompanyEntry, get_registry, save_companies
from scrape.text_match import keyword_matches

DEFAULT_MANIFEST_URL = "https://storage.stapply.ai/jobhive/v1/manifest.json"

# ATS platforms this app's scrapers can actually pull jobs from (scrape/careers_client.py)
# — the only ones worth bulk-seeding from jobhive; the manifest lists ~47 platforms,
# most of which we have no scraper for (and adding one is a separate, larger task).
SEEDABLE_ATS = ["greenhouse", "lever", "ashby", "smartrecruiters", "workday",
                "workday_cxs",   # Workday URLs resolve to the public cxs JSON reader
                "workable", "recruitee", "personio", "rippling", "bamboohr",
                # E1 wave-2 small ATSes: subdomain-keyed, scrapable from the
                # jobhive row's URL alone (detect_ats resolves them), no
                # side-channel metadata needed. These are the ones present in the
                # jobhive manifest that our scrapers can seed cleanly.
                "breezy", "pinpoint", "teamtailor", "jazzhr"]

# E1 wave-2 ATSes that ARE in the jobhive manifest but are DELIBERATELY NOT
# bulk-seedable: eightfold (needs the employer corp-domain query param), oracle
# (needs the CX_N siteNumber scraped from the tenant page), and phenom (needs the
# refNum scraped from the page). None of those side-channel values are carried in
# a jobhive CSV row, so a row alone can't produce a scrapable board — they're
# onboarded explicitly via build_company_list / the power paste form instead.
_UNSEEDABLE_WAVE2_ATS = ("eightfold", "oracle", "phenom", "paylocity", "adp")

# jobhive requires a real User-Agent on every request (an unset/blank UA 403s).
_UA = "JobSearchTool/1.0 (personal use)"
_STREAM_TIMEOUT = 30  # seconds — connect/first-byte timeout for the CSV GET

# The verified jobhive per-ATS CSV column names (22 columns) this module reads.
# NEVER read 'description' here — it is the huge free-text field the whole
# streaming design exists to avoid pulling into the relevance blob.
_COL_URL = "url"
_COL_TITLE = "title"
_COL_COMPANY = "company"
_COL_ATS_TYPE = "ats_type"
_COL_LOCATION = "location"
_COL_DEPARTMENT = "department"

_TOKEN_RE = re.compile(r"[\s_\-/,]+")


@dataclass
class FieldSpec:
    """One target field/industry to bulk-seed for. `tag` is the industry tag
    stamped on every company matched under this field; `keywords` are the
    scrape.text_match boolean terms checked against each row's light relevance
    blob (title + department + location)."""
    tag: str
    keywords: list[str]


# Single tokens too COMMON to indicate a field for company-SELECTION: a job whose
# only match is one of these (a "Data Analyst" or "Director" at any company) is NOT
# evidence the employer hires in the target field, so matching on them alone would
# pollute the registry with unrelated companies. Multi-word phrases ("clinical
# informatics") and distinctive single tokens ("informatics", "ehr", "scada") are
# always kept. (Seniority words come straight from the exec title_terms.)
_GENERIC_TOKENS = frozenset({
    "vp", "director", "chief", "manager", "lead", "senior", "junior", "head",
    "principal", "staff", "associate", "coordinator", "specialist", "officer",
    "president", "executive", "intern", "assistant", "supervisor",
    "analyst", "engineer", "engineering", "developer", "scientist", "consultant",
    "advisor", "representative", "agent", "administrator", "technician",
    "health", "data", "business", "operations", "sales", "marketing", "care",
    "technology", "tech", "digital", "product", "project", "program", "service",
    "services", "support", "admin", "clinical", "nurse", "physician", "medical",
    "general", "global", "national", "team", "group", "corporate",
})


def keywords_for_industry(industry: str) -> list[str]:
    """Derive a jobhive relevance-keyword vocabulary for `industry`: its own
    tokens + industry_profile.resolve(industry)'s query_synonyms/title_terms,
    deduped and lowercased, then filtered to DISTINCTIVE terms (multi-word phrase
    OR a single token not in `_GENERIC_TOKENS`) so the seed selects companies that
    genuinely hire in the field rather than any company with a generic role.

    Returns [] when a field has NO distinctive terms (e.g. "general manager" ->
    only 'general'/'manager', both generic). Callers must treat an empty result as
    "too generic to seed precisely" and SKIP — never seed on generics, which would
    re-pollute the registry (the exact failure this filter exists to prevent)."""
    import industry_profile
    prof = industry_profile.resolve(industry)
    terms = (_TOKEN_RE.split((industry or "").lower())
             + list(prof.query_synonyms or []) + list(prof.title_terms or []))
    out: list[str] = []
    seen: set[str] = set()
    for t in terms:
        t = (t or "").strip().lower()
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return [k for k in out if (" " in k) or (k not in _GENERIC_TOKENS)]


def _fallback_slug(company: str) -> str:
    """Best-effort slug from a company display name, used only when
    detect_ats(url) can't resolve a real board (no/unrecognized url)."""
    return re.sub(r"[^a-z0-9]+", "-", (company or "").strip().lower()).strip("-")


_HEX_SLUG = re.compile(r"^[0-9a-f]{12,}$")


def _looks_junk(slug: str) -> bool:
    """Reject obviously-anonymous/test board slugs — a long hex hash, or a long
    DIGIT-HEAVY string (e.g. '55564patriot334567software868575745'). Deliberately
    NOT length-alone: real orgs concatenate into long slugs
    ('lawrencelivermorenationallaboratory', 'johnsonandjohnsoninnovativemedicine',
    hospital systems, universities) that we very much want to seed."""
    s = (slug or "").replace("-", "").replace("_", "")
    if not s:
        return True
    if _HEX_SLUG.match(s):
        return True
    digits = sum(c.isdigit() for c in s)
    return len(s) >= 20 and digits / len(s) >= 0.4


def _derive_board(row_ats_type: str, url: str, company: str, csv_ats: str) -> tuple[str, str]:
    """One CSV row -> (ats_type, slug) in our vocab, or ("", "") if unusable.
    Prefers detect_ats(url) (authoritative — the same fingerprint the rest of
    the app uses to detect boards from a career URL); falls back to the row's
    own ats_type + company columns when detect fails (no/unrecognized url).
    `csv_ats` is the ATS this CSV slice is FOR (the manifest's by_ats key) —
    the fallback's last resort when the row's own ats_type column is unusable."""
    if url:
        d_ats, d_slug = detect_ats(url)
        if d_ats and d_ats != "direct" and d_slug and not _looks_junk(d_slug):
            return d_ats, d_slug
    ats = normalize_ats(row_ats_type) or csv_ats
    slug = _fallback_slug(company)
    if not ats or not slug or _looks_junk(slug):
        return "", ""
    return ats, slug


def _probe_board(entry: CompanyEntry) -> int | None:
    """Liveness probe for a candidate board (the default `probe` for
    seed_from_jobhive). Delegates to scrape.ats_detect.probe_count for the
    ATSes it already knows how to count (greenhouse/lever/ashby/
    smartrecruiters/workday/bamboohr/rippling); workable/recruitee/personio
    have no count endpoint, so this reuses that ATS's own careers-scraper
    fetch() — the SAME code path a real scrape run uses, so a board that
    verifies here is provably scrapable later, not just theoretically live.
    Those three scrapers already fail-soft (return [] on any error), so an
    unreachable board and a genuinely-empty one both read as 0 here — the
    same class of ambiguity discover.dataset_seed's probe already accepts for
    its own uncountable ATSes (icims/taleo/successfactors/jsonld)."""
    t = entry.ats_type
    try:
        if t == "workable":
            from scrape.workable_scraper import fetch
            return len(fetch(entry.slug))
        if t == "recruitee":
            from scrape.recruitee_scraper import fetch
            return len(fetch(entry.slug))
        if t == "personio":
            from scrape.personio_scraper import fetch
            return len(fetch(entry.slug))
    except Exception:
        return None
    return _probe_count(entry)


class _ByteCountedLines:
    """Turns a bytes-chunk iterator (e.g. requests' Response.iter_content())
    into an iterator of decoded text LINES, suitable for csv.reader — the same
    shape csv.reader expects from an open text file. Buffers a partial
    trailing line across chunk boundaries (a chunk can end mid-row) and
    tracks the raw byte count consumed so far (self.total). Embedded newlines
    inside quoted CSV fields (e.g. jobhive's own 'description'/'raw' columns)
    are handled correctly downstream: csv.reader itself pulls additional
    lines from this iterator whenever a quoted field isn't closed by
    end-of-line, exactly as it does for a real text file.

    `max_bytes` (optional) caps the TOTAL bytes ever pulled from `chunks`:
    once reached, no NEW network chunk is fetched, but any already-buffered,
    already-downloaded complete line is still returned (a byte budget should
    never waste data that's already in hand) — a whole-chunk-sized "hangover"
    past the cap is possible (real chunk boundaries don't line up with rows),
    but never more than one extra chunk. A cap-triggered stop raises a plain
    StopIteration WITHOUT flushing a dangling partial line (that fragment is
    very likely mid-row) — only a genuine end-of-stream flushes the tail, so
    a byte cap landing inside a quoted multi-line field never surfaces as a
    csv.Error."""

    def __init__(self, chunks, max_bytes: int | None = None):
        self._chunks = chunks
        self._buf = ""
        self.total = 0
        self._eof = False       # the underlying chunk stream is exhausted
        self._capped = False    # the byte budget stopped further pulls
        self._max_bytes = max_bytes

    def __iter__(self):
        return self

    def __next__(self) -> str:
        while "\n" not in self._buf:
            if self._capped or self._eof:
                if self._buf and self._eof:
                    line, self._buf = self._buf, ""
                    return line
                raise StopIteration
            if self._max_bytes is not None and self.total >= self._max_bytes:
                self._capped = True
                continue
            try:
                chunk = next(self._chunks)
            except StopIteration:
                self._eof = True
                continue
            if not chunk:
                continue
            if isinstance(chunk, bytes):
                self.total += len(chunk)
                chunk = chunk.decode("utf-8", errors="replace")
            else:
                self.total += len(chunk.encode("utf-8", errors="replace"))
            self._buf += chunk
        line, self._buf = self._buf.split("\n", 1)
        return line + "\n"


def _process_ats(ats: str, csv_url: str, fields: list[FieldSpec], existing_keys: set,
                 candidates: dict, field_counts: dict, *, session, max_bytes_per_ats: int,
                 limit_per_field: int, chunk_size: int, log) -> dict:
    """Stream ONE ATS's CSV slice, updating `candidates`/`field_counts` in
    place (shared across every ATS pass, so the same board matched from two
    different slices — shouldn't happen, ats is part of the key, but a company
    on the same ATS matching two fields is exactly the point — merges).
    Returns this ATS's own {streamed_bytes, rows_scanned, candidates, error}."""
    summary = {"streamed_bytes": 0, "rows_scanned": 0, "candidates": 0, "error": None}
    resp = None
    lines = None
    try:
        resp = session.get(csv_url, headers={"User-Agent": _UA}, stream=True,
                           timeout=_STREAM_TIMEOUT)
        if hasattr(resp, "raise_for_status"):
            resp.raise_for_status()
        lines = _ByteCountedLines(iter(resp.iter_content(chunk_size=chunk_size)),
                                  max_bytes=max_bytes_per_ats)
        reader = csv.reader(lines)
        header = next(reader, None)
        if not header:
            summary["error"] = "empty response (no header row)"
            return summary
        col = {(name or "").strip().lower(): i for i, name in enumerate(header)}

        def _get(row: list, name: str) -> str:
            i = col.get(name)
            if i is None or i >= len(row):
                return ""
            return row[i] or ""

        row_iter = iter(reader)
        while True:
            if fields and all(field_counts.get(f.tag, 0) >= limit_per_field for f in fields):
                break
            try:
                row = next(row_iter)
            except StopIteration:
                break
            except csv.Error:
                # The byte cap can land mid-quoted-field (a huge 'raw'/
                # 'description' column) — that's an EXPECTED truncation from
                # our own budget, not a real parse failure, so stop quietly
                # instead of surfacing summary["error"].
                break
            summary["rows_scanned"] += 1

            url = _get(row, _COL_URL)
            title = _get(row, _COL_TITLE)
            company = _get(row, _COL_COMPANY)
            location = _get(row, _COL_LOCATION)
            department = _get(row, _COL_DEPARTMENT)
            row_ats_type = _get(row, _COL_ATS_TYPE)

            board_ats, board_slug = _derive_board(row_ats_type, url, company, ats)
            if not board_ats or not board_slug:
                continue
            key = (board_ats, board_slug)
            if key in existing_keys:
                continue

            blob = f"{title} {department} {location}"
            matched = [f.tag for f in fields
                      if field_counts.get(f.tag, 0) < limit_per_field
                      and any(keyword_matches(kw, blob) for kw in f.keywords)]
            if not matched:
                continue

            is_new = key not in candidates
            if is_new:
                candidates[key] = {"name": company.strip() or _name_from_slug(*key),
                                   "tags": set()}
                summary["candidates"] += 1
            tags = candidates[key]["tags"]
            for tag in matched:
                if tag not in tags:
                    tags.add(tag)
                    field_counts[tag] = field_counts.get(tag, 0) + 1
    except Exception as e:
        summary["error"] = f"{type(e).__name__}: {e}"
        log(f"  [jobhive] {ats}: slice fetch/parse failed ({summary['error']}) — skipping.")
    finally:
        summary["streamed_bytes"] = lines.total if lines is not None else 0
        try:
            if resp is not None and hasattr(resp, "close"):
                resp.close()
        except Exception:
            pass
    return summary


def _fetch_manifest(manifest_url: str, session) -> dict:
    resp = session.get(manifest_url, headers={"User-Agent": _UA}, timeout=CAREERS_REQUEST_TIMEOUT)
    if hasattr(resp, "raise_for_status"):
        resp.raise_for_status()
    return resp.json()


def _verify_candidates(candidates: dict, *, probe, max_workers: int):
    """Probe-verify the UNION of collected (ats, slug) candidates ONCE each,
    in parallel. Returns (verified: list[CompanyEntry], dropped: list[(ats, slug, reason)])."""
    verified: list[CompanyEntry] = []
    dropped: list[tuple] = []

    def _one(key):
        ats, slug = key
        info = candidates[key]
        name = info["name"] or _name_from_slug(ats, slug)
        entry = CompanyEntry(name, ats, slug, sorted(info["tags"]))
        try:
            n = probe(entry)
        except Exception as e:
            return key, f"probe error: {type(e).__name__}", None
        if n is None:
            return key, f"unverifiable board ({ats})", None
        if n <= 0:
            return key, "no live jobs", None
        return key, "ok", entry

    with ThreadPoolExecutor(max_workers=max(1, max_workers)) as ex:
        futs = [ex.submit(_one, k) for k in candidates]
        for fut in as_completed(futs):
            key, reason, entry = fut.result()
            if entry is not None:
                verified.append(entry)
            else:
                dropped.append((key[0], key[1], reason))

    verified.sort(key=lambda e: e.name.lower())
    return verified, dropped


def seed_from_jobhive(fields: list[FieldSpec], ats_list: list[str], *,
                      max_bytes_per_ats: int = 60_000_000,
                      limit_per_field: int = 500,
                      max_workers: int = 24,
                      dry_run: bool = False,
                      companies_json=None,
                      manifest_url: str = DEFAULT_MANIFEST_URL,
                      session=None,
                      probe: Callable[[CompanyEntry], int | None] | None = None,
                      existing: set | None = None,
                      chunk_size: int = 65_536,
                      log: Callable[[str], None] = print) -> dict:
    """Bulk-seed companies.json from the jobhive open dataset, one field-
    targeted, byte-and-candidate-bounded streaming pass per ATS.

    `fields`: the FieldSpecs to seed for (a board matching >1 field's
    keywords gets all those tags on one registry entry). `ats_list`: which
    ATS platforms (jobhive manifest keys) to stream — non-seedable/unknown
    entries are skipped with a log line. `max_bytes_per_ats` and
    `limit_per_field` are the two hard caps that keep this bounded regardless
    of how large the upstream dataset is; a slice's stream stops the instant
    EITHER is hit. `existing` (a set of (ats_type, slug)) overrides the
    registry snapshot used to skip already-known boards — when None it's
    computed once via scrape.company_registry.get_registry(user_json=companies_json)
    (never per-row: dedup happens BEFORE any probing). `probe` overrides the
    default liveness check (_probe_board) — inject a fake in tests. `session`
    overrides the HTTP client (must expose .get(url, headers=, stream=,
    timeout=) -> a response with .raise_for_status()/.iter_content()/.json()/
    .close()) — when None a real requests.Session() is used (and closed when
    this call created it).

    Returns a summary dict:
        {"manifest_url", "ats": {ats: {streamed_bytes, rows_scanned,
         candidates, error}}, "fields": {tag: {candidates, verified, added}},
         "verified", "added", "dropped", "entries"(the verified CompanyEntry
         list, for callers/tests that want the actual boards, not just
         counts), "error"(top-level, only on a manifest-fetch failure)}
    Per-field "added" assumes every verified entry for that tag was actually
    written — true unless save_companies additionally skipped one on a rare
    company-NAME collision (the pre-probe (ats,slug) dedup already prevents
    the far more common case); the top-level "added" (save_companies' own
    return value) is always the authoritative total.
    """
    if probe is None:
        probe = _probe_board
    created_session = session is None
    sess = session or requests.Session()

    field_counts: dict[str, int] = {f.tag: 0 for f in fields}
    candidates: dict[tuple, dict] = {}
    ats_summary: dict[str, dict] = {}
    result: dict = {
        "manifest_url": manifest_url,
        "ats": ats_summary,
        "fields": {f.tag: {"candidates": 0, "verified": 0, "added": 0} for f in fields},
        "verified": 0,
        "added": 0,
        "dropped": [],
        "entries": [],
    }

    try:
        try:
            manifest = _fetch_manifest(manifest_url, sess)
        except Exception as e:
            log(f"  [jobhive] manifest fetch failed ({type(e).__name__}: {e}) — aborting.")
            result["error"] = f"manifest: {type(e).__name__}: {e}"
            return result

        by_ats = manifest.get("by_ats") or {}

        if existing is None:
            try:
                existing = {(e.ats_type, e.slug) for e in get_registry(user_json=companies_json)}
            except Exception:
                existing = set()

        wanted: list[str] = []
        for raw in ats_list:
            norm = normalize_ats(raw) or (raw or "").strip().lower()
            if norm not in SEEDABLE_ATS:
                log(f"  [jobhive] '{raw}' is not a seedable ATS (no scraper support) — skipping.")
                continue
            wanted.append(norm)

        for ats in wanted:
            slice_info = by_ats.get(ats)
            csv_url = slice_info.get("csv") if isinstance(slice_info, dict) else None
            if not csv_url:
                log(f"  [jobhive] {ats}: no CSV slice in the manifest — skipping.")
                ats_summary[ats] = {"streamed_bytes": 0, "rows_scanned": 0, "candidates": 0,
                                    "error": "no csv slice in manifest"}
                continue
            log(f"  [jobhive] {ats}: streaming {csv_url} ...")
            s = _process_ats(ats, csv_url, fields, existing, candidates, field_counts,
                             session=sess, max_bytes_per_ats=max_bytes_per_ats,
                             limit_per_field=limit_per_field, chunk_size=chunk_size, log=log)
            ats_summary[ats] = s
            log(f"  [jobhive] {ats}: {s['rows_scanned']} row(s) scanned, "
                f"{s['candidates']} candidate(s), {s['streamed_bytes']:,} byte(s).")

        for f in fields:
            result["fields"][f.tag]["candidates"] = field_counts.get(f.tag, 0)

        if not candidates:
            return result

        verified, dropped = _verify_candidates(candidates, probe=probe, max_workers=max_workers)
        result["verified"] = len(verified)
        result["dropped"] = dropped
        result["entries"] = verified
        for e in verified:
            for tag in e.industries:
                if tag in result["fields"]:
                    result["fields"][tag]["verified"] += 1

        added = 0
        if not dry_run and verified:
            added = save_companies(verified, companies_json)
        result["added"] = added
        if not dry_run:
            for e in verified:
                for tag in e.industries:
                    if tag in result["fields"]:
                        result["fields"][tag]["added"] += 1

        return result
    finally:
        if created_session:
            try:
                sess.close()
            except Exception:
                pass


# ── CLI ───────────────────────────────────────────────────────────────────────
def _cli_tag(industry: str) -> str:
    try:
        import workspace
        return workspace.slugify(industry)
    except Exception:
        return re.sub(r"[^a-z0-9]+", "-", (industry or "").strip().lower()).strip("-") or "field"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Bulk-seed the company registry from the jobhive open ATS dataset, "
                    "field-targeted and probe-verified.")
    ap.add_argument("--industry", action="append", default=[], dest="industries",
                    help="A field/industry to seed for (repeatable — one FieldSpec per "
                         "flag; tag = a slug of the industry, keywords via "
                         "keywords_for_industry()). Give it 1 or more times.")
    ap.add_argument("--ats", default=",".join(SEEDABLE_ATS),
                    help=f"Comma-separated ATS platforms to stream (default: all seedable — "
                         f"{','.join(SEEDABLE_ATS)})")
    ap.add_argument("--max-bytes", type=int, default=60_000_000,
                    help="Byte cap per ATS slice (default 60,000,000 = 60MB)")
    ap.add_argument("--limit", type=int, default=500,
                    help="Max candidates collected per field before it stops being matched "
                         "further (default 500)")
    ap.add_argument("--workers", type=int, default=24,
                    help="Parallel probe-verify workers (default 24)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Resolve + verify but never write companies.json")
    ap.add_argument("--json", action="store_true",
                    help="Print the summary as JSON instead of the staged narrative")
    args = ap.parse_args(argv)

    if not args.industries:
        print("error: at least one --industry is required.")
        return 2

    fields = []
    for ind in args.industries:
        kws = keywords_for_industry(ind)
        if not kws:
            print(f"  [jobhive] skipping '{ind}': no distinctive terms to seed on "
                  f"(too generic — a match would pollute the registry).")
            continue
        fields.append(FieldSpec(tag=_cli_tag(ind), keywords=kws))
    if not fields:
        print("error: no field had distinctive keywords to seed on.")
        return 2
    ats_list = [a.strip() for a in args.ats.split(",") if a.strip()]

    result = seed_from_jobhive(fields, ats_list, max_bytes_per_ats=args.max_bytes,
                              limit_per_field=args.limit, max_workers=args.workers,
                              dry_run=args.dry_run)

    if args.json:
        print(json.dumps(result, indent=2, default=str))
        return 0

    print("\n" + "=" * 64)
    print("jobhive bulk seed")
    print("=" * 64)
    for ats, s in result.get("ats", {}).items():
        if s.get("error"):
            print(f"  {ats:16}: FAILED — {s['error']}")
        else:
            print(f"  {ats:16}: {s['rows_scanned']} rows, {s['candidates']} candidate(s), "
                  f"{s['streamed_bytes']:,} bytes")
    print()
    for tag, s in result.get("fields", {}).items():
        print(f"  [{tag}] candidates={s['candidates']} verified={s['verified']} added={s['added']}")
    print(f"\nTotal verified: {result.get('verified', 0)}, added: {result.get('added', 0)}"
          f"{' (dry-run)' if args.dry_run else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
