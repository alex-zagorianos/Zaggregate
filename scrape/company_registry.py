import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Serializes the read-modify-write of companies.json. The GUI's "+ Add
# Companies" and the embedded Flask browser-receiver (/clip) both write this file
# from the SAME process, and Flask serves on threaded=True — so two near-
# simultaneous /clip POSTs (or a clip racing a GUI add) would otherwise each read
# the same base list, append, and the second atomic write would clobber the
# first, silently losing a board. A single in-process lock is the correct, cheap
# fix for this single-process local app (cross-process writers — the separate
# MCP process — are never concurrent with the receiver). Held only around the
# read-modify-write in save_companies, never around the live network probe.
_SAVE_LOCK = threading.Lock()


@dataclass
class CompanyEntry:
    name: str
    ats_type: str       # "greenhouse" | "lever" | "ashby" | "smartrecruiters" | "workday" | "direct"
    slug: str           # ATS slug for GH/Lever/Ashby/SmartRecruiters; "tenant:N:site" for workday; full careers URL for direct
    industries: list[str] = field(default_factory=list)
    # Per-board scraper metadata that isn't part of the slug identity: e.g. an
    # Oracle Recruiting Cloud siteNumber ("CX_1") or a Phenom refNum, each
    # normally scraped once from the tenant's careers-page HTML and then cached
    # here so subsequent runs skip that discovery request. Empty for the ATSes
    # that need no side-channel metadata (greenhouse/lever/workday/...). Kept off
    # the (ats_type, slug) dedup key so a re-onboard can't duplicate a board that
    # only differs by a re-discovered extra.
    extra: dict = field(default_factory=dict)


# Key inside CompanyEntry.extra marking a board that FAILED its live probe at
# add-time (P0-6). Such an entry is persisted (so the user's paste isn't lost and
# they can see/prune it) but is EXCLUDED from scraping until it verifies — a
# later VERIFIED re-add (via '+ Add Companies', browser clip, or AI seed) matches
# it by (ats_type, slug) or name and upgrades it in place, clearing this flag so
# it re-enters the scraped set (save_companies(..., upgrade_unverified=True), the
# default). This is what makes the "+ Add Companies" probe status actually matter
# instead of being advisory-only.
UNVERIFIED_FLAG = "unverified"


def is_unverified(entry: "CompanyEntry") -> bool:
    """True when `entry` was flagged unverified (failed its live probe) and must
    be kept out of scraping until it verifies."""
    return bool((getattr(entry, "extra", None) or {}).get(UNVERIFIED_FLAG))


