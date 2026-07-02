# Review — Tracking Lifecycle & Product Surface

Lens: tracking lifecycle + product surface, verified against the tracker package
(`tracker/db.py`, `tracker/service.py`), `rerank/{import_,export,schema}.py`,
`workspace.py`, `daily_run.py`, and `gui.py`.
Source: 8 blank-slate general-user personas (`general-user-tests-2026-07/persona-*.md`,
`_structured-results.json`).

Bottom line: **All 8 personas completed apply→interview→offer/rejected/ghosted
successfully and every status/round/note persisted and re-read cleanly.** There is
NO blocking functional gap in the cycle. What the personas logged are **coherence,
silent-failure, and side-effect traps** — each confirmed in code below, most of
them low-effort fixes that materially raise trust for a non-technical user.

Findings ranked most-severe first.

---

## L1 — `daily_run.py --project X` persistently flips the GLOBAL active project (side effect of a scoped run) — CONFIRMED, live tonight

`daily_run.py:218`

```python
if args.project and not args.user_config:
    workspace.set_active(args.project)          # <-- persistent write to projects.json
...
workspace.pin_active(args.project or workspace.active_slug())   # :225  S27 process-local pin
...
finally:
    workspace.unpin_active()                    # :629  clears the pin, does NOT restore 'active'
```

