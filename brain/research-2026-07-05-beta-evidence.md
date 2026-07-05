# Beta Research Evidence Digest (2026-07-05)

Companion to `beta-roadmap-2026-07-05.md` (the synthesis/build order). This
digest persists the load-bearing findings of all nine research threads so the
evidence survives the session. Confidence labels: solid / directional /
anecdotal; vendor-blog numbers flagged.

## 1. What gets people hired (funnel evidence review)

Datasets: Ashby (~38M applications / 250k hires), Gem (140M / 1.3M), Greenhouse
(640M), Huntr (1.78M tracked jobs). None peer-reviewed; tech-skewed. No
controlled A/B study of any job-search tool exists anywhere.

- Cold application → interview ~2–3%, → offer ~0.2% (Ashby; solid-directional).
- Referred candidates: 40% reach interview; ~1% of applications but ~18% of
  hires (Ashby) — 20–40x per-application advantage. Widely-quoted "referrals =
  30–50% of hires" is inflated (Zippia aggregation).
- Cold inbound still = 43–52% of ALL hires (4-year high) — volume works, it's
  a numbers game with known odds.
- Recruiter-sourced candidates convert ~5x better (Gem) → being findable +
  responsive taps a free channel.
- Channel spread ~4x (Huntr 600k jobs): Google Jobs 11.3%, government boards
  8.7%, Wellfound 6.0%, Glassdoor 5.5%, Indeed 4.5%, LinkedIn 3.1%,
  ZipRecruiter 2.8% response. Career pages convert ~4x better than boards.
- Tailoring: 1.6x measured (5.8% vs 3.6%; 65k tailored vs 1M+ untailored,
  Huntr). "2x/115%/3x" claims are vendor marketing.
- Apply early (days 1–3): directionally real; the "3.1x/6x in 48h" multipliers
  are marketing.
- Cadence: ~10–20 quality apps/week; offers mostly land within 20–80 total;
  search intensity decays over the spell (NY-Fed/academic — solid).
- Follow-ups: ONE follow-up + interview thank-you (91% of employers welcome;
  ~50% of candidates skip); more than one backfires (Belkins 16.5M emails).
- Apply at ~60%+ fit: only 27% of applicants meet all listed requirements and
  hiring proceeds; the "women wait for 100%" HP stat failed a preregistered
  replication (Eur. J. Soc. Psych 2024).
- Market context: applications/posting 116→244 (2022→2025); applicant ~3x less
  likely to be hired than 3 yrs ago; median time-to-first-offer 57→83 days
  across 2025; LinkedIn ~11–14k applications/minute (+45–58% YoY).
- DEBUNKED: "75% of resumes auto-rejected by ATS" (traces to defunct 2012
  vendor Preptel; 92% of recruiters say no format auto-reject; ATSs rank).
  "70–80% of jobs never posted" (1970s career-coach marketing).
- Auto-apply bots counterproductive: LazyApply user 5,000 apps → 20 interviews
  (0.4%); BI journalist 126 → 7 (6%); Indeed classifies bot-pattern
  applications as fraud-adjacent (official docs); 33.5% of hiring managers
  spot AI applications in <20s, 19.6% reject outright (TopResume n=600).

## 2. Seeker/market pain points

- Ghosting = #1 complaint: 71–79% ghosted in past year; r/jobs analysis (967
  posts): silence damages more than rejection. 72% say search hurts mental
  health.
- Ghost jobs: best studies 1-in-7 (Clarify Capital, 175k listings: active 30+
  days w/o hiring; worst = wholesale 51%, mining 48%, biotech 43%; senior
  roles worse) to 1-in-3; Greenhouse 18–22%; 93% of HR pros admit posting
  them (LiveCareer n=918). CA now requires vacancy-status disclosure on
  public ads.
- Recruiter side: 2/3 got more applicants/role; TA headcount down while reqs/
  recruiter +56%; 81% spend <1 min on first-pass resume review; Greenhouse
  CEO: "Trust is at an all-time low for both sides."
