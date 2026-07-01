"""Register one Windows Task Scheduler job per project for the daily headless run.

For every project in projects/projects.json whose `daily` flag is true, creates a
task named JobSearchDaily_<slug> that invokes `py daily_run.py --project <slug>`.
Runs are staggered a few minutes apart (07:30, 07:35, ...) so two projects don't
hammer the free API tiers at the same instant. Projects with daily=false are
skipped (and any stale task for them is removed). Idempotent: /Create /F replaces
an existing task with the same name.

Run:    py scripts\\setup_schedule.py
Remove: schtasks /Delete /TN JobSearchDaily_<slug> /F
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import workspace

BASE = workspace.BASE_DIR
START_HOUR = 7
START_MIN = 30
STAGGER_MIN = 5  # minutes between successive project runs


def _start_time(index: int) -> str:
    """HH:MM for the index-th project, staggered STAGGER_MIN apart from 07:30."""
    total = START_HOUR * 60 + START_MIN + index * STAGGER_MIN
    total %= 24 * 60
    return f"{total // 60:02d}:{total % 60:02d}"


def _task_name(slug: str) -> str:
    return f"JobSearchDaily_{slug}"


def _create_task(slug: str, start_time: str) -> int:
    """schtasks /Create for one project. Returns the process return code."""
    task = _task_name(slug)
    script_dir = str(BASE)
    # cmd /c cd /d "<dir>" && py daily_run.py --project <slug> >> "<log>" 2>&1
    # The redirect is essential: without it, every print() the ingest pipeline
    # emits (per-source counts, a source that 429'd, an expired key, a scraper
    # schema change) is discarded on the headless scheduled run, so a broken
    # source is indistinguishable from a genuinely empty one (finding #2). The
    # app's own log() only captures its own lines, not the engine/clients'.
    log_name = f"daily_task_{slug}.log"
    tr = (f'cmd /c cd /d "{script_dir}" && py daily_run.py --project {slug} '
          f'>> "{log_name}" 2>&1')
    cmd = ["schtasks", "/Create", "/F", "/SC", "DAILY", "/ST", start_time,
           "/TN", task, "/TR", tr]
    print(f"  {task} @ {start_time} -> {tr}")
    return subprocess.run(cmd).returncode


def _delete_task(slug: str) -> None:
    """Remove a stale task for a project that's no longer daily (best-effort)."""
    task = _task_name(slug)
    subprocess.run(["schtasks", "/Delete", "/TN", task, "/F"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def setup(projects=None) -> int:
    """Register a staggered daily task per daily-enabled project. Returns the
    count of tasks successfully created. projects defaults to list_projects()."""
    projects = workspace.list_projects() if projects is None else projects
    if not projects:
        print("No projects found (projects/projects.json missing?). Nothing to do.")
        print("Tip: run the single-project setup_schedule.bat instead.")
        return 0

    created = 0
    index = 0
    for p in projects:
        slug = p.get("slug")
        if not slug:
            continue
        if not p.get("daily", False):
            print(f"  skip {slug} (daily=false)")
            _delete_task(slug)
            continue
        rc = _create_task(slug, _start_time(index))
        if rc == 0:
            created += 1
        else:
            print(f"  FAILED to create task for {slug} (rc={rc}); "
                  f"try running as Administrator.")
        index += 1

    print()
    print(f"Done: {created} daily task(s) registered.")
    print(f"App log per project: projects\\<slug>\\output\\daily_run.log")
    print(f"Full scheduled-run console (per project): daily_task_<slug>.log")
    return created


if __name__ == "__main__":
    setup()
