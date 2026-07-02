# HANDOFF 2026-06-09 | Session 7 — Throughput Overhaul: Score → Inbox → Apply Queue

## SESSION SUMMARY

Rebuilt the tool around one goal: **find and apply to as many qualifying jobs as possible with minimum clicks**. The pipeline is now: scheduled daily search → local 0–100 match scoring → deduped Inbox → optional Claude fit-ranking via **copy-paste bridge (no API key needed)** → Apply Queue with one-click resume prompts and "Mark Applied ▸ Next". Two free no-key job sources added (The Muse, RemoteOK). Stayed in Python/Tkinter — a rewrite bought nothing.

**Design decisions confirmed with Alex:**

- **Assisted batch, never auto-submit** — tool ranks, preps docs, queues; Alex clicks Submit.
- **No Claude API key required** — clipboard bridge: tool copies a prompt, Alex pastes into claude.ai, pastes the JSON reply back. API path kept as optional upgrade (`ANTHROPIC_API_KEY` in `.env`).
- **Scheduled daily + manual** — `setup_schedule.bat` registers a 07:30 Task Scheduler run.

✅ **SMOKE TEST PASSED** (2026-06-09, after shell restored by switching to Opus 4.8):

- `py -m py_compile` all 13 modules → COMPILE OK
- import check of every new/modified module → OK
- scorer: good job 70 vs excluded sales job 0 (penalty applied) → OK
- bridge: `parse_fit_response` on fenced JSON, `_extract_json` on prose-wrapped → OK; fit prompt + profile_summary build
- DB (temp db): inbox migration, dedup, fit re-sort, `inbox_track`→application carries fit_score, `inbox_dismiss`→seen_urls filter → OK
- `gui.py` imports clean (Inbox/Search/ApplyQueue tabs wired)
- **Live `py daily_run.py --max-pages 1`**: 3564 raw → 649 deduped → 419 ≥40 → **399 new jobs in inbox**. TheMuse (88) + RemoteOK (168) both live.

Open GUI to triage: `py gui.py` (opens on Inbox, 399 waiting).

---

## WHAT GOT DONE

### 1. Local match scorer — `match/scorer.py` (new)

`score_job()` → 0–100: title 35 / skills 25 / salary 15 / location 15 / recency 10; −30 per `exclude_keywords` hit (noted in `score_notes`).

- Skill terms auto-extracted from the TECHNICAL SKILLS section of `experience.md` (memoized on file mtime).
- Missing salary = neutral 0.5, not zero. Salary below floor degrades smoothly.
- `score_jobs(results, ...)` scores in place and sorts best-first.
- `JobResult` gained `score: int = -1` and `score_notes: str` (models.py).

### 2. Claude copy-paste bridge — `claude_bridge.py` (new)

No API key anywhere in this path.

- `build_fit_prompt(jobs, profile)` — numbered batch (≤20 sensible), demands strict JSON `[{"i","fit","why","flags"}]` with scoring guide (clearance-required caps at 40).
- `parse_fit_response(text, n)` — strips fences/prose, clamps 0–100, skips malformed entries.
- `build_resume_prompt(posting, experience)` / `parse_resume_response()` — same JSON shape `resume/generator.py` produces, so the DOCX builder is shared.
- `to_clipboard()` uses Windows `clip` with UTF-16 encoding.
- `profile_summary()` condenses experience.md (skills + first 3 bullets per role) to keep fit prompts small.

### 3. Inbox — `tracker/db.py` + GUI tab

New `inbox` table, `norm_url UNIQUE` = dedup key. Helpers: `inbox_add_many` (skips tracked ∪ dismissed ∪ inboxed), `inbox_all` (orders by fit if present else score), `inbox_set_fit`, `inbox_track` (promotes → applications status=interested, carries score/fit), `inbox_dismiss`, `inbox_count`, `inbox_delete`.
Tracker `applications` gained `score`, `fit_score`, `fit_rationale` columns (self-migrating ALTER pattern).

### 4. Daily scheduled search — `daily_run.py` + `setup_schedule.bat` (new)

Headless: free sources only (`DAILY_SOURCES` in config.py — **jsearch deliberately excluded** to protect the 200/mo quota), scores everything, inserts jobs ≥ `DAILY_MIN_SCORE` (40, overridable via `daily_min_score` in user_config.json or `--min-score`) into the inbox. Logs to `output\daily_run.log`, never raises out of `log()`. Double-click `setup_schedule.bat` once to register 07:30 daily; remove with `schtasks /Delete /TN JobSearchDaily /F`.

### 5. Two new free sources (no keys)

- `search/themuse_client.py` — The Muse public API. **No keyword param** → keyword-blind cached fetch shared across all 10 keywords (keyword absent from cache key on purpose), client-side keyword filter. Engineering categories, 0-based pages, no salary data.
- `search/remoteok_client.py` — RemoteOK single JSON feed, cached once, `page>1` returns empty, legal-notice first element filtered, custom User-Agent required.
- Both wired into `search/cli.py` `ALL_SOURCES`, `user_config.json` sources, and `DAILY_SOURCES`.

