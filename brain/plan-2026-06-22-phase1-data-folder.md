# Phase 1 — Data Folder + Preferences Contract (Implementation Plan)

> **For agentic workers:** TDD. Each task: failing test → run (fail) → implement → run (pass) →
> commit. Steps use checkbox (`- [ ]`). Branch: `feat/phase1-data-folder`.

**Goal:** Externalize all user-editable state into one resolvable `USER_DATA_DIR`, and add the
`preferences.md` + `preferences.json` tailoring contract (with cheap hard-gating + migration from
`user_config.json`), without changing Alex's current dev workflow.

**Architecture:** `config.USER_DATA_DIR` becomes the single writable + user root. `workspace.BASE_DIR`
points at it (fixes frozen `_MEIPASS` writability). Bundle (`DATA_DIR`/`_MEIPASS`) holds read-only
templates used to scaffold an empty data folder on first run.

**Tech Stack:** Python 3.12 (`py`), pytest, stdlib only (no new deps).

## Global Constraints

- `py` not `python`; commit trailers (Co-Authored-By + Claude-Session); no push (held by user).
- Dev/non-frozen back-compat: `USER_DATA_DIR` = repo root (current files-at-root setup unchanged).
- `--data <path>` / `JOBPROGRAM_DATA` env overrides everywhere; frozen default = `<exe>/data` ›
  `%LOCALAPPDATA%/JobProgram`.
- Tests stay green (≥294 baseline before Phase 1 tasks; each task adds tests).

## File structure

- Modify `config.py`: add `_get_user_data_dir()` + `USER_DATA_DIR`; add `PREFERENCES_MD`,
  `PREFERENCES_JSON`, `SECRETS_DIR`; repoint `EXPERIENCE_FILE`, `COMPANIES_JSON`, `USER_CONFIG_JSON`,
  `CACHE_DIR`, `OUTPUT_DIR` at `USER_DATA_DIR`.
- Modify `workspace.py`: `BASE_DIR = config.USER_DATA_DIR` (call-time monkeypatchable; tests override).
- Create `preferences.py`: `load_preferences()`, `Preferences` shape, `hard_gate(jobs, prefs)`,
  `migrate_from_user_config()`.
- Create `data_templates/`: `experience.template.md`, `preferences.template.md`, `preferences.json`.
- Create `userdata.py`: `scaffold(dir)` — copy any missing template into the data folder; idempotent.
- Tests: `tests/test_userdata.py`, `tests/test_preferences.py`.

---

## Task 1: USER_DATA_DIR resolution (config.py)

**Files:** Modify `config.py`; Test `tests/test_userdata.py`.

**Interfaces — Produces:** `config._get_user_data_dir() -> Path`, `config.USER_DATA_DIR: Path`,
`config.PREFERENCES_MD`, `config.PREFERENCES_JSON`, `config.SECRETS_DIR`.

- [ ] **Step 1 — failing test** (`tests/test_userdata.py`):

```python
import importlib, sys
from pathlib import Path
import config

def test_user_data_dir_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("JOBPROGRAM_DATA", str(tmp_path / "mydata"))
    assert config._get_user_data_dir() == Path(str(tmp_path / "mydata"))

def test_user_data_dir_dev_is_repo_root(monkeypatch):
    monkeypatch.delenv("JOBPROGRAM_DATA", raising=False)
    monkeypatch.setattr(config, "_is_frozen", lambda: False)
    assert config._get_user_data_dir() == Path(config.__file__).parent

def test_user_data_dir_frozen_prefers_exe_data(monkeypatch, tmp_path):
    monkeypatch.delenv("JOBPROGRAM_DATA", raising=False)
    monkeypatch.setattr(config, "_is_frozen", lambda: True)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "JobProgram.exe"))
    assert config._get_user_data_dir() == tmp_path / "data"
```

- [ ] **Step 2 — run, expect fail** (`_get_user_data_dir` undefined).
- [ ] **Step 3 — implement** in `config.py` (after `_get_writable_dir`):

```python
def _get_user_data_dir() -> Path:
    """External, user-editable data root: experience/preferences/companies/db/
    cache/output/secrets live here. JOBPROGRAM_DATA overrides. Frozen default:
    <exe>/data (writable) else %LOCALAPPDATA%/JobProgram. Dev: the repo root, so
    the current files-at-root setup is unchanged."""
    override = os.getenv("JOBPROGRAM_DATA")
    if override:
        return Path(override)
    if _is_frozen():
        exe_data = Path(sys.executable).parent / "data"
        return exe_data if _dir_writable(exe_data) else Path(os.getenv("LOCALAPPDATA", ".")) / "JobProgram"
    return Path(__file__).parent

USER_DATA_DIR = _get_user_data_dir()
PREFERENCES_MD   = USER_DATA_DIR / "preferences.md"
PREFERENCES_JSON = USER_DATA_DIR / "preferences.json"
SECRETS_DIR      = USER_DATA_DIR / "secrets"
```

