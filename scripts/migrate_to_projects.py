"""One-time migration to the projects/ workspace model.

Moves current root data into projects/controls-cincinnati (the existing campaign)
and creates projects/dad-health-informatics from config_dad.json (fresh, empty
inbox). Idempotent guard: aborts if projects/projects.json already exists.

Safety: backs up tracker.db -> tracker.db.bak before moving; verifies inbox +
applications row counts survive. Run: py -m scripts.migrate_to_projects
"""
import json
import shutil
import sqlite3
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import workspace

BASE = workspace.BASE_DIR
PROJECTS = BASE / "projects"


def _counts(db: Path) -> tuple[int, int]:
    if not db.exists():
        return (0, 0)
    conn = sqlite3.connect(str(db))
    def n(t):
        try:
            return conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        except sqlite3.OperationalError:
            return 0
    res = (n("inbox"), n("applications"))
    conn.close()
    return res


def _seed_project(slug: str, name: str, *, config_src: Path, db_src: Path | None,
                  exp_src: Path) -> Path:
    pdir = PROJECTS / slug
    (pdir / "output").mkdir(parents=True, exist_ok=True)
    # config
    if config_src.exists():
        shutil.copy2(config_src, pdir / "config.json")
    else:
        (pdir / "config.json").write_text("{}", encoding="utf-8")
    # resume base
    if exp_src.exists():
        shutil.copy2(exp_src, pdir / "experience.md")
    else:
        (pdir / "experience.md").write_text("# Experience\n", encoding="utf-8")
    # tracker.db: move the existing one for controls; dad starts empty (lazy init)
    if db_src is not None and db_src.exists():
        shutil.move(str(db_src), str(pdir / "tracker.db"))
    return pdir


def migrate(today: str | None = None) -> bool:
    if (PROJECTS / "projects.json").exists():
        print("projects/projects.json already exists — migration already done. Aborting.")
        return False

    today = today or date.today().isoformat()
    root_db = BASE / "tracker.db"
    root_cfg = BASE / "user_config.json"
    root_exp = BASE / "experience.md"
    root_out = BASE / "output"
    dad_cfg = BASE / "config_dad.json"

    before = _counts(root_db)
    print(f"root tracker.db: inbox={before[0]} applications={before[1]}")

    # Backup the DB we're about to move.
    if root_db.exists():
        shutil.copy2(root_db, root_db.with_name("tracker.db.bak"))
        print("backed up -> tracker.db.bak")

    # 1) controls-cincinnati ← current root (move db + output, copy config + resume)
    cc = _seed_project("controls-cincinnati", "Controls — Cincinnati",
                       config_src=root_cfg, db_src=root_db, exp_src=root_exp)
    if root_out.exists():
        for item in root_out.iterdir():
            dest = cc / "output" / item.name
            if not dest.exists():
                shutil.move(str(item), str(dest))

    # 2) dad-health-informatics ← config_dad.json, copy of resume, fresh empty db
    _seed_project("dad-health-informatics", "Dad — Health Informatics",
                  config_src=dad_cfg, db_src=None, exp_src=root_exp)

    # 3) registry (controls active; dad's morning run off until he opts in)
    reg = {
        "active": "controls-cincinnati",
        "projects": [
            {"slug": "controls-cincinnati", "name": "Controls — Cincinnati",
             "created": today, "daily": True},
            {"slug": "dad-health-informatics", "name": "Dad — Health Informatics",
             "created": today, "daily": False},
        ],
    }
    (PROJECTS / "projects.json").write_text(json.dumps(reg, indent=2), encoding="utf-8")

    # 4) verify
    after = _counts(cc / "tracker.db")
    print(f"controls-cincinnati tracker.db: inbox={after[0]} applications={after[1]}")
    ok = after == before
    print("ROW-COUNT PARITY:", "OK" if ok else f"MISMATCH before={before} after={after}")
    print("active project:", workspace.active_slug())
    return ok


if __name__ == "__main__":
    sys.exit(0 if migrate() else 1)
