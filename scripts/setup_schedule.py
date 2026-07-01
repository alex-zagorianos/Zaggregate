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


# ── shared task-run construction (used by CLI setup AND the GUI toggle) ─────────
# The GUI's "Turn on daily updates" dialog and this CLI both register the SAME
# per-user Task Scheduler job, so the command they schedule must be built in ONE
# place or they drift. When frozen, the shipped .exe supports `--daily` (see
# gui.main()); in dev the scheduled command is `py daily_run.py`. Neither needs
# admin: schtasks with no /RU runs the task as the current interactive user.

def _is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def _run_command(slug: str) -> tuple[str, str]:
    """(working_dir, task-run string) for the daily run of one project.

    Frozen: <exe> --daily --project <slug>, cwd = the exe's folder.
    Dev:    py daily_run.py --project <slug>, cwd = the repo/data root.
    A `>> "<log>" 2>&1` redirect is essential either way — without it every
    print() the ingest pipeline emits (per-source counts, a 429'd source, an
    expired key, a scraper schema change) is discarded on the headless run, so a
    broken source is indistinguishable from a genuinely empty one (finding #2).
    """
    log_name = f"daily_task_{slug}.log"
    if _is_frozen():
        exe = Path(sys.executable)
        work_dir = str(exe.parent)
        tr = (f'cmd /c cd /d "{work_dir}" && "{exe}" --daily --project {slug} '
              f'>> "{log_name}" 2>&1')
    else:
        work_dir = str(BASE)
        tr = (f'cmd /c cd /d "{work_dir}" && py daily_run.py --project {slug} '
              f'>> "{log_name}" 2>&1')
    return work_dir, tr


def register_daily_task(slug: str, start_time: str | None = None) -> int:
    """Register (idempotently, /F) the per-user daily task for ONE project.
    Returns the schtasks return code (0 = ok). No admin required. Shared by the
    GUI 'Turn on daily updates' dialog and the CLI setup() below."""
    task = _task_name(slug)
    _, tr = _run_command(slug)
    st = start_time or _start_time(0)
    cmd = ["schtasks", "/Create", "/F", "/SC", "DAILY", "/ST", st,
           "/TN", task, "/TR", tr]
    print(f"  {task} @ {st} -> {tr}")
    return subprocess.run(cmd).returncode


def unregister_daily_task(slug: str) -> int:
    """Delete the per-user daily task for one project. Returns the schtasks
    return code (0 = deleted; nonzero when no such task existed)."""
    return subprocess.run(
        ["schtasks", "/Delete", "/TN", _task_name(slug), "/F"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode


def task_status(slug: str) -> dict:
    """Best-effort state of a project's daily task: {"registered": bool,
    "next_run": str|"", "raw": str}. Parses `schtasks /Query /FO LIST /V`.
    Never raises — a missing task or a schtasks failure reports not-registered."""
    task = _task_name(slug)
    out = {"registered": False, "next_run": "", "raw": ""}
    try:
        r = subprocess.run(
            ["schtasks", "/Query", "/TN", task, "/FO", "LIST", "/V"],
            capture_output=True, text=True)
    except OSError:
        return out
    if r.returncode != 0:
        return out
    out["registered"] = True
    out["raw"] = r.stdout or ""
    for line in (r.stdout or "").splitlines():
        if "Next Run Time:" in line:
            out["next_run"] = line.split(":", 1)[1].strip()
            break
    return out


def _create_task(slug: str, start_time: str) -> int:
    """schtasks /Create for one project (CLI path). Returns the return code."""
    return register_daily_task(slug, start_time)


def _delete_task(slug: str) -> None:
    """Remove a stale task for a project that's no longer daily (best-effort)."""
    unregister_daily_task(slug)


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
