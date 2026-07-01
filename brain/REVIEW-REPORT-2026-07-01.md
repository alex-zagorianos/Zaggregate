# JobScout — Deep Review & Reach Test (2026-07-01, overnight, autonomous)

**Scope:** exhaustive test of the app using Dad's (Dad) real resume/data — VP-level
Health Informatics, Cincinnati + remote-favoring — focused on the four goals you set:
(1) reach as close to **all relevant employers/jobs** as possible, (2) work for **any field** (agnostic),
(3) **easy setup** for a non-technical user, (4) a real way to **measure reach**.

**Method:** live measurement of Dad's actual reach across every source; a 44-agent adversarial review
workflow (2.4 M tokens) over the whole codebase with per-finding verification; two web-research passes
(competitor tools + free data sources). Then I fixed the highest-value issues, kept the suite green
(**949 passed**, was 923), and committed each locally. **Push is HELD** per your standing gate.

Companion files: `brain/review-2026-07-01-findings.txt` (all 38 verified findings), `brain/overnight-changes-2026-07-01.md`
(commit-by-commit changelog).

---

## 1. Headline: the reach problem was real, and mostly free to fix

Dad's search **as configured tonight** reached **18 jobs / 10 companies** total — for a 20-year VP.
The only source producing anything was the ToS-gray LinkedIn guest endpoint (10); Adzuna returned **0**;
every tech remote board returned 0; the careers/registry path returned 0 relevant.

The root cause was **not** missing sources — it was two things:

| Lever                                                                                                                                                                       | Before           | After (measured)                                                             | Cost |
| --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------- | ---------------------------------------------------------------------------- | ---- |
| **Keyword strategy** — the app searched on Dad's exact target _titles_ ("VP Clinical Informatics", "Chief Medical Information Officer"). Job APIs phrase-match → ~0 recall. | 18 jobs / 10 cos | **361 jobs / 104 cos (20×)**, 87% health-relevant, same 4 sources            | free |
| **Two free sources hardcoded to "engineering"** (The Muse, Jobicy) → 0 for any non-eng field.                                                                               | Muse 0           | **Muse 25+** for Dad                                                         | free |
| **Health company registry leaned on weak `direct` scrapers** — ~26 health-IT cos existed but ~18 are Workday/custom portals the direct scraper can't read.                  | ~5 careers jobs  | **+28 API-backed health boards** (~1,900 live jobs); careers 5→8 and growing | free |

**Real end-to-end daily run for Dad after the fixes:** Adzuna 0→**70**, The Muse 0→**32**, USAJobs 21,
HN 18, Himalayas 7, careers 5→8 → **154 raw → 139 deduped → 47 after the preference gate → 5 into the
inbox (≥40)**. Reach is now genuinely broad; the remaining bottleneck moved to **scoring** (only 5 of 47
relevant jobs cleared the score-40 inbox threshold), which is why I also fixed the ranking (below).

**Takeaway:** the architecture is sound. The app just wasn't _searching_ the way job boards want to be
searched, and two sources were needlessly field-locked. Both are fixed.

---

## 2. What I changed tonight (all committed locally, tests green, Alex byte-identical)

See `overnight-changes-2026-07-01.md` for the commit list. In priority order:

1. **Broad-query keyword strategy** (`search/keyword_strategy.py`) — search broad field terms, score on the
   real target roles. The single biggest lever (20×). No-op for your engineering IC titles.
2. **Industry-driven Muse/Jobicy** (`search/source_taxonomy.py`) — unlocks two free non-eng sources.
3. **Target-level (seniority) fit in the scorer** — an exec seeker's VP/Director/CMIO roles now rank above
   clearly-junior keyword matches. Engages only for management+ targets → your searches unchanged.
4. **28 probe-verified health employers** seeded into the registry (~1,900 live jobs).
5. **Bug fixes:** URL-less dedup no longer silently merges distinct-city postings; Jobicy no longer burns
   ~2 min for 0 results; scheduled runs now capture their console so a broken source ≠ an empty one.
6. **Agnostic/measurement:** non-eng resume skill-heading aliases; `registry_stats()` + a preflight warning
   when your field has <10 employers in the registry; field-neutral Guide copy; a wizard tip that stops a
   user from re-creating the narrow-keyword regression.

---

## 3. The review: 38 verified findings (7 critical, 21 major)

Full list with file:line, impact, and fix in `brain/review-2026-07-01-findings.txt`. Grouped:

