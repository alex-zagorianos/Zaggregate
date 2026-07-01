# Research — Field-agnostic + multi-user wide-net (2026-07-01)

_Confidence: n/a_

## Summary
JobScout already has the right architecture for field-agnosticism (industry_profile.py's resolve() + search/keyword_strategy.py's de-seniorization + per-person projects in workspace.py), but the field knowledge itself is hand-written: ~20 token-matched rule buckets covering common fields, with a documented but unimplemented TODO to swap in the real O*NET taxonomy. The U.S. Department of Labor's O*NET database (CC BY 4.0, free, redistributable, already partially bundled at data_static/onet_soc_alt_titles.tsv as a 40-row curated stub) is the concrete, data-driven fix: its Job Titles file (57,543 alternate titles across all 1,016 O*NET-SOC occupations) and Sample of Reported Titles file (7,953 real-world incumbent titles) can replace the hand-written _RULES list, giving every one of BLS's 23 SOC major groups (healthcare, trades, admin, logistics, education, protective services, farming, arts — not just the ~20 fields coded today) a synonym map out of the box. Source coverage is uneven: RemoteOK/Remotive/Jobicy/Himalayas/Arbeitnow/HN-whoishiring are remote-first tech/knowledge-work niche boards that JobScout's own Muse/Jobicy gating already partly compensates for; Adzuna and USAJobs are the genuinely industry-agnostic aggregators and deserve more weight for non-tech fields. Per-user personalization already exists via workspace.create_project(person=) with a config.json industry field; the missing piece is keying that field off a stable O*NET-SOC code instead of free-text tokens, which would also fix the cross-person/cross-industry facts-cache-leak class of bug the team hit in Session 23.

## Findings
## Current state in the repo

JobScout's genre-agnostic machinery is centralized in three files:

- **[industry_profile.py](E:\ClaudeWork\ZAG0005 - Job Search App\industry_profile.py)** — `resolve(industry)` returns an `IndustryProfile` (Muse categories, Jobicy slug, `query_synonyms`, `title_terms`). Resolution order is user JSON override → a hand-written `_RULES` list (~20 token-set buckets: software/engineering, health, nursing, data, finance, sales, marketing, education, legal, HR, ops, design, construction/trades, hospitality, energy, fitness, veterinary, transportation, customer-support, management) → a generic full-reach fallback.
- **[search/keyword_strategy.py](E:\ClaudeWork\ZAG0005 - Job Search App\search\keyword_strategy.py)** — `deseniorize()`/`broad_query_keywords()` strips seniority tokens so phrase-matching APIs (Adzuna/USAJobs/JSearch) hit on the field stem instead of a 0-result exact title; `_MAX_SYNONYMS = 6` caps auto-added synonyms.
- **[workspace.py](E:\ClaudeWork\ZAG0005 - Job Search App\workspace.py)** (`create_project(..., person=)`, `people()`, `projects_for_person()`) already models "a person is a set of projects," each with its own `config.json` carrying an `industry` field consumed by `industry_profile.resolve()` and `search/source_taxonomy.py`.
- **[data_static/onet_soc_alt_titles.tsv](E:\ClaudeWork\ZAG0005 - Job Search App\data_static\onet_soc_alt_titles.tsv)** already exists — a **40-row hand-curated subset** of O\*NET Alternate Titles, currently consumed only by `coverage/entity.py` for dedup/entity resolution, **not** by `industry_profile.py` or `keyword_strategy.py`. `data_static/README.md` literally documents the follow-up: *"Replace the O\*NET subset with the full Alternate Titles download (~30k rows) and regenerate once entity resolution is stable."* This is the exact lever the task is asking about, already half-wired.
- `search/adzuna_client.py` and `search/usajobs_client.py` pass **no category/series filter at all** — unlike Muse/Jobicy (which were hardcoded to engineering categories until the 2026-06-30 fix), Adzuna and USAJobs already query full-breadth. That's good; it means they're the two sources least likely to need a genre-specific gate.

