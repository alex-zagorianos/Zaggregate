# Beta Roadmap — what stands between Zaggregate and genuinely helping users (2026-07-05)

Alex's ask: what's needed to reach beta, grounded in data on what actually
gets people hired, compared against what the app does. Basis: 9 research
reports (success-factor evidence review incl. Ashby 38M-application / Gem
140M / Greenhouse 640M datasets; beta-readiness checklist; competitive
deep-dives on Huntr/Simplify/Careerflow/JobScan/LoopCV; platform privacy;
subscription dark patterns; LinkedIn ToS enforcement; US legal analysis;
market pain points). Confidence labels preserved; vendor numbers flagged.

## 0. THE REFRAME (most important finding)

**"Most jobs possible" is the wrong objective function.** The evidence
actively argues against raw application-count maximization (auto-apply bots:
0.4–6% response rates, platform bans, 19.6% of hiring managers auto-reject
spotted AI applications). The defensible levers for a TOOL are:

1. **Discovery breadth + freshness** (see everything, be early) — we excel.
2. **Referral/warm-path surfacing** — biggest per-application multiplier; we
   have almost nothing.
3. **Channel intelligence** (which sources convert) — nobody offers this
   per-user; we uniquely could (the data is already in our tracker).
4. **Cheap per-job tailoring** (measured lift 1.6x, real but modest) — have.
5. **Cadence/consistency support** (search intensity decays exactly when it
   shouldn't — solid academic finding) — partial (daily runs), no UX.
6. **Human approves every submission** — our founding stance, now
   data-validated. Market AGAINST auto-apply, never build it.

## 1. The funnel math (best-measured numbers)

- Cold application → offer ≈ **0.2%**; application → interview ~2–3%
  (Ashby, 38M applications). Applications per posting doubled 2022→2025
  (116→244, Greenhouse); a given applicant is ~3x less likely to be hired
  than 3 years ago (Gem).
- **Referred candidates: 40% reach interview** (vs 2–3% cold) — a 20–40x
  per-application advantage. BUT cold inbound still = **43–52% of ALL hires**
  (4-year high) — volume through the front door works, it's a numbers game
  with known odds. Both channels matter; referrals multiply, discovery feeds.
- **Channel spread is ~4x** (Huntr 600k jobs): Google Jobs 11.3%, government
  boards 8.7%, Wellfound 6.0%, Glassdoor 5.5%, Indeed 4.5%, LinkedIn 3.1%,
  ZipRecruiter 2.8% response. Career-page applications convert ~4x better
  than job-board ones (Gem) — our careers-registry emphasis is validated.
- Apply early (first 1–3 days): directionally real (shortlists form fast,
  first-week applications dominate); the "3.1x/6x within 48h" multipliers are
  vendor marketing.
- Tailoring: **1.6x** measured (5.8% vs 3.6%, 65k tailored vs 1M+ untailored,
  Huntr). Bigger claims are marketing. Title-match + key-skill mirroring +
  cover-letter-when-asked captures most of it.
- Cadence: ~10–20 quality applications/week; most offers land within 20–80
  total; intensity decays over the search (solid, NY-Fed/academic).
- Follow-ups: exactly ONE follow-up + the interview thank-you (91% of
  employers welcome it, half of candidates skip it); more backfires.
- Apply at ~60%+ requirements fit — requirements are wish lists (only 27% of
  applicants meet all; hiring proceeds anyway). The "women apply at 100%"
  stat failed a preregistered replication.
- **Debunked myths we should never build for**: "75% of resumes auto-rejected
  by ATS" (traces to a defunct 2012 vendor; 92% of recruiters say no
  auto-reject; ATSs rank, they don't secretly delete) and "70–80% of jobs are
  never posted" (1970s career-coach marketing; real kernel = referral+
  internal+sourced ≈ half of hires).
- Seeker pain: ghosting is the #1 complaint (71–79% ghosted; silence hurts
  more than rejection); 72% say the search damages mental health; ghost jobs
  are real (best studies: 1-in-7 to 1-in-3 listings; 93% of HR pros admit
  posting them).

## 2. Scorecard — Zaggregate vs the evidence + table stakes

DELIVERS TODAY (at or above the bar):

- **Discovery no competitor has**: ~20-source daily ingest + scoring. Huntr
  explicitly does NOT find jobs or alert; Teal/JobScan don't either. This is
  the headline differentiator and it targets lever #1.
