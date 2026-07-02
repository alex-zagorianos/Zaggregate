# Onboarding / Time-to-Value UX Research — Zaggregate

**Date:** 2026-07-02
**Research area:** Onboarding / time-to-value patterns for a desktop tkinter + .exe BYO-AI/BYO-key job aggregator.
**Method:** Grounded in the 8 blank-slate general-user persona reports + `_structured-results.json` (this folder); external patterns gathered via web search/fetch with URL evidence.

---

## 0. The measured pain (from the 8 persona runs)

Before mapping external patterns, the concrete onboarding failures the tests surfaced:

| Pain                                                                               | Evidence in the persona data                                                                                                                                                                                                                                                                                                                                                                             |
| ---------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Setup takes 18–40 min**                                                          | `setup_minutes`: seven at 18–22, the data career-changer at **40**.                                                                                                                                                                                                                                                                                                                                      |
| **Free API keys are the #1 coverage unlock but users skip them**                   | Every persona's `biggest_gap` names an unkeyed source. Adzuna alone was **86% of the data-changer inbox and 100% of its local wins**; **85–97%** of local inboxes rode on Adzuna. CareerOneStop (the Guide's own #1/#2 local lever) was unkeyed in **all 8 runs**.                                                                                                                                       |
| **Silent zero-contribution when keys are absent**                                  | Every run logged "careeronestop skipped — credentials missing", "jooble/careerjet/brave skipped — no key" as passive warning lines. A general user "won't notice their local coverage is quietly capped" (SWE-Austin bug list).                                                                                                                                                                          |
| **AI-assisted seeding needs copy-paste round-trips and mostly fails**              | Across personas the AI produced correct company _names_ but wrong ATS _slugs_: SWE **5/13 wrong**, nurse **0/14 live**, consultant **1/17 live**, mecheng first-pass 404s. "The AI can't reliably know a Workday tenant string from the public careers URL."                                                                                                                                             |
| **The Guide is good but lives in Help; the wizard never routes users to the keys** | The 5-step wizard is `Welcome → Roles → Where → Resume → Keep-jobs-coming` (`ui/setup_wizard.py:416`). The excellent "Connect job sources" dialog (`ui/source_keys.py` — signup URLs, masked entry, Save, **per-source live Test**) is only reachable from the **Tools menu**, _after_ setup. `open_dialog` is never called from the wizard. This is the structural root cause of "users skip the keys." |
| **The wizard's own field box silently mis-routes**                                 | Free-text `industry` with no picker/validation caused the space-vs-underscore bug (mecheng/warehouse/data — "mechanical engineering" matches 0 companies) and health-informatics synonym pollution (marketing). A dropdown/validation would prevent it.                                                                                                                                                  |

The app already has most of the right _machinery_ (a keys dialog with live Test, an ATS probe, a reach badge, an "ask your AI" seeding flow). The gap is almost entirely **sequencing, placement, and friction** — exactly what onboarding UX research addresses.

---

## 1. Making BYO-API-key signup near-zero-friction

