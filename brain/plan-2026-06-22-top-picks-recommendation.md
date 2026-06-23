# Top Picks Recommendation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an AI view the entire inbox in one snapshot, rank it, and write back a top-X shortlist that surfaces in a new GUI "Top Picks" tab.

**Architecture:** The AI's shortlist rides in each inbox row's existing `extras` JSON (`rank` + `rec_batch`) — no DB migration. One service helper defines that shape; the MCP path, the file round-trip, and the Top Picks view all read/write through it. Latest `rec_batch` wins, so a fresh run supersedes the prior shortlist.

**Tech Stack:** Python 3.13, SQLite (stdlib `sqlite3`), tkinter/ttk GUI, FastMCP, pytest.

## Global Constraints

- **READ-ONLY on real data.** Every test that touches the DB MUST `monkeypatch.setattr(db, "DB_PATH", tmp_path / "tracker.db")` first. Never read or write `projects/*/tracker.db` or the repo-root `tracker.db`.
- **No DB schema migration.** `rank` and `rec_batch` live inside the existing `inbox.extras` TEXT column. Do not add columns or bump `SCHEMA_VERSION`.
- **`RERANK_CSV_COLUMNS` is frozen** (golden-file test `test_columns_frozen_exact_order`). Do not reorder/rename CSV columns — only prompt wording changes.
- **`list_inbox` defaults unchanged** (`limit=20`, `unscored_only=True`). Only `limit=0` (= all) and the additive output keys `rank` + `job_key` are new.
- **Extras shape defined once** in `tracker/service.py::rank_patch` — keys `rank` (int), `rec_batch` (str), optional `tags` (str). No second definition anywhere.
- **Commits are gated on the user** (standing rule: commit only when asked). The per-task `git commit` steps are the recommended cadence; at execution time, batch or confirm per the user's instruction. On Windows PowerShell, embedded double-quotes in `-m` get mangled — use Git Bash or `git commit -F <file>`.
- **Finish green:** the full suite (currently 537 passing) must pass at the end. Run `py -m pytest -q`.

---

### Task 1: Data layer — extras merge, rank read/write, `top_picks`

**Files:**

- Modify: `tracker/db.py` (add `inbox_merge_extras`, after `inbox_set_extras` ~line 495)
- Modify: `tracker/service.py` (add `import json` at top; add a "Top Picks" section)
- Test: `tests/test_top_picks.py` (create)

**Interfaces:**

- Produces:
  - `db.inbox_merge_extras(inbox_id: int, patch: dict) -> None` — JSON-merge `patch` into the row's `extras`, preserving keys not in `patch`.
  - `service.new_rec_batch() -> str` — UTC ISO second-precision stamp.
  - `service.rank_patch(rank: int, batch: str, tags: str | None = None) -> dict` — the canonical extras shape `{"rank", "rec_batch"[, "tags"]}`.
  - `service.read_rank(row: dict) -> int` — `rank` from `extras`, or `-1`.
  - `service.top_picks(limit: int = 10) -> list[dict]` — latest-batch ranked rows, rank-ascending, capped (`0` = all); each row augmented with int `rank`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_top_picks.py`:

```python
import json
import pytest
import tracker.db as db
from tracker import service
from models import JobResult


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "tracker.db")
    db.init_db()
    return db.DB_PATH


def _job(url, title="Software Developer", company="Acme"):
    return JobResult(title=title, company=company, location="Cincinnati, OH",
                     salary_min=None, salary_max=None, description="controls",
                     url=url, source_keyword="", created="2026-06-21",
                     source_api="adzuna", score=70)


def test_merge_extras_preserves_other_keys(tmp_db):
    db.inbox_add_many([_job("https://x/1")])
    iid = db.inbox_all()[0]["id"]
    db.inbox_set_extras(iid, '{"tags":"plc"}')
    db.inbox_merge_extras(iid, {"rank": 1, "rec_batch": "B1"})
    extras = json.loads(db.inbox_all()[0]["extras"])
    assert extras == {"tags": "plc", "rank": 1, "rec_batch": "B1"}


def test_merge_extras_tolerates_garbage_blob(tmp_db):
    db.inbox_add_many([_job("https://x/1")])
    iid = db.inbox_all()[0]["id"]
    db.inbox_set_extras(iid, "not json")
    db.inbox_merge_extras(iid, {"rank": 2, "rec_batch": "B"})
    assert json.loads(db.inbox_all()[0]["extras"]) == {"rank": 2, "rec_batch": "B"}


def test_read_rank_missing_is_minus_one(tmp_db):
    db.inbox_add_many([_job("https://x/1")])
    assert service.read_rank(db.inbox_all()[0]) == -1