### 6. GUI — now 5 tabs (`py gui.py`)

| Tab                  | Purpose                                                                                                                                                                                                                                                                                   |
| -------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Inbox (n)**        | Daily-run triage. Sorted by fit/score. Multi-select → Track ▸ Interested / Dismiss. **Copy Fit Prompt → paste into claude.ai → Paste Fit Results** writes fit+why back. Badge count in tab title.                                                                                         |
| **Search**           | Manual search. Score column first, sorted best-first. Keywords/location/min-salary prefilled from user_config.json, editable per run. Multi-select track/dismiss; skips already-seen.                                                                                                     |
| **Apply Queue**      | All status=interested, best fit first. Per job: Open Posting → Copy Resume Prompt → Paste Reply ▸ DOCX (resume + cover letter, company-slugged filenames) → **Mark Applied ▸ Next** (auto-advances). Fit prompt/results buttons here too. "Generate via API" appears only if key present. |
| **Job Tracker**      | Unchanged CRUD + status pipeline; date fields now validated (YYYY-MM-DD).                                                                                                                                                                                                                 |
| **Resume Generator** | Standalone: 1. Copy Prompt / 2. Paste Reply ▸ DOCX. API button only if key present.                                                                                                                                                                                                       |

Opens on Inbox if non-empty, else Search. New shared widgets: `PasteDialog` (modal paste box), `copy_or_warn`.

### 7. Search CLI upgrades

`--sort-by score` (new default) | `--min-score N` | scoring runs after tracked/dismissed filtering; hidden-count printed. CSV gained leading `score` column; HTML report gained color score badge (≥70 green / ≥40 orange / gray) + "Best match" sort dropdown option (default).

### 8. Resume service refactor — `resume/service.py`

Bridge is the default path: `build_prompt()` / `data_from_paste()` / `save_bundle_from_data()`. API path (`build_bundle`, `save_bundle`) kept, lazy-imports anthropic so it's not required. Filenames now `resume_{companyslug}_{date}.docx` — same-day batch applying can't collide.

---

## BUGS FOUND IN SELF-REVIEW (fixed, untested)

1. `App._update_badges` ran during `InboxTab.__init__` before any tabs existed → TclError. Guard: `if not self._nb.tabs(): return`.
2. InboxTab fit prompt rebuilt JobResults without salary → Claude saw "Not listed". Now prepends `Salary: {salary_text}` to description.

---

## NEW FILE MAP

```
match/scorer.py            local 0-100 scoring (+ match/__init__.py)
claude_bridge.py           copy-paste prompts/parsers, clipboard, profile summary
daily_run.py               headless scheduled search -> inbox
setup_schedule.bat         one-time Task Scheduler registration (07:30)
search/themuse_client.py   The Muse (free, no key)
search/remoteok_client.py  RemoteOK (free, no key)
```

Modified: `models.py`, `config.py`, `tracker/db.py`, `gui.py` (largest change), `search/cli.py`, `search/report_csv.py`, `search/templates/report.html`, `resume/service.py`, `user_config.json`.

---

## INTENDED DAILY WORKFLOW

1. 07:30 — Task Scheduler runs `daily_run.py` → fresh scored jobs land in Inbox.
2. Open `py gui.py` → Inbox tab. Skim by score.
3. (Optional) Copy Fit Prompt → claude.ai → Paste Fit Results → re-ranked by Claude fit.
4. Multi-select winners → **Track ▸ Interested**; junk → **Dismiss** (never resurfaces).
5. Apply Queue tab: top job → Open Posting → Copy Resume Prompt → claude.ai → Paste Reply ▸ DOCX → attach docs, submit on site → **Mark Applied ▸ Next**. Repeat down the list.

---

## OUTSTANDING

1. **Smoke test** (top of file) — nothing has been executed.
2. **Run `setup_schedule.bat` once** to register the daily task (may need Administrator).
3. `ANTHROPIC_API_KEY` in `.env` — still optional; bridge covers everything without it.
4. `BRAVE_SEARCH_API_KEY` — still optional (company discovery).
5. **Git: nothing committed.** Working tree now holds session-6 (2026-06-02 hardening) + this entire session. HEAD still `8fa925b`-era / last pushed `ae59a08` lineage on `master`.
6. Existing tests (76) not re-run; no tests written for the new modules yet — scorer and bridge parsers are the highest-value targets (`parse_fit_response`, `_extract_json`, `score_job` edge cases).

## ENVIRONMENT

- Python: `py`, global packages, Windows 11, repo `git@github.com:alex-zagorianos/Job-Program.git` (master)
- Model note: session ran on claude-fable-5 (released 2026-06-09, set as default); shell-tool safety classifier for it was down all session — the reason the smoke test is deferred.
