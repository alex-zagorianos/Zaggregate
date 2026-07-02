# General-User Test — Sofia Alvarez (Digital Marketing, Remote-Only)

**Date:** 2026-07-02
**Tester:** Opus subagent playing the persona end-to-end (blank slate; only what ships to a general user + the free-key signups the Guide prescribes).
**Project:** `projects/gu-marketing-remote/` (slug `gu-marketing-remote`, name "GU - Sofia Alvarez") — kept.

## Persona

7 yrs digital marketing, managed $2M ad budgets and a team of 3. Lives in Whitefish, MT,
**remote-only, will not relocate**. Targets: marketing manager / digital marketing manager /
growth marketing manager / demand generation manager. Location: Remote (US). Salary floor
$90,000. Level mid-senior.

## Keys context (disclosure)

`.env` has **Adzuna + JSearch + USAJobs** keys (treat as "user did the Guide's free signups").
**Not keyed:** CareerOneStop (known gap), plus **Jooble, Careerjet, Brave (discovery), SerpApi
(reach probe)** — my config enabled jooble/careerjet but they need keys not present, so they
skipped. No 429 / quota events occurred; every "skipped" line was a missing-key notice, not a failure.

---

## 1. New-user lens — wizard & Guide

**Wizard (`ui/setup_wizard.py`): 5 steps** — Welcome → (1) Roles + optional field/level + free-text
"Anything else?" → (2) Where + remote checkbox + salary → (3) Resume paste/load → (4) "Keep jobs
coming" (daily updates + build-my-list). Progress reads "Step N of 4". Salary accepts annual OR
hourly. Resume paste is auto-structured into `## ` headings so it can't crash scoring later.

**Wizard clarity: 8/10.** Plain-English, well-sequenced, remote is a first-class checkbox, and the
"Anything else?" box (the highest-leverage field) is explained. Two dings, both real for THIS persona:

- The **Location** step offers "Remote" as an example but there's no explicit "remote-only" toggle —
  a remote-only user types "Remote" as their city and ticks "remote jobs fine too", which is
  slightly awkward and (see §4) makes the geocoded aggregators return nothing.
- The optional **field/industry** box silently drives a lot (source routing, synonyms, company
  filter). A marketing user who leaves it blank gets auto-assigned an O*NET occupation (see bugs).

**Guide (`ui/help.py`): excellent, 9/10.** The "Set up your sources — the 10 minutes that matters
most" section is honest ("free feeds lean toward remote tech jobs"), names Adzuna + CareerOneStop as
the two keys that matter, and has a dedicated **ask-your-own-AI employer-list** flow with a
copy-paste prompt — exactly the seeding path this test exercised. The privacy/BYO-AI story is clear.

## 2. Project setup

Created programmatically via `workspace.create_project(name="GU - Sofia Alvarez",
slug="gu-marketing-remote", config=..., make_active=False)`, then wrote `config.json`,
`preferences.json` (hard filters: $90k floor, locations [Remote, Whitefish MT], remote_ok,
dealbreakers on-site/relocation, seniority_exclude intern/entry/junior, employment_types full-time,
fit_preference remote-only), `preferences.md` (natural-language profile), and `experience.md`
(structured resume — parser reads it clean, contact name resolved, 2648-char corpus). All shapes
round-trip through the app's own `preferences.load()` / `workspace.load_config()` / resume parser.

`create_project` auto-attached `onet_soc_code: 11-2011.00 / "Advertising and Promotions Managers"`
to the config — confirming the wizard path lands a marketing user on the _advertising_ O*NET code.

**Config note (deliberate, in-project):** I set `industry: "digital marketing"` (what a user types
in the field box) so my seeded companies are visible to the careers path, and `broaden_keywords:
false` to suppress a synonym-pollution bug (see §Bugs). A naive user who leaves industry blank or
types "digital marketing" hits both traps; a savvy user/AI works around them exactly as I did.

## 3. Seeding — ask-your-own-AI flow

As Sofia's AI, produced 15 "Name | ATS URL" lines for remote-first marketing-hiring companies and
pushed them through the **real GUI pipeline**: `ats_detect.parse_line` → `ats_detect.probe_count` →
`company_registry.save_companies` (the same three functions the "+ Add Companies" dialog calls).