**Reach (fixed / partially):** Muse/Jobicy eng-lock ✅; narrow keywords ✅; GUI paging 1→2 ✅.
Still open: jooble/careerjet are single-page and excluded from the scheduled run (#9/#10 — and you'd need
the free keys); live per-run discovery targets only 5 startup ATS platforms, never the enterprise ATS
(iCIMS/Taleo/Workday) where health systems live (#12); the `direct` scraper only matches anchor text so
JS career portals silently return 0 (#30).

**Scoring (fixed the core):** the deterministic scorer had **no** seniority awareness — session-22's exec
logic only fed the optional "Ask AI to rank" path, not the score you see ✅ now added. Still open and left
for your eyeball because it perturbs _your_ engineering scores: `_title_score`'s lenient partial-credit
disagrees with the strict title-miss penalty, so title phrasing can swing ~70 of 100 points (#4/#33).

**Agnostic:** Muse/Jobicy ✅, skill-heading aliases ✅. Open: `DEFAULT_KEYWORDS` (all engineering) is the
silent fallback in 4 code paths when a project has no keywords — a non-eng project created via the People/
Project button (not the full wizard) silently searches for engineers (#19/#21); `DAILY_SOURCES` includes
eng-only remote boards with no per-project override (#20).

**Setup UX:** only Anthropic/SerpAPI have in-app key entry — Adzuna/USAJobs/Jooble/Careerjet are env-only
and undocumented (README is a one-line stub), and scheduling is CLI-only (#1/#6/#23/#34). This is the
biggest remaining gap for a _non-technical_ user (Dad) and is GUI work that needs your eyeball.

**Measurement:** the capture-recapture math (company- and job-level) is correctly implemented but
disconnected — `run_benchmark` has zero callers, `company_coverage.py` needs a hand-sourced list, nothing
is surfaced in the GUI (#7/#25/#26/#27/#38). I added the `registry_stats()` backend + preflight warning;
the dashboard tab is the recommended next step.

---

## 4. Competitor scan — features worth adding (full detail in the report body)

Key strategic point: **JobScout's ATS-API + registry architecture is the correct and only legitimate
reach mechanism** — the giants (LinkedIn/Indeed/JobRight) get breadth by being _inside_ the ATS as a
syndication target, which a local app can't and shouldn't replicate (LinkedIn is closed/litigious; JobSpy's
GraphQL/JA3-spoofing is exactly what NOT to adopt). JobScout already out-covers Teal/Huntr/Careerflow
(which have no scraper at all — just a "clip this job" button). The real gaps are enrichment + UX:

Highest-ROI, on tools you already have keys for:

1. **Adzuna `Top Companies` endpoint** → free per-search company discovery to auto-grow the registry (S).
2. **Adzuna `Jobsworth` salary predictor** → estimate comp on _any_ posting with a missing salary (S).
3. **Common Crawl / jobhive (MIT, 86 K cos) slug harvest** → kill hand-curation of the registry (M).
4. **Browser-extension autofill** (Simplify/Teal pattern: human-triggered, manual submit) — the field's
   actual killer feature, at low ToS risk (L).
5. **LLM/semantic match score** (Huntr caps keyword weight <20% to prevent keyword-stuffing) (M).
6. **TF-IDF cross-source dedup + ghost-job/stale-listing filter** — turns aggregation into a quality edge (S).
7. **Enterprise-ATS parsers** (Workday/iCIMS/Taleo) — where non-tech, remote, healthcare jobs live (M-L).
8. **ATS-specific resume format advice** — JobScout already knows each job's ATS; Teal/Huntr can't do this (S).

Auto-apply posture: build "fill this page I opened," never unattended cloud auto-submit — Workday shipped
"Fraudulent Application Detection" (Mar 2026) that silently discards high-velocity automated applicants.

---

## 5. Getting to "as close to ALL companies as possible" (the registry acquisition plan)

Free + legal, ranked by impact/effort (full sourcing in the data-source research):

- **Tier 0 (today):** the 28 health boards I seeded + hand-add Becker's top-100 health systems and ~50
  major payers (Fortune-500 scale → resolve to Workday/SuccessFactors instantly).
- **Tier 1 (agnostic engine):** Common Crawl CDX harvest against the ATS domains (greenhouse/lever/ashby/
  workday/…) — 85–95 K company slugs, owned outright; adopt the **jobhive** MIT `name,slug,url` schema
  (86 K cos) as the import format. `discover/cc_harvest.py` + `seed_companies.py` already exist for this.
- **Tier 2 (health names → probe-verify gate):** CMS Hospital General Info (~5,300), **ONC CHPL** (the
  definitive free health-IT vendor list), NPPES bulk (taxonomy-filtered), HIFLD, HRSA FQHCs. All
  public-domain; they give names, the app resolves the board.
- **Tier 3:** USAJobs occupational series 2210/0669/0670/0671 for federal health-IT (bypasses ATS scraping).

---

## 6. Measuring reach (goal 4)

The pieces exist but aren't wired. Recommended **Reach dashboard** (mostly existing plumbing):

1. **Registry panel** — `registry_stats()` per-field counts (added tonight) + last capture-recapture estimate.
2. **Per-source run history** — persist the per-source counts `SearchEngine` already prints to a JSONL, show
   a "jobs per source per run" table (dead source detection).
3. **Coverage %** — wire `coverage/benchmark.py` (job-level, BLS-JOLTS-gated) + `registry_coverage.py`
   (company-level) so the user gets a real "you're seeing ~X% of the reachable universe, ~Y employers unseen."

---

## 7. What needs you (tomorrow)

1. **Eyeball `py gui.py`** — the wizard tip + Guide copy, and confirm nothing broke.
2. **Decide on push** — 7 commits held on `master`. All tests green.
3. **Run a bulk registry seed** when you want real breadth (jobhive dataset → `seed_companies.py`; and the
   CMS/ONC health lists). I seeded 28 health boards as a starting point + proof.
4. **Free keys** — grab Jooble + Careerjet free keys (2 min each) for more non-tech breadth; add to `.env`.
5. **Decide** on the bigger builds: in-app key panel, Reach dashboard, browser autofill, enterprise-ATS.
6. Dad's project config still has narrow exec keywords — that's now fine (the app broadens at query time),
   but you may want to eyeball his inbox and tune his target list (note: CMIO is a _physician_ exec role,
   which may not fit his non-MD analytics-leader profile — worth a look).

Nothing here is fleet-safety code; everything is additive and reversible.
