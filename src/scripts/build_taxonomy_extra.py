"""Regenerate data_static/onet_related_occupations.tsv from the REAL, full O*NET
database (public domain / CC-BY 4.0 — https://www.onetcenter.org/database.html
license) — the cross-occupation relatedness graph that powers Search Discovery's
"adjacent" / "worth a look" keyword tiers.

Companion to ``build_onet_alt_titles.py`` (same O*NET 30.3 release, same license,
same network-optional / never-clobber-on-failure discipline). Where that script
builds the WITHIN-occupation title expansion (alt titles for one SOC), THIS one
builds the BETWEEN-occupation graph so "Mechanical Engineer" can surface "Test
Engineer" / "Manufacturing Engineer" — occupations the user would never have
typed, which same-SOC alt-titles can't reach.

Downloads two O*NET text-database files and joins them:
  - "Related Occupations.txt"  O*NET-SOC Code, Related O*NET-SOC Code,
                               Relatedness Tier, Index
    (Tier ∈ {Primary-Short, Primary-Long, Supplemental} — Primary-* = a close
    match ("adjacent"), Supplemental = a looser one ("exploratory"))
  - "Occupation Data.txt"      O*NET-SOC Code, Title, Description
    (used to attach the canonical Title of the RELATED SOC, which the relatedness
    file carries only as a bare code)

Output format:
    # onet_version=<version>
    # format: soc_code<TAB>related_soc<TAB>tier<TAB>related_title
    <soc_code>\t<related_soc>\t<tier>\t<related_title>
    ...

Network access is optional: if the download fails (blocked environment, no
internet, O*NET reorganizes their file layout again), the script prints a clear
diagnostic and exits non-zero WITHOUT touching any existing bundled tsv — the
app's Search Discovery falls back to same-SOC alt-titles for adjacency until the
file is present.

Run:    py -3.12 -m scripts.build_taxonomy_extra
        py -3.12 -m scripts.build_taxonomy_extra --dry-run
        py -3.12 -m scripts.build_taxonomy_extra --out PATH
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Reuse the sibling script's proven fetch/parse helpers so the two O*NET builders
# never drift on download behavior, encoding, or header-skipping.
from scripts.build_onet_alt_titles import (  # noqa: E402
    DownloadError,
    _fetch_first_available,
    _parse_tsv_rows,
    _BASE_URL,
    _ONET_VERSION,
    _OCCUPATION_DATA_FILE,
)

_RELATED_OCC_FILE = "Related Occupations.txt"

_DEFAULT_OUT = (Path(__file__).resolve().parent.parent
                / "data_static" / "onet_related_occupations.tsv")

# The three relatedness tiers O*NET publishes, mapped to Search Discovery's
# suggestion tiers. Primary-* are close matches (surfaced as "adjacent"),
# Supplemental is a looser link (surfaced as "exploratory").
_VALID_TIERS = {"Primary-Short", "Primary-Long", "Supplemental"}


def fetch_related_data(base_url: str = _BASE_URL, timeout: int = 60) -> dict:
    """Download the two source files. Returns
        {"occupation_rows": [...], "related_rows": [...]}
    Raises DownloadError on any failure (network, HTTP status, empty body)."""
    occ_text, _ = _fetch_first_available(base_url, [_OCCUPATION_DATA_FILE], timeout=timeout)
    occupation_rows = _parse_tsv_rows(occ_text)
    if not occupation_rows:
        raise DownloadError(f"{_OCCUPATION_DATA_FILE} downloaded but parsed to 0 rows")

    rel_text, _ = _fetch_first_available(base_url, [_RELATED_OCC_FILE], timeout=timeout)
    related_rows = _parse_tsv_rows(rel_text)
    if not related_rows:
        raise DownloadError(f"{_RELATED_OCC_FILE} downloaded but parsed to 0 rows")

    return {"occupation_rows": occupation_rows, "related_rows": related_rows}


def build_rows(data: dict) -> list[tuple[str, str, str, str]]:
    """Join the two sources into (soc_code, related_soc, tier, related_title) rows.
    Pure function of the parsed data — no I/O, trivially unit-testable.

    A related SOC whose code is absent from Occupation Data (should not happen in
    a consistent release, but O*NET occasionally lags a file) is skipped rather
    than emitted with a blank title. An unrecognized tier string is likewise
    skipped so a schema change upstream surfaces as a row-count drop, not silent
    garbage tiers."""
    soc_title = {row[0].strip(): row[1].strip()
                 for row in data["occupation_rows"] if len(row) >= 2 and row[0].strip()}

    out: list[tuple[str, str, str, str]] = []
    for row in data["related_rows"]:
        if len(row) < 3:
            continue
        soc, related_soc, tier = row[0].strip(), row[1].strip(), row[2].strip()
        if not soc or not related_soc or tier not in _VALID_TIERS:
            continue
        title = soc_title.get(related_soc)
        if not title:
            continue
        out.append((soc, related_soc, tier, title))
    return out


def render_tsv(rows: list[tuple[str, str, str, str]], version: str = _ONET_VERSION) -> str:
    lines = [
        f"# onet_version={version}  (O*NET Related Occupations + Occupation Data; "
        f"public domain / CC-BY 4.0; regenerate with scripts/build_taxonomy_extra.py)",
        "# format: soc_code<TAB>related_soc<TAB>tier<TAB>related_title",
    ]
    for soc, related_soc, tier, title in rows:
        lines.append(f"{soc}\t{related_soc}\t{tier}\t{title}")
    return "\n".join(lines) + "\n"


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base-url", default=_BASE_URL,
                    help="O*NET text-database base URL (default: the 30.3 release)")
    ap.add_argument("--out", default=str(_DEFAULT_OUT),
                    help="Output tsv path (default: data_static/onet_related_occupations.tsv)")
    ap.add_argument("--timeout", type=int, default=60, help="Per-file download timeout (s)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Download + parse + report counts; do not write the output file")
    args = ap.parse_args(argv)

    print(f"Downloading O*NET {_ONET_VERSION} relatedness data from {args.base_url} ...")
    try:
        data = fetch_related_data(base_url=args.base_url, timeout=args.timeout)
    except DownloadError as e:
        print(f"\nERROR: could not download O*NET data — keeping any existing bundled "
              f"tsv untouched.\n{e}\n\nThis is expected in a network-restricted "
              f"environment; re-run from a machine with internet access. Search "
              f"Discovery falls back to same-SOC alt-titles for adjacency meanwhile.",
              file=sys.stderr)
        return 1
    except Exception as e:
        print(f"\nERROR: unexpected failure fetching O*NET data ({type(e).__name__}: {e}) "
              f"— keeping any existing bundled tsv untouched.", file=sys.stderr)
        return 1

    print(f"  Occupation Data: {len(data['occupation_rows'])} occupations")
    print(f"  {_RELATED_OCC_FILE}: {len(data['related_rows'])} rows")

    rows = build_rows(data)
    print(f"Joined -> {len(rows)} (soc, related_soc, tier, title) rows")
    if len(rows) < 1000:
        print("ERROR: joined row count looks too small to be the real dataset "
              "(expected tens of thousands) — aborting without writing.", file=sys.stderr)
        return 1

    out_path = Path(args.out)
    if args.dry_run:
        print(f"[dry-run] would write {len(rows)} rows to {out_path}")
        return 0

    text = render_tsv(rows)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    print(f"Wrote {len(rows)} rows to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