# ---------------------------------------------------------------------------
# Health Informatics
# Greenhouse slugs verified 2026-05-26 against boards-api.greenhouse.io
# Lever slugs verified 2026-05-26 against api.lever.co
# Direct = company uses Workday/Taleo/custom portal (best-effort scrape)
# ---------------------------------------------------------------------------
_HEALTH_INFORMATICS: list[CompanyEntry] = [
    # --- Confirmed Greenhouse ---
    CompanyEntry("Inovalon",         "greenhouse", "inovalon",      ["health_informatics", "analytics", "payer"]),
    CompanyEntry("Doximity",         "greenhouse", "doximity",      ["health_informatics", "clinical"]),
    CompanyEntry("Elation Health",   "greenhouse", "elationhealth", ["health_informatics", "ehr", "primary_care"]),
    CompanyEntry("athenahealth",     "greenhouse", "athena",        ["health_informatics", "ehr", "rcm"]),
    CompanyEntry("CareDx",           "greenhouse", "caredxinc",     ["health_informatics", "clinical"]),

    # --- Confirmed Lever ---
    CompanyEntry("PointClickCare",   "lever", "pointclickcare", ["health_informatics", "ehr", "ltpac"]),
    CompanyEntry("Arcadia",          "lever", "arcadia",         ["health_informatics", "analytics", "value_based_care"]),
    CompanyEntry("Veeva Systems",    "lever", "veeva",           ["health_informatics", "life_sciences"]),

    # --- Direct (Workday with CSRF enabled — JS session required; scraping limited) ---
    # These confirmed as Workday but CSRF/session protection prevents JSON API access.
    # Use "workday" type below only for tenants confirmed CSRF-disabled.
    CompanyEntry("Epic Systems",           "direct", "https://epiccareers.wd5.myworkdayjobs.com/External",            ["health_informatics", "ehr"]),
    CompanyEntry("Optum / UnitedHealth",   "direct", "https://uhg.wd5.myworkdayjobs.com/External",                   ["health_informatics", "payer", "analytics"]),
    CompanyEntry("Meditech",               "direct", "https://meditech.wd3.myworkdayjobs.com/meditech",               ["health_informatics", "ehr"]),
    CompanyEntry("Vizient",                "direct", "https://vizientinc.wd1.myworkdayjobs.com/External",             ["health_informatics", "analytics", "supply_chain"]),
    CompanyEntry("Cotiviti",               "direct", "https://cotiviti.wd1.myworkdayjobs.com/Cotiviti_Careers",       ["health_informatics", "analytics", "payer"]),
    CompanyEntry("Oracle Health / Cerner", "direct", "https://careers.oracle.com/jobs/#en/sites/jobsearch/requisitions?keyword=health+informatics", ["health_informatics", "ehr"]),
    CompanyEntry("Waystar",                "direct", "https://www.waystar.com/careers/open-positions/",               ["health_informatics", "rcm"]),
    CompanyEntry("Evolent Health",         "direct", "https://www.evolenthealth.com/careers/open-positions",          ["health_informatics", "payer"]),
    CompanyEntry("Privia Health",          "direct", "https://www.priviahealth.com/careers/",                         ["health_informatics", "clinical"]),
    CompanyEntry("Health Catalyst",        "direct", "https://www.healthcatalyst.com/careers/",                       ["health_informatics", "analytics"]),
    CompanyEntry("Nuance / Microsoft Health", "direct", "https://careers.microsoft.com/v2/global/en/nuance.html",    ["health_informatics", "clinical", "ai"]),
    CompanyEntry("Phreesia",               "direct", "https://www.phreesia.com/careers/",                             ["health_informatics", "patient_engagement"]),
    CompanyEntry("Surescripts",            "direct", "https://surescripts.com/about-surescripts/careers/",            ["health_informatics", "pharmacy"]),
    CompanyEntry("Availity",               "direct", "https://www.availity.com/about-availity/careers/",              ["health_informatics", "rcm"]),
    CompanyEntry("Veradigm / Allscripts",  "direct", "https://veradigm.com/careers/",                                ["health_informatics", "ehr", "analytics"]),
    CompanyEntry("Netsmart",               "direct", "https://www.ntst.com/Careers",                                  ["health_informatics", "ehr", "behavioral_health"]),
    CompanyEntry("Ciox Health",            "direct", "https://www.cioxhealth.com/about-ciox/careers/",                ["health_informatics", "him", "rcm"]),
    CompanyEntry("DrFirst",                "direct", "https://drfirst.com/about/careers/",                            ["health_informatics", "pharmacy", "ehr"]),
    CompanyEntry("Apixio",                 "direct", "https://www.apixio.com/careers/",                               ["health_informatics", "ai", "payer"]),
]


