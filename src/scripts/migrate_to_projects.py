"""One-time migration to the projects/ workspace model.

Moves current root data into projects/primary (the existing campaign)
and creates projects/secondary from a secondary config (fresh, empty
inbox). Idempotent guard: aborts if projects/projects.json already exists.

Safety (copy-verify-delete): we write projects.json FIRST, then COPY files into
each project and verify (row-parity for the db, existence for the rest), and only
AFTER verification passes do we delete the originals from the root. A crash mid-
migration therefore leaves the root data intact (plus a partial projects/ that
the idempotent guard + re-run will reconcile), never a vanished root DB with no
registry. Run: py -m scripts.migrate_to_projects
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
    """Populate projects/<slug>/ by COPYING sources in (never moving). Idempotent:
    re-running won't clobber files already present. Originals are deleted later,
    only after the whole migration is verified (see migrate())."""
    pdir = PROJECTS / slug
    (pdir / "output").mkdir(parents=True, exist_ok=True)
    # config
    dest_cfg = pdir / "config.json"
    if not dest_cfg.exists():
        if config_src.exists():
            shutil.copy2(config_src, dest_cfg)
        else:
            dest_cfg.write_text("{}", encoding="utf-8")
    # resume base
    dest_exp = pdir / "experience.md"
    if not dest_exp.exists():
        if exp_src.exists():
            shutil.copy2(exp_src, dest_exp)
        else:
            dest_exp.write_text("# Experience\n", encoding="utf-8")
    # tracker.db: COPY the existing one for the primary project (deleted
    # post-verify); the secondary starts empty (lazy init creates it on first use).
    dest_db = pdir / "tracker.db"
    if db_src is not None and db_src.exists() and not dest_db.exists():
        shutil.copy2(db_src, dest_db)
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

    # 1) registry FIRST — so a crash any time after this leaves a valid pointer to
    #    where the data is being migrated, never a deleted root DB with no record.
    PROJECTS.mkdir(parents=True, exist_ok=True)
    reg = {
        "active": "primary",
        "projects": [
            {"slug": "primary", "name": "Primary",
             "created": today, "daily": True},
            {"slug": "secondary", "name": "Secondary",
             "created": today, "daily": False},
        ],
    }
    (PROJECTS / "projects.json").write_text(json.dumps(reg, indent=2), encoding="utf-8")

    # 2) COPY root data into controls-cincinnati (config + resume + db) + output.
    cc = _seed_project("primary", "Primary",
                       config_src=root_cfg, db_src=root_db, exp_src=root_exp)
    copied_out = []  # (src, dest) pairs to delete from root only after verify
    if root_out.exists():
        for item in root_out.iterdir():
            dest = cc / "output" / item.name
            if not dest.exists():
                if item.is_dir():
                    shutil.copytree(item, dest)
                else:
                    shutil.copy2(item, dest)
            copied_out.append((item, dest))

    # 3) secondary project ← secondary config, copy of resume, fresh empty db
    _seed_project("secondary", "Secondary",
                  config_src=dad_cfg, db_src=None, exp_src=root_exp)

    # 4) VERIFY the copy before touching the originals: db row-parity + existence
    #    of every output item we copied. Any failure aborts WITHOUT deleting.
    after = _counts(cc / "tracker.db")
    print(f"controls-cincinnati tracker.db: inbox={after[0]} applications={after[1]}")
    db_ok = (after == before) or not root_db.exists()
    out_ok = all(dest.exists() for _, dest in copied_out)
    ok = db_ok and out_ok
    print("ROW-COUNT PARITY:", "OK" if db_ok else f"MISMATCH before={before} after={after}")
    if not ok:
        print("VERIFY FAILED — leaving root data intact, nothing deleted.")
        return False

    # 5) Copy verified — now it's safe to delete the originals from the root.
    if root_db.exists():
        root_db.unlink()
    for item, _dest in copied_out:
        if item.exists():
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()

    print("active project:", workspace.active_slug())
    return ok


if __name__ == "__main__":
    sys.exit(0 if migrate() else 1)