Then repoint: `EXPERIENCE_FILE = USER_DATA_DIR / "experience.md"`, `COMPANIES_JSON = USER_DATA_DIR /
"companies.json"`, `USER_CONFIG_JSON = USER_DATA_DIR / "user_config.json"`, `CACHE_DIR =
USER_DATA_DIR / "cache"`, `OUTPUT_DIR = USER_DATA_DIR / "output"`. (In dev these all equal the repo
root, so no behavior change.)

- [ ] **Step 4 — run, expect pass** + full suite green.
- [ ] **Step 5 — commit** `feat(config): external USER_DATA_DIR resolution`.

## Task 2: workspace roots under USER_DATA_DIR

**Files:** Modify `workspace.py`; Test `tests/test_userdata.py`.

- [ ] Test: `workspace.BASE_DIR == config.USER_DATA_DIR` at import (and projects resolve under it).
- [ ] Implement: `import config` then `BASE_DIR = config.USER_DATA_DIR` (keep the call-time helpers;
      tests still `monkeypatch.setattr(workspace, "BASE_DIR", tmp_path)`). Watch import order (config
      has no workspace dep → no cycle).
- [ ] Suite green → commit `feat(workspace): root projects under USER_DATA_DIR (frozen-safe)`.

## Task 3: preferences module — load + shape

**Files:** Create `preferences.py`; Test `tests/test_preferences.py`.

**Produces:** `preferences.load() -> dict` returning `{"profile_md": str, "hard": dict}` where `hard` =
`{salary_min:int|None, locations:list[str], remote_ok:bool, work_auth:str, dealbreakers:list[str],
seniority_exclude:list[str]}` with safe defaults when files are absent.

- [ ] Test: missing files → defaults (`profile_md == ""`, `hard` all-permissive); present files → parsed.
- [ ] Implement `load(prefs_md=None, prefs_json=None)` reading `config.PREFERENCES_MD/JSON`, JSON-tolerant.
- [ ] Commit `feat(preferences): load profile.md + hard-filter json with defaults`.

## Task 4: hard_gate

**Files:** Modify `preferences.py`; Test `tests/test_preferences.py`.

**Produces:** `preferences.hard_gate(jobs, hard) -> list` dropping jobs below `salary_min` (when the
job has a known salary), outside `locations` (unless `remote_ok` and the job is remote), or matching a
`dealbreakers`/`seniority_exclude` term in the title. Jobs with unknown salary are KEPT (don't over-cut).

- [ ] Tests: salary floor cuts low-known, keeps unknown; dealbreaker term in title cuts; remote_ok keeps
      remote when location mismatched.
- [ ] Implement using `models.JobResult` fields (`salary_min`, `location`, `title`).
- [ ] Commit `feat(preferences): cheap hard-gate before AI ranking`.

## Task 5: migration from user_config.json

**Files:** Modify `preferences.py`; Test `tests/test_preferences.py`.

**Produces:** `preferences.migrate_from_user_config(cfg: dict) -> dict` mapping legacy `salary_min`,
`location`, `exclude_titles`/`seniority_exclude`, `keywords` into the new `{profile_md, hard}` shape
(keywords → a generated profile_md hint block; exclude_titles → dealbreakers).

- [ ] Test: a representative `user_config.json` dict → expected prefs shape.
- [ ] Implement; pure function (no I/O).
- [ ] Commit `feat(preferences): migrate legacy user_config.json -> preferences`.

## Task 6: templates + scaffold

**Files:** Create `data_templates/{experience.template.md,preferences.template.md,preferences.json}`,
`userdata.py`; Test `tests/test_userdata.py`.

**Produces:** `userdata.scaffold(data_dir: Path) -> list[str]` — copy each bundle template into the data
folder if the target is missing; return names created; idempotent (second call creates nothing).

- [ ] Test: scaffold into an empty tmp dir creates experience.md/preferences.md/preferences.json; second
      call returns []; existing files are not overwritten.
- [ ] Implement reading templates from `config.DATA_DIR / "data_templates"` (bundle) → `data_dir`.
- [ ] Commit `feat(userdata): first-run scaffold of the data folder from templates`.

## Done criteria

`USER_DATA_DIR` resolves correctly (dev=repo root, frozen=`./data`, env-override), workspace + config
paths root under it, `preferences.{md,json}` load + hard-gate + migrate, templates scaffold an empty
folder. Suite green. Dev workflow unchanged. Then Phase 2 (wide-net + AI ranking) gets its own plan.