| Metric                             | Count                                                                                                                   |
| ---------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| Attempted (non-comment lines)      | 15                                                                                                                      |
| Parsed to CompanyEntry             | 15                                                                                                                      |
| Probed **live** (job count)        | 6 — GitLab (141), Remote.com (294), Vercel (65), Webflow (24), Toptal (16), Doximity (11)                               |
| Parsed as **direct** (uncountable) | 3 — HubSpot, Buffer, Grammarly (I gave marketing-landing-page URLs, not ATS slugs)                                      |
| Probed **unreachable** (404)       | 6 — Zapier, Automattic, Sourcegraph, Deel, Clipboard Health, 1Password (all off those exact Greenhouse/Lever slugs now) |
| **Saved to companies.json**        | **13**                                                                                                                  |
| Skipped (already present)          | 2 (Doximity was in the shipped health registry; one dup)                                                                |

`save_companies` adds every parsed entry regardless of probe result (probe is advisory in the GUI),
so 13 landed even though only 6 verified live. The flow worked exactly as designed: my imperfect
AI-suggested slugs got flagged live (404 / uncountable) and the good ones (GitLab, Vercel, Webflow)
went on to produce this run's **top 4 inbox rows**. `companies.json` is shared and will be restored
by the janitor — I did not restore it.

## 4. Run

`py -3.12 daily_run.py --project gu-marketing-remote` — **exit 0, 27 s wall-clock.**

**Funnel (final full pass):**

- **76 raw → 41 dedup** (page-2 paging added +1 raw)
- **hard-gate 41 → 17** (dropped: **location 22**, employment_type 2)
- **scored ≥40: 8 of 17**
- **8 new → inbox** (inbox now 8)