# ---------------------------------------------------------------------------
# Controls & Automation Engineering
# Greenhouse/Lever verified 2026-05-26 — most large industrials use Workday
# Hardware/robotics/manufacturing GH+Lever boards added & verified 2026-06-09
# against boards-api.greenhouse.io / api.lever.co (these are the only entries
# in this registry the scraper can actually pull jobs from — the big
# industrials below are all CSRF-protected Workday/custom portals).
# ---------------------------------------------------------------------------
_CONTROLS_ENGINEERING: list[CompanyEntry] = [
    # --- Confirmed Greenhouse (verified 2026-06-09) ---
    CompanyEntry("SpaceX",              "greenhouse", "spacex",            ["controls_engineering", "aerospace", "manufacturing"]),
    CompanyEntry("Anduril Industries",  "greenhouse", "andurilindustries", ["controls_engineering", "robotics", "embedded", "defense"]),
    CompanyEntry("Path Robotics",       "greenhouse", "pathrobotics",      ["controls_engineering", "robotics", "welding", "ohio"]),
    CompanyEntry("Formlabs",            "greenhouse", "formlabs",          ["controls_engineering", "3d_printing", "hardware"]),
    CompanyEntry("Zipline",             "greenhouse", "flyzipline",        ["controls_engineering", "robotics", "aerospace"]),
    CompanyEntry("Nuro",                "greenhouse", "nuro",              ["controls_engineering", "robotics", "autonomy"]),
    CompanyEntry("Redwood Materials",   "greenhouse", "redwoodmaterials",  ["controls_engineering", "manufacturing", "battery"]),
    CompanyEntry("Relativity Space",    "greenhouse", "relativity",        ["controls_engineering", "aerospace", "additive_manufacturing"]),

    # --- Confirmed Lever (verified 2026-06-09) ---
    CompanyEntry("Zoox",                "lever", "zoox",           ["controls_engineering", "robotics", "autonomy"]),
    CompanyEntry("Bright Machines",     "lever", "brightmachines", ["controls_engineering", "automation", "manufacturing"]),

    # --- Small/mid robotics-automation-manufacturing (verified 2026-06-09
    #     against boards-api.greenhouse.io / api.lever.co; job counts at
    #     verification in comments — these are the small-company supply fix).
    #     Dead slug guesses, do NOT re-add: scytherobotics, plusonerobotics,
    #     picklerobot, realtimerobotics, standardbots, vecnarobotics, vention,
    #     hadrian (left Lever), monarchtractor, mujin, burro, instrumental,
    #     chefrobotics, mytra, rapidrobotics, sightmachine. On other ATSes:
    #     geckorobotics -> Ashby (gecko-robotics), machinemetrics -> Workable.
    CompanyEntry("Formic",              "greenhouse", "formic",           ["controls_engineering", "robotics", "manufacturing", "small_company", "midwest"]),  # 31
    CompanyEntry("Agility Robotics",    "greenhouse", "agilityrobotics",  ["controls_engineering", "robotics", "small_company"]),                # 43
    CompanyEntry("Apptronik",           "greenhouse", "apptronik",        ["controls_engineering", "robotics", "small_company"]),                # 90
    CompanyEntry("Locus Robotics",      "greenhouse", "locusrobotics",    ["controls_engineering", "robotics", "small_company"]),                # 19
    CompanyEntry("Carbon Robotics",     "greenhouse", "carbonrobotics",   ["controls_engineering", "robotics", "agriculture", "small_company"]), # 24
    CompanyEntry("Tulip Interfaces",    "greenhouse", "tulip",            ["controls_engineering", "manufacturing", "software", "small_company"]),  # 60
    CompanyEntry("Paperless Parts",     "greenhouse", "paperlessparts",   ["controls_engineering", "cnc", "manufacturing", "software", "small_company"]),  # 14
    CompanyEntry("Fictiv",              "greenhouse", "fictiv",           ["controls_engineering", "cnc", "manufacturing", "small_company"]),    # 70
    CompanyEntry("Divergent Technologies", "greenhouse", "divergent",     ["controls_engineering", "additive_manufacturing", "automation", "small_company"]),  # 56
    CompanyEntry("Ursa Major",          "greenhouse", "ursamajor",        ["controls_engineering", "aerospace", "manufacturing", "small_company"]),  # 38
    CompanyEntry("Stoke Space",         "greenhouse", "stokespacetechnologies", ["controls_engineering", "aerospace", "small_company"]),         # 54 (non-obvious slug)
    CompanyEntry("Seurat Technologies", "greenhouse", "seurat",           ["controls_engineering", "additive_manufacturing", "small_company"]),  # 3
    CompanyEntry("Outrider",            "greenhouse", "outrider",         ["controls_engineering", "robotics", "autonomy", "small_company"]),    # 6
    CompanyEntry("Dexterity",           "lever",      "dexterity",        ["controls_engineering", "robotics", "small_company"]),                # 8
    CompanyEntry("OSARO",               "lever",      "osaro",            ["controls_engineering", "robotics", "small_company"]),                # 10
    CompanyEntry("Copia Automation",    "lever",      "copia",            ["controls_engineering", "plc", "software", "small_company"]),         # 9 (Git for PLC code)
    CompanyEntry("Ambi Robotics",       "lever",      "ambirobotics",     ["controls_engineering", "robotics", "small_company"]),                # 8

    # --- Confirmed Ashby (verified 2026-06-09 against api.ashbyhq.com) ---
    CompanyEntry("Gecko Robotics",      "ashby",      "gecko-robotics",   ["controls_engineering", "robotics", "small_company"]),                # 10, Pittsburgh

    # --- Workday CSRF-disabled (JSON API works without a browser session) ---
    # Verified 2026-05-26: cat.wd5 returns 200 with job data, no CSRF required.
    CompanyEntry("Caterpillar",         "workday", "cat:5:CaterpillarCareers",               ["controls_engineering", "embedded", "heavy_equipment"]),

    # --- Direct (Workday with CSRF enabled — JS session required; scraping limited) ---
    # Confirmed as Workday but CSRF protection active: rockwellautomation:1, phstock:1,
    # honeywell:5, siemens:3, danaher:1, trimble:1 all return HTTP 422 on bare POST.
    CompanyEntry("Rockwell Automation", "direct", "https://rockwellautomation.wd1.myworkdayjobs.com/External",     ["controls_engineering", "plc", "scada"]),
    CompanyEntry("Honeywell",           "direct", "https://honeywell.wd5.myworkdayjobs.com/Honeywell_Jobs",        ["controls_engineering", "automation", "aerospace"]),
    CompanyEntry("Parker Hannifin",     "direct", "https://phstock.wd1.myworkdayjobs.com/Parker_Hannifin",         ["controls_engineering", "motion_control", "hydraulics"]),
    CompanyEntry("Siemens",             "direct", "https://siemens.wd3.myworkdayjobs.com/Siemens",                 ["controls_engineering", "automation", "plc"]),
    CompanyEntry("Danaher",             "direct", "https://danaher.wd1.myworkdayjobs.com/Danaher",                 ["controls_engineering", "instrumentation"]),
    CompanyEntry("Trimble",             "direct", "https://trimble.wd1.myworkdayjobs.com/Trimble_Careers",         ["controls_engineering", "gps", "automation"]),

    # --- Direct (non-Workday custom portals) ---
    CompanyEntry("Emerson Electric",    "direct", "https://www.emerson.com/en-us/careers/search-jobs",        ["controls_engineering", "process_control"]),
    CompanyEntry("Eaton",               "direct", "https://eaton.eightfold.ai/careers",                       ["controls_engineering", "power_management"]),
    CompanyEntry("Moog",                "direct", "https://www.moog.com/company/careers.html",                ["controls_engineering", "motion_control", "aerospace"]),
    CompanyEntry("Cognex",              "direct", "https://www.cognex.com/company/careers",                   ["controls_engineering", "machine_vision"]),
    CompanyEntry("Zebra Technologies",  "direct", "https://careers.zebra.com/careers/",                      ["controls_engineering", "automation", "iot"]),
    CompanyEntry("Roper Technologies",  "direct", "https://www.ropertech.com/careers",                       ["controls_engineering", "instrumentation"]),
    CompanyEntry("Keyence",             "direct", "https://www.keyence.com/company/careers/",                 ["controls_engineering", "sensors", "machine_vision"]),
    CompanyEntry("MathWorks",           "direct", "https://www.mathworks.com/company/jobs/opportunities/",   ["controls_engineering", "simulation", "matlab"]),
    CompanyEntry("Beckhoff Automation", "direct", "https://www.beckhoff.com/en-us/company/careers/",         ["controls_engineering", "plc", "automation"]),
    CompanyEntry("FANUC America",       "direct", "https://www.fanucamerica.com/company/careers",            ["controls_engineering", "robotics", "cnc"]),
    CompanyEntry("Yaskawa",             "direct", "https://www.yaskawa.com/us/careers",                      ["controls_engineering", "robotics", "motion_control"]),
    CompanyEntry("ABB",                 "direct", "https://careers.abb/global/en",                           ["controls_engineering", "automation", "robotics"]),
]


