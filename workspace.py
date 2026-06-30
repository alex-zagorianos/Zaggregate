"""Workspace = the active job-search *project*. A project groups everything for
one search campaign -- its config, resume base, inbox/applications/dismissed
(tracker.db), and generated output -- under projects/<slug>/, so two campaigns
(e.g. controls-cincinnati and dad-health-informatics) never mix.

Paths are resolved at call-time from projects/projects.json, so the app can
switch the active project at runtime. Back-compat: when no projects/ dir exists
(pre-migration), every path falls back to the current root, so nothing changes.

First-project migration: when the FIRST real project is created, the existing
root workspace is automatically registered as "default" so its inbox, config,
and experience stay reachable in the project switcher.

Shared (NOT per-project): .env keys, cache/, companies.json, source/scraper code.
"""
import json
import re
from datetime import date
from pathlib import Path

import config

# Slug for the pre-migration root workspace entry.  project_dir("default") always
# resolves to BASE_DIR so every existing root-level file is reachable unchanged.
_ROOT_SLUG = "default"

# The user data folder (external + writable) is the project root. config resolves
# it: the repo root in dev, <exe>/data when frozen — so projects/ and tracker.db
# never land in the read-only _MEIPASS bundle. Tests monkeypatch BASE_DIR.
BASE_DIR = config.USER_DATA_DIR

_EXPERIENCE_STUB = """# Experience

> Fill this in for THIS project's candidate. Used for resume/cover generation
> and skill-based job scoring. Keep the five `## ` headings below.

## CONTACT

- Name:
- Email:
- Phone:
- Location:

## EDUCATION

## TECHNICAL SKILLS

## WORK EXPERIENCE

## NOTES FOR RESUME GENERATION
"""


# ── path helpers (read BASE_DIR at call-time so tests can monkeypatch it) ──────
def _projects_dir() -> Path:
    return BASE_DIR / "projects"


def _registry_path() -> Path:
    return _projects_dir() / "projects.json"


def has_projects() -> bool:
    return _registry_path().exists()


def _registry() -> dict:
    p = _registry_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"active": None, "projects": []}


def _write_registry(reg: dict) -> None:
    _projects_dir().mkdir(parents=True, exist_ok=True)
    _registry_path().write_text(json.dumps(reg, indent=2), encoding="utf-8")


# ── queries ───────────────────────────────────────────────────────────────────
def list_projects() -> list[dict]:
    return _registry().get("projects", [])


def active_slug() -> str | None:
    reg = _registry()
    slug = reg.get("active")
    if slug:
        return slug
    projs = reg.get("projects", [])
    return projs[0]["slug"] if projs else None


def project_dir(slug: str | None = None) -> Path:
    """The active (or named) project's data root. ROOT BASE_DIR pre-migration and
    always for the 'default' slug so existing root files stay reachable."""
    slug = slug or active_slug()
    if not has_projects() or not slug or slug == _ROOT_SLUG:
        return BASE_DIR
    return _projects_dir() / slug


def db_path(slug=None) -> Path:
    return (BASE_DIR / "tracker.db") if not has_projects() else project_dir(slug) / "tracker.db"


def experience_file(slug=None) -> Path:
    return (BASE_DIR / "experience.md") if not has_projects() else project_dir(slug) / "experience.md"


def output_dir(slug=None) -> Path:
    d = (BASE_DIR / "output") if not has_projects() else project_dir(slug) / "output"
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_path(slug=None) -> Path:
    # The root workspace used "user_config.json"; named projects use "config.json".
    # "default" is a registry alias for BASE_DIR, so it keeps the old filename.
    resolved = slug or active_slug()
    if not has_projects() or not resolved or resolved == _ROOT_SLUG:
        return BASE_DIR / "user_config.json"
    return project_dir(resolved) / "config.json"


def preferences_paths(slug=None) -> tuple[Path, Path]:
    """The active (or named) project's preferences files as (json, md). Falls back
    to the root pre-migration, so it coincides with config.PREFERENCES_* for the
    common single-workspace case; once projects exist, each project gets its own
    preferences so they never desync from its config.json/experience.md."""
    base = project_dir(slug)
    return base / "preferences.json", base / "preferences.md"


def load_config(slug=None) -> dict:
    p = config_path(slug)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def save_config(cfg: dict, slug=None) -> Path:
    """Write the active (or named) project's config.json (root user_config.json
    pre-migration). Returns the path written."""
    p = config_path(slug)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return p


# ── mutations ─────────────────────────────────────────────────────────────────

def _ensure_default_root_registered(today: str | None = None) -> None:
    """Register the pre-migration root workspace as slug 'default' so it stays
    reachable in the project switcher after the first real project is created.
    No-op when 'default' is already registered. Does NOT move or delete any files;
    project_dir('default') always resolves to BASE_DIR."""
    reg = _registry()
    existing = {p["slug"] for p in reg.get("projects", [])}
    if _ROOT_SLUG not in existing:
        reg.setdefault("projects", []).insert(0, {
            "slug": _ROOT_SLUG, "name": "Default",
            "created": today or date.today().isoformat(), "daily": False,
        })
        _write_registry(reg)


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "project"


def set_active(slug: str) -> None:
    reg = _registry()
    if slug not in {p["slug"] for p in reg.get("projects", [])}:
        raise ValueError(f"unknown project: {slug}")
    reg["active"] = slug
    _write_registry(reg)


def create_project(name: str, *, slug: str | None = None, config: dict | None = None,
                   copy_resume_from: str | Path | None = None,
                   make_active: bool = False, today: str | None = None) -> str:
    """Create projects/<slug>/ with config.json, experience.md, output/. Returns
    the slug. copy_resume_from = a project slug or a path to seed experience.md.

    When this is the very FIRST project (no registry exists yet), the existing root
    workspace is automatically registered as 'default' first so the root inbox,
    config, and experience stay reachable via the project switcher after the switch.
    """
    # First-project guard: register the root as "default" before creating a new
    # campaign, so the existing data is never orphaned in the switcher.
    if not has_projects():
        _ensure_default_root_registered(today=today)
    slug = slug or slugify(name)
    reg = _registry()
    existing = {p["slug"] for p in reg.get("projects", [])}
    pdir = _projects_dir() / slug
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "output").mkdir(exist_ok=True)

    cfg_file = pdir / "config.json"
    if not cfg_file.exists():
        cfg_file.write_text(json.dumps(config or {}, indent=2), encoding="utf-8")

    exp = pdir / "experience.md"
    if not exp.exists():
        src = None
        if copy_resume_from is not None:
            src = Path(copy_resume_from)
            if not src.exists():            # treat as a project slug
                src = _projects_dir() / str(copy_resume_from) / "experience.md"
        exp.write_text(src.read_text(encoding="utf-8") if src and src.exists()
                       else _EXPERIENCE_STUB, encoding="utf-8")

    if slug not in existing:
        reg.setdefault("projects", []).append({
            "slug": slug, "name": name,
            "created": today or date.today().isoformat(), "daily": False,
        })
    if make_active or reg.get("active") is None:
        reg["active"] = slug
    _write_registry(reg)
    return slug