def test_top_picks_orders_by_rank_and_caps(tmp_db):
    db.inbox_add_many([_job("https://x/1", "A"), _job("https://x/2", "B"),
                       _job("https://x/3", "C")])
    rows = db.inbox_all()
    b = service.new_rec_batch()
    db.inbox_merge_extras(rows[0]["id"], service.rank_patch(2, b))
    db.inbox_merge_extras(rows[1]["id"], service.rank_patch(1, b))
    db.inbox_merge_extras(rows[2]["id"], service.rank_patch(3, b))
    assert [p["rank"] for p in service.top_picks(2)] == [1, 2]
    assert len(service.top_picks(0)) == 3


def test_top_picks_latest_batch_supersedes(tmp_db):
    db.inbox_add_many([_job("https://x/1", "A"), _job("https://x/2", "B")])
    rows = db.inbox_all()
    db.inbox_merge_extras(rows[0]["id"],
                          service.rank_patch(1, "2026-06-22T00:00:00+00:00"))
    db.inbox_merge_extras(rows[1]["id"],
                          service.rank_patch(1, "2026-06-22T01:00:00+00:00"))
    picks = service.top_picks(0)
    assert len(picks) == 1 and picks[0]["id"] == rows[1]["id"]


def test_top_picks_empty_when_unranked(tmp_db):
    db.inbox_add_many([_job("https://x/1")])
    assert service.top_picks() == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `py -m pytest tests/test_top_picks.py -q`
Expected: FAIL — `AttributeError: module 'tracker.db' has no attribute 'inbox_merge_extras'` (and `service.top_picks` / `rank_patch` / `new_rec_batch` / `read_rank` missing).

- [ ] **Step 3: Add `inbox_merge_extras` to `tracker/db.py`**

Insert immediately after `inbox_set_extras` (ends ~line 495):

```python
def inbox_merge_extras(inbox_id: int, patch: dict):
    """Merge keys into an inbox row's extras JSON, preserving keys not in
    `patch` (so a rank-only write keeps an existing `tags`). Tolerant of a
    missing or non-dict current blob (treated as {})."""
    import json
    with get_conn() as conn:
        row = conn.execute("SELECT extras FROM inbox WHERE id=?",
                           (inbox_id,)).fetchone()
        current = {}
        if row and row["extras"]:
            try:
                loaded = json.loads(row["extras"])
                if isinstance(loaded, dict):
                    current = loaded
            except (ValueError, TypeError):
                current = {}
        current.update(patch)
        conn.execute("UPDATE inbox SET extras=? WHERE id=?",
                     (json.dumps(current), inbox_id))
        conn.commit()
```

- [ ] **Step 4: Add the Top Picks section to `tracker/service.py`**

Add `import json` near the top (after the stdlib imports, before `from tracker import db`). Then append at the end of the file:

```python
# ── Top Picks (AI shortlist over the whole inbox) ─────────────────────────────

def new_rec_batch() -> str:
    """A fresh recommendation-batch stamp (UTC ISO, second precision). One per
    set_fit_scores / import call, so a newer AI run's picks supersede the old."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def rank_patch(rank: int, batch: str, tags: str | None = None) -> dict:
    """The extras keys a shortlist write stamps onto an inbox row. ONE place
    defines the shape so the MCP and file-import paths agree."""
    patch = {"rank": int(rank), "rec_batch": batch}
    if tags is not None and str(tags).strip():
        patch["tags"] = str(tags)
    return patch


def _parse_extras(raw) -> dict:
    if not raw:
        return {}
    try:
        d = json.loads(raw)
        return d if isinstance(d, dict) else {}
    except (ValueError, TypeError):
        return {}


def read_rank(row: dict) -> int:
    """The AI shortlist rank on an inbox row (1=best), or -1 if unranked/bad."""
    try:
        return int(_parse_extras(row.get("extras")).get("rank"))
    except (TypeError, ValueError):
        return -1


def _rec_batch_of(row: dict) -> str:
    return str(_parse_extras(row.get("extras")).get("rec_batch", "") or "")


def top_picks(limit: int = 10) -> list[dict]:
    """The current AI recommendation: inbox rows in the latest rec_batch,
    ordered by rank ascending, capped at `limit` (0 = every ranked row). Each
    returned dict is an inbox row augmented with an int 'rank' key for display.
    Returns [] when nothing has been ranked yet."""
    ranked = [(read_rank(r), r) for r in db.inbox_all()]
    ranked = [(rk, r) for rk, r in ranked if rk >= 1]
    if not ranked:
        return []
    latest = max(_rec_batch_of(r) for _, r in ranked)
    picks = [dict(r, rank=rk) for rk, r in ranked if _rec_batch_of(r) == latest]
    picks.sort(key=lambda r: r["rank"])
    if limit and limit > 0:
        picks = picks[:limit]
    return picks
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `py -m pytest tests/test_top_picks.py -q`
Expected: PASS (6 passed).

- [ ] **Step 6: Commit**

```bash
git add tracker/db.py tracker/service.py tests/test_top_picks.py
git commit -m "feat(tracker): rank in extras + top_picks recommendation read"
```

---

### Task 2: File round-trip carries rank + rec_batch

**Files:**

- Modify: `rerank/import_.py` (`import_scores`; add `_extras_for` helper)
- Test: `tests/rerank/test_import.py` (add 1 test), `tests/rerank/test_service_rerank.py` (add 1 end-to-end test)

**Interfaces:**

- Consumes: `service.new_rec_batch`, `service.rank_patch` (Task 1).
- Produces: `import_scores` now stamps `update["extras"]` as `json.dumps(rank_patch(new_rank, batch, tags))` (one `batch` per call). `apply_rerank_scores` is unchanged — it still writes `update["extras"]` verbatim via `inbox_set_extras`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/rerank/test_import.py`:

```python
def test_import_writes_rank_and_rec_batch_extras(tmp_path):
    import json
    seen, writer = _capture()
    body = "job_key,new_fit,new_rank,tags\nk1,88,1,plc\n"
    import_scores(_write_csv(tmp_path, body), _rows_by_key(), _apply=writer)
    extras = json.loads(seen["updates"][0]["extras"])
    assert extras["rank"] == 1 and extras["tags"] == "plc" and extras["rec_batch"]


def test_import_blank_rank_no_rank_key(tmp_path):
    import json
    seen, writer = _capture()
    body = "job_key,new_fit,new_rank,tags\nk1,88,,plc\n"
    import_scores(_write_csv(tmp_path, body), _rows_by_key(), _apply=writer)
    extras = json.loads(seen["updates"][0]["extras"])
    assert extras == {"tags": "plc"}      # tags-only, no rank/rec_batch
```

Add to `tests/rerank/test_service_rerank.py`:

```python
def test_import_to_top_picks_end_to_end(tmp_db, tmp_path):
    from rerank.import_ import import_scores
    db.inbox_add_many([_job("https://x.co/1", title="A"),
                       _job("https://x.co/2", title="B")])
    m = service.inbox_rows_by_key()
    keys = list(m.keys())
    p = tmp_path / "ret.csv"
    p.write_text("job_key,new_fit,new_rank\n"
                 f"{keys[0]},90,2\n{keys[1]},95,1\n", encoding="utf-8")
    res = import_scores(p, m)
    assert res.updated == 2
    picks = service.top_picks(0)
    assert [pp["rank"] for pp in picks] == [1, 2]
    assert picks[0]["fit"] == 95
```

(`_job` in that file takes `title=`/`company=` kwargs — pass `title=` as shown.)

- [ ] **Step 2: Run to verify they fail**

Run: `py -m pytest tests/rerank/test_import.py::test_import_writes_rank_and_rec_batch_extras tests/rerank/test_service_rerank.py::test_import_to_top_picks_end_to_end -q`
Expected: FAIL — current extras carries `new_rank` (string) not `rank`/`rec_batch`; `KeyError`/assertion on `extras["rank"]`.

- [ ] **Step 3: Rewrite the extras build in `rerank/import_.py`**

Add a module-level helper above `import_scores`:

```python
def _extras_for(rec, batch, service) -> str | None:
    """The extras JSON for one imported row: rank (mapped from new_rank) +
    rec_batch via service.rank_patch, plus tags. Tolerant of a bad rank cell —
    falls back to tags-only, then None."""
    rank_raw = rec.get("new_rank")
    tags = rec.get("tags")
    has_tags = bool(str(tags or "").strip())
    if str(rank_raw or "").strip():
        try:
            return json.dumps(service.rank_patch(
                _coerce_int(rank_raw), batch, tags if has_tags else None))
        except (ValueError, TypeError):
            pass
    if has_tags:
        return json.dumps({"tags": str(tags)})
    return None
```

In `import_scores`, after the `apply = _apply or _default_apply` line add:

```python
    from tracker import service
    batch = service.new_rec_batch()
```

Then replace the existing extras block:

```python
        update = {"id": row["id"], "new_fit": new_fit,
                  "fit_rationale": str(rec.get("fit_rationale", "") or "").strip()}
        extras = {k: rec.get(k) for k in ("new_rank", "tags")
                  if str(rec.get(k, "") or "").strip()}
        if extras:
            update["extras"] = json.dumps(extras)
        updates.append(update)
```

with:

```python
        update = {"id": row["id"], "new_fit": new_fit,
                  "fit_rationale": str(rec.get("fit_rationale", "") or "").strip()}
        extras = _extras_for(rec, batch, service)
        if extras:
            update["extras"] = extras
        updates.append(update)
```

- [ ] **Step 4: Run to verify they pass**

Run: `py -m pytest tests/rerank/ tests/test_top_picks.py -q`
Expected: PASS (all rerank tests, including the unchanged `test_import_csv_overwrite` and `test_apply_rerank_scores_persists_extras`).

- [ ] **Step 5: Commit**

```bash
git add rerank/import_.py tests/rerank/test_import.py tests/rerank/test_service_rerank.py
git commit -m "feat(rerank): import maps new_rank -> extras rank + rec_batch batch"
```

---