# ---------------------------------------------------------------------------
# Registry dict — add a new industry by adding a new key here
# ---------------------------------------------------------------------------
REGISTRIES: dict[str, list[CompanyEntry]] = {
    "health_informatics":   _HEALTH_INFORMATICS,
    "controls_engineering": _CONTROLS_ENGINEERING,
}

# Flat combined list (all industries)
REGISTRY: list[CompanyEntry] = [
    entry for entries in REGISTRIES.values() for entry in entries
]


def _load_user_companies(json_path: Optional[Path] = None) -> list[CompanyEntry]:
    """Load user-defined companies from companies.json. Returns [] if file missing or invalid."""
    from config import COMPANIES_JSON
    path = json_path or COMPANIES_JSON
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        entries = []
        for item in raw.get("companies", []):
            if "_example" in item or not item.get("name"):
                continue
            extra = item.get("extra") or {}
            entries.append(CompanyEntry(
                name=item["name"],
                ats_type=item.get("ats_type", "direct"),
                slug=item.get("slug", ""),
                industries=item.get("industries", []),
                extra=dict(extra) if isinstance(extra, dict) else {},
            ))
        return entries
    except Exception as e:
        print(f"  [registry] Warning: could not load {path.name} — {e}")
        return []


def save_companies(new_entries: list[CompanyEntry], json_path: Optional[Path] = None,
                   *, upgrade_unverified: bool = True) -> int:
    """Append companies to companies.json, preserving its comments/examples and
    skipping any whose (ats_type, slug) or name already exists. Atomic write.
    Returns the number actually added (fresh inserts + unverified upgrades).

    Re-verify path (P0-6): when ``upgrade_unverified`` is True (the default) an
    incoming VERIFIED entry (i.e. NOT flagged unverified) that matches an
    existing record by (ats_type, slug) OR name — where the STORED record is
    currently flagged unverified — UPGRADES it in place: the stored record's
    fields are replaced with the fresh entry's and the UNVERIFIED_FLAG is
    cleared (dropping `extra` if it becomes empty). This is what makes a board
    that failed its first live probe (a transient network blip / rate-limit /
    ATS outage, then kept-anyway) scrapeable again once the user re-adds,
    re-clips, or re-seeds it after it verifies — instead of being permanently
    locked out. A verified board already stored as verified stays a plain
    duplicate (skipped); an incoming still-unverified entry never overwrites a
    verified stored record.

    The read-modify-write is serialized by a module lock (_SAVE_LOCK) so
    concurrent writers (the threaded Flask /clip receiver, the GUI add) can't
    lose a write by racing on companies.json."""
    from config import COMPANIES_JSON
    path = json_path or COMPANIES_JSON
    with _SAVE_LOCK:
        return _save_companies_locked(new_entries, path,
                                      upgrade_unverified=upgrade_unverified)


