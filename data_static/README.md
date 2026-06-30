# data_static — bundled read-only reference data

These are **curated public-domain subsets** shipped inside the read-only bundle
(`config.DATA_DIR/data_static/`). They feed the `coverage/` entity-resolution and
geography modules. The whole directory is treated as immutable at runtime; all
writes go under `config.USER_DATA_DIR`.

## Files

- **`onet_soc_alt_titles.tsv`** — tab-separated `alt_title<TAB>soc_code<TAB>soc_title`
  with a leading `# onet_version=<v>` comment. Source: O\*NET **Alternate Titles**
  (O\*NET Resource Center, public domain). This file holds a hand-curated subset
  (~40 common engineering / software / health titles incl. `software developer`
  → `15-1252.00`) — enough to drive entity resolution and the test suite.
- **`cbsa_delineation.csv`** — `cbsa_code,cbsa_title,principal_city,state` for ~15
  top U.S. metros incl. `Cincinnati, OH`. Source: U.S. Census Bureau **Core Based
  Statistical Area delineation** (public domain). Curated subset.
- **`company_aliases.json`** — editable `{"alias": "canonical"}` map merged into
  `canonicalize_company` (e.g. `optum → unitedhealth`).

## Follow-ups (not in WS-1 scope)

- Replace the O\*NET subset with the full Alternate Titles download (`~30k` rows)
  and regenerate once entity resolution is stable.
- Replace the CBSA subset with the full OMB/Census delineation file.
- The labeled-pair dedup gold set (`tests/fixtures/coverage/labeled_pairs.jsonl`)
  starts at ~40 pairs; expand toward ~200 as real cross-source examples are seen.
