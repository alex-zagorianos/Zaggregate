# Overnight autonomous review + fixes — 2026-07-01

Context: Alex asked for an exhaustive test of the app using his dad's (Dad, VP Health
Informatics, Cincinnati + remote) resume/data, focused on COMPANY/JOB REACH ("as close to ALL
as possible"), agnostic use, easier setup, and measuring reach. Ran on Opus (ultracode). Full
test suite was green at start (923 passed, 2 skipped). Everything below is config-gated /
backward-compatible; Alex's engineering flow stays byte-identical. Push HELD (standing gate).

See also: `brain/review-2026-07-01-findings.txt` (38 verified findings from a 44-agent adversarial
review workflow) and the scratchpad `measured_findings.md` (live before/after reach numbers).

## Headline measured result

- Dad's CURRENT config (8 narrow exec-title keywords) reaches **18 jobs / 10 companies** — only the
  ToS-gray LinkedIn guest endpoint produced anything; Adzuna returned 0; the registry path returned 0.
- Same 4 sources with **broad FIELD keywords → 361 jobs / 104 companies (20×), 87% health-relevant**.
- Root cause = keyword strategy: the app searches on the user's exact _target titles_; APIs phrase-match
  → ~0 recall. Fix = search broad, rank by seniority.

## Changes made this session (committed locally; push HELD)

Full suite **949 passed, 3 skipped** (was 923). Alex's engineering flow verified byte-identical
(every new behavior no-ops for eng/IC/empty-industry profiles).

1. `f8c87b3` feat(reach): **industry-driven Muse/Jobicy category** (`search/source_taxonomy.py`). The
   Muse/Jobicy were hardcoded to the engineering slice server-side (0 for any non-eng seeker); now derived
   from the project `industry`, eng-default byte-identical. Verified: dad Muse 0→25. (#5/#8/#18)
2. `c92c960` feat(reach): **broad-query keyword strategy** (`search/keyword_strategy.py`). Search broad
   FIELD terms (de-seniorized roles + industry), score on the original target roles. Wired cli/daily/gui;
   GUI paging 1→2. No-op for eng IC titles. **Measured 18→361 jobs (20×).** (#24/#29/#31)
3. `43e9d10` feat(scoring): **target-level (seniority) fit** in the deterministic scorer — engages only for
   management+ targets, so IC/eng byte-identical; fixes the measured ranking inversion. (#3/#16/#32)
4. `618c79d` fix(bugs): **URL-less dedup keeps distinct locations** (#14); **Jobicy skips** unserved fields
   (was ~121 s for 0 results in dad's run).
5. `5c310ad` feat(agnostic+measurement): **skill-heading aliases** (#17); **registry_stats()** + daily_run
   preflight NOTE when <10 companies match the field (#28); **scheduled-run log capture** (#2).
6. `ece4ce7` fix(ux): field-neutral Guide copy (#35) + wizard tip against narrow senior-title phrases (#24).
7. `b42a7e1` feat(reach): **seeded 28 probe-verified health-tech employer boards** into the registry
   (~1,900 live jobs; Lyra/Oscar/Included/Headway/Commure/Cohere/Aledade/Ro/…). Careers path for dad 5→8
   (and now backed by 36 API-scrapeable health boards that grow over time). `data_templates/health_employers_seed.json`.

Correction to an early note: the registry was NOT empty for health — it ships ~26 curated health-IT cos,
but ~18 are `direct`-type (Workday/custom) the direct scraper reads poorly, so effective health reach was
~8 API-backed boards. The seed adds 28 more API-backed boards.

## Recommended, NOT done tonight (need your eyeball / a decision) — see REVIEW-REPORT-2026-07-01.md

- In-app job-source **API-key panel** (#1/#6) + "Connect job sources" — GUI, needs eyeball.
- **Reach dashboard** tab composing registry_stats + per-source run history + capture-recapture (#7/#38/#25/#27).
- **Scheduling from the GUI** (#23); README real setup section (#34).
- **DEFAULT_KEYWORDS eng-fallback** should fail-loud for a configured non-eng project (#19/#21).
- **jooble/careerjet**: get the free keys, add paging + daily opt-in (#9/#10).
- **Enterprise-ATS live discovery** (iCIMS/Taleo/Workday) + convert the `direct`-Workday health entries to
  proper `workday` slugs so they scrape (#12/#30).
- **title_hit/miss penalty refactor** (#4/#33) — left alone because it perturbs Alex's eng scores; your call.
- Bulk registry seed from the **jobhive** MIT dataset + CMS/ONC-CHPL health lists (data-op; see report).