def _save_companies_locked(new_entries: list[CompanyEntry], path: Path,
                           *, upgrade_unverified: bool) -> int:
    """The read-modify-write body of save_companies. MUST be called holding
    _SAVE_LOCK (see save_companies)."""
    from scrape.cache_helpers import write_cache
    try:
        raw = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception as e:
        print(f"  [registry] Could not read {path.name} — {e}; not saving.")
        return 0
    if not isinstance(raw, dict):
        raw = {}
    companies = raw.get("companies", [])
    real = [c for c in companies if "_example" not in c]
    # Index existing REAL records so a dup is a no-op and an upgrade can find &
    # mutate the stored record in place (identity = (ats_type, slug) or name).
    by_key = {(c.get("ats_type"), c.get("slug")): c for c in real}
    by_name = {(c.get("name") or "").lower(): c for c in real}

    def _record_for(e: CompanyEntry) -> dict:
        record = {
            "name": e.name,
            "ats_type": e.ats_type,
            "slug": e.slug,
            "industries": list(e.industries),
        }
        # Only persist `extra` when non-empty so byte-identical output is
        # preserved for the vast majority of boards that carry no side-channel
        # metadata (a bare {} would gratuitously churn every existing entry).
        if getattr(e, "extra", None):
            record["extra"] = dict(e.extra)
        return record

    changed = 0
    for e in new_entries:
        existing = by_key.get((e.ats_type, e.slug)) or by_name.get(e.name.lower())
        if existing is not None:
            # A verified re-add of a board stored as unverified clears the flag
            # (user-wins-by-identity) so it re-enters the scraped set. Any other
            # collision (verified<->verified, or an incoming still-unverified
            # entry) stays a no-op skip — we never demote a verified record.
            if (upgrade_unverified and not is_unverified(e)
                    and bool((existing.get("extra") or {}).get(UNVERIFIED_FLAG))):
                upgraded = _record_for(e)
                # Merge industries (union) so a re-verify with a different active
                # field doesn't silently drop the board's prior field tags.
                merged = list(dict.fromkeys(
                    list(existing.get("industries") or []) + list(e.industries)))
                upgraded["industries"] = merged
                existing.clear()
                existing.update(upgraded)
                changed += 1
            continue
        record = _record_for(e)
        companies.append(record)
        by_key[(e.ats_type, e.slug)] = record
        by_name[e.name.lower()] = record
        changed += 1

    if changed:
        raw["companies"] = companies
        write_cache(path, raw)
    return changed