- AI arms race: 38–40% of seekers use AI for applications; 80% of hiring
  managers claim they detect AI resumes; 41% of seekers admit prompt-injection
  tricks; deepfake interview fraud up 1,300% YoY.

## 3. Competitive deep-dives (2026)

- **Teal**: $29/30d (no annual). One-click autofill CONFIRMED (official page).
  No mobile app, no email parsing, manual follow-ups. Privacy policy (Jan
  2026): resume content sent to OpenAI; used aggregated for model improvement;
  GA + marketing cookies; recurring spam-email complaints; Trustpilot 4.0
  (107) w/ 15% 1-star (billing/spam). Best-loved: tracker + Chrome clipper.
- **Huntr**: $40/mo Pro (credits don't roll over). NO job discovery/alerts
  ("Huntr does not find jobs for you" — own FAQ). Native mobile apps. 4.7–4.9★
  stores; complaints: resume-builder lock-in, support black hole, cancel
  friction. Extension requests PII/financial/web-history permissions.
- **Simplify**: autofill free (its moat, 100+ ATSs, manual submit; ~90%
  accuracy Greenhouse/Lever, ~70% Workday, ~0% gov forms). Simplify+ $39.99,
  no refund policy; Trustpilot 3.0 (67% 1-star); Featurebase board allegedly
  exposed user PII. CWS 4.9★/500k users.
- **Careerflow**: $23.99/mo; autofill on 12 ATSs (~60% Workday accuracy);
  LinkedIn Profile Optimizer = the loved free feature; account deletion only
  via email (GDPR smell); appears on a "blacklisted LinkedIn plugins" list
  (unexplained entry) while a competitor ranks it near-zero-risk — contested.
- **JobScan**: ~$50/mo or $90/quarter trap; refund = 2 days + 3.5% fee.
  Match-score not predictive (100+ apps at high score → 0 responses, G2);
  keyword extraction incoherent; AI cover letter fabricated an employer.
- **LoopCV**: €9.99–29.99/mo mass-apply; "seven loops... went direct to CEOs
  and half weren't even open reqs"; matched-vs-actually-applied gap (60
  claimed → 2 real).
- **Auto-apply tier (Sonara/LazyApply/JobCopilot/Massive)**: Sonara $2.95
  trial→$23.95/4wk rollover, 25–40% application failure rate, no tailoring;
  LazyApply $99–999/yr, 1,500/day tier, Trustpilot ~2.1, renamed its
  Trustpilot page to parent-co name, on the LinkedIn plugin blacklist,
  documented ATS spam-flagging at 14k applications; JobCopilot ~$28/mo, 11%
  scam-posting exposure incident, "25 applicants same fake email" recruiter
  report; Massive ~1–2 interviews per 100 apps (own-site admission).
- **Category-wide**: email-inbox status detection = NOBODY has it (market
  gap, not debt). Kanban tracking + job-clipper extensions = the universally
  loved features. AI tailoring = the universal complaint (hallucinated
  skills across Teal/Careerflow/Sonara/JobScan).

## 4. Privacy / trust landscape (the wedge evidence)

- Incogni (May 2026, n=1,000): 8 of 9 major job platforms sell user data per
  CCPA definition; 40% never delete old profiles; Monster > LinkedIn >
  ZipRecruiter most invasive.
- Career.io extension policy: "may use personal data collected from your
  resume to sell to third parties." resume.io: sells to data brokers; 2043
  tracking cookie.
- LinkedIn "BrowserGate" (Apr 2026, BleepingComputer-confirmed): hidden JS
  scans visitors for 6,236 extensions incl. 509 job-search tools + 48
  fingerprint attrs; ~405M users' extension footprints; two class actions.
  Plus €310M Irish DPC GDPR fine (Oct 2024).
- Breaches: HireClick 5.7M resumes (open S3); LiveCareer 5M+ (Azure);
  pattern = cloud misconfig, not sophisticated attacks.
- Subscription dark patterns: ZipRecruiter BBB ($24/day → $504/mo charges;
  10/86 complaints resolved); Adobe $150M ROSCA settlement (the playbook);
  ICPEN sweep: 75.7% of sites use ≥1 dark pattern. Zuora: 47% of consumers
  actively cancelled subs in 2026.

