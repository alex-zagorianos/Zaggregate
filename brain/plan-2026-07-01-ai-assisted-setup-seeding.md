# Plan — AI-assisted setup & local-area seeding ("Seed My Area")

> **STATUS 2026-07-02: BUILT in Session 32** (was HELD 2026-07-01). Shipped as SB-1/SB-2/SB-3 of the
> general-user improvement plan:
>
> - **Leg A — BUILT, re-scoped** to careers-URL-only prompts (per the AI-slug coin-flip evidence):
>   BYO-AI "set me up with my AI" module + URL-only seed prompts + MCP `seed_companies` tool
>   (`ed3371b` → merge `3f0a1fa`). The industry-tag + probe pipeline it feeds is P0-1/P0-6-fixed.
> - **Leg B — BUILT, KEY-GATED**: CareerOneStop Business Finder client + `seed_my_metro` pipeline +
>   Tools ▸ "Seed my area…" dialog (`e2b1238`/`05c37bb` → merge `6f87d00`). Endpoint provisional —
>   **awaits a CareerOneStop key**; drop one real Business Finder response at `COS_BF_FIXTURE` to
>   verify the mapping once keyed.
> - **Third leg — clip-to-seed (SB-3), BUILT**: a browser `/clip` receiver + `resolve_board`
>   verified-at-clip gate + extension v1.5 (`272e7ea`/`ce953f3` → merge `a52a4e7`) — the
>   competitor-proven mechanic that sidesteps the slug coin-flip entirely.
> - **Success-metric status:** a non-Cincinnati user now reaches a seeded, verified local registry
>   via one Tools-click **once the CareerOneStop key is added** (Leg B), or immediately via BYO-AI
>   URL seeding (Leg A) / browser clip (SB-3). The Workday `wday/cxs` resolver (SB-1) is the supply
>   side this plan called its "missing half" — also built.
>
> See `docs/handoffs/handoff_20260702_session32.md` + `brain/general-user-tests-2026-07/README.md`.
> Original held-plan text below is intact.

**Status: HELD (Alex, 2026-07-01) — noted for a future session. Pulled forward and
built same day: the SmartRecruiters fetcher + consulting taxonomy entry. The K-12
ATS (Frontline) was an illustrative example only — backlog, not committed work.**

## Why

Live blank-canvas test runs (2026-07-01, controls + dad-health) measured the source
mix: 85% / 58% of the two inboxes came from the `careers` company registry, ~14-37%
from Adzuna, ~1% from the keyless feeds. The registry ships with the app, but its
_local-employer_ layer is Cincinnati-shaped (hand-seeded health systems). A user in
another metro/field inherits the national startup layer but not their own local
employers — that gap is exactly what hand-seeding fixed for Dad (19-row inbox with
his hospitals in it), and what this plan productizes.

Design insight that makes it cheap: **the import half already exists.**
`scrape/ats_detect.detect_ats()` turns a pasted careers URL into `(ats_type, slug)`,
`probe_count()` live-verifies, and the Add Companies dialog accepts `Name | URL`
lines. Hallucinated employers fail the probe harmlessly. Only the _supply_ side
(where the employer list comes from) is missing.

## Leg A — BYO-AI hand-seeding (user's own $20 Claude/ChatGPT sub) — ~2-3 days

1. **"Seed my area" prompt generator** (mirror the ranker's clipboard bridge):
   build a prompt from the project's industry + metro — _"List the 25-40 largest
   employers of [K-12 teachers] in [Columbus, OH]. For each: name, website domain,
   careers-page URL if known. Return as `Name | URL` lines."_ User pastes into
   their own AI (web-search models return real careers URLs), pastes the reply back.
2. **Lenient reply parser** -> existing `parse_company_lines` -> probe queue with
   live progress -> honest report ("22 verified+added, 6 unreachable, 3 already
   registered"). Industry-tag every import so gating works.
3. **MCP tool twin** (`seed_companies`) so a Claude Code/Desktop user runs the loop
   conversationally (mcp_server.py + find-jobs skill already exist).
4. Failed-probe URLs fall back to the `direct` JSON-LD scraper instead of dropping.
5. Fold into onboarding: a wizard step ("Have an AI subscription? Let it build your
   local employer list") + Guide section. Marginal user cost: $0.

## Leg B — built-in company aggregator — ~2-4 days

1. **CareerOneStop Business Finder API** (free; SAME key as the job feed we already
   integrated): employers by area + industry code, names/websites -> same probe
   pipeline -> a zero-AI "Seed my metro" button. RECOMMENDED FIRST — one key
   unlocks the job feed AND the employer directory.
2. **TheirStack (paid, optional):** sells "companies in [metro] using [ATS]" —
   direct board seeding; already spec'd as an opt-in overlap sampler (Wave E).
   Evaluate cost first.
3. **Fallback enumerators:** Google Places / OpenStreetMap category queries
   (schools, hospitals, firms). Lower priority.

## Persona follow-ups

- **Teaching (K-12) [BACKLOG — illustrative example, per Alex]:** taxonomy split
  K-12 vs higher-ed (one `education` entry serves both; kindergarten teachers get
  professor-flavored routing). K-12 districts post on Frontline Education
  (AppliTrack)/SchoolSpring/TalentEd — a Frontline scraper would be the
  highest-value ATS add for this persona (districts enumerable per county,
  compounds with seeding).
- **Business consulting:** `consulting` taxonomy entry (triggers/synonyms/title
  credit; was falling through to the generic O*NET path). Big firms run
  SmartRecruiters/SuccessFactors/Taleo/Avature; `ats_detect` already detects+probes
  SmartRecruiters — **promoting it to a full fetcher is the cheapest wave-3 add.**
  [PULLED FORWARD — built 2026-07-01.] SuccessFactors/Taleo/Avature remain backlog.

## Build order (when resumed)

A1-A2 (clipboard seeding) -> B1 (CareerOneStop Business Finder) -> A3 (MCP tool)
-> B2/B3 as demand shows. Success metric: a non-Cincinnati test persona (e.g.
Denver nurse) reaches a seeded, verified local registry in <20 min without Alex.