### Task 3: MCP — full snapshot + rank in/out

**Files:**

- Modify: `mcp_server.py` (`list_inbox`, `set_fit_scores`)
- Test: `tests/test_mcp_server.py` (add 2 tests)

**Interfaces:**

- Consumes: `service.read_rank`, `service.rank_patch`, `service.new_rec_batch`, `db.inbox_merge_extras`, `rerank.schema._job_key_for_row`.
- Produces: `list_inbox(limit=0)` returns ALL rows; each row gains `rank` + `job_key`. `set_fit_scores` items accept optional `"rank"`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_mcp_server.py`:

```python
def test_list_inbox_limit_zero_returns_all_with_rank(monkeypatch):
    rows = [{"id": i, "title": "T", "company": "C", "fit": -1, "score": 70,
             "extras": ('{"rank":1,"rec_batch":"B"}' if i == 1 else "")}
            for i in (1, 2, 3)]
    monkeypatch.setattr(mcp_server.db, "inbox_all", lambda: rows)
    out = mcp_server.list_inbox(limit=0, unscored_only=False)
    assert len(out) == 3
    by_id = {r["id"]: r for r in out}
    assert by_id[1]["rank"] == 1 and by_id[2]["rank"] == -1
    assert all(r["job_key"] for r in out)


def test_set_fit_scores_persists_rank(monkeypatch):
    fits, patches = [], []
    monkeypatch.setattr(mcp_server.db, "inbox_set_fit",
                        lambda i, f, r: fits.append((i, f, r)))
    monkeypatch.setattr(mcp_server.db, "inbox_merge_extras",
                        lambda i, p: patches.append((i, p)))
    out = mcp_server.set_fit_scores([
        {"id": 1, "fit": 90, "rationale": "x", "rank": 1},
        {"id": 2, "fit": 80, "rationale": "y"},   # no rank -> no merge
    ])
    assert out["applied"] == 2
    assert len(patches) == 1 and patches[0][0] == 1
    assert patches[0][1]["rank"] == 1 and patches[0][1]["rec_batch"]
```

- [ ] **Step 2: Run to verify they fail**

Run: `py -m pytest tests/test_mcp_server.py -q`
Expected: FAIL — `list_inbox` output has no `rank`/`job_key`; `set_fit_scores` does not call `inbox_merge_extras`.

- [ ] **Step 3: Extend `list_inbox` in `mcp_server.py`**

Replace the body of `list_inbox` (lines 84–98) with:

```python
    from tracker import service
    from rerank.schema import _job_key_for_row
    rows = db.inbox_all()
    out = []
    for r in rows:
        if unscored_only and (r.get("fit", -1) or -1) >= 0:
            continue
        out.append({
            "id": r["id"], "title": r["title"], "company": r["company"],
            "location": r.get("location", ""), "salary": r.get("salary_text", ""),
            "score": r.get("score", -1), "fit": r.get("fit", -1),
            "rank": service.read_rank(r), "job_key": _job_key_for_row(r),
            "url": r.get("url", ""),
            "description": (r.get("description", "") or "")[:800],
        })
        if limit and len(out) >= limit:   # limit=0 -> no cap (full snapshot)
            break
    return out
```

Also update the docstring's first line to mention `limit=0`:

```python
    """List inbox postings for YOU to rank. limit=0 returns the ENTIRE inbox in
    one snapshot — use it to see ALL relevant jobs before picking a top-X. Each
    row has id, title, company, location, salary, local `score`, current `fit`
    (-1 = unranked by you), your shortlist `rank` (-1 if not on it), the stable
    `job_key`, url, and a description snippet. Rank against preferences, then
    call set_fit_scores."""
```

- [ ] **Step 4: Extend `set_fit_scores` in `mcp_server.py`**

Replace the body of `set_fit_scores` (lines 106–114) with:

```python
    from tracker import service
    batch = service.new_rec_batch()
    applied = 0
    for s in scores:
        try:
            iid = int(s["id"])
            db.inbox_set_fit(iid, max(0, min(100, int(s["fit"]))),
                             str(s.get("rationale", "")))
        except (KeyError, TypeError, ValueError):
            continue
        applied += 1
        rank = s.get("rank")
        if rank is not None and str(rank).strip() != "":
            try:
                db.inbox_merge_extras(iid, service.rank_patch(int(rank), batch))
            except (TypeError, ValueError):
                pass
    return {"applied": applied}
```

Also update its docstring to document `rank`:

```python
    """Persist YOUR preference-ranking back to the inbox. `scores` is a list of
    {"id", "fit": 0-100, "rationale": "<2-line why>", "rank"?: 1=best}. An
    optional `rank` marks the row as part of your recommended shortlist; ranked
    rows surface in the app's Top Picks tab. Returns how many were applied."""
