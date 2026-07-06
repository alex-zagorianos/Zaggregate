"""Regenerate data_static/cbsa_delineation.csv from the REAL, full U.S. Census
Bureau CBSA delineation file (public domain), replacing the ~15-metro curated
subset with all ~900+ Core Based Statistical Areas.

Source: the Census Bureau "List 1" metropolitan/micropolitan delineation file
(https://www.census.gov/programs-surveys/metro-micro/about/delineation-files.html
-- public domain U.S. government work). The July 2023 vintage is the default:

    https://www2.census.gov/programs-surveys/metro-micro/geographies/
        reference-files/2023/delineation-files/list1_2023.xlsx

The file is one row per COUNTY (a CBSA spans many counties); this script collapses
it to one row per CBSA and derives a principal city + a 2-letter state anchor from
the CBSA title (e.g. "Cincinnati, OH-KY-IN" -> city "Cincinnati", state "OH"),
matching the shape coverage/geography.py already consumes:

    cbsa_code,cbsa_title,principal_city,state
    17140,"Cincinnati, OH-KY-IN Metro Area",Cincinnati,OH

The .xlsx is parsed with the standard library only (zipfile + ElementTree over the
OOXML parts) -- NO openpyxl/pandas dependency is added.

Network access is optional: if the download fails (blocked env, no internet, or
Census reorganizes the file layout), the script prints a clear diagnostic and
exits non-zero WITHOUT touching the bundled csv -- the app keeps working off the
curated subset either way (coverage/geography.py degrades gracefully).

Run:    py -3.12 -m scripts.build_cbsa
        py -3.12 -m scripts.build_cbsa --dry-run   (download + parse, don't write)
        py -3.12 -m scripts.build_cbsa --out PATH  (write elsewhere, e.g. for review)
"""
from __future__ import annotations

import argparse
import csv
import io
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_CENSUS_VINTAGE = "2023"
_DEFAULT_URL = (
    "https://www2.census.gov/programs-surveys/metro-micro/geographies/"
    f"reference-files/{_CENSUS_VINTAGE}/delineation-files/list1_{_CENSUS_VINTAGE}.xlsx"
)

_DEFAULT_OUT = (Path(__file__).resolve().parent.parent
                / "data_static" / "cbsa_delineation.csv")

_UA = "Mozilla/5.0 (JobScout CBSA data-refresh script; contact via project README)"

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _xml(data: bytes) -> ET.Element:
    """Parse XML with DTD/entity processing disabled, so a malicious workbook
    can't mount an XXE / billion-laughs attack via the OOXML parts. (The Census
    source is trusted, but this stays safe if the URL is ever repointed.)"""
    parser = ET.XMLParser()
    try:
        # expat: refuse DOCTYPE and external/parameter entities outright.
        parser.parser.DefaultHandlerExpand = lambda *a, **k: None
        parser.parser.ExternalEntityRefHandler = lambda *a, **k: False
    except Exception:
        pass
    parser.feed(data)
    return parser.close()

# CSV header the loader (coverage/geography.py) expects. Keep byte-identical.
_HEADER = ["cbsa_code", "cbsa_title", "principal_city", "state"]

# Column labels in Census List 1 (row 3 header). Matched case-insensitively so a
# minor Census relabel doesn't silently mis-map columns.
_COL_CBSA_CODE = "cbsa code"
_COL_CBSA_TITLE = "cbsa title"
_COL_AREA_TYPE = "metropolitan/micropolitan statistical area"

_STATE_ABBR_RE = re.compile(r"\b([A-Z]{2})\b")


class DownloadError(RuntimeError):
    pass


def _fetch_bytes(url: str, timeout: int = 90) -> bytes:
    import requests
    resp = requests.get(url, timeout=timeout, headers={"User-Agent": _UA})
    resp.raise_for_status()
    if not resp.content:
        raise DownloadError(f"{url} returned an empty body")
    return resp.content