`workspace.set_active` (`workspace.py:388`) does `reg["active"] = slug; _write_registry(reg)`
— it rewrites projects.json on disk. Running `daily_run.py --project gu-teacher-columbus`
therefore leaves projects.json permanently pointing at the teacher project; the GUI
opens to it next launch. Teacher persona logged this exactly ("running the persona's
update flipped on-disk projects.json 'active' from gu-nurse-boise to gu-teacher-columbus"),
and the orchestrator had to manually restore the registry after the overnight run
(it "ended pointed at the last persona").

The S27 process-local pin (`pin_active`/`unpin_active`) already gives the run the
isolation it needs: `active_slug()` (`workspace.py:246`) returns `_PINNED_SLUG` first,
so **every** db/config/output path in the running process resolves to the pinned
project regardless of projects.json. The `set_active` call is doing NOTHING the pin
doesn't already do for the running process — its ONLY observable effect is the
persistent, unwanted global flip.

**Right fix (given the pin already exists):** delete the `set_active(args.project)`
call for the scoped-run path and rely solely on `pin_active(args.project)`. A scoped
`--project` run should not mutate which project the user's GUI is looking at. If a
future caller genuinely wants "run this AND make it active," that should be a separate
explicit flag (`--set-active`), not the default. (A restore-in-`finally` alternative
works but is race-prone across concurrent runs and still writes the registry twice for
no reason; not calling set_active is cleaner and matches the pin's intent.)

Severity: highest in this lens — it's the one finding that silently corrupts shared
state a user sees, and it's a ~1-line fix.

---

## L2 — File-import re-rank ("Load AI results") writes fit but no rank/rec_batch → Top Picks silently empty — CONFIRMED (warehouse B3), nuanced

`tracker/service.apply_rerank_scores` (`service.py:497`) calls `db.inbox_set_fit`
(writes `fit`/`fit_why`) and merges `extras` **only when the import row carried an
`extras` blob**. The extras blob is built by `rerank/import_.py::_extras_for` (`:79`),
which stamps `rank` + `rec_batch` (via `service.rank_patch`) **only if the imported
CSV/JSON has a non-blank `new_rank` cell**. `top_picks()` (`service.py:584`) returns
`[]` unless a row has `rank >= 1` AND a `rec_batch`.

Reproduced (temp DB):

```
apply_rerank_scores([{id, new_fit:88, fit_rationale:...}], source='file_import')
  -> inbox fit = 88, extras = ''   (no rank/rec_batch)
  -> top_picks() == []
```

Contrast: the clipboard route `score_inbox_from_reply` (`service.py:430`) ALWAYS
derives a shortlist itself — it sorts the scored rows and stamps `rank_patch` on each
(`:457-460`), so Top Picks fills even if the AI never mentioned rank.

So the persona's "B3 = file route leaves Top Picks empty" is real but conditional:
the file route CAN populate Top Picks, but only if the returned file includes a
`new_rank` column. The export prompt (`schema.build_prompt`) tells the AI new_rank is
how Top Picks gets populated, but the human MD (`export._write_md:88`) labels it
**"optional `new_rank`"**, and `new_fit` is the primary field. A user (or their BYO-AI)
who fills only `new_fit` — the obvious, required-feeling column — gets a correctly
re-scored, Fit-sortable inbox and a **silently empty Top Picks tab, with no message
saying "0 rows were shortlisted."** That mismatch between the two BYO-AI routes (paste
= Top Picks always fills; file = only if new_rank present) is the trap.

**Assessment / fix options (product decision, low effort):**

- Cheapest + most consistent: when a file import updates ≥1 fit but produces **zero
  ranked rows**, have the clipboard route's fallback kick in — derive a rank order
  from `new_fit` descending and stamp `rank_patch` (exactly what `score_inbox_from_reply`
  already does). Then BOTH BYO-AI routes fill Top Picks identically and the "optional"
  new_rank stays optional without a dead tab.
- Or at minimum, surface it: `_import_scores` already reports "Re-ranked N"; add
  "(0 shortlisted for Top Picks — include a new_rank column to populate it)" when
  no ranked rows landed, so the empty tab isn't a mystery.

---

## L3 — `tracker.db.update_job` silently ignores unknown field names (data-loss trap) — CONFIRMED (warehouse B4)

`db.update_job` (`db.py:678`): `updates = {k: v for k, v in fields.items() if k in _EDITABLE}`.
Any key not in `_EDITABLE` (`db.py:73`) is dropped with **no error, no warning, no
return value** (function returns None regardless). Reproduced:

```
update_job(id, offer_salary='53669')  -> offer_amount stays '' ; value lost, no signal
update_job(id, offer_amount='53669')  -> works (correct column)
```

The real column is `offer_amount`; `offer_salary` is a plausible wrong guess. A user
scripting the tracker, or their BYO-AI writing back via the API/MCP surface, can lose
data by guessing a field name and never know. This is the single most dangerous
lifecycle defect for the "BYO-AI drives the tracker" story, because it fails **silently
and destructively**.

**Fix (low effort):** `update_job` should distinguish "no editable fields supplied"
from "unknown field supplied." Either return the count of applied fields (callers can
assert), or raise/log on an unknown key that isn't in `_EDITABLE` (a `KeyError` or a
logged warning listing the ignored keys). The service-layer `update_job` passthrough
(`service.py:26`) should propagate the signal. Same class of bug would affect
`update_interview_round` (`db.py:847`, `_ROUND_EDITABLE`) — apply the same guard there.

---

## L4 — Two overlapping ways to model a phone screen; the GUI doesn't reconcile them — CONFIRMED (coherence)

- `phone_screen` is a **STATUS** (`db.py:34 STATUSES`, label "Phone Screen"), settable
  from the JobDialog status combobox (`gui.py:264`) and the tracker quick-status
  dropdown (`gui.py:722`).
- `phone` is an interview-**round KIND** (`gui.py:215 _ROUND_KINDS = ["phone","tech",
"onsite","final","other"]`), chosen in the Add-Round dialog (`gui.py:517`).

(Minor correction to the persona wording: the round kind is `phone`, not
`phone_screen` — the two aren't even the same token, which makes the overlap subtler,
not clearer.) Nothing links them: setting status → "Phone Screen" does not create a
round; adding a `phone` round does not advance status. A user tracking the same event
can put it in either place and get different data; `count_followups_due` /
`followups_due` key off the `phone_screen` _status_ (`db.py:554`, `:588`), so a user
who logs their phone screen as a _round_ while leaving status at "applied" won't get
the right follow-up nudging.

Neither is "wrong" — status = funnel stage, round = a scheduled event with a date/ICS —
but the product never says which is canonical, so it's genuinely conflatable.
**Which is canonical:** the STATUS should be the funnel source of truth (it drives
analytics + follow-up logic); rounds are the calendar detail _under_ an interview-y
status. **Fix (low/medium):** make them cohere — e.g. when the first round is added,
offer to advance status to `phone_screen`/`interview`; and/or drop `phone` from round
kinds in favor of `phone_screen` so the vocabulary matches, or relabel the round-kind
list to make clear it's "event type," not "stage." Documentation-only is acceptable
but leaves the follow-up-nudge mismatch above.

---

## L5 — `add_interview_round` kind/outcome are free-text with no enum validation — CONFIRMED (design, low risk)

`db.add_interview_round` (`db.py:812`) and `update_interview_round` (`db.py:847`) accept
arbitrary `kind`/`outcome` strings; the DB columns default `kind='other'`, `outcome=''`
with no CHECK. Today the GUI constrains `kind` to `_ROUND_KINDS` via a readonly combobox
(`gui.py:517`), but **`outcome` is a free-text Entry** (`gui.py:534`) and the service/db
API accept anything, so the API/MCP/scripted routes (and any future GUI without the
combobox) can write inconsistent values ("passed" vs "pass" vs "advanced"). This is fine
for power use and there's no data-loss risk; it just means outcome can't be aggregated
reliably later. **Assessment:** acceptable as-is; if analytics on round outcomes is ever
wanted, add a small suggested-value combobox for `outcome` (advanced / rejected /
pending / withdrawn) mirroring the kind one, keeping free-text allowed.

---

## L6 — `add_status_note` stored as a same-status self-transition — CONFIRMED (cosmetic; export leaks it)

`db.add_status_note` (`db.py:760`) inserts a `status_history` row with
`old_status == new_status` (the app's current status) carrying the note. Reproduced:
a note on an accepted app yields an `accepted -> accepted` history row.

The interactive timeline handles this correctly: `status_timeline` (`db.py:785`) tags
such a row `kind='note'` (not `'status'`) so the JobDialog timeline pane can render it
as a note, not a no-op stage change. **BUT the CSV export does not:**
`status_timeline_all` (`db.py:1562`, used by `export_applications_csv:1531`) emits the
raw `old->new`, so the exported history column shows `accepted->accepted [Signed the
offer today]` — reading as a phantom self-transition in the spreadsheet a user hands to
someone else. Data-changer-phoenix flagged exactly this. **Fix (low):** in
`status_timeline_all` / the CSV formatter, when `old==new` render it as a note event
(`accepted [note]` or `note: ...`) instead of `accepted->accepted`. Purely cosmetic;
no data at risk.

---

## L7 — Repeated skip / "verify manually" log noise, once PER PASS — CONFIRMED (UX, non-technical users)

All 8 personas run headless `daily_run.py` and read the console. `daily_run` defaults to
`--max-pages 2` (`daily_run.py:214`), which runs a **page-1 baseline pass**
(`:316-325`) then the **full pass** (`:329`), plus a **rescore pass** (`:462`). Each pass
re-invokes the careers/keyless path, and these warnings are unconditional `print()`s
with no run-once guard:

- `scrape/direct_scraper.py:122` — `[direct] <company>: link extraction + JSON-LD — verify results manually` (once per direct company per pass)
- `scrape/discoverer.py:37` — `[discover] WARNING: BRAVE_SEARCH_API_KEY unset ...`
- `search/jooble_client.py:29`, `search/careerjet_client.py:29` — per-source "skipped, unset key" WARNINGs
- `search/cli.py:72-157` — `[<source>] Skipping — <reason>` for adzuna/jsearch/usajobs/careeronestop/serpapi

Result matches nurse-boise / teacher-columbus reports: dozens of duplicated skip/verify
lines for a ~29-49-job run, burying real signal for a user who can't tell benign noise
from a failure. **Fix (low):** dedup the keyless/unkeyed-source and "verify manually"
warnings to once per run (a module-level `set()` of already-warned keys, reset at run
start, or emit them once during a preflight banner instead of inside per-pass client
construction). This is presentation only — no behavior change to scraping.

---

## What a user could NOT do from the GUI that agents did via API (persona narratives)

Checked against `gui.py` wiring — the GUI is close to complete:

- **Contacts / referral CRM** (`db.add_contact`, `contacts_for_company`,
  `referral_hint`) is fully in the service layer and the referral _hint_ renders in the
  JobDialog (`gui.py:283`), but I found no GUI **Add-Contact** dialog wired to
  `add_contact` in the reviewed surface — agents added contacts via the API. If there's
  no Contacts entry form in the GUI, the referral hint can never populate for a
  GUI-only user (they can't record who they know). Worth a quick confirm; if absent,
  it's a missing product surface for the highest-conversion channel the app itself
  promotes.
- Interview rounds, per-stage notes, offer fields, all statuses (incl. accepted/
  ghosted/withdrawn), timeline, ICS export, follow-up/deadline: **all reachable from
  GUI buttons** (JobDialog `gui.py:340-410`, quick-status `:722/:876`). No gap.
- Nurse/consultant flagged that rounds+offer fields are editable only inside the
  double-click JobDialog, not the list quick-status dropdown — a discoverability nit,
  not a missing capability.

---

## Verdict

The application cycle is **functionally complete and durable** across all 8 personas —
this lens found zero cycle-breaking bugs. The issues are (in order): one persistent
global-state side effect (L1, ~1 line), one silent-empty-Top-Picks route mismatch (L2),
one silent data-loss trap (L3), and a cluster of coherence/cosmetic/log-hygiene items
(L4-L7). L1, L2, L3 are the ones that erode trust and are all low effort.