def _normalize_industry(s: str) -> str:
    """Canonical industry token form: lowercase, and every word boundary
    (space or hyphen) folded to a single underscore. So 'Data Analytics',
    'data analytics', 'data-analytics' and 'data_analytics' all normalize to
    'data_analytics'. Used on BOTH sides of _industry_tag_match so the lookup
    key and the stored company tag are always compared apples-to-apples."""
    import re
    return re.sub(r"[\s\-_]+", "_", (s or "").strip().lower()).strip("_")


def _industry_tag_match(key: str, tag: str) -> bool:
    """Token-aware, symmetric industry/tag match.

    Both `key` (the --industry value) and `tag` (a company industry tag) are
    normalized to the same underscore-token form first (P0-1: the old code
    normalized only the key, so any multi-word field — 'warehouse logistics',
    'mechanical engineering', 'data analytics' — matched 0 companies because the
    stored tag kept its spaces).

    Matching is on WHOLE tokens, not raw substrings, which fixes two bugs at
    once:

      * multi-word fields now match their own seeds (all tokens equal), and
      * a generic single-token tag no longer bleeds into an unrelated compound
        field. The old bidirectional substring test let 'analytics' match
        'data_analytics' (`'analytics' in 'data_analytics'`), so a search for
        'data analytics' pulled in 7 wrong-vertical health-informatics companies
        tagged 'analytics' while excluding the user's real 'data analytics'
        seeds. Whole-token subset matching drops that leak.

    A user company tagged the SHORTER 'controls' must still survive industry
    'controls_engineering', so the tag-is-subset-of-key direction is kept — but
    ONLY when the tag is a leading-token prefix of the key ('controls_' heads
    'controls_engineering'). A trailing generic token ('analytics' in
    'data_analytics', 'engineering' in 'controls_engineering') is not a
    prefix, so it no longer matches an unrelated field."""
    k = _normalize_industry(key)
    t = _normalize_industry(tag)
    if not k or not t:
        return False
    if k == t:
        return True
    ks = [x for x in k.split("_") if x]
    ts = [x for x in t.split("_") if x]
    kset, tset = set(ks), set(ts)
    # Searched field's tokens are all present in the company's (more specific)
    # tag: a broad 'logistics' search catches a 'warehouse_logistics' company,
    # and 'controls' catches 'controls_engineering'.
    if kset <= tset:
        return True
    # Company tag is a subset of the searched field, but only when the tag is a
    # leading-token prefix of the key (so 'controls' -> 'controls_engineering'
    # still works, while 'analytics' -> 'data_analytics' does not).
    if tset <= kset and k.startswith(t + "_"):
        return True
    return False


