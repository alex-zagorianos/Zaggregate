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
import os
import re
import time
from datetime import date
from pathlib import Path

import config

# Slug for the pre-migration root workspace entry.  project_dir("default") always
# resolves to BASE_DIR so every existing root-level file is reachable unchanged.
_ROOT_SLUG = "default"


class RegistryCorruptError(RuntimeError):
    """projects.json exists but is unreadable (corrupt/partial write).

    Raised instead of silently falling back to an EMPTY registry — because an
    empty registry reroutes every db/config/output path to the ROOT workspace,
    which after a project switch means one project's writes land in another's
    data (the S27 cross-project bleed). Write-path resolution and any mutation
    REFUSE on corruption; the fresh-install (no-file) path is unaffected.
    """

# The user data folder (external + writable) is the project root. config resolves
# it: the repo root in dev, <exe>/data when frozen — so projects/ and tracker.db
# never land in the read-only _MEIPASS bundle. Tests monkeypatch BASE_DIR.
BASE_DIR = config.USER_DATA_DIR

_EXPERIENCE_STUB = """# Experience

> Fill this in for THIS project's candidate. Used for resume/cover generation
> and skill-based job scoring. Keep the `## ` headings below; leave any you
> don't need empty.

## CONTACT

- Name:
- Email:
- Phone:
- Location:

## SUMMARY

## EDUCATION

## TECHNICAL SKILLS

## LICENSES & CERTIFICATIONS

## WORK EXPERIENCE

## NOTES FOR RESUME GENERATION
"""

# The empty preferences.md profile a new project ships with, so the AI-ranking
# routes (bridge/API/MCP/file) always find a real profile file rather than an
# empty/absent contract. Mirrors setup_wizard.build_preferences' header so a
# scaffolded project reads identically to a wizard-completed one until the user
# fills it in.
_PREFERENCES_MD_STUB = """# My Job Preferences

> Describe the roles you want in plain English. The AI reads this to rank
> and sort jobs to your taste. Be specific about what you love and avoid.
"""

# The permissive default hard-filter contract a new project ships with. Kept in
# sync with preferences._DEFAULT_HARD (imported lazily to avoid a workspace ->
# preferences import cycle); if that import fails we fall back to this literal so
# scaffolding never crashes project creation.
_PREFERENCES_HARD_STUB = {
    "salary_min": None,
    "locations": [],
    "remote_ok": True,
    "remote_regions_ok": False,
    "work_auth": "",
    "dealbreakers": [],
    "seniority_exclude": [],
    "target_roles": [],
    "employment_types": [],
}


def _default_hard() -> dict:
    """The permissive default hard-filter dict, preferring preferences._DEFAULT_HARD
    (the single source of truth) and falling back to the local literal so a
    scaffold can never fail on an import hiccup."""
    try:
        import preferences
        return dict(preferences._DEFAULT_HARD)
    except Exception:
        return dict(_PREFERENCES_HARD_STUB)


# ── path helpers (read BASE_DIR at call-time so tests can monkeypatch it) ──────
def _projects_dir() -> Path:
    return BASE_DIR / "projects"


def _registry_path() -> Path:
    return _projects_dir() / "projects.json"


def has_projects() -> bool:
    return _registry_path().exists()


def _registry() -> dict:
    """Load projects.json.

    No file yet (fresh install / pre-migration) -> a clean empty registry, so
    the root-fallback path is unchanged. But a file that EXISTS and won't parse
    is corruption, not "no projects": we do NOT silently return empty (that
    reroutes every path to the ROOT workspace = cross-project bleed). We log
    loudly and raise RegistryCorruptError so both read and write callers get a
    clear error instead of silent data loss.
    """
    p = _registry_path()
    if not p.exists():
        return {"active": None, "projects": []}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        msg = (f"CORRUPT project registry at {p}: {e}. Refusing to fall back to "
               f"the root workspace (would misroute this project's data). Fix or "
               f"remove the file.")
        try:
            import logging
            logging.getLogger(__name__).error(msg)
        except Exception:
            pass
        raise RegistryCorruptError(msg) from e