## O*NET-SOC as the data-driven synonym source

The [O*NET Resource Center database](https://www.onetcenter.org/database.html) (U.S. Dept. of Labor/ETA, current release 30.3, next major refresh **O*NET 30.2/31.0 due Feb 2026** per [onetcenter.org/whatsnew](https://www.onetcenter.org/whatsnew.html)) is licensed **CC BY 4.0** — free, commercial use permitted, redistribution in a desktop app permitted with attribution (credit "O\*NET 30.3 Database" + DOL/ETA, link the license) per [onetcenter.org/license_db.html](https://www.onetcenter.org/license_db.html). Three files matter directly:

1. **Job Titles.xlsx** — 57,543 rows, `alt_title -> O*NET-SOC code -> SOC title`. This is a drop-in replacement for the 40-row stub, at the exact same TSV shape the code already parses.
2. **Sample of Reported Titles.xlsx** — 7,953 real incumbent-reported titles per occupation (noisier but closer to how postings are actually phrased — useful as a secondary, lower-weight synonym tier).
3. **Related Occupations.txt/xlsx** and **Occupation Data** — 1,016 O*NET-SOC codes rolling up to the **23 BLS SOC 2018 major groups** (867 detailed SOC occupations) per [bls.gov/soc/2018/major_groups.htm](https://www.bls.gov/soc/2018/major_groups.htm) — this is the exhaustive field list that covers healthcare (29-/31-0000), office/admin support (43-0000), construction/extraction (47-0000), installation/maintenance/repair (49-0000), production (51-0000), transportation/material-moving (53-0000), protective service (33-0000), farming/fishing/forestry (45-0000), food prep (35-0000), personal care (39-0000), arts/media (27-0000), etc. — several of which have **no bucket in today's `_RULES`** (protective service, farming, personal care, arts/media are absent or only loosely covered).

O*NET also exposes a free **Web Services API** (registration required, no published hard rate cap — best-effort with a "wait 200ms on 429" guideline per [services.onetcenter.org/reference/](https://services.onetcenter.org/reference/)) with a live keyword-search endpoint. Given JobScout's local/offline/no-registration-friction philosophy, the **static bundled-file approach is the right fit**, not a live API call — it keeps SOC resolution instant, offline, and free of a second credential the user has to obtain.

**ESCO** (EU occupations/skills taxonomy, EUPL-1.2, free download at [esco.ec.europa.eu/en/use-esco/download](https://esco.ec.europa.eu/en/use-esco/download)) ships an official [O\*NET↔ESCO crosswalk](https://esco.ec.europa.eu/en/about-esco/data-science-and-esco/crosswalk-between-esco-and-onet), so if JobScout ever needs EU-market users it's a low-effort extension of the same SOC-keyed mechanism rather than a parallel system.

**Lightcast Open Skills/Titles** (75,000+ standardized titles, free tier, [lightcast.io/open-titles](https://lightcast.io/open-titles)) is a plausible secondary/validation source (built from real postings so it captures more contemporary title drift than O\*NET's periodic refresh), but it's API-gated rather than a redistributable static file, so it's a worse fit for a bundled offline app — worth a future cross-check, not the primary mechanism.

## Non-tech source coverage gaps

JobScout's aggregator mix skews tech/remote/startup more than it looks:

- **RemoteOK, Remotive, Himalayas, Jobicy, Arbeitnow, HN "Who's Hiring"** are all remote-first knowledge-work/tech boards. Arbeitnow in particular is confirmed as **"Germany's leading English-friendly tech job board"** (DACH-region, developer-heavy) per multiple aggregator listings — not a general board at all. JobScout's `jobicy_industry=None` gating in `industry_profile.py` already skips Jobicy for trades/hospitality/education/etc., which is correct; the same "skip when off-genre" treatment should be extended explicitly to RemoteOK/Remotive/Himalayas/Arbeitnow (currently these clients likely fetch unconditionally — worth auditing `search/remoteok_client.py`, `search/remotive_client.py`, `search/himalayas_client.py` the same way Muse/Jobicy were audited in the 2026-06-30 fix).
- **Adzuna** and **USAJobs** are the two genuinely industry-agnostic sources already in the stack — Adzuna's categories endpoint (`/{vertical}/{country}/categories`, [developer.adzuna.com/docs/categories](https://developer.adzuna.com/docs/categories)) spans Accounting & Finance, IT, Sales, Healthcare & Nursing, Trade & Construction, Logistics & Warehouse, Teaching, Hospitality & Catering, and more; USAJobs covers essentially every federal job series (health, trades, admin, law enforcement, logistics) with zero tech bias. These deserve to be the primary recall engine for non-tech fields, with the niche remote boards as precision add-ons only when `eng_like` or a knowledge-work profile is active.
- **Careerjet/Jooble/JSearch/SerpApi/LinkedIn-guest** are general meta-search aggregators (JSearch wraps Google for Jobs, which itself aggregates ATS/Indeed/LinkedIn postings agnostically) — no field bias, good breadth already.

## Recommended mechanism (concrete, data-driven, agnostic)

1. **(M effort)** Regenerate `data_static/onet_soc_alt_titles.tsv` from the full O\*NET 30.3 **Job Titles** + **Sample of Reported Titles** files (CC BY 4.0 attribution note already scaffolded in `data_static/README.md`) — a one-time offline script, ships as a ~2-4 MB static TSV, zero runtime dependency or API key.
2. **(M effort)** Add a fourth resolution tier in `industry_profile.resolve()`: **before** falling to the generic full-reach fallback, look up the industry string against the full O\*NET alt-titles index (fuzzy/token match), get its O*NET-SOC code, then derive `query_synonyms` (top-N alternate titles for that SOC) and `title_terms` (SOC title tokens + related-occupation tokens) automatically — same `IndustryProfile` shape, `source="onet"`. This literally satisfies "a brand-new field gets broad reach out-of-the-box" without adding a `_RULES` entry per field.
3. **(S effort)** Feed the derived SOC's BLS major-group into a small `SOC_MAJOR_GROUP -> {muse_categories, jobicy_industry}` table (23 entries, once) instead of continuing to grow the free-text `_RULES` list — this is the taxonomically complete version of what `_RULES` is approximating today, and it also fixes today's coverage holes (protective service, farming/fishing/forestry, personal care, arts/media have no bucket currently).
4. **(S effort)** In `search/keyword_strategy.py`, feed `Related Occupations` as a second, lower-priority synonym tier beyond direct alt-titles, still bounded by `_MAX_SYNONYMS`, to widen recall to adjacent job families (e.g. "nurse" → "clinical care coordinator") without diluting precision — `match/gate.py`/`match/scorer.py` remain the precision backstop, matching the existing design philosophy stated in the module docstring ("query on broad field terms for RECALL... let scoring handle precision").
5. **(M effort)** Persist the **resolved O\*NET-SOC code** (not just the free-text industry string) in each project's `config.json` when `workspace.create_project(person=...)` runs (wizard or Person button). Key `industry_profile.resolve()`, `facts_for` caching, and the registry-industry filter off that stable code, which removes the token-collision ambiguity that caused the Session 23 cross-person/cross-industry facts-cache leak and makes multi-user isolation exact rather than string-heuristic.
6. **(S effort)** Audit `search/remoteok_client.py`, `remotive_client.py`, `himalayas_client.py`, `arbeitnow` fetch (if present) the same way Muse/Jobicy were fixed 2026-06-30: gate them behind `industry_profile.resolve(industry).eng_like` (or a new `knowledge_work` flag) so a nurse/electrician/paralegal project doesn't burn API budget on boards that structurally can't return relevant results, and so Adzuna/USAJobs get proportionally more of the query budget for non-tech fields.

None of this requires new paid APIs, breaks the "never reduce reach" invariant (additions only), or touches the FREE/LOCAL/LEGAL constraints — O\*NET's files are public-domain-adjacent CC BY 4.0 static data, bundled exactly like `cbsa_delineation.csv` already is.

## Key recommendations

- **[M/high/risk:none]** Regenerate data_static/onet_soc_alt_titles.tsv from the FULL O*NET 30.3 'Job Titles' (57,543 rows) + 'Sample of Reported Titles' (7,953 rows) files, replacing the current 40-row curated stub (this is an already-documented TODO in data_static/README.md).  
  CC BY 4.0, free, redistributable in a desktop app with attribution; single offline regen script, no runtime API dependency; unlocks all 1,016 O*NET-SOC occupations instead of ~40 hand-picked titles.
- **[M/high/risk:none]** Add an O*NET-SOC-derived resolution tier to industry_profile.resolve(), inserted before the generic fallback, that fuzzy-matches the industry string against the bundled alt-titles index and auto-derives query_synonyms/title_terms from the matched SOC code + its alternate titles.  
  Directly satisfies 'a brand-new field gets broad reach out-of-the-box' without hand-writing a new _RULES bucket per field; keeps the existing IndustryProfile contract and user-override precedence unchanged.
- **[S/medium/risk:none]** Replace/extend the ~20 hand-written _RULES token buckets with a 23-entry SOC-major-group -> {muse_categories, jobicy_industry} table derived from BLS SOC 2018 major groups.  
  BLS SOC has 23 major groups (867 detailed occupations); current _RULES has no bucket for protective service, farming/fishing/forestry, personal care, or arts/media — taxonomically complete coverage closes those holes for free.
- **[S/medium/risk:none]** Gate RemoteOK/Remotive/Himalayas/Arbeitnow (and HN whoishiring) behind the same eng_like/knowledge-work check that Muse and Jobicy already use, since these are confirmed remote-first tech/DACH-tech boards, not general aggregators.  
  Prevents wasting API call budget on structurally-irrelevant sources for non-tech fields and lets Adzuna/USAJobs (confirmed industry-agnostic, already unfiltered) carry more of the query weight for e.g. healthcare/trades/admin projects.
- **[M/medium/risk:none]** Persist the resolved O*NET-SOC code (not just free-text industry) in each project's config.json created via workspace.create_project(person=...), and key industry_profile.resolve()/facts caching off that code.  
  Removes the string-token-collision ambiguity class of bug (the Session 23 cross-person/cross-industry facts-cache leak) and makes per-person, per-project isolation exact for the multi-user 'person = project' model.
- **[S/low/risk:none]** Add Related Occupations as a second, lower-priority synonym tier in search/keyword_strategy.py broad_query_keywords(), still bounded by _MAX_SYNONYMS, to widen recall to adjacent job families.  
  Matches the module's own stated design philosophy (broad recall query terms, precision handled downstream by match/scorer.py and match/gate.py) and uses data already bundled once O*NET files are regenerated.

## Sources
- https://www.onetcenter.org/database.html
- https://www.onetcenter.org/taxonomy.html
- https://www.onetcenter.org/crosswalks.html
- https://www.onetcenter.org/license_db.html
- https://www.onetonline.org/help/license
- https://www.onetcenter.org/whatsnew.html
- https://services.onetcenter.org/reference/
- https://esco.ec.europa.eu/en/use-esco/download
- https://esco.ec.europa.eu/en/about-esco/data-science-and-esco/crosswalk-between-esco-and-onet
- https://www.bls.gov/soc/2018/major_groups.htm
- https://www.bls.gov/soc/2018/
- https://lightcast.io/open-titles
- https://lightcast.io/open-skills
- https://developer.adzuna.com/docs/categories
- https://developer.adzuna.com/overview
- https://www.arbeitnow.com/blog/job-board-api