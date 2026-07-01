"""Regenerate data_static/onet_soc_alt_titles.tsv from the REAL, full O*NET
database (public domain / CC-BY 4.0 — https://www.onetcenter.org/database.html
license), replacing the ~40-row curated stub with tens of thousands of real
occupation title -> SOC code rows.

Downloads three O*NET text-database files and joins them:
  - "Job Titles.txt"                 O*NET-SOC Code, Job Title, Short Title, ...
    (this is the CURRENT name for what older O*NET releases called
    "Alternate Titles.txt" -- both filenames are tried, oldest-first fallback,
    so this script keeps working if O*NET reverts or an older mirror is used)
  - "Sample of Reported Titles.txt"  O*NET-SOC Code, Reported Job Title, ...
  - "Occupation Data.txt"            O*NET-SOC Code, Title, Description
    (the canonical occupation Title per SOC code -- the alt-title files don't
    carry it, so we join it in)

Output format (unchanged from the curated stub, see data_static/README.md):
    # onet_version=<version>
    # format: alt_title<TAB>soc_code<TAB>soc_title
    <alt_title>\t<soc_code>\t<soc_title>
    ...

Network access is optional: if the download fails (blocked environment, no
internet, O*NET reorganizes their file layout again), the script prints a
clear diagnostic and exits non-zero WITHOUT touching the existing bundled
tsv -- the app keeps working off the curated stub either way.

Run:    py -3.12 -m scripts.build_onet_alt_titles
        py -3.12 -m scripts.build_onet_alt_titles --dry-run   (download + parse, don't write)
        py -3.12 -m scripts.build_onet_alt_titles --out PATH  (write elsewhere, e.g. for review)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_BASE_URL = "https://www.onetcenter.org/dl_files/database/db_30_3_text"
_ONET_VERSION = "30.3"

# Oldest-name-first fallback: current O*NET releases (28+) merged the historic
# "Alternate Titles.txt" into "Job Titles.txt"; older releases/mirrors may still
# use the original name. Both have the same 4 columns we need (SOC code + the
# alternate/job title), so either is a valid source.
_ALT_TITLE_FILE_CANDIDATES = ["Job Titles.txt", "Alternate Titles.txt"]
_REPORTED_TITLES_FILE = "Sample of Reported Titles.txt"
_OCCUPATION_DATA_FILE = "Occupation Data.txt"

_DEFAULT_OUT = (Path(__file__).resolve().parent.parent
               / "data_static" / "onet_soc_alt_titles.tsv")

_UA = "Mozilla/5.0 (JobScout O*NET data-refresh script; contact via project README)"


class DownloadError(RuntimeError):
    pass


def _fetch_text(url: str, timeout: int = 60) -> str:
    import requests
    resp = requests.get(url, timeout=timeout, headers={"User-Agent": _UA})
    resp.raise_for_status()
    resp.encoding = resp.encoding or "utf-8"
    return resp.text


def _fetch_first_available(base_url: str, filenames: list[str], timeout: int = 60) -> tuple[str, str]:
    """Try each filename in order; return (text, filename_used). Raises
    DownloadError with all attempted URLs/errors if every candidate fails."""
    from urllib.parse import quote
    errors = []
    for name in filenames:
        url = f"{base_url}/{quote(name)}"
        try:
            return _fetch_text(url, timeout=timeout), name
        except Exception as e:
            errors.append(f"{url} -> {e}")
    raise DownloadError("All candidate URLs failed:\n  " + "\n  ".join(errors))


def _parse_tsv_rows(text: str) -> list[list[str]]:
    """Split O*NET's tab-delimited text into rows, skipping the header and any
    blank trailing lines. O*NET fields never contain embedded tabs/newlines."""
    lines = text.splitlines()
    if not lines:
        return []
    rows = []
    for line in lines[1:]:                 # skip header row
        if not line.strip():
            continue
        rows.append(line.split("\t"))
    return rows


def fetch_onet_data(base_url: str = _BASE_URL, timeout: int = 60) -> dict:
    """Download the three source files. Returns
        {"occupation_rows": [...], "alt_title_rows": [...], "alt_title_file": name,
         "reported_title_rows": [...]}
    Raises DownloadError on any failure (network, HTTP status, empty body)."""
    occ_text, _ = _fetch_first_available(base_url, [_OCCUPATION_DATA_FILE], timeout=timeout)
    occupation_rows = _parse_tsv_rows(occ_text)
    if not occupation_rows:
        raise DownloadError(f"{_OCCUPATION_DATA_FILE} downloaded but parsed to 0 rows")

    alt_text, alt_file = _fetch_first_available(base_url, _ALT_TITLE_FILE_CANDIDATES, timeout=timeout)
    alt_title_rows = _parse_tsv_rows(alt_text)
    if not alt_title_rows:
        raise DownloadError(f"{alt_file} downloaded but parsed to 0 rows")

    reported_text, _ = _fetch_first_available(base_url, [_REPORTED_TITLES_FILE], timeout=timeout)
    reported_title_rows = _parse_tsv_rows(reported_text)
    if not reported_title_rows:
        raise DownloadError(f"{_REPORTED_TITLES_FILE} downloaded but parsed to 0 rows")

    return {
        "occupation_rows": occupation_rows,
        "alt_title_rows": alt_title_rows,
        "alt_title_file": alt_file,
        "reported_title_rows": reported_title_rows,
    }


def build_rows(data: dict) -> list[tuple[str, str, str]]:
    """Join the three sources into (alt_title, soc_code, soc_title) rows.
    Pure function of the parsed data -- no I/O, easy to unit-test with a small
    fixture that mirrors the real O*NET column layout.

    IMPORTANT (found 2026-07-01 running this against the real dataset): the SAME
    literal title text can appear attached to DIFFERENT, unrelated SOC codes
    across the three sources -- e.g. a generic phrase that shows up as one
    occupation's official title AND as some other occupation's self-reported
    title. The consuming loader (coverage.entity._onet) builds a dict keyed by
    the casefolded text, so whichever row is LAST in the file silently wins --
    arbitrary, not authoritative. To keep the bundled data trustworthy, this
    function instead lets the FIRST (highest-priority) source to see an exact
    text CLAIM it; every later, lower-priority source is skipped for that exact
    text rather than allowed to overwrite it. Priority (highest first):
      1. the canonical Occupation Data title (authoritative, curated)
      2. O*NET's own curated Job/Alternate titles
      3. Sample of Reported Titles (self-reported by survey workers -- useful
         for recall, but the noisiest/most ambiguous source)
    """
    soc_title = {row[0].strip(): row[1].strip()
                for row in data["occupation_rows"] if len(row) >= 2 and row[0].strip()}

    claimed: dict[str, tuple[str, str, str]] = {}   # alt.casefold() -> (alt, soc, soc_title)

    def _claim(alt: str, soc: str):
        alt = (alt or "").strip()
        soc = (soc or "").strip()
        if not alt or not soc or soc not in soc_title:
            return
        key = alt.casefold()
        if key in claimed:
            return                        # a higher-priority source already claimed this text
        claimed[key] = (alt, soc, soc_title[soc])

    # Priority 1: the canonical occupation title maps to itself, so an
    # exact-title query always resolves to the RIGHT occupation.
    for soc, title in soc_title.items():
        _claim(title, soc)

    # Priority 2: O*NET's own curated Job/Alternate titles.
    for row in data["alt_title_rows"]:
        if len(row) < 3:
            continue
        soc, job_title, short_title = row[0].strip(), row[1].strip(), row[2].strip()
        _claim(job_title, soc)
        if short_title and short_title.lower() not in ("n/a", "na", ""):
            _claim(short_title, soc)

    # Priority 3 (lowest): self-reported titles.
    for row in data["reported_title_rows"]:
        if len(row) < 2:
            continue
        soc, reported_title = row[0].strip(), row[1].strip()
        _claim(reported_title, soc)

    return list(claimed.values())


def render_tsv(rows: list[tuple[str, str, str]], version: str = _ONET_VERSION) -> str:
    lines = [
        f"# onet_version={version}  (O*NET Job/Alternate Titles + Sample of Reported "
        f"Titles + Occupation Data; public domain / CC-BY 4.0; regenerate with "
        f"scripts/build_onet_alt_titles.py)",
        "# format: alt_title<TAB>soc_code<TAB>soc_title",
    ]
    for alt, soc, title in rows:
        lines.append(f"{alt}\t{soc}\t{title}")
    return "\n".join(lines) + "\n"


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base-url", default=_BASE_URL,
                    help="O*NET text-database base URL (default: the 30.3 release)")
    ap.add_argument("--out", default=str(_DEFAULT_OUT),
                    help="Output tsv path (default: data_static/onet_soc_alt_titles.tsv)")
    ap.add_argument("--timeout", type=int, default=60, help="Per-file download timeout (s)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Download + parse + report counts; do not write the output file")
    args = ap.parse_args(argv)

    print(f"Downloading O*NET {_ONET_VERSION} title data from {args.base_url} ...")
    try:
        data = fetch_onet_data(base_url=args.base_url, timeout=args.timeout)
    except DownloadError as e:
        print(f"\nERROR: could not download O*NET data — keeping the existing bundled tsv "
              f"untouched.\n{e}\n\nThis is expected in a network-restricted environment; "
              f"re-run this script from a machine with internet access when you want the "
              f"full dataset. The app works fine off the curated stub in the meantime.",
              file=sys.stderr)
        return 1
    except Exception as e:
        print(f"\nERROR: unexpected failure fetching O*NET data ({type(e).__name__}: {e}) — "
              f"keeping the existing bundled tsv untouched.", file=sys.stderr)
        return 1

    print(f"  Occupation Data: {len(data['occupation_rows'])} occupations")
    print(f"  {data['alt_title_file']}: {len(data['alt_title_rows'])} rows")
    print(f"  {_REPORTED_TITLES_FILE}: {len(data['reported_title_rows'])} rows")

    rows = build_rows(data)
    print(f"Joined -> {len(rows)} unique (alt_title, soc_code) rows")
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
