# data_static — bundled read-only reference data

These are **curated public-domain subsets** shipped inside the read-only bundle
(`config.DATA_DIR/data_static/`). They feed the `coverage/` entity-resolution and
geography modules. The whole directory is treated as immutable at runtime; all
writes go under `config.USER_DATA_DIR`.

## Files

- **`onet_soc_alt_titles.tsv`** — tab-separated `alt_title<TAB>soc_code<TAB>soc_title`
  with a leading `# onet_version=<v>` comment. Source: the O\*NET 30.3 text
  database — **Occupation Data** (canonical title per SOC code), **Job Titles**
  (O\*NET's own curated alternate titles; the current release's name for what
  older releases called "Alternate Titles") and **Sample of Reported Titles**
  (self-reported by O\*NET's worker survey), joined by
  `scripts/build_onet_alt_titles.py` (all public domain / CC-BY 4.0, see
  https://www.onetcenter.org/database.html#licenseType). As of 2026-07-01 this
  is the FULL real dataset (~51k unique title→SOC rows, one row per title —
  see "join priority" below), downloaded live from onetcenter.org.

  Regenerate with:
  py -3.12 -m scripts.build_onet_alt_titles
  Add `--dry-run` to download + parse + report counts without writing, or
  `--out PATH` to write elsewhere for review. If the download fails (no
  internet, or O\*NET reorganizes their file layout again — it already has
  once, see the script's fallback filename list), the script prints a clear
  diagnostic and leaves the existing bundled tsv untouched; the app keeps
  working off whatever is currently bundled either way.

  **Join priority** (found running this against the real ~62k raw rows: the
  same literal title text can be attached to unrelated SOC codes across
  sources, e.g. a generic self-reported title colliding with a different
  occupation's canonical name): a title is claimed by the FIRST, highest-
  priority source to see it — (1) the canonical Occupation Data title, (2)
  O\*NET's curated Job/Alternate titles, (3) the noisier self-reported titles
  — and never overwritten by a later, lower-priority source for the same text.

  `industry_profile.py`'s O\*NET-SOC resolution tier does a **deterministic
  exact (+ simple singular/plural) lookup** against this file, NOT a fuzzy
  match: `rapidfuzz.token_set_ratio` (used by `coverage/entity.py` for its own
  dedup/coverage-estimation purpose, where an occasional miss is just
  statistical noise) is lenient to word reordering and subset/superset token
  differences, and over the full dataset that leniency produces confidently
  wrong matches (e.g. "registered nurse" → "Health Education Specialists" at
  a REPORTED confidence of 1.0). A field-routing tier can't tolerate that, so
  it only trusts a literal match.

- **`cbsa_delineation.csv`** — `cbsa_code,cbsa_title,principal_city,state` for the
  FULL set of ~935 U.S. Core Based Statistical Areas (metro + micro), incl.
  `Cincinnati, OH`. Source: U.S. Census Bureau **Core Based Statistical Area
  delineation** — the "List 1" file (public domain U.S. government work).

  Regenerate with:
  py -3.12 -m scripts.build_cbsa
  Add `--dry-run` to download + parse + report counts without writing, or
  `--out PATH` to write elsewhere for review. The script downloads the Census
  List 1 `.xlsx`, parses it with the standard library only (no openpyxl/pandas
  dependency), collapses the county-level rows to one row per CBSA, and derives a
  principal city + 2-letter state anchor from each CBSA title. If the download
  fails (no internet, or Census reorganizes their layout), it prints a clear
  diagnostic and leaves the bundled csv untouched; `coverage/geography.py`
  degrades gracefully to substring matching regardless.

- **`company_aliases.json`** — editable `{"alias": "canonical"}` map merged into
  `canonicalize_company` (e.g. `optum → unitedhealth`).

## Follow-ups (not in WS-1 scope)

- The labeled-pair dedup gold set (`tests/fixtures/coverage/labeled_pairs.jsonl`)
  starts at ~40 pairs; expand toward ~200 as real cross-source examples are seen.