def has_industry(industry: str | None, user_json: Optional[Path] = None) -> bool:
    """True when the registry has at least one company for `industry` (hardcoded
    ∪ companies.json). Empty/None industry -> True (the whole registry applies).
    Used to decide whether a non-tech first-run needs a free discovery pass so it
    isn't left with an empty, eng-only starter registry (plan 1D)."""
    if not (industry or "").strip():
        return True
    return bool(get_registry(industry=industry, user_json=user_json))


def industry_company_count(industry: str | None, user_json: Optional[Path] = None) -> int:
    """How many registry companies (hardcoded ∪ companies.json) match `industry`.
    Empty/None → the whole registry size. Lets callers warn before a search when a
    field has almost no employers (the ATS-scraper path would return ~0)."""
    if not (industry or "").strip():
        return len(get_registry(user_json=user_json))
    return len(get_registry(industry=industry, user_json=user_json))


def registry_stats(user_json: Optional[Path] = None) -> dict[str, int]:
    """Company count per industry TAG across the merged registry. Powers a
    'companies for your field' readout so an empty/eng-only registry is visible
    before a live search returns near-zero (finding #28)."""
    from collections import Counter
    counts: Counter = Counter()
    for e in get_registry(user_json=user_json):
        for tag in (e.industries or ["(untagged)"]):
            counts[tag] += 1
    return dict(counts)


def get_registry(industry: str | None = None, user_json: Optional[Path] = None,
                 include_unverified: bool = False) -> list[CompanyEntry]:
    """Return companies filtered by industry key or tag, merged with user companies.json.

    User entries override hardcoded ones by name (case-insensitive match).
    Pass user_json=Path(...) to use a non-default file path.

    By default (include_unverified=False) any user entry flagged unverified
    (failed its live probe at add-time, P0-6) is EXCLUDED — this is what keeps
    dead/junk boards from being scraped and re-throwing soft errors every run.
    Pass include_unverified=True to see them too (e.g. a prune/manage UI).
    """
    user_entries = _load_user_companies(user_json)
    if not include_unverified:
        user_entries = [e for e in user_entries if not is_unverified(e)]

    # Build base list: hardcoded registry filtered by industry
    if industry is None:
        base = list(REGISTRY)
    else:
        key = _normalize_industry(industry)
        if key in REGISTRIES:
            base = list(REGISTRIES[key])
        else:
            base = [e for e in REGISTRY
                    if any(_industry_tag_match(key, tag) for tag in e.industries)]

    # Filter user entries by industry too. The tag match is symmetric and
    # token-aware (see _industry_tag_match): a user company tagged ['controls']
    # survives --industry controls_engineering, and a multi-word field
    # ('warehouse logistics') now matches its own seeds instead of silently
    # dropping every one of them (P0-1).
    if industry is not None:
        key = _normalize_industry(industry)
        user_entries = [
            e for e in user_entries
            if not e.industries or any(_industry_tag_match(key, t) for t in e.industries)
        ]

    if not user_entries:
        return base

    # Merge: user wins on name collision
    base_by_name = {e.name.lower(): e for e in base}
    for ue in user_entries:
        base_by_name[ue.name.lower()] = ue
    return list(base_by_name.values())
