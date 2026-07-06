# Design — ATS autofill assist, review-before-submit ONLY (S38, awaiting Alex GO)

**Why** (beta research): tailored + timely applications convert ~1.6x, but a
Workday-style form costs 15–30 min. The research is equally clear that
auto-SUBMIT bots convert at 0.4–6% and get accounts banned — so this is an
assist that fills, highlights, and stops. Submission is always human.

## Shape

Browser-extension feature (MV3, `browser_ext/`) + one new read-only endpoint.
The extension already talks to the receiver on 127.0.0.1:5002 (capture path)
— autofill rides the same trust boundary in the opposite direction.

1. **Endpoint**: `GET /api/profile/application-pack` — JSON twin of the S37
   `copy_pack.py` payload (contact, links, work history rows, education,
   work-authorization answers). Origin-gated like every /api route; nothing
   new is exposed beyond what copy-pack already renders as text.
2. **UI**: popup button "Fill from Zaggregate", enabled on known ATS domains
   (greenhouse.io, lever.co, ashbyhq.com, myworkday.com, icims.com,
   smartrecruiters.com). Content script runs only on click (activeTab —
   no new blanket host permissions).
3. **Adapters**: per-ATS field maps (greenhouse stable ids, lever name attrs,
   workday `data-automation-id`) + a generic fallback that fuzzy-matches
   visible label text (name/email/phone/linkedin/city/school/degree/dates).
   Selects/radios matched by option text. Unknown fields skipped, never
   guessed.
4. **Review-only guarantees** (each pinned by a test):
   - filled fields get a visible outline + a summary banner "Filled N fields —
     review before submitting";
   - the content script contains NO click/submit on button/submit selectors
     (lint-style test over the adapter source);
   - file inputs are never set (browser can't anyway without a user gesture) —
     the banner shows the tailored-resume path with a copy button instead.
5. **Nothing persisted** page-side; the pack is fetched per click, kept in
   memory, and discarded.

## Test plan

Adapter unit tests over saved ATS form-DOM fixtures (fill counts + values);
generic-fallback label-matching table tests; the no-submit lint pin; endpoint
contract test (shape + origin gate + `__origin_gated__`).

## Risks / open

- ATS DOM drift → adapters are data (selector maps), generic fallback catches
  the rest; failures degrade to "0 fields filled", never wrong values silently
  (each fill echoes into the summary for eyeballing).
- Workday multi-page wizards → v1 fills the visible page only (re-click per
  page). Documented.
- **Needs Alex GO** — extension permission surface + whether the fill button
  should also appear for unrecognized forms (generic-only mode).
