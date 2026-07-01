"""A3: the fix_* backfill scripts resolve+pin the target project once (via
--project, default active) so a concurrent switch can't move their target DB.

Driven as real subprocesses through JOBPROGRAM_DATA so the __main__ arg/pin path
is exercised end-to-end (no live network: dry-run, and the URLs carry their own
slugs so no registry lookup is needed)."""
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _mk_inbox(db_path, rows):
    """rows = list of (norm_url, company, url). Minimal inbox table."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE inbox (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "norm_url TEXT UNIQUE NOT NULL, title TEXT DEFAULT '', company TEXT, "
        "url TEXT, source TEXT DEFAULT 'careers')"
    )
    for nu, company, url in rows:
        conn.execute(
            "INSERT INTO inbox (norm_url, company, url) VALUES (?,?,?)",
            (nu, company, url))
    conn.commit()
    conn.close()


def _two_project_workspace(base: Path):
    """Register 'controls' (active) and 'dad' with their own inbox DBs."""
    projdir = base / "projects"
    (projdir / "controls").mkdir(parents=True)
    (projdir / "dad").mkdir(parents=True)
    (projdir / "projects.json").write_text(json.dumps({
        "active": "controls",
        "projects": [{"slug": "controls", "name": "Controls"},
                     {"slug": "dad", "name": "Dad"}],
    }), encoding="utf-8")


def _run(module, base, *extra):
    env = dict(os.environ, JOBPROGRAM_DATA=str(base))
    return subprocess.run(
        [sys.executable, "-m", module, "--dry-run", *extra],
        cwd=str(REPO), env=env, capture_output=True, text=True)


@pytest.mark.parametrize("module,url,expect_fix", [
    # A non-canonical hosted greenhouse link -> would be rewritten (fixable).
    ("scripts.fix_greenhouse_urls",
     "https://boards.greenhouse.io/acme/jobs/123", True),
    # A site-less workday link WITHOUT a registry site -> not fixable (skipped),
    # but the run still resolves against the pinned project without error.
    ("scripts.fix_workday_urls",
     "https://cat.wd5.myworkdayjobs.com/en-US/x/job/Some-Role_R1", False),
])
def test_script_default_pins_active_project(tmp_path, module, url, expect_fix):
    _two_project_workspace(tmp_path)
    _mk_inbox(tmp_path / "projects" / "controls" / "tracker.db",
              [("k1", "Acme", url)])
    _mk_inbox(tmp_path / "projects" / "dad" / "tracker.db", [])

    r = _run(module, tmp_path)                      # default -> active = controls
    assert r.returncode == 0, r.stderr
    # It resolved against the ACTIVE project (controls) with its populated inbox,
    # never silently against the empty root or the other project.
    assert "would fix" in r.stdout.lower()


def test_greenhouse_project_flag_targets_named_project(tmp_path):
    _two_project_workspace(tmp_path)
    # Put a fixable row in DAD only; controls empty. --project dad must find it.
    _mk_inbox(tmp_path / "projects" / "controls" / "tracker.db", [])
    _mk_inbox(tmp_path / "projects" / "dad" / "tracker.db",
              [("k1", "Acme", "https://boards.greenhouse.io/acme/jobs/123")])

    r = _run("scripts.fix_greenhouse_urls", tmp_path, "--project", "dad")
    assert r.returncode == 0, r.stderr
    assert "[dry-run] would fix 1" in r.stdout


def test_greenhouse_all_projects_still_scans_every_db(tmp_path):
    _two_project_workspace(tmp_path)
    _mk_inbox(tmp_path / "projects" / "controls" / "tracker.db",
              [("k1", "Acme", "https://boards.greenhouse.io/acme/jobs/1")])
    _mk_inbox(tmp_path / "projects" / "dad" / "tracker.db",
              [("k2", "Beta", "https://boards.greenhouse.io/beta/jobs/2")])
    r = _run("scripts.fix_greenhouse_urls", tmp_path, "--all-projects")
    assert r.returncode == 0, r.stderr
    assert "TOTAL: [dry-run] would fix 2" in r.stdout