```

- [ ] **Step 5: Run to verify they pass**

Run: `py -m pytest tests/test_mcp_server.py tests/rerank/test_mcp_rerank.py -q`
Expected: PASS — incl. the unchanged `test_set_fit_scores_applies_and_clamps` (no `rank` → no merge) and `test_list_inbox_filters_unscored`.

- [ ] **Step 6: Commit**

```bash
git add mcp_server.py tests/test_mcp_server.py
git commit -m "feat(mcp): list_inbox(limit=0) full snapshot + rank in set_fit_scores"
```

---

### Task 4: Prompt — new_rank is the shortlist

**Files:**

- Modify: `rerank/schema.py` (`build_prompt`)
- Test: `tests/rerank/test_schema.py` (add 1 test)

**Interfaces:**

- Consumes: nothing new. Produces: prompt text that explains `new_rank` as the shortlist signal.

- [ ] **Step 1: Write the failing test**

Add to `tests/rerank/test_schema.py`:

```python
def test_prompt_explains_shortlist_rank():
    p = schema.build_prompt("x")
    assert "Top Picks" in p and "shortlist" in p.lower()
```

- [ ] **Step 2: Run to verify it fails**

Run: `py -m pytest tests/rerank/test_schema.py::test_prompt_explains_shortlist_rank -q`
Expected: FAIL — "Top Picks" not in the prompt.

- [ ] **Step 3: Reword the `new_rank` bullet in `build_prompt`**

Replace this line in `rerank/schema.py`:

```python
        "- `new_rank`: optional integer ordering within the batch (1 = best).",
```

with:

```python
        "- `new_rank`: rank your recommended shortlist 1..X (1 = best); leave it "
        "BLANK for jobs not on the shortlist. Only ranked rows appear in the "
        "app's Top Picks view, so rank as many as you'd recommend.",
```

- [ ] **Step 4: Run to verify it passes**

Run: `py -m pytest tests/rerank/test_schema.py -q`
Expected: PASS (all schema tests, incl. `test_build_prompt_anchors_to_preferences_and_fit_instructions`).

- [ ] **Step 5: Commit**

```bash
git add rerank/schema.py tests/rerank/test_schema.py
git commit -m "docs(rerank): prompt explains new_rank as the Top Picks shortlist"
```

---

### Task 5: GUI — Export-for-AI scope toggle (entire inbox vs current view)

**Files:**

- Modify: `gui.py` (`InboxTab._build` AI-ranking bar; add `_export_rows`; `_export_for_ai`)
- Test: `tests/ui/test_export_scope.py` (create)

**Interfaces:**

- Produces: `InboxTab._export_scope` (`tk.StringVar`, default `"Entire inbox"`); `InboxTab._export_rows() -> list[dict]`.

- [ ] **Step 1: Write the failing test**

Create `tests/ui/test_export_scope.py`:

```python
import tkinter as tk
import pytest
import tracker.db as db
import gui


@pytest.fixture
def root_tmpdb(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "tracker.db")
    db.init_db()
    try:
        r = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    r.withdraw()
    gui.theme.apply_theme(r)
    yield r
    r.destroy()


def _row(i, score, location):
    return {"id": i, "score": score, "fit": -1, "title": f"T{i}", "company": "X",
            "location": location, "salary_text": "", "source": "s",
            "date_added": "2026-06-22", "board_count": -1, "description": "",
            "fit_why": "", "score_notes": "", "url": ""}


def test_export_scope_entire_vs_view(root_tmpdb):
    tab = gui.InboxTab(root_tmpdb)
    tab._all = [_row(1, 90, "Cincinnati, OH"), _row(2, 10, "Cincinnati, OH")]
    tab._f_location.set("All locations")   # isolate the min-score filter
    tab._f_minscore.set("50")              # view drops id 2
    tab._export_scope.set("Entire inbox")
    assert {r["id"] for r in tab._export_rows()} == {1, 2}
    tab._export_scope.set("Current view")
    assert {r["id"] for r in tab._export_rows()} == {1}
```

- [ ] **Step 2: Run to verify it fails**

Run: `py -m pytest tests/ui/test_export_scope.py -q`
Expected: FAIL — `AttributeError: 'InboxTab' object has no attribute '_export_scope'`.

- [ ] **Step 3: Add the scope control to the AI-ranking bar**

In `InboxTab._build`, immediately before the `theme.tip(theme.btn(abar, "Export for AI", ...))` line (~822), insert:

```python
        self._export_scope = tk.StringVar(value="Entire inbox")
        esc = ttk.Combobox(abar, textvariable=self._export_scope, state="readonly",
                           width=13, values=["Entire inbox", "Current view"])
        theme.tip(esc, "What to hand the AI: the whole inbox (so it can judge "
                       "relevance and pick your top matches), or just the rows "
                       "currently shown by your filters.")
        esc.pack(side="left", padx=(8, 0))
```

- [ ] **Step 4: Add `_export_rows` and use it in `_export_for_ai`**

Add a method just above `_export_for_ai`:

```python
    def _export_rows(self) -> list[dict]:
        """Rows to hand the AI: the entire inbox by default (so it can judge
        relevance over everything and pick a top-X), or just the current
        filtered view when chosen."""
        if self._export_scope.get() == "Current view":
            return self._filtered()
        return list(self._all)