**The stakes are quantified.** API-onboarding surveys put **early-stage quit rates at 50–70% when friction appears at signup/auth**, and the biggest wins come from removing that friction first ([Young Copy — API onboarding benchmark](https://www.youngcopy.com/insights/how-fast-is-your-api-onboarding-benchmark-your-first-call-time-in-five-minutes)). For Zaggregate, "the key" _is_ the product's coverage, so key-signup friction directly caps the value delivered.

### Pattern 1a — Deep-link straight to the key page, don't just name it

Acquisition/onboarding teams deliberately deep-link a click to the _exact_ step rather than a generic landing page, because "users see exactly what they expect" and it lifts conversion ([Branch — deep-link generator](https://www.branch.io/resources/blog/deep-link-generator-how-to-create-manage-and-optimize-links-for-mobile-growth/); [Punith Uppar — deep linking & attribution guide](https://medium.com/@punithsuppar7795/mastering-deep-linking-and-attribution-in-mobile-apps-a-developers-practical-guide-2551cb704cba)).

- **Zaggregate mapping:** `source_keys.py` _already_ opens the free-key URL in the browser (`webbrowser.open(u)`). What's missing is landing the user on the **exact registration form** (Adzuna's `developer.adzuna.com` app-create page; CareerOneStop's `registration.aspx` — that specific URL is already used) **and** doing this _from inside the first-run wizard_, not only from a Tools-menu dialog they never open. **Step improved:** first-run wizard → new "Connect your sources" step.

### Pattern 1b — Instant, local key validation with visible pass/fail

Clerk's API-key redesign is the canonical friction case study: they made keys detectable as valid/malformed _without a server round-trip_ by appending a `$` **stop character** and using a familiar (Stripe-style `pk_test_`) format, on the principle "familiar DX is the best DX" ([Clerk — refactoring our API keys](https://clerk.com/blog/refactoring-our-api-keys)). The broader benchmark advice: give **instant sandbox credentials / instant feedback** so the developer can confirm the key works immediately rather than discovering failure later ([Treblle — accelerating API integrations](https://treblle.com/blog/accelerating-api-integrations-best-practices-for-faster-onboarding); [Young Copy](https://www.youngcopy.com/insights/how-fast-is-your-api-onboarding-benchmark-your-first-call-time-in-five-minutes)). Client-side key-shape detection is a recognized pattern — tools identify a key's _type/validity_ purely client-side and hand back a green/red verdict ([SecurityWall API key checker](https://securitywall.co/tools/api-key-checker)).

- **Zaggregate mapping:** `source_keys.test_source()` **already does exactly this** — one tiny live probe per source returning `OK - N sample result(s)`. The unrealized value is that (a) this Test runs only if the user opens the Tools dialog, and (b) there's no cheap _shape_ check before the live probe (e.g. Adzuna app_id is numeric, CareerOneStop token is a long base64-ish string) to catch a paste error instantly. **Step improved:** the "Connect your sources" step should auto-run `test_source()` on paste/blur and show a green "OK — 226 sample results" / red "check your key" inline, mirroring Clerk's instant-feedback principle.

### Pattern 1c — Paste-from-clipboard detection

Modern clipboard UX detects that a pasted blob "is not the same as a regular sentence the moment it lands" (token/key patterns) and can auto-fill the field ([MDN Clipboard API](https://developer.mozilla.org/en-US/docs/Web/API/Clipboard_API); [SecurityWall](https://securitywall.co/tools/api-key-checker)). Adzuna hands the user two values (App ID + App Key) on one page; a "Paste both" that splits them reduces two error-prone copies to one.

- **Zaggregate mapping:** after the user creates the Adzuna app, offer a single "Paste from clipboard" button on the Adzuna box that recognizes the `id` + `key` shapes and fills both masked fields. **Step improved:** Adzuna/CareerOneStop entry in the sources step.

**Net for area 1:** Zaggregate has the pieces; the fix is _promotion + sequencing_ — surface `source_keys.open_dialog` (or an embedded equivalent) as a **wizard step**, auto-Test on paste, and deep-link the two headline keys. This converts "silently skipped, coverage capped" into "guided, validated, done in ~5 min."

---

## 2. AI-assisted onboarding precedents (an LLM interviews the user / writes their config)

There is now a clear product precedent for **natural-language → generated config**, which maps directly onto Zaggregate's two AI-shaped onboarding moments (setup profile + company seeding).

### Pattern 2a — Prompt-to-config ("describe it, we build the setup")

- **Amazon Quick:** the user "enters a simple natural language prompt describing what you want your agent to do," and the system "automatically expand[s] your prompt into a detailed persona and response instructions while scanning available resources to link relevant … connectors" ([AWS — build onboarding agents with Amazon Quick](https://aws.amazon.com/blogs/machine-learning/build-ai-powered-employee-onboarding-agents-with-amazon-quick/)).
- **The general shift:** "AI does the onboarding work for users instead of guiding them through it — auto-filling setup steps (fields, mappings, configurations) and generating first artifacts," and can activate a user "in under 60 seconds" ([ProductLed — AI onboarding](https://productled.com/blog/ai-onboarding); [Userpilot — AI user onboarding](https://userpilot.com/blog/ai-user-onboarding/)).
- **Zaggregate mapping:** the wizard's Roles/Field/Salary/Location fields (and the fragile free-text `industry`) are exactly "fields/mappings/config" an LLM can fill from one paragraph. Because Zaggregate is **BYO-AI**, the honest, ToS-safe version is a **copyable prompt block**: "Paste your résumé + one sentence about the job you want into your AI, then paste its answer here" → the app parses a small JSON/`Name|value` block into `config.json`/`preferences.*`. This also _fixes the mis-routing bug_: the AI returns a canonical field token, sidestepping the space-vs-underscore trap. **Step improved:** Roles/Field wizard step + résumé step.

### Pattern 2b — Conversational (chat) onboarding replacing forms

- **Miro:** "the entire first experience with your workspace is an AI chatbot," and onboarding answers update the clickable AI prompts ([Userpilot — AI user onboarding](https://userpilot.com/blog/ai-user-onboarding/)).
- **Adaptive interviewer:** an LLM "interviewing you, … adapt[ing] its questions based on your responses, just like a human interviewer" is a documented pattern; prompt-driven conversational field plugins already ship (SurveyCTO's OpenAI plugin is "completely prompt-driven and can adapt to any … workflow based on the system prompt") ([Hackaday — pair programming with an LLM](https://hackaday.com/2026/04/27/trying-pair-programming-with-an-llm-chatbot/); [surveycto/llm-conversations](https://github.com/surveycto/llm-conversations)).
- **Zaggregate mapping:** Zaggregate should NOT bake in a paid LLM. The precedent-aligned, BYO-AI-honest design is a **structured copy-paste "interview" prompt the user runs in their own AI**: one prompt that asks the AI to interview them briefly (target role, level, city, salary floor, dealbreakers) and emit a config block. This is the same "ask your own AI, paste the answer, bad answers fail validation" contract the Guide already uses for company seeding — extended to the _profile_. **Step improved:** whole wizard, optional "Set me up with my AI" path.

### Pattern 2c — AI-assisted **company seeding**, but validate the _slug_, not just the name

The persona data is unambiguous: the AI reliably knows company **names** but guesses ATS **slugs** wrong (Workday tenant strings are unguessable from a public careers URL). The AI-onboarding literature's answer is to have the AI "generate the first artifact" _and then verify it_ ([ProductLed](https://productled.com/blog/ai-onboarding)) — Zaggregate already verifies via `probe_count`, but currently `save_companies` persists dead slugs anyway (a design gap noted in every persona).

- **Zaggregate mapping:** keep the "ask your AI for `Name | careers-link`" flow, but (a) make the AI prompt ask for the **careers-page URL only** (which it _can_ get right) and let the app's own ATS detector resolve the slug, and (b) split the Add button into "Add verified (live jobs)" vs "Add unverified anyway", so the default no longer silently stores dead boards. **Step improved:** `+ Add Companies` / Build-My-List.

---

## 3. Time-to-first-value patterns (progressive disclosure, sample/demo data, first-run success)

TTFV is "perhaps the single most critical metric in the early customer journey," and hitting first value in-session drives **3–5× long-term retention**; within 5 min ≈ **+40% 30-day retention** vs 15+ min ([Saber — time-to-first-value](https://www.saber.app/glossary/time-to-first-value); [ProductLed — aha moments](https://productled.com/blog/how-to-use-aha-moments-to-drive-onboarding-success)). Concrete, quantified levers below map cleanly onto Zaggregate.

### Pattern 3a — Sample/demo data _before_ real setup (~80% faster first insight)

The single biggest documented TTFV lever: "show value with sample data first, then ask for real data" — an analytics tool cut first-insight from a **3–5 day baseline to an 8-minute median**, and **71% of users progressed to connecting real data afterward** ([Saber](https://www.saber.app/glossary/time-to-first-value)). "Demo data instead of empty states … accelerate[s] the Aha moment" ([Appcues — aha moment examples](https://www.appcues.com/blog/aha-moment-examples)).

- **Zaggregate mapping:** Zaggregate's aha moment is **a scored, location-clean inbox**. Ship a tiny **bundled sample inbox** (e.g. 20 pre-scored rows for a couple of generic roles) so the very first screen after "Welcome" is a _populated, sortable inbox with Scores_ — the user sees the payoff in seconds, _then_ runs their real search. This also demonstrates the Score-vs-Fit split before they've connected anything. **Step improved:** first render after Welcome; empty-inbox state.

### Pattern 3b — Guided first task / "forced first action" (+30% completion, +20–30pp activation)

Interactive wizards improve completion **+30%** and cut task time **~45%**; a "forced first action" that makes the user actually experience the value milestone lifts achievement **20–30 percentage points** ([Saber](https://www.saber.app/glossary/time-to-first-value)). Guided empty states outperform blank screens ([Appcues](https://www.appcues.com/blog/aha-moment-examples)).

- **Zaggregate mapping:** the wizard already ends on "Keep jobs coming" with "Update my inbox now." Make **"Update my Inbox now"** the wizard's terminal, unmissable primary action (the forced first action), and make the resulting empty-until-then Inbox state a **guided** one ("Run your first update →") rather than a blank table. **Step improved:** wizard finish → first daily_run → Inbox empty state.

### Pattern 3c — Progressive disclosure: defer non-essential setup past first value

Guidance is explicit: "users should only encounter complexity when it becomes relevant to their goals"; collect only what's needed for immediate functionality, then introduce integrations/keys "as users demonstrate readiness and motivation through actual product engagement" (Spotify/Canva hybrid models) ([Digia — progressive disclosure vs front-loaded setup](https://www.digia.tech/post/onboarding-patterns-progressive-disclosure-vs-front-loaded-setup); [UXPin — progressive disclosure](https://www.uxpin.com/studio/blog/what-is-progressive-disclosure/)).

- **Zaggregate tension & resolution:** this _seems_ to argue against Area 1 (adding a keys step upfront). The reconciliation the persona data forces: keys aren't "non-essential" for Zaggregate — Adzuna is 85–97% of local coverage — but they _are_ a moment of real friction. So the right sequencing is: **let the user reach a first (keyless) inbox immediately** (Pattern 3a/3b), then present the keys step **framed by the payoff they just felt** — "You're seeing ~X local jobs. Add one free key to see the rest." That's progressive disclosure _and_ it converts the key ask because it's now motivated, not upfront homework. **Step improved:** ordering of the keys step relative to first inbox.

### Pattern 3d — Templates / field presets (~40–60% TTFV reduction)

Template-based experiences give "40–60% TTFV reduction" (one case cut signup 4 min → 45 s) ([Saber](https://www.saber.app/glossary/time-to-first-value)). This maps to the _field_ problem: instead of a free-text `industry` box that breaks routing, ship a **field picker** (nursing, teaching, SWE, warehouse/logistics, consulting, mech-eng, data, marketing, …) that presets the correct token, source routing, and any known local employers — a "template" per field.

- **Zaggregate mapping:** replaces the fragile free-text field with validated presets, killing the space-vs-underscore and synonym-pollution bugs _and_ seeding the company layer for that field on day one. **Step improved:** Roles/Field wizard step.

---

## 4. Honestly communicating coverage / completeness (the "reach badge")

Zaggregate already has a **reach badge** that estimates market coverage (Good-Turing completeness) and honestly says **"cannot certify"** when it can't (no SerpApi key / disjoint sources) — this is exactly the direction the research endorses. **94% of consumers prefer brands that are upfront about their practices**, and transparency ("being upfront about … limitations," visible/understandable trade-offs) is repeatedly cited as the trust-builder ([DevRev — customer transparency guide](https://devrev.ai/blog/customer-transparency); [LinkedIn — honest & transparent UX](https://www.linkedin.com/advice/3/what-best-practices-ensuring-honest-transparent-j56af)). Showing the **result count / what was searched** is the standard, expected coverage signal in search UX ([UX Patterns — search results](https://uxpatterns.dev/patterns/advanced/search-results)).

### Pattern 4a — Turn the honest badge into an _actionable_ one

The persona reports show the badge often reads "cannot certify" and stops there — honest but a dead end. Empty/limited states should "move users forward," not just report ([Appcues](https://www.appcues.com/blog/aha-moment-examples)).

- **Zaggregate mapping:** when reach is low or uncertifiable, the badge should name _the reason and the fix_: "Seeing mostly remote/tech jobs because Adzuna + CareerOneStop aren't connected — [Connect a free key] to widen your local reach." This ties the coverage-honesty surface (Area 4) directly to the key-conversion surface (Area 1), so the moment the user _feels_ the gap they're one click from closing it. **Step improved:** reach badge on the Inbox.

### Pattern 4b — Name the structural blind spots plainly

The Guide already says free feeds "lean toward remote tech jobs" — persona runs confirm this is the single most important honest disclosure (a remote-marketer got 8 jobs; a nurse would get ~7 federal-only without keys). Transparency research says stating limitations _increases_ trust and informed decisions ([DevRev](https://devrev.ai/blog/customer-transparency)).

- **Zaggregate mapping:** keep and _surface earlier_ the "free feeds skew remote/tech; local jobs need a key" message — ideally on the first (sample or keyless) inbox, as the caption on a thin result set, not buried in Help. It reframes a thin first inbox from "this app is weak" to "this is expected until you add one free key." **Step improved:** first-inbox caption + reach badge.

---

## 5. Recommended onboarding sequence (synthesis)

Putting the patterns in order, the re-sequenced first run that the evidence supports:

1. **Welcome** → immediately show a **bundled sample inbox** (Pattern 3a) so value is felt in seconds.
2. **Field picker + optional "set me up with my AI" paste** (Patterns 2a/2b, 3d) — validated presets kill the routing bugs; the AI path fills the profile from a résumé paragraph.
3. **Roles / Where / Salary / Résumé** (existing, largely fine).
4. **Forced first action: "Update my Inbox now"** (Pattern 3b) → real, keyless inbox.
5. **Motivated keys step**, framed by the reach the user just saw (Patterns 1a–1c, 3c, 4a): deep-link Adzuna + CareerOneStop, paste-detect, auto-Test with green/red inline feedback.
6. **Company seeding** via "ask your AI for careers-page URLs" with slug-resolution + verified/unverified split (Pattern 2c).
7. **Reach badge stays honest but becomes actionable** (Pattern 4a/4b).

This preserves everything already built (keys dialog + live Test, ATS probe, reach badge, ask-your-AI flow) and mostly **re-orders and re-frames** it: value first, motivated friction second — the core TTFV finding (3–5× retention when first value lands in-session).

---

## Source list

- Saber — Time-to-First-Value (quantified TTFV levers): https://www.saber.app/glossary/time-to-first-value
- ProductLed — Aha moments in onboarding: https://productled.com/blog/how-to-use-aha-moments-to-drive-onboarding-success
- ProductLed — AI onboarding (activate in <60s, auto-fill config): https://productled.com/blog/ai-onboarding
- Appcues — Aha moment examples (demo data, guided empty states): https://www.appcues.com/blog/aha-moment-examples
- Digia — Progressive disclosure vs front-loaded setup: https://www.digia.tech/post/onboarding-patterns-progressive-disclosure-vs-front-loaded-setup
- UXPin — Progressive disclosure in UX: https://www.uxpin.com/studio/blog/what-is-progressive-disclosure/
- Clerk — Refactoring our API keys (stop char, familiar format, instant validity): https://clerk.com/blog/refactoring-our-api-keys
- Young Copy — API onboarding benchmark (50–70% quit on friction; instant feedback): https://www.youngcopy.com/insights/how-fast-is-your-api-onboarding-benchmark-your-first-call-time-in-five-minutes
- Treblle — Accelerating API integrations (instant sandbox creds): https://treblle.com/blog/accelerating-api-integrations-best-practices-for-faster-onboarding
- Branch — Deep-link generator (land users on the exact step): https://www.branch.io/resources/blog/deep-link-generator-how-to-create-manage-and-optimize-links-for-mobile-growth/
- Punith Uppar (Medium) — Deep linking & attribution guide: https://medium.com/@punithsuppar7795/mastering-deep-linking-and-attribution-in-mobile-apps-a-developers-practical-guide-2551cb704cba
- MDN — Clipboard API: https://developer.mozilla.org/en-US/docs/Web/API/Clipboard_API
- SecurityWall — API key checker/validator (client-side key-shape detection): https://securitywall.co/tools/api-key-checker
- AWS — Build onboarding agents with Amazon Quick (prompt→persona/config): https://aws.amazon.com/blogs/machine-learning/build-ai-powered-employee-onboarding-agents-with-amazon-quick/
- Userpilot — AI user onboarding (Miro chat-first; auto-fill fields): https://userpilot.com/blog/ai-user-onboarding/
- Hackaday — Pair programming with an LLM chatbot (AI-interviews-you): https://hackaday.com/2026/04/27/trying-pair-programming-with-an-llm-chatbot/
- surveycto/llm-conversations — prompt-driven conversational field plugin: https://github.com/surveycto/llm-conversations
- DevRev — Customer transparency guide (94% prefer upfront brands): https://devrev.ai/blog/customer-transparency
- LinkedIn — Honest & transparent UX best practices: https://www.linkedin.com/advice/3/what-best-practices-ensuring-honest-transparent-j56af
- UX Patterns — Search results (result count as coverage signal): https://uxpatterns.dev/patterns/advanced/search-results