# -- minimal stdlib .xlsx reader (one sheet, shared strings) -------------------
def _read_shared_strings(z: zipfile.ZipFile) -> list[str]:
    try:
        root = _xml(z.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    out: list[str] = []
    for si in root.findall(f"{_NS}si"):
        out.append("".join(t.text or "" for t in si.iter(f"{_NS}t")))
    return out


def _cell_text(c: ET.Element, shared: list[str]) -> str:
    """Value of a worksheet cell as text (shared-string, inline-string, or number)."""
    t = c.get("t")
    if t == "inlineStr":
        return "".join(x.text or "" for x in c.iter(f"{_NS}t")).strip()
    v = c.find(f"{_NS}v")
    if v is None or v.text is None:
        return ""
    if t == "s":
        try:
            return shared[int(v.text)].strip()
        except (ValueError, IndexError):
            return ""
    return v.text.strip()


def _sheet_rows(xlsx_bytes: bytes) -> list[list[str]]:
    """Parse the first worksheet into a list of string rows (ragged-safe)."""
    with zipfile.ZipFile(io.BytesIO(xlsx_bytes)) as z:
        shared = _read_shared_strings(z)
        sheet = _xml(z.read("xl/worksheets/sheet1.xml"))
    data = sheet.find(f"{_NS}sheetData")
    if data is None:
        return []
    rows: list[list[str]] = []
    for r in data.findall(f"{_NS}row"):
        rows.append([_cell_text(c, shared) for c in r.findall(f"{_NS}c")])
    return rows


def _find_header(rows: list[list[str]]) -> Optional[int]:
    """Index of the header row (the one carrying 'CBSA Code' + 'CBSA Title')."""
    for i, row in enumerate(rows[:10]):
        low = [c.strip().lower() for c in row]
        if _COL_CBSA_CODE in low and _COL_CBSA_TITLE in low:
            return i
    return None


def _principal_city_and_state(title: str) -> tuple[str, str]:
    """Derive (principal_city, 2-letter state) from a Census CBSA title like
    'Cincinnati, OH-KY-IN' or 'Aberdeen, SD'. City = the first named place
    (before the first '-' in the place part); state = the first 2-letter code
    after the comma. ('', '') when the title has no comma-delimited state part."""
    title = (title or "").strip()
    if "," not in title:
        return ("", "")
    place, _, tail = title.partition(",")
    # The place part may list several cities joined by '-' ("Los Angeles-Long
    # Beach-Anaheim"); the FIRST is the principal anchor.
    principal = place.split("-")[0].strip()
    m = _STATE_ABBR_RE.search(tail)
    state = m.group(1) if m else ""
    return (principal, state)


def build_rows(rows: list[list[str]]) -> list[list[str]]:
    """Collapse the county-level Census rows to one (code,title,city,state) row
    per CBSA. Pure function of the parsed rows -- easy to unit-test with a small
    fixture that mirrors the real column layout. First occurrence of each CBSA
    code wins (they're contiguous in the file, all sharing one title)."""
    hi = _find_header(rows)
    if hi is None:
        raise DownloadError("could not locate the 'CBSA Code'/'CBSA Title' header "
                            "row -- Census may have changed the file layout")
    header = [c.strip().lower() for c in rows[hi]]
    idx_code = header.index(_COL_CBSA_CODE)
    idx_title = header.index(_COL_CBSA_TITLE)
    idx_type = header.index(_COL_AREA_TYPE) if _COL_AREA_TYPE in header else None

    seen: dict[str, list[str]] = {}
    order: list[str] = []
    for row in rows[hi + 1:]:
        if len(row) <= max(idx_code, idx_title):
            continue
        code = (row[idx_code] or "").strip()
        raw_title = (row[idx_title] or "").strip()
        if not code or not raw_title or not code.isdigit():
            continue
        if code in seen:
            continue
        area_type = (row[idx_type].strip().lower()
                     if idx_type is not None and len(row) > idx_type else "")
        # Suffix mirrors the curated subset's style ("... Metro Area").
        if "metropolitan" in area_type:
            suffix = " Metro Area"
        elif "micropolitan" in area_type:
            suffix = " Micro Area"
        else:
            suffix = ""
        title = f"{raw_title}{suffix}"
        city, state = _principal_city_and_state(raw_title)
        seen[code] = [code, title, city, state]
        order.append(code)
    return [seen[c] for c in order]


def render_csv(rows: list[list[str]]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(_HEADER)
    w.writerows(rows)
    return buf.getvalue()


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--url", default=_DEFAULT_URL,
                    help="Census List 1 .xlsx URL (default: the July 2023 file)")
    ap.add_argument("--out", default=str(_DEFAULT_OUT),
                    help="Output csv path (default: data_static/cbsa_delineation.csv)")
    ap.add_argument("--timeout", type=int, default=90, help="Download timeout (s)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Download + parse + report counts; do not write the csv")
    args = ap.parse_args(argv)

    print(f"Downloading Census CBSA delineation ({_CENSUS_VINTAGE}) from {args.url} ...")
    try:
        raw = _fetch_bytes(args.url, timeout=args.timeout)
        sheet_rows = _sheet_rows(raw)
        if not sheet_rows:
            raise DownloadError("workbook parsed to 0 rows")
        rows = build_rows(sheet_rows)
    except DownloadError as e:
        print(f"\nERROR: could not build the CBSA table -- keeping the existing "
              f"bundled csv untouched.\n{e}\n\nThis is expected in a "
              f"network-restricted environment; re-run from a machine with "
              f"internet access when you want the full table. The app works fine "
              f"off the curated subset in the meantime.", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"\nERROR: unexpected failure ({type(e).__name__}: {e}) -- keeping "
              f"the existing bundled csv untouched.", file=sys.stderr)
        return 1

    print(f"Parsed {len(rows)} unique CBSAs")
    if len(rows) < 500:
        print("ERROR: CBSA count looks too small to be the real dataset "
              "(expected ~900+) -- aborting without writing.", file=sys.stderr)
        return 1

    out_path = Path(args.out)
    if args.dry_run:
        print(f"[dry-run] would write {len(rows)} CBSAs to {out_path}")
        return 0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_csv(rows), encoding="utf-8")
    print(f"Wrote {len(rows)} CBSAs to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