```

In `_export_for_ai`, replace:

```python
        rows = self._filtered()   # export what's shown (honors Location + filters)
        if not rows:
            messagebox.showinfo("Nothing to export",
                                "No jobs match the current filters.")
            return
```

with:

```python
        rows = self._export_rows()
        if not rows:
            messagebox.showinfo(
                "Nothing to export",
                "The inbox is empty — run a search first."
                if self._export_scope.get() == "Entire inbox"
                else "No jobs match the current filters.")
            return
```

- [ ] **Step 5: Run to verify it passes**

Run: `py -m pytest tests/ui/test_export_scope.py -q`
Expected: PASS (skips only if no display).

- [ ] **Step 6: Commit**

```bash
git add gui.py tests/ui/test_export_scope.py
git commit -m "feat(ui): Export-for-AI scope toggle (entire inbox by default)"
```

---

### Task 6: GUI — Top Picks tab

**Files:**

- Modify: `gui.py` (add `TopPicksTab` class after `InboxTab`; wire into `App._build_tabs`, `_rebuild_tabs`, `_on_tab_changed`)
- Test: `tests/ui/test_top_picks_tab.py` (create)

**Interfaces:**

- Consumes: `tracker_service.top_picks` (Task 1), `tracker_service.track_job`, `tracker_service.dismiss_job`.
- Produces: `gui.TopPicksTab(parent, on_change=None)` with `_tree`, `_n() -> int`, `refresh()`, `_showing_empty: bool`.

- [ ] **Step 1: Write the failing tests**

Create `tests/ui/test_top_picks_tab.py`:

```python
import tkinter as tk
import pytest
import gui


@pytest.fixture
def root(monkeypatch):
    try:
        r = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    r.withdraw()
    gui.theme.apply_theme(r)
    yield r
    r.destroy()


def _picks():
    return [
        {"id": 1, "rank": 1, "title": "Software Developer", "company": "Acme",
         "location": "Cincinnati, OH", "fit": 92, "fit_why": "strong",
         "score": 70, "source": "adzuna", "url": "https://x/1"},
        {"id": 2, "rank": 2, "title": "Controls Eng", "company": "Beta",
         "location": "Remote", "fit": 85, "fit_why": "good",
         "score": 66, "source": "muse", "url": "https://x/2"},
    ]


def test_top_picks_renders_in_rank_order(root, monkeypatch):
    monkeypatch.setattr(gui.tracker_service, "top_picks", lambda n: _picks())
    tab = gui.TopPicksTab(root, on_change=None)
    assert list(tab._tree.get_children()) == ["1", "2"]
    assert tab._tree.set("1", "title") == "Software Developer"
    assert tab._showing_empty is False


def test_top_picks_empty_state(root, monkeypatch):
    monkeypatch.setattr(gui.tracker_service, "top_picks", lambda n: [])
    tab = gui.TopPicksTab(root, on_change=None)
    assert not tab._tree.get_children()
    assert tab._showing_empty is True


def test_top_picks_n_reads_all(root, monkeypatch):
    captured = {}
    monkeypatch.setattr(gui.tracker_service, "top_picks",
                        lambda n: captured.update(n=n) or [])
    tab = gui.TopPicksTab(root, on_change=None)
    tab._topn.set("All")
    tab.refresh()
    assert captured["n"] == 0
```

- [ ] **Step 2: Run to verify they fail**

Run: `py -m pytest tests/ui/test_top_picks_tab.py -q`
Expected: FAIL — `AttributeError: module 'gui' has no attribute 'TopPicksTab'`.

- [ ] **Step 3: Add `TopPicksTab` to `gui.py`**

Insert after the `InboxTab` class ends (just before the `# ── Search tab ──` comment ~line 1223):