## 5. Legal posture (US)

- Privacy policy: zero-telemetry local app almost certainly isn't a CCPA
  "business" (thresholds: $26.6M rev / 100k CA residents / 50% data revenue);
  all ~21 state laws share the controller-threshold architecture. Publish a
  5-line policy anyway (trust asset; REQUIRED for the Chrome extension's Web
  Store listing if it requests data permissions). Not legal advice.
- Scraping: hiQ v. LinkedIn ended with hiQ paying $500k + permanent
  injunction — CFAA isn't the weapon for public pages, ToS breach-of-contract
  is. LinkedIn v. Nubela/Proxycurl (Jan 2025, settled; Proxycurl shut down).
  Apollo.io/Seamless.ai pages removed 2025; HeyReach banned 2026 (secondary
  sources). ALL enforcement targets centralized commercial scrapers.
- Our architecture (each user's own machine fetches; LinkedIn/Indeed via the
  user's OWN browser extension only; ToS-blocked sources gated; no
  auto-apply) = the browser-vendor analogy; under-litigated but conservative.
  Precedent: JobSpy (MIT, 3.8k stars, scrapes LinkedIn/Indeed openly, years,
  no reported action, no legal disclaimer). Add a one-paragraph "you query
  sources on your own behalf" disclaimer anyway.
- LinkedIn ToS §8.2 bans scraping/automation extensions generally; risk
  gradient: passive capture/autofill-with-manual-submit tools have NO
  documented user bans; auto-apply bots do (3,000-apps-in-a-day ban case;
  > 25–30 apps/day flag threshold per SEO blogs, unverified).

## 6. Beta-readiness facts

- SmartScreen: unsigned exe = "More info → Run anyway" soft block; Win11
  Smart App Control can hard-block unknown binaries. EV certs NO LONGER give
  instant reputation (since Mar 2024) — OV/EV identical, reputation is
  organic download volume.
- **Microsoft Store: individual dev registration FREE since Sept 2025; Store
  re-signs packages — users never see SmartScreen.** Best path; needs MSIX.
- Azure Trusted Signing (now "Artifact Signing"): $9.99/mo Basic; US/CA
  individual signup pause LIFTED (FAQ 2026-06-22); needs paid Azure sub;
  same organic reputation curve.
- winget: free manifest PR; CLI installs skip the SmartScreen dialog;
  validation pipeline itself runs SmartScreen checks.
- Updates: PyUpdater dead; tufup = successor; hand-rolled GitHub-Releases
  check + toast = 0.5–1 day (recommended for beta). Ship SHA-256 checksums.
- Crash reporting: Pachli pattern (user SEES the scrubbed report before
  sending; mailto/GitHub-issue prefill) — no telemetry. Bugsink = single-
  container Sentry-compatible if ever needed.
- Onboarding: activation = "first search returns scored results the user
  opens"; TTV <15 min; 7% D7 retention = top quartile (Amplitude); 3-step
  flows complete 62% vs 44% at 5+; compounding drop-off (0.85^6 ≈ 38%);
  "unclear progress" is the top drop-off driver → show step X of Y.
- Feedback: in-app mailto/hosted form primary (job seekers often lack GitHub
  accounts); GitHub Issues = internal tracker; Canny overkill (25-user free
  cap); pick ONE channel.
- Recruiting: value-comments in r/jobs-type subs (self-promo posts get
  removed); r/alphaandbetausers; Show HN (local-first/privacy/free/Python =
  HN catnip; HN punishes signup-gated tools); university career centers =
  dead end for indies; documented pattern: "anyone want to beta test?" post
  in a narrow sub BEFORE polish → 47 DMs case.

## 7. Where the findings live

- Synthesis + build order: `brain/beta-roadmap-2026-07-05.md`.
- This digest: the persisted evidence base.
- Raw agent transcripts (session-scoped, will expire with temp cleanup):
  session task outputs under the 2026-07-05 conversation.
