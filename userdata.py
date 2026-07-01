"""First-run scaffolding for the user data folder.

The bundle (DATA_DIR/_MEIPASS) ships neutral templates under data_templates/;
`scaffold()` copies any MISSING user file into the data folder so a fresh install
(or a friend's unzipped copy) starts with editable preferences/experience without
shipping anyone's personal data. Idempotent — it never overwrites existing files.
"""
import shutil
import sys
from pathlib import Path

import config

# File-sync roots that corrupt a WAL-mode SQLite DB when they sync mid-write. We
# never relocate anything automatically (that would surprise the user); we just
# warn loudly once per launch and let daily_run record it in last_run.json errors
# so "Report a problem" surfaces the root cause of a mystery corruption.
_SYNC_MARKERS = ("onedrive", "dropbox", "google drive", "googledrive")


def sync_folder_warning(data_dir=None) -> str | None:
    """If the data dir sits under a known file-syncer (OneDrive/Dropbox/Google
    Drive), return a human-readable warning string; else None. A file syncer
    copying the DB mid-write is a real WAL-SQLite corruption vector."""
    d = str(data_dir if data_dir is not None else config.USER_DATA_DIR)
    low = d.replace("\\", "/").lower()
    for marker in _SYNC_MARKERS:
        if marker in low:
            pretty = {"onedrive": "OneDrive", "dropbox": "Dropbox",
                      "google drive": "Google Drive",
                      "googledrive": "Google Drive"}[marker]
            return (
                f"Your data folder is inside {pretty} ({d}). A file syncer can "
                "corrupt the job database while it is being written. Move your "
                "data folder outside the synced area (Help -> Open my data "
                "folder) or exclude it from syncing.")
    return None

# bundle template filename (in data_templates/) -> target name in the data folder
_TEMPLATES = {
    "experience.template.md":  "experience.md",
    "preferences.template.md": "preferences.md",
    "preferences.json":        "preferences.json",
}


def templates_dir() -> Path:
    """The read-only bundle directory holding the seed templates."""
    return config.DATA_DIR / "data_templates"


def scaffold(data_dir) -> list[str]:
    """Copy each missing user file into `data_dir` from the bundle templates.
    Returns the list of target names created. Idempotent; never overwrites an
    existing file, and skips any template that isn't present in the bundle."""
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    tdir = templates_dir()
    created = []
    for template_name, target_name in _TEMPLATES.items():
        dst = data_dir / target_name
        src = tdir / template_name
        if not dst.exists() and src.exists():
            shutil.copyfile(src, dst)
            created.append(target_name)
    # Seed the starter careers registry too. It lives at the bundle ROOT (app.spec
    # ships companies.json there), not under data_templates/. Without this a
    # locked-down (LOCALAPPDATA) install or any non-exe first run gets only the
    # tiny hardcoded REGISTRY. Resolve from the templates bundle's parent so this
    # tracks the same bundle the templates came from (in production that parent IS
    # config.DATA_DIR, the PyInstaller bundle root).
    companies_dst = data_dir / "companies.json"
    companies_src = tdir.parent / "companies.json"
    if not companies_dst.exists() and companies_src.exists():
        shutil.copyfile(companies_src, companies_dst)
        created.append("companies.json")
    return created


def bootstrap() -> list[str]:
    """First-run setup, safe to call on every launch: ensure the data folder
    exists, is seeded from templates, and has its cache/output dirs. Returns the
    names of any files created (empty after the first run). Wire this into each
    entry point (GUI, daily_run, CLI) so a fresh/unzipped copy just works.

    Also emits a one-time sync-folder warning (log + stderr) when the data dir is
    under OneDrive/Dropbox/Google Drive — a WAL-SQLite corruption vector — but
    NEVER relocates anything on its own. daily_run reads sync_folder_warning()
    separately to persist it into last_run.json."""
    created = scaffold(config.USER_DATA_DIR)
    config.ensure_writable_dirs()
    warning = sync_folder_warning()
    if warning:
        try:
            import applog
            applog.get_logger("userdata").warning(warning)
        except Exception:
            pass
        print(f"WARNING: {warning}", file=sys.stderr)
    return created
