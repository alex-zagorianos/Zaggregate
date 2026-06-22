"""First-run scaffolding for the user data folder.

The bundle (DATA_DIR/_MEIPASS) ships neutral templates under data_templates/;
`scaffold()` copies any MISSING user file into the data folder so a fresh install
(or a friend's unzipped copy) starts with editable preferences/experience without
shipping anyone's personal data. Idempotent — it never overwrites existing files.
"""
import shutil
from pathlib import Path

import config

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
    return created


def bootstrap() -> list[str]:
    """First-run setup, safe to call on every launch: ensure the data folder
    exists, is seeded from templates, and has its cache/output dirs. Returns the
    names of any files created (empty after the first run). Wire this into each
    entry point (GUI, daily_run, CLI) so a fresh/unzipped copy just works."""
    created = scaffold(config.USER_DATA_DIR)
    config.ensure_writable_dirs()
    return created