- Ghost/stale/repost shielding (BUILT, under-marketed) — targets the #1
  seeker pain and the ghost-job tax directly.
- Tracking/kanban/rounds/.ics/follow-up nudges — table stakes met.
- BYO-AI tailoring + cover letters + DOCX + ATS skill-gap hint — table
  stakes met WITHOUT account/API-key/upload (competitors' AI is the #1
  quality complaint: hallucinated skills, fabricated employers — our
  human-in-loop flow avoids the trap).
- Channel emphasis on career pages (validated: ~4x conversion).
- **Privacy wedge, documented**: Incogni — 8 of 9 job platforms sell user
  data; Career.io/resume.io policies permit selling resume data; LinkedIn
  "BrowserGate" scans visitors for 6,236 extensions; Huntr's extension
  requests PII/financial/web-history permissions. We: local-only, zero
  telemetry, no account.
- **Price/dark-pattern wedge, documented**: Huntr $40/mo, JobScan ~$50/mo +
  trial→$90-quarterly trap + 2-day refund window, Simplify+ $39.99 w/ no
  refund policy (3.0 Trustpilot, 67% 1-star), ZipRecruiter BBB billing
  horrors. We: free, no card, nothing to cancel.
- Desktop app + web; 2,968-test suite; scoring transparency.

GAPS (ranked by outcome impact):

1. **Referral/warm-path assistance** — the 20–40x lever; we have a contacts
   field and nothing else. Networking hesitancy is a measured bottleneck
   (~70% believe network > resume but freeze on outreach).
2. **Channel-conversion analytics** — response rate by source from the
   user's OWN tracker data (+ the published benchmarks as context). Data
   already in tracker.db; no surface renders it. NOBODY offers per-user
   channel intelligence — differentiator.
3. **Cadence support** — weekly application target + streak/decay awareness
   (solid science; zero UX today).
4. **Follow-up/thank-you drafting** — nudges exist; add one-click BYO-AI
   draft (one follow-up + thank-you = cheap, capped, real).
5. **Interview prep** — nothing today; 44% of candidates use AI for prep;
   per-job BYO-AI prep prompt is cheap and on-pattern.
6. **Speed-to-apply signals** — posting-age urgency in Inbox + optional
   local Windows toast for high-fit new matches (daily runs exist; latency
   to user awareness is the gap).
7. **ATS form autofill** — the one true table-stake gap (Simplify free tier
   = the bar, 100+ ATSs, manual submit). Big build; extension-based;
   review-before-submit only. Post-beta candidate, or start with a "copy
   application pack" (formatted profile fields for fast manual fill).
8. Mobile — structural non-goal for a local-first desktop app; accept.
   (Email status detection: NOT table stakes — none of the six majors have
   it; a local-IMAP version would be uniquely on-brand but is post-beta.)

## 3. Beta blockers (checklist w/ costs)

1. **First-run success path.** Activation event = "first search returns
   scored results the user opens" (not wizard completion). Today: SmartScreen
   wall → keys → ~12-min first careers scrape. Fix: first-run quick-run
   default (max_pages=1, progressive fill), expectation copy, keys framed as
   post-first-value upgrades. Time-to-first-value target <15 min.
2. **Distribution trust.** Closed cohort: unsigned + winget manifest (free;
   no SmartScreen in CLI flow; PR to microsoft/winget-pkgs) + SHA-256 hashes
   - FIRST-RUN.txt (publish checksums with every release — future updater
     integrity + trust). Strangers-with-a-link: **Azure Trusted Signing
     $9.99/mo** (US-individual signup pause LIFTED per the 2026-06-22 FAQ;
     needs paid Azure sub; no instant reputation — same organic download-volume
     curve as any cert) or **Microsoft Store MSIX** (individual dev
     registration FREE since Sept 2025; Store re-signs → NO SmartScreen ever;
     MSIX packaging work). EV certs no longer buy instant reputation
     (post-2024) — don't bother. PyInstaller: --noupx, prefer one-dir (AV
     heuristics).
3. **Update check.** GitHub Releases API compare + "new version" toast =
   hours of work, matches beta expectations. tufup later if it sticks.
   (PyUpdater is dead.)