**Source mix (this run's contributors):**

| Source                                                                | Results |
| --------------------------------------------------------------------- | ------- |
| WeWorkRemotely                                                        | 37      |
| RemoteOK                                                              | 17      |
| careers (my seeded cos: GitLab 3, Vercel 3+1, Webflow 1)              | 8       |
| Himalayas                                                             | 8       |
| HN "who is hiring"                                                    | 3       |
| The Muse                                                              | 2       |
| Working Nomads                                                        | 1       |
| **Adzuna**                                                            | **0**   |
| USAJobs, Jobicy, Remotive, Careerjet, Jooble, HigherEdJobs, RNJobSite | 0       |

**No errors, no traceback, no 429/quota.** Warnings were all missing-key notices
(BRAVE_SEARCH / JOOBLE / CAREERJET / — and CareerOneStop unkeyed).

**Headline finding:** For a **remote-only** search (`location=Remote`), **Adzuna — the Guide's #1
"biggest unlock" — returned 0**, and every geocoded/keyed aggregator (USAJobs too) returned 0. The
entire harvest came from the remote-native boards (WWR/RemoteOK/Himalayas) plus the seeded careers
pages. The location hard-gate then dropped 22 of 41 (postings that stated a real non-remote city).
Net: a remote marketer's supply on this app is thin — **8 inboxed**.

**Reach badge:** "cannot certify a coverage % — no cross-source overlap … 76 raw → 41 distinct from
7 independent source families (sample completeness ~46% by Good-Turing)." Honest, but it can't size
the universe because (a) no SerpApi key for the overlap probe and (b) the families are near-disjoint
for remote marketing.

## 5. Inbox analysis (BYO-AI re-rank)

Total inbox = **8** (this IS the "top 40" — the whole inbox). Locality: **0 in-area MT, 8 remote,
0 wrong-location** (location gate did its job). Local-score dist: 4 in 60–79, 4 in 40–59, mean 55.9.
Source mix of inbox: weworkremotely 4, careers 3 (all GitLab), workingnomads 1.

### BYO-AI Top 10 (only 8 available)

| #   | Title                                   | Company         | Location                      | Source         | Score | Fit rationale                                                                                          |
| --- | --------------------------------------- | --------------- | ----------------------------- | -------------- | ----- | ------------------------------------------------------------------------------------------------------ |
| 1   | Staff Lifecycle Marketing Manager       | GitLab          | Remote, US                    | careers        | 79    | Bullseye: lifecycle mktg mgmt, remote-US, top remote-first co, staff-level clears $90k.                |
| 2   | Lead Global Marketing Campaigns Manager | GitLab          | Remote, US                    | careers        | 66    | Senior campaigns manager, remote-US, exactly her wheelhouse.                                           |
| 3   | Ecommerce Lifecycle Manager             | North Spore LLC | Remote/in-person, Portland ME | weworkremotely | 43    | Real DTC lifecycle/email/retention role — her exact skillset; remote OK. Underscored by keyword model. |
| 4   | SaaS Project/Marketing Manager          | BlueBox         | Remote (UK hours)             | weworkremotely | 65    | Marketing+PM blend, but **$1,500/mo (~$18k) and UK hours** — take only if desperate. FALSE-comp.       |
| 5   | Senior Google Ads Account Manager       | StubGroup       | Remote (LatAm/EU/CA/UK/ZA)    | workingnomads  | 41    | Google Ads is her skill, but **explicitly excludes the US** and $48–60k. Geo+comp fail.                |
| 6   | Technical Partnerships Manager          | Origami Risk    | Remote, US                    | weworkremotely | 44    | Remote-US ✓ $140k ✓ but a **partnerships/revenue** role, not marketing. Adjacent.                      |
| 7   | Senior Regional Marketing Manager, EMEA | GitLab          | Remote, EMEA                  | careers        | 66    | Right title/company but **EMEA-only** — wrong region for a US-remote candidate.                        |
| 8   | Manager, Product Design                 | BrowserStack    | Remote (Mumbai HQ)            | weworkremotely | 43    | **Product Design**, not marketing at all. Pure title-word ("Manager") match.                           |

(9–10: none — inbox exhausted at 8.)

### False positives in the top 40 (of 8): **4**

- **GitLab EMEA (#7, score 66):** title+company perfect, but region is EMEA-only. Scored high because
  scorer rewards "marketing manager" + "remote" and doesn't parse "EMEA" as excluding a US candidate.
- **BlueBox (#4, score 65):** ~$18k/yr, UK-hours contract. Passed the $90k hard-gate because
  `salary_from_text("$18,000+")` → `(None,None)` (the "+" band with no upper bound doesn't parse), so
  "unknown salary → kept". The real comp lives only in the description, which the gate doesn't read.
- **StubGroup (#5, 41):** explicitly non-US remote + $48–60k. Title had "Manager"+"Remote".
- **BrowserStack (#8, 43):** Product Design management, zero marketing. Pure "Manager"+"remote" match.

**Local scorer quality:** decent at the top (the two GitLab US roles surfaced at 79/66 via the seed),
weak in the tail — it over-weights the word "Manager" and the token "remote" and under-weights
(a) region qualifiers inside a remote string (EMEA/LatAm-only) and (b) obviously-sub-floor comp that
only appears in the description. For 8 rows a human/AI re-rank is trivial; the scorer's ranking was
"good enough to not miss the winner" but produced a 50% false-positive rate in the tail.

## 6. Tracking to completion

Drove 5 jobs through the lifecycle with the **same functions the GUI buttons call**
(`service.track_job` → `db.inbox_track`; `db.update_job`; `db.add_interview_round`;
`db.add_status_note`). Re-read the DB independently — **everything persisted:**

- **All 5 → applied** (date_applied auto-stamped 2026-07-02, +7-day follow-up auto-armed 2026-07-09
  on first entry to `applied` — nice touch, fires on every path into applied).
- **2 → interview** with rounds: app 1 (GitLab Staff Lifecycle) got 2 rounds (phone + technical),
  app 2 (GitLab Campaigns) got 1 (phone). `interview_rounds` rows verified.
- **1 → offer → accepted** (app 1): offer_amount `$155,000`, offer_deadline `2026-07-25`,
  offer_notes persisted; accepted-note in status_history.
- **1 → rejected** (Origami Risk) + note.
- **1 → ghosted** (StubGroup) + note.
- `status_history` captured every MOVE and every NOTE-only event with UTC timestamps. Inbox correctly
  dropped the 5 promoted rows (8 → 3 left).

Final counts: 1 accepted / 1 interview / 1 applied / 1 rejected / 1 ghosted.

**Lifecycle gaps:** none blocking. The full status set (interested→applied→phone_screen→interview→
offer→accepted/rejected/withdrawn/ghosted), interview rounds, per-stage notes, and offer fields are
all reachable and persist correctly. Minor: `phone_screen` is a valid status but I jumped straight to
`interview` (both work). The API is clean and complete for a GUI user.

---

## Verdict (as Sofia)

**Could I run my whole search on this app?** _Partly._ The tracker is genuinely better than a
spreadsheet — one-click track, auto-stamped applied date + follow-up, interview rounds, offer fields,
ghosted status, full history. The seeding flow is powerful: my own AI's list of remote-first
employers produced my two best matches (the GitLab roles) that no free feed surfaced. And it's
private/local, which I like.

**But the supply is too thin for a remote-only marketer today.** One run gave me **8 jobs**, and half
the tail was noise (EMEA-only, $18k, Product Design). Adzuna — the source the Guide tells me matters
most — returned **zero** for a remote search, so I'm leaning almost entirely on WeWorkRemotely +
RemoteOK + whatever employers I personally seed. That's a real gap vs. just searching "remote
marketing manager" on LinkedIn, which would show me 100+ in one scroll (and Indeed more).

**Where it beats LinkedIn/Indeed:** the career-page seeding (I watch GitLab/Vercel/Webflow directly,
day-one of a posting) and the tracker/lifecycle. Where it loses: raw volume and recency for remote
knowledge-work, because the big-board feeds (LinkedIn/Indeed) are exactly the ones the app can't
query, and its keyed aggregator (Adzuna) whiffs on "Remote".

**Single biggest improvement for THIS persona:** make **remote-only search actually productive** —
(a) when `location=="Remote"`, route the keyed aggregators (Adzuna/CareerOneStop) with their
remote/`what_only` parameters instead of geocoding "Remote" to nothing, and (b) lean harder on the
remote-native boards' pagination. Secondary: teach the scorer to penalize region-locked remotes
(EMEA/LatAm-only) and sub-floor comp found in the description. Would I stay? Yes for the tracker + as
a _complement_ — not yet as my only tool.

## Bugs / findings (with evidence)

1. **Adzuna returns 0 for `location=Remote`.** Guide's #1 recommended key produced nothing for a
   remote-only search; USAJobs also 0. Not a crash — a coverage gap that guts the value prop for
   remote knowledge-workers. (`[AdzunaClient] 0 results` both passes.)
2. **Industry-synonym pollution for marketing.** `industry_profile.resolve("digital marketing")`
   has no marketing profile and falls back to **health-informatics defaults**, so
   `broad_query_keywords(..., "digital marketing")` injects
   `['clinical informatics','healthcare analytics','health data','electronic health record','epic']`
   into a marketing query. A naive user who types "digital marketing" gets healthcare noise in their
   search. Worked around with `broaden_keywords:false`.
3. **`demand generation manager` mis-resolves in O\*NET** to `"Hydroelectric Production Managers"`
   (`industry_profile.resolve_soc("demand generation manager")` → 11-3051.06). Comical but harmless
   here since I didn't let it set the industry; would mislead a user who leaned on auto-detect.
4. **Industry tag vs. wizard-derived industry don't match, silently zeroing the careers path.** The
   wizard derives `industry="Advertising and Promotions Managers"` for a marketing user, but seeded
   companies get tagged `digital_marketing`. `industry_company_count("Advertising and Promotions
Managers") == 0` while `== 13` for "digital marketing" — so a user who finishes the wizard normally
   would seed 13 employers and then **the daily run wouldn't scrape any of them** because the industry
   strings don't tag-match. This is the most impactful silent trap. (`_industry_tag_match("digital
marketing","digital_marketing")` is even False; only the containment path in `get_registry` saves it.)
5. **Sub-floor salary in the description slips the hard-gate.** BlueBox's real comp is
   "US$1,500 per Month" (~$18k) but its `salary_text` field is "$18,000+", which
   `salary_from_text` parses to `(None,None)` → "unknown → kept". The gate never reads the
   description, so a clearly sub-$90k role passed a $90k floor and scored 65.

**Setup friction:** enabling Jooble/Careerjet in config but having no keys (silent skip); CareerOneStop
unkeyed (the Guide's #2 key) so the DOL/NLx feed — best for non-tech local jobs — was absent;
the industry/tag mismatch above required manual reasoning to make seeding pay off.