def _write_registry(reg: dict) -> None:
    """Write projects.json ATOMICALLY (tmp file + os.replace) so a crash mid-write
    can never leave a truncated/partial registry that later reads as corrupt.
    Mirrors scrape.cache_helpers.write_cache."""
    _projects_dir().mkdir(parents=True, exist_ok=True)
    dest = _registry_path()
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.write_text(json.dumps(reg, indent=2), encoding="utf-8")
    os.replace(tmp, dest)


# ── cross-process registry lock (advisory) ────────────────────────────────────
# A lockfile created O_EXCL beside projects.json. Registry MUTATIONS acquire it
# so GUI + daily_run + MCP racing on set_active/create_project/upsert serialize
# their read-modify-write instead of clobbering each other's registry. It is
# ADVISORY: only code that goes through _registry_lock() honors it. On timeout we
# warn and proceed (a stale lock from a crashed process must not deadlock the
# app) rather than blocking forever.
_LOCK_TIMEOUT_S = 10.0
_LOCK_POLL_S = 0.05
_LOCK_STALE_S = 60.0   # a lockfile older than this is assumed abandoned


def _lock_path() -> Path:
    return _registry_path().with_suffix(".json.lock")


class _RegistryLock:
    """Context manager: best-effort exclusive lock around a registry mutation.

    Acquire = create the lockfile with O_CREAT|O_EXCL (atomic "only one wins").
    On contention, poll until timeout; on timeout, warn-and-proceed (never
    deadlock). A lockfile older than _LOCK_STALE_S is treated as abandoned by a
    crashed holder and reclaimed. Release removes the file if we own it.
    """

    def __init__(self, timeout: float = _LOCK_TIMEOUT_S):
        self.timeout = timeout
        self._held = False

    def _try_create(self) -> bool:
        try:
            fd = os.open(str(_lock_path()), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return False
        except OSError:
            return False
        try:
            os.write(fd, str(os.getpid()).encode("ascii", "ignore"))
        finally:
            os.close(fd)
        return True

    def _reclaim_if_stale(self) -> None:
        lp = _lock_path()
        try:
            age = time.time() - lp.stat().st_mtime
        except OSError:
            return
        if age > _LOCK_STALE_S:
            try:
                lp.unlink()
            except OSError:
                pass

    def __enter__(self):
        _projects_dir().mkdir(parents=True, exist_ok=True)
        deadline = time.time() + self.timeout
        while True:
            if self._try_create():
                self._held = True
                return self
            self._reclaim_if_stale()
            if time.time() >= deadline:
                try:
                    import logging
                    logging.getLogger(__name__).warning(
                        "registry lock %s contended past %.0fs; proceeding "
                        "without it (another process may be mid-write).",
                        _lock_path(), self.timeout)
                except Exception:
                    pass
                return self          # warn-and-proceed, unlocked
            time.sleep(_LOCK_POLL_S)

    def __exit__(self, *exc):
        if self._held:
            try:
                _lock_path().unlink()
            except OSError:
                pass
            self._held = False
        return False


def _registry_lock(timeout: float = _LOCK_TIMEOUT_S) -> _RegistryLock:
    """Acquire the advisory registry lock (see _RegistryLock). Use `with`."""
    return _RegistryLock(timeout=timeout)


# ── queries ───────────────────────────────────────────────────────────────────
def list_projects() -> list[dict]:
    return _registry().get("projects", [])


# Process-local active-project pin. When set, active_slug() returns it and
# ignores projects.json, so a long operation (a daily_run) resolves EVERY path
# (db/output/experience/config) to one project even if another process rewrites
# projects.json 'active' mid-run — a concurrent second run or a GUI project
# switch. Default None = unpinned = read projects.json as before (no behavior
# change for the GUI/CLI, tests, or single-run use).
_PINNED_SLUG: str | None = None


def pin_active(slug: str | None) -> None:
    """Pin the active project for THIS process (see _PINNED_SLUG). Pass a slug to
    pin; None is a no-op pin (leaves resolution reading projects.json)."""
    global _PINNED_SLUG
    _PINNED_SLUG = slug or None


def unpin_active() -> None:
    """Clear the process-local pin (resolution returns to projects.json)."""
    global _PINNED_SLUG
    _PINNED_SLUG = None


def pinned() -> str | None:
    """The process-local pin, or None. The GUI uses this to refuse a project
    switch while a pinned run (Update-now) is in flight — switching would show
    project B while every DB call still resolves to pinned A (review finding)."""
    return _PINNED_SLUG


def active_slug() -> str | None:
    if _PINNED_SLUG is not None:
        return _PINNED_SLUG
    return registry_active_slug()


def registry_active_slug() -> str | None:
    """The active project persisted in projects.json, IGNORING the process-local
    pin. ``active_slug()`` deliberately shadows this with the pin so every in-flight
    DB call resolves to the pinned project for the duration of a run. But a request
    handler that wants the user's CURRENT intended project (e.g. to echo a switch it
    just wrote, or to resolve the TARGET of a new run) must read the registry
    directly — under a pin the two diverge, and using the pin misattributes the
    caller's intent to the running project. (scenario findings #6/#7)"""
    reg = _registry()
    slug = reg.get("active")
    if slug:
        return slug
    projs = reg.get("projects", [])
    return projs[0]["slug"] if projs else None


# ── people (a person = a set of projects; plan GOAL 2) ────────────────────────
def people() -> list:
    """Distinct `person` labels across projects, in registry order. `None` is the
    default/unassigned person (pre-GOAL-2 projects, and the root 'default')."""
    seen = []
    for p in list_projects():
        person = p.get("person")
        if person not in seen:
            seen.append(person)
    return seen


def projects_for_person(person) -> list[dict]:
    """Projects belonging to `person` (None = the default/unassigned person)."""
    return [p for p in list_projects() if p.get("person") == person]


def person_of(slug: str | None = None):
    """The person label owning a project (None if unassigned)."""
    resolved = slug or active_slug()
    for p in list_projects():
        if p.get("slug") == resolved:
            return p.get("person")
    return None


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


def scaffold_preferences(slug=None, *, hard: dict | None = None,
                         profile_md: str | None = None,
                         overwrite: bool = False) -> tuple[Path, Path]:
    """Ensure this project's preferences.{json,md} exist, writing a valid empty
    contract when they don't (or `hard`/`profile_md` when supplied). Returns the
    (json, md) paths.

    The single scaffold helper both the setup wizard's apply() and the
    AI-assisted-setup path share, so a programmatic/AI-created project can never
    hit an empty/absent preferences contract (onboarding §2.1). Non-destructive
    by default: an existing file is left untouched unless `overwrite=True`, so
    calling this at project creation can't clobber a project the user already
    configured. Writing content (hard/profile_md) implies overwrite for the file
    that content is given for."""
    pj, pm = preferences_paths(slug)
    pj.parent.mkdir(parents=True, exist_ok=True)

    if hard is not None or overwrite or not pj.exists():
        payload = dict(_default_hard())
        if hard:
            payload.update(hard)
        pj.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if profile_md is not None or overwrite or not pm.exists():
        pm.write_text(profile_md if profile_md is not None else _PREFERENCES_MD_STUB,
                      encoding="utf-8")
    return pj, pm


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

def _attach_onet_soc(cfg_data: dict) -> None:
    """Resolve + persist a STABLE O*NET-SOC code alongside a new project's
    free-text `industry` (item 25), so downstream callers (industry_profile,
    match.facts) can key off a code that doesn't drift if the user later edits
    the industry text slightly. Best-effort and additive: no `industry`, an
    eng-flavored one, or one that doesn't confidently resolve to a real
    occupation leaves `cfg_data` untouched (no new keys) -- and this only ever
    runs once, at project creation, so it never touches an existing project's
    config.json (mirrors the `if not cfg_file.exists()` guard around the only
    caller)."""
    industry = (cfg_data.get("industry") or "").strip()
    if not industry or "onet_soc_code" in cfg_data:
        return
    try:
        import industry_profile
        soc = industry_profile.resolve_soc(industry)
    except Exception:
        soc = None
    if soc:
        cfg_data["onet_soc_code"] = soc["code"]
        cfg_data["onet_soc_title"] = soc["title"]


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
    with _registry_lock():
        reg = _registry()
        if slug not in {p["slug"] for p in reg.get("projects", [])}:
            raise ValueError(f"unknown project: {slug}")
        reg["active"] = slug
        _write_registry(reg)


def create_project(name: str, *, slug: str | None = None, config: dict | None = None,
                   copy_resume_from: str | Path | None = None,
                   make_active: bool = False, today: str | None = None,
                   person: str | None = None) -> str:
    """Create projects/<slug>/ with config.json, experience.md, output/. Returns
    the slug. copy_resume_from = a project slug or a path to seed experience.md.
    `person` tags the project's owner (GOAL 2 — a person is just a set of projects);
    None = the default/unassigned person, so old callers are unchanged.

    When this is the very FIRST project (no registry exists yet), the existing root
    workspace is automatically registered as 'default' first so the root inbox,
    config, and experience stay reachable via the project switcher after the switch.
    """
    # Serialize the whole read-modify-write against concurrent registry mutators
    # (GUI switch / daily_run / MCP). _ensure_default_root_registered is called
    # lock-free below because it only ever runs INSIDE this held lock.
    with _registry_lock():
        # First-project guard: register the root as "default" before creating a
        # new campaign, so the existing data is never orphaned in the switcher.
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
            cfg_data = dict(config or {})
            _attach_onet_soc(cfg_data)
            cfg_file.write_text(json.dumps(cfg_data, indent=2), encoding="utf-8")

        exp = pdir / "experience.md"
        if not exp.exists():
            src = None
            if copy_resume_from is not None:
                src = Path(copy_resume_from)
                if not src.exists():            # treat as a project slug
                    src = _projects_dir() / str(copy_resume_from) / "experience.md"
            exp.write_text(src.read_text(encoding="utf-8") if src and src.exists()
                           else _EXPERIENCE_STUB, encoding="utf-8")

        # Scaffold the preferences contract too (persona finding: create_project
        # seeded config + experience but NOT preferences, so a programmatic/AI
        # path hit an empty/absent contract). Non-destructive: only writes files
        # that don't already exist.
        scaffold_preferences(slug)

        if slug not in existing:
            entry = {"slug": slug, "name": name,
                     "created": today or date.today().isoformat(), "daily": False}
            if person is not None:
                entry["person"] = person       # omit when unassigned (back-compat)
            reg.setdefault("projects", []).append(entry)
        if make_active:
            reg["active"] = slug
        elif reg.get("active") is None:
            # Registry missing an 'active' key (fresh install / legacy file):
            # repair it, but NEVER by overriding an explicit make_active=False
            # with the just-created project (S37 review CRITICAL: the web
            # create-project route's switch:false was silently ignored on a
            # fresh registry). Prefer any OTHER registered project (the default
            # root that _ensure_default_root_registered adds comes first); only
            # fall back to the new slug when it is genuinely the only project.
            others = [p.get("slug") for p in reg.get("projects", [])
                      if p.get("slug") and p.get("slug") != slug]
            reg["active"] = others[0] if others else slug
        _write_registry(reg)
    return slug