```python
# ── Top Picks tab ─────────────────────────────────────────────────────────────
class TopPicksTab(ttk.Frame):
    """The AI's current shortlist over the whole inbox, best-first. Reads
    tracker_service.top_picks (rows carrying an int `rank`); this tab never runs
    AI itself — it shows whatever the round-trip / API / MCP path ranked."""

    _COLS = [
        ("rank",     "#",         40, "center"),
        ("fit",      "Fit",       45, "center"),
        ("title",    "Title",    300, "w"),
        ("company",  "Company",  150, "w"),
        ("location", "Location", 140, "w"),
        ("why",      "Why",      340, "w"),
        ("score",    "Score",     55, "center"),
        ("source",   "Source",    80, "w"),
    ]

    def __init__(self, parent, on_change=None):
        super().__init__(parent)
        self._rows: dict[str, dict] = {}
        self._on_change = on_change
        self._showing_empty = False
        self._build()
        self.refresh()

    def _n(self) -> int:
        v = self._topn.get()
        return 0 if v == "All" else int(v)

    def _build(self):
        theme.header_bar(self, "Top Picks",
                         "The AI's shortlist over your whole inbox, best-first.")
        theme.tip_strip(
            self, "Ask an AI to rank your inbox (Inbox ▸ Export for AI, or the "
                  "find-jobs skill). The ones it recommends land here, ordered "
                  "best-first. Track the ones you like.")

        bar = tk.Frame(self, bg=theme.WINDOW)
        bar.pack(fill="x", padx=6, pady=(6, 0))
        tk.Label(bar, text="Show top:", bg=theme.WINDOW, fg=theme.INK,
                 font=theme.FONT_SM).pack(side="left")
        self._topn = tk.StringVar(value="10")
        ncb = ttk.Combobox(bar, textvariable=self._topn, state="readonly",
                           width=5, values=["10", "15", "20", "25", "50", "All"])
        ncb.pack(side="left", padx=(2, 10))
        ncb.bind("<<ComboboxSelected>>", lambda _e: self.refresh())
        theme.btn(bar, "Refresh", self.refresh, "ghost").pack(side="left")

        tf = ttk.Frame(self)
        tf.pack(fill="both", expand=True, padx=6, pady=2)
        self._tree = ttk.Treeview(tf, columns=[c[0] for c in self._COLS],
                                  show="headings", selectmode="extended")
        for col, label, width, anchor in self._COLS:
            self._tree.heading(col, text=label)
            self._tree.column(col, width=width, anchor=anchor, minwidth=40)
        theme.zebra(self._tree)
        vsb = ttk.Scrollbar(tf, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self._tree.bind("<Double-1>", lambda _e: self._open_url())
        self._tree.bind("t", lambda _e: self._track())
        self._tree.bind("d", lambda _e: self._dismiss())
        self._tree.bind("o", lambda _e: self._open_url())

        # Empty-state hint, packed only when there are no picks.
        self._empty = tk.Label(
            self, bg=theme.WINDOW, fg=theme.MUTED, font=theme.FONT_SM, justify="left",
            text="No AI picks yet — go to Inbox ▸ Export for AI (or run a "
                 "re-rank), then come back.")

        abar = tk.Frame(self, bg=theme.WINDOW, pady=6)
        abar.pack(fill="x", padx=6, side="bottom")
        theme.tip(theme.btn(abar, "Track \N{BLACK RIGHT-POINTING SMALL TRIANGLE} Interested",
                            self._track, "accent"),
                  "Move the selected job(s) to your Apply Queue.").pack(side="left", padx=2)
        theme.tip(theme.btn(abar, "Dismiss", self._dismiss, "ghost"),
                  "Hide the selected job(s) from all future searches.").pack(side="left", padx=2)
        theme.btn(abar, "Open", self._open_url, "ghost").pack(side="left", padx=2)
        self._status = tk.Label(abar, text="", bg=theme.WINDOW, fg=theme.MUTED,
                                font=theme.FONT_SM)
        self._status.pack(side="left", padx=10)

    def refresh(self):
        picks = tracker_service.top_picks(self._n())
        self._rows = {}
        for iid in self._tree.get_children():
            self._tree.delete(iid)
        for i, r in enumerate(picks):
            iid = str(r["id"])
            self._rows[iid] = r
            self._tree.insert("", "end", iid=iid, tags=(theme.row_tag(i),), values=(
                r["rank"],
                r["fit"] if r.get("fit", -1) >= 0 else "",
                r["title"], r["company"], r.get("location", ""),
                (r.get("fit_why") or "")[:200],
                r["score"] if r.get("score", -1) >= 0 else "",
                r.get("source", "")))
        self._showing_empty = not picks
        if self._showing_empty:
            self._empty.pack(fill="x", padx=14, pady=8)
        else:
            self._empty.pack_forget()
        if self._on_change:
            self._on_change()

    def _selected(self) -> list[dict]:
        return [self._rows[iid] for iid in self._tree.selection()
                if iid in self._rows]

    def _track(self):
        sel = self._selected()
        if not sel:
            messagebox.showinfo("No selection", "Select a row first.")
            return
        n = sum(1 for r in sel if tracker_service.track_job(r["id"]) is not None)
        set_status(self._status, f"Tracked {n} job(s).", "ok")
        self.refresh()

    def _dismiss(self):
        sel = self._selected()
        if not sel:
            messagebox.showinfo("No selection", "Select a row first.")
            return
        for r in sel:
            tracker_service.dismiss_job(r["id"])
        set_status(self._status, f"Dismissed {len(sel)} job(s).", "muted")
        self.refresh()

    def _open_url(self):
        for r in self._selected()[:5]:
            if r.get("url"):
                webbrowser.open(r["url"])
```

- [ ] **Step 4: Wire `TopPicksTab` into `App`**

In `App._build_tabs`, after `self._inbox = InboxTab(...)` add the instance, and add it to the notebook right after Inbox:

```python
        self._inbox   = InboxTab(self._nb, on_change=self._update_badges)
        self._toppicks = TopPicksTab(self._nb, on_change=self._update_badges)
        self._search  = SearchTab(self._nb)
```

and:

```python
        self._nb.add(self._inbox,    text="Inbox")
        self._nb.add(self._toppicks, text="Top Picks")
        self._nb.add(self._search,   text="Search")
```

In `App._rebuild_tabs`, add `self._toppicks` to the destroy tuple:

```python
        for tab in (self._inbox, self._toppicks, self._search, self._queue,
                    self._tracker, self._resume, self._guide):
            tab.destroy()
```

In `App._on_tab_changed`, add a branch so the shortlist refreshes when shown:

```python
        elif current is self._toppicks:
            self._toppicks.refresh()
```

(Place it alongside the existing `self._queue` / `self._tracker` branches.)

- [ ] **Step 5: Run to verify they pass**

Run: `py -m pytest tests/ui/test_top_picks_tab.py -q`
Expected: PASS (skips only if no display).

- [ ] **Step 6: Commit**

```bash
git add gui.py tests/ui/test_top_picks_tab.py
git commit -m "feat(ui): Top Picks tab showing the AI shortlist best-first"
```

---

### Task 7: find-jobs skill — snapshot-then-rank playbook

**Files:**

- Modify: `claude-code/skills/find-jobs/SKILL.md`

**Interfaces:** none (documentation for the MCP-driving AI). Reflects Task 3.

- [ ] **Step 1: Rewrite the Workflow + Notes sections**

Replace the `## Workflow` and `## Notes` sections of `claude-code/skills/find-jobs/SKILL.md` with:

```markdown
## Workflow

1. **Read preferences** — call `get_preferences`. Note `profile_md` (what they want,
   in their own words) and `hard_filters` (already enforced by search).
2. **Search** (when asked to find new jobs, or the inbox is thin) — call
   `search_jobs` with the user's keywords/location, or no args for their config
   defaults. It hard-gates, scores, and adds new postings to the inbox.
3. **Pull the WHOLE inbox in one snapshot** — call
   `list_inbox(limit=0, unscored_only=false)`. This returns every posting with its
   signal (title, company, location, salary, local `score`, current `fit`, your
   `rank`, `job_key`, a description snippet). You decide what's relevant — don't
   rely on a pre-filter.
4. **Judge & rank** — score each posting 0–100 against `profile_md` AND the user's
   background (Guide: 90+ apply today · 70–89 strong · 50–69 stretch · <50 skip).
   Then choose the **top X** to recommend (default 10, or whatever the user asked
   for) and order them 1..X, 1 = best. Be honest; flag red flags (clearance,
   seniority mismatch, contract-only, misleading title).
5. **Persist** — call `set_fit_scores` with `[{"id", "fit", "rationale", "rank"}, ...]`.
   Give `rank` 1..X to your shortlist; omit `rank` for everything else. Ranked rows
   supersede the previous shortlist and appear in the app's **Top Picks** tab.
6. **Present** — show the top X best-first: `# · title · company · location · fit ·
one-line why`. Tell them these are now in the **Top Picks** tab. Offer to
   `track_job` the ones they like.

## Notes

- One snapshot is enough: `list_inbox(limit=0, unscored_only=false)` returns the
  full inbox, so rank everything in a single pass rather than batching.
- `track_job(inbox_id)` promotes a posting to their tracker; `dismiss_job(inbox_id)`
  hides it from future searches.
- A fresh `set_fit_scores` run with new `rank`s replaces the old Top Picks shortlist.
- Never invent postings — only rank what `list_inbox` actually returns.
```

- [ ] **Step 2: Sanity-check the file**

Run: `py -c "import pathlib; t=pathlib.Path('claude-code/skills/find-jobs/SKILL.md').read_text(encoding='utf-8'); assert 'limit=0' in t and 'Top Picks' in t; print('ok')"`

Expected: prints `ok` (the file contains `limit=0` and `Top Picks`).

- [ ] **Step 3: Commit**

```bash
git add claude-code/skills/find-jobs/SKILL.md
git commit -m "docs(skill): find-jobs snapshots whole inbox then ranks a top-X"
```

---

### Final: full suite + manual smoke

- [ ] **Step 1: Run the whole suite**

Run: `py -m pytest -q`
Expected: PASS — 537 prior + new tests (Task 1: 6, Task 2: 3, Task 3: 2, Task 4: 1, Task 5: 1, Task 6: 3) ≈ **553 passing**, 0 failed. GUI tests skip only on a headless box.

- [ ] **Step 2: Manual smoke (windowed — user runs)**

`py gui.py` → Inbox ▸ "Ask AI to rank these" or "Export for AI" (note the scope toggle defaults to **Entire inbox**) → import a ranked file → open the **Top Picks** tab → confirm the shortlist shows best-first, the "Show top N" selector trims it, Track/Dismiss work, and it looks right in **both light and dark** mode.

```

```
