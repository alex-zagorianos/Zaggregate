# Orchestrator review — 8-persona general-user night (2026-07-02, Fable 5)

Written by the orchestrating session between the persona phase and the lens/research
phase; independent of the lens agents' reports. Corpus: `persona-*.md` +
`_structured-results.json` in this folder.

## The headline

All 8 personas completed the full journey (setup → seed → run → top-10 → tracked
lifecycle to completion) with zero crashes and zero failed runs. Verdicts clustered
6–7/10, all eight "would stay", 7/8 "beats manual" — the exception is the
remote-only persona. The app IS general-user viable today, but it is carried by
one keyed source and a scoring layer with systematic blind spots that only the
BYO-AI re-rank corrects.

## Cross-persona systemic findings (my ranking by blast radius)

1. **Industry-tag space/underscore mismatch (`scrape/company_registry.py`,
   `get_registry`/`_industry_tag_match`)** — multi-word industry values never match,
   silently zeroing the entire careers/registry path. Hit warehouse-memphis,
   mecheng-seattle, data-changer-phoenix outright (careers ≈ 0–1); consultant's
   careers=0 is likely the same. This one bug converts "620-board registry + your
   verified seeds" into "Adzuna only" for most multi-word fields. Worst defect of
   the night; trivially fixable; must be P0.
2. **Adzuna is a single point of failure for local coverage.** Source-mix across
   personas: warehouse 53/53 Adzuna, consultant 187/196, teacher 36/49, nurse 22/29,
   data-changer 66/77. With no key (true out-of-box) most of these inboxes would be
   near-empty. The Guide already says this; the app doesn't enforce/nudge it.
3. **Remote-only is broken on the keyed aggregators**: Adzuna and USAJobs return 0
   for location='Remote'. The remote-only marketer got 8 inbox rows and was the only
   beats_manual=False. Remote users currently live off WWR/RemoteOK/Himalayas alone.
4. **Probe is advisory in + Add Companies** (`save_companies` writes every parsed
   line). All 8 personas flagged it. Combined with (5), seeding quality is luck.
5. **AI slug-guessing is a coin-flip** — the strongest evidence yet for Seed-My-Area
   Leg B (CareerOneStop Business Finder / verified directories) over pure
   ask-your-AI: SWE persona got 5/13 real-company slugs wrong; nurse got 0/14 live
   (hospital "direct" pages unprobeable); marquee employers (FedEx, Nike, Banner,
   Dignity, ASU) sit behind Workday/CSRF where the scraper can't follow. The flow
   _worked as designed_ — junk failed harmlessly — but design ≠ payoff: seeds
   contributed almost nothing to any persona's top-10.
6. **Seniority-blind + country-blind scoring** — 'Sr.'/'III'/'8+ YOE' pass the
   'senior' word-boundary excludes (an SE III scored 100 = the #1 row in a new-grad
   inbox); any 'remote' string earns location 100% with no work-auth country check
   (Czech/UK/Canada-only rows outranked Austin). Entry-level configs don't downrank
   senior titles at all. The BYO-AI fixed all of it — a no-AI user gets misled.
7. **Taxonomy holes**: 'nursing' unresolved to SOC; 'digital marketing' falls through
   (one title → "Hydroelectric Production Manager"); no warehouse/logistics profile;
   'management consulting' no SOC. The wizard-derived industry strings are also the
   multi-word strings that trip bug (1) — the two compound.
8. **Location-label trust**: Adzuna stamps the query metro on postings; wrong_area
   rows leaked in for nurse (3) and teacher (3). Sub-floor salary in description
   text slipped a $90k hard gate ($1,500/month role).
9. **`daily_run --project X` flips the GLOBAL active project** (set_active ~line 218)
   — confirmed live: after the phase the registry pointed at the last persona; I
   restored test-controls. The S27 pin protects the process, not the registry.
10. **Silent-zero UX**: unkeyed sources (CareerOneStop, Jooble, Careerjet) self-skip
    with only log lines. Every persona independently called out that the Guide's #1
    recommended source contributes nothing and the user is never told in-app.
11. **Tracker minors**: `apply_rerank_scores` writes fit but not rank/rec_batch (so
    top_picks comes back empty after a re-rank import — B3); `update_job` silently
    ignores unknown fields (B4); phone_screen is both a status and a round kind;
    status-note stored as self-transition noise.

## The setup-ease answer (Alex's direct question)

Measured: 18–40 min to full setup (median ~18), wizard clarity 8–9/10. The honest
statement: a general user reaches a _working_ inbox in ~20 minutes **if** they have
the Adzuna key; without any keys, only remote/tech personas get anything. Nothing
in-app surfaces that cliff — it's the difference between "works out of the box" and
"works after one free signup nobody is forced to notice." Time-to-first-value is
gated on key acquisition + industry-string luck (bugs 1/7), not on UI complexity.

## What the night validated

- S27/S29/S30 lifecycle work held: 8/8 personas completed apply→interview→offer/
  rejected/ghosted with clean persistence; date_applied + follow-up auto-stamps work.
- The funnel and caps behaved at every scale (76 → 2,230 raw).
- Sequential same-registry testing with snapshot/restore janitors worked; registry
  byte-identical after all 8.
- The consulting taxonomy added in S30 routed correctly (196 inboxed) — but ranking
  precision, not recall, is consulting's problem (engagement-manager ambiguity).

## Process notes (for the morning read)

- Zero agent failures across 16 persona-phase agents (~1.93M tokens, ~110 min).
- Persona projects `gu-*` (8) are KEPT under projects/ for browsing; registry active
  restored to test-controls; companies.json restored byte-exact.
- Keys context: Adzuna/JSearch/USAJobs keyed (simulating Guide-following user);
  CareerOneStop deliberately left unkeyed (it has no key on this machine) — its
  absence became a finding in itself, consistently.