4. **Feedback loop.** Primary = in-app "Send feedback" (mailto / hosted
   form — job seekers are often non-technical; a GitHub account is a real
   barrier). GitHub Issues stays the INTERNAL tracker; Discord only if the
   cohort asks (silo risk). In-app "Report a problem" already builds a
   scrubbed local zip → wire it to the feedback path. Crash = Pachli
   pattern: local scrubbed crash_report.txt + a dialog where the user SEES
   the report before anything is sent. NO telemetry (privacy identity;
   measure via interviews, not tracking).
5. **Web create-project flow** (queued) — betas onboard on web/desktop.
6. **Legal/trust page** (~1 day): 5-line privacy policy ("nothing leaves
   your machine"; covers opt-in report path; REQUIRED for the extension's
   Chrome Web Store listing), EULA/as-is disclaimer, LICENSE. Scraping
   posture already conservative (user's own machine fetches; LinkedIn/Indeed
   only via user's own browser; ToS-gated sources; no auto-apply) — ToS
   should say users query sources on their own behalf; don't market
   "LinkedIn scraping". Precedent: JobSpy (3.8k stars) operates openly for
   years; enforcement (Proxycurl/Apollo/HeyReach) targets centralized
   commercial scrapers.
7. **Cohort recruiting**: helpful-comments pattern in r/jobs /
   r/jobsearchhacks / r/recruitinghell (privacy-hostile audience = our wedge
   users) + r/alphaandbetausers + **Show HN** (local-first/privacy/free/
   Python = HN catnip). 10–20 users, weekly interviews. Windows-only +
   technical install filters the cohort — winget converts that into a
   channel.

## 4. Build order

- **Wave 1 — beta blockers**: first-run quick-run + progressive results ·
  update check · GitHub feedback wiring · web create-project flow · privacy/
  EULA/LICENSE page · winget manifest + start signing/Store application
  (lead time).
- **Wave 2 — outcome-movers (all BYO-AI, no keys)**: referral assist
  ("find my path in" per job: networking targets + outreach drafts from JD +
  user background; referral-source field; Guide section w/ the 40%-vs-2%
  math) · channel-conversion analytics panel (per-source response rates from
  tracker + benchmark context) · cadence widget (weekly target, decay
  awareness) · follow-up/thank-you drafts on nudges · interview-prep prompt
  per tracked job.
- **Wave 3 — differentiators/polish**: high-fit new-match Windows toast ·
  posting-age urgency signal · application "copy pack" (evaluate true
  autofill extension later; review-before-submit only, 2–3 ATSs max) ·
  market the wedge (privacy/free/finds-jobs/ghost-shielding) in README +
  landing page + Guide.

## 5. Sources (key)

Funnel: Ashby Talent Trends (38M applications; referral 40%→interview;
inbound 43–52% of hires); Gem 2025 Benchmarks (140M apps; sourced ~5x;
career pages ~4x); Greenhouse Hire Standard (640M apps; 116→244/posting);
Huntr 2025 Annual (1.78M jobs; tailoring 1.6x; channel spread 11.3%→2.8%);
NY-Fed/academic cadence-decay work. Debunks: Preptel-origin "75% ATS
auto-reject"; 1970s-origin "hidden job market"; HP-anecdote "100% qualified"
(failed replication, Eur. J. Soc. Psych 2024). Pain: Fortune "AI doom loop"
(Greenhouse CEO); ResumeGenius/Interview Guys ghosting surveys; Clarify
Capital ghost jobs; LiveCareer HR survey. Competitive: huntr.co pricing/help

- store reviews; Simplify Trustpilot/CWS + jobhire/remotejobassistant
  reviews; Careerflow help-center + Capterra; JobScan hirecarta review +
  pricing; LoopCV reviews ("seven loops... went direct to CEOs"); Jobscan
  auto-apply risk taxonomy. Privacy: Incogni (8/9 platforms sell data); LayerX
  (Career.io); Toolbox-Kit (resume.io); BleepingComputer/Tom's Hardware
  (BrowserGate); Irish DPC €310M LinkedIn fine. Legal: CPPA statute/FAQ; hiQ
  settlement; LinkedIn v. Nubela 3:25-cv-00828; LinkedIn Help a1341387;
  JobSpy precedent; MS Store Policies v7.19; CWS program policies. Beta ops:
  MS SmartScreen/code-signing docs; Azure Artifact Signing pricing; tufup;
  GlitchTip; Appcues/Amplitude activation benchmarks (7% D7 top-quartile;
  3-step 62% vs 5+ 44% completion).
