"""One place that makes the app genre-agnostic.

Every per-field ("genre") knob the app needs to adapt to a NON-engineering
seeker lives here, resolved from a single call: `resolve(industry)`. Previously
this knowledge was scattered across hardcoded maps (Muse categories, Jobicy
industry, relevance title-terms, enumeration angles), so supporting a new field
meant editing several files. Now:

    resolve("culinary arts") -> IndustryProfile(muse_categories=[...], ...)

Resolution order (first hit wins):
  1. USER / AI OVERRIDE  — <USER_DATA_DIR>/industry_profiles.json. Human-editable
     AND the target the optional AI enrichment writes to. This is the "somewhere
     to put instructions/tweaks" — edit the JSON, or let the AI fill it.
  2. SHIPPED SEED        — the _SEED rules below (engineering, health, finance,
     nursing, education, legal, trades, ... — the common genres work out of the box).
  3. GENERIC FALLBACK    — safe defaults that RETAIN FULL REACH: no Muse category
     filter (fetch all, keyword-filter), skip the tech-only Jobicy board, no
     synonyms. So an unknown genre still searches broadly; it just isn't routed.

Reach is never reduced: category routing only *adds precision*; query synonyms
only *widen* recall (capped); the generic fallback fetches everything.

The engineering profile stays effectively unchanged for Alex (see ENG_MUSE note).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# The Muse's real category taxonomy (validated live 2026-07-01 against the public
# API — several plausible names like "Engineering"/"IT"/"Finance" are NOT valid and
# silently return 0, so only these strings may be emitted).
MUSE_CATEGORIES_ALL = [
    "Account Management", "Accounting and Finance", "Advertising and Marketing",
    "Animal Care", "Business Operations", "Cleaning and Facilities", "Construction",
    "Data and Analytics", "Education", "Energy Generation and Mining",
    "Food and Hospitality Services", "Healthcare", "Human Resources and Recruitment",
    "Installation, Maintenance, and Repairs", "Legal Services", "Management",
    "Project Management", "Sales", "Science and Engineering", "Software Engineering",
    "Sports, Fitness, and Recreation",
]
_MUSE_VALID = set(MUSE_CATEGORIES_ALL)

# NOTE: the app previously requested Muse category "Engineering" (invalid -> 0) plus
# "Science and Engineering", so engineering searches silently missed the entire
# "Software Engineering" category. The eng profile below uses the CORRECT pair, so
# Alex's Muse reach GROWS (never shrinks) — consistent with "retain the blast radius".
_ENG_MUSE = ["Software Engineering", "Science and Engineering"]


@dataclass
class IndustryProfile:
    industry: str
    muse_categories: list[str] = field(default_factory=list)  # [] => all (no filter)
    jobicy_industry: Optional[str] = None                     # None => skip Jobicy
    query_synonyms: list[str] = field(default_factory=list)   # extra broad query terms (ADD only)
    title_terms: list[str] = field(default_factory=list)      # role words for relevance classification
    eng_like: bool = False
    source: str = "generic"                                   # user | seed | ai | generic

    def as_dict(self) -> dict:
        return {"muse_categories": self.muse_categories,
                "jobicy_industry": self.jobicy_industry,
                "query_synonyms": self.query_synonyms,
                "title_terms": self.title_terms}


def _tokens(industry: str) -> list[str]:
    return [t for t in re.split(r"[\s_\-/,]+", (industry or "").lower()) if t]


# ── shipped seed rules ────────────────────────────────────────────────────────
# Each rule: a set of industry tokens -> the knobs. First rule whose tokens
# intersect the industry wins. Engineering first so eng-flavored fields resolve to
# the eng profile (byte-identical intent). Add a field = add a rule here OR (better,
# no code change) an entry in the user JSON.
_RULES: list[tuple[set[str], dict]] = [
    ({"software", "developer", "programming", "backend", "frontend", "fullstack",
      "devops", "sre", "web"},
     {"muse": _ENG_MUSE, "jobicy": "engineering", "syn": [],
      "titles": ["engineer", "developer", "software"]}),
    ({"engineering", "engineer", "controls", "control", "robotics", "robot",
      "embedded", "mechanical", "mechatronics", "automation", "hardware",
      "electrical", "manufacturing", "industrial", "aerospace", "systems",
      "ai", "ml", "applied"},
     {"muse": _ENG_MUSE, "jobicy": "engineering", "syn": [],
      "titles": ["engineer", "engineering", "technician"]}),
    ({"health", "healthcare", "clinical", "medical", "informatics", "ehr", "emr",
      "hospital", "patient", "pharma", "pharmacy", "biomedical", "digital"},
     {"muse": ["Healthcare", "Data and Analytics"], "jobicy": None,
      "syn": ["clinical informatics", "healthcare analytics", "health data",
              "electronic health record", "epic"],
      "titles": ["clinical", "informatics", "health", "analyst", "epic", "ehr",
                 "nurse", "physician", "director", "vp", "chief"]}),
    ({"nursing", "nurse", "rn", "lpn", "caregiver", "care"},
     {"muse": ["Healthcare"], "jobicy": None,
      "syn": ["registered nurse", "patient care"],
      "titles": ["nurse", "nursing", "rn", "clinical", "care"]}),
    ({"data", "analytics", "analyst", "science", "bi"},
     {"muse": ["Data and Analytics"], "jobicy": "data-science",
      "syn": ["data analyst", "business intelligence"],
      "titles": ["data", "analyst", "analytics", "scientist"]}),
    ({"finance", "financial", "accounting", "accountant", "audit", "banking",
      "investment"},
     {"muse": ["Accounting and Finance", "Business Operations"], "jobicy": "finance",
      "syn": ["accounting", "financial analyst"],
      "titles": ["finance", "financial", "accountant", "accounting", "audit", "analyst"]}),
    ({"sales", "account", "business-development"},
     {"muse": ["Sales", "Account Management"], "jobicy": "sales",
      "syn": [], "titles": ["sales", "account", "representative"]}),
    ({"marketing", "advertising", "pr", "communications", "brand", "content"},
     {"muse": ["Advertising and Marketing"], "jobicy": "marketing",
      "syn": [], "titles": ["marketing", "brand", "content", "communications"]}),
    ({"education", "teacher", "teaching", "school", "academic", "professor",
      "instructor", "tutor"},
     {"muse": ["Education"], "jobicy": None,
      "syn": ["teacher", "instructor"], "titles": ["teacher", "instructor", "education", "professor"]}),
    ({"legal", "law", "attorney", "paralegal", "compliance", "counsel"},
     {"muse": ["Legal Services"], "jobicy": "legal",
      "syn": [], "titles": ["legal", "attorney", "counsel", "paralegal", "compliance"]}),
    ({"hr", "human-resources", "recruiting", "recruiter", "talent", "people"},
     {"muse": ["Human Resources and Recruitment"], "jobicy": "hr",
      "syn": ["recruiter", "talent acquisition"], "titles": ["recruiter", "human resources", "talent", "hr"]}),
    ({"operations", "ops", "admin", "administrative", "office", "logistics",
      "supply", "procurement"},
     {"muse": ["Business Operations", "Project Management", "Management"], "jobicy": "business",
      "syn": [], "titles": ["operations", "coordinator", "administrator", "manager", "logistics"]}),
    ({"design", "ux", "ui", "graphic", "product-design"},
     {"muse": ["Software Engineering"], "jobicy": "design",
      "syn": ["ux designer"], "titles": ["design", "designer", "ux", "ui"]}),
    ({"construction", "trades", "trade", "hvac", "plumbing", "electrician",
      "carpentry", "welding"},
     {"muse": ["Construction", "Installation, Maintenance, and Repairs"], "jobicy": None,
      "syn": [], "titles": ["technician", "installer", "construction", "mechanic", "trades"]}),
    ({"hospitality", "food", "culinary", "chef", "restaurant", "hotel", "kitchen"},
     {"muse": ["Food and Hospitality Services"], "jobicy": None,
      "syn": [], "titles": ["chef", "cook", "hospitality", "restaurant", "kitchen"]}),
    ({"energy", "oil", "gas", "mining", "utilities", "power"},
     {"muse": ["Energy Generation and Mining", "Science and Engineering"], "jobicy": None,
      "syn": [], "titles": ["energy", "power", "utilities", "technician", "engineer"]}),
    ({"fitness", "sports", "recreation", "wellness", "coach", "trainer"},
     {"muse": ["Sports, Fitness, and Recreation"], "jobicy": None,
      "syn": [], "titles": ["coach", "trainer", "fitness", "instructor"]}),
    ({"veterinary", "animal", "vet", "zoo"},
     {"muse": ["Animal Care"], "jobicy": None,
      "syn": [], "titles": ["veterinary", "animal", "vet"]}),
    ({"transportation", "driver", "driving", "trucking", "delivery", "warehouse",
      "fleet", "courier", "cdl"},
     {"muse": ["Business Operations", "Installation, Maintenance, and Repairs"],
      "jobicy": None, "syn": [],
      "titles": ["driver", "transportation", "logistics", "warehouse", "delivery"]}),
    ({"customer", "support", "success", "helpdesk", "call-center"},
     {"muse": ["Account Management"], "jobicy": None, "syn": [],
      "titles": ["customer", "support", "service", "representative", "success"]}),
    ({"management", "executive", "operations-leadership"},
     {"muse": ["Management", "Business Operations"], "jobicy": "business",
      "syn": [], "titles": ["manager", "director", "vp", "chief", "head"]}),
]


# ── SOC major-group (2-digit) -> source knobs (item 23) ────────────────────────
# The 23 BLS/O*NET-SOC major groups, mapped to Muse categories + a Jobicy slug so
# The Muse / Jobicy category selection works for ANY occupation the O*NET tier
# resolves (below), not just the ~20 hand-listed fields in _RULES above. _RULES
# still wins whenever it matches (byte-identical for every field already
# covered) — this table only BACKS the O*NET-SOC tier for everything else.
# muse: [] where no Muse category cleanly covers the group (keeps full reach —
# the client still fetches unfiltered + keyword-matches, rather than mis-route).
SOC_MAJOR_GROUPS: dict[str, dict] = {
    "11": {"muse": ["Management", "Business Operations"], "jobicy": "management"},
    "13": {"muse": ["Accounting and Finance", "Business Operations"], "jobicy": "business"},
    "15": {"muse": ["Software Engineering", "Data and Analytics"], "jobicy": "engineering"},
    "17": {"muse": ["Science and Engineering"], "jobicy": "engineering"},
    "19": {"muse": ["Science and Engineering"], "jobicy": None},
    "21": {"muse": [], "jobicy": None},
    "23": {"muse": ["Legal Services"], "jobicy": "legal"},
    "25": {"muse": ["Education"], "jobicy": None},
    "27": {"muse": [], "jobicy": "design"},
    "29": {"muse": ["Healthcare"], "jobicy": None},
    "31": {"muse": ["Healthcare"], "jobicy": None},
    "33": {"muse": [], "jobicy": None},
    "35": {"muse": ["Food and Hospitality Services"], "jobicy": None},
    "37": {"muse": ["Cleaning and Facilities"], "jobicy": None},
    "39": {"muse": ["Sports, Fitness, and Recreation"], "jobicy": None},
    "41": {"muse": ["Sales", "Account Management"], "jobicy": "sales"},
    "43": {"muse": ["Business Operations"], "jobicy": "admin"},
    "45": {"muse": [], "jobicy": None},
    "47": {"muse": ["Construction"], "jobicy": None},
    "49": {"muse": ["Installation, Maintenance, and Repairs"], "jobicy": None},
    "51": {"muse": [], "jobicy": None},
    "53": {"muse": ["Business Operations", "Installation, Maintenance, and Repairs"], "jobicy": None},
    "55": {"muse": [], "jobicy": None},
}


def _user_json_path() -> Path:
    import config
    return Path(config.USER_DATA_DIR) / "industry_profiles.json"


def _load_user_overrides() -> dict:
    p = _user_json_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _sanitize_muse(cats) -> list[str]:
    """Keep only real Muse category names so a typo/hallucination can't zero out a
    source (an invalid category returns 0)."""
    return [c for c in (cats or []) if c in _MUSE_VALID]


_cache: dict[str, IndustryProfile] = {}


def resolve(industry: Optional[str]) -> IndustryProfile:
    """The one call. Returns the genre knobs for `industry` (user override > seed >
    generic). Empty/None industry -> the engineering profile (today's default)."""
    key = (industry or "").strip().lower()
    if key in _cache:
        return _cache[key]

    from discover.enumerate import is_eng_like
    eng = is_eng_like(industry or "")

    # 1) user / AI override (matched by exact key or any token)
    overrides = _load_user_overrides()
    ov = overrides.get(key)
    if ov is None and key:
        toks = set(_tokens(industry))
        for okey, oval in overrides.items():
            if toks & set(_tokens(okey)):
                ov = oval
                break
    if ov:
        prof = IndustryProfile(
            industry=key,
            muse_categories=_sanitize_muse(ov.get("muse_categories")),
            jobicy_industry=ov.get("jobicy_industry"),
            query_synonyms=list(ov.get("query_synonyms") or []),
            title_terms=list(ov.get("title_terms") or []),
            eng_like=eng, source="user")
        _cache[key] = prof
        return prof

    # 2) empty / eng -> engineering profile (Alex path)
    if not key or eng:
        prof = IndustryProfile(
            industry=key or "engineering", muse_categories=list(_ENG_MUSE),
            jobicy_industry="engineering", query_synonyms=[],
            title_terms=["engineer", "engineering"], eng_like=True, source="seed")
        _cache[key] = prof
        return prof

    # 3) seed rule by token intersection
    toks = set(_tokens(industry))
    for rule_tokens, knobs in _RULES:
        if toks & rule_tokens:
            prof = IndustryProfile(
                industry=key, muse_categories=_sanitize_muse(knobs["muse"]),
                jobicy_industry=knobs["jobicy"], query_synonyms=list(knobs["syn"]),
                title_terms=list(knobs["titles"]), eng_like=False, source="seed")
            _cache[key] = prof
            return prof

    # 4) generic fallback — full reach, no routing
    prof = IndustryProfile(industry=key, muse_categories=[], jobicy_industry=None,
                           query_synonyms=[], title_terms=[], eng_like=False,
                           source="generic")
    _cache[key] = prof
    return prof


def clear_cache() -> None:
    _cache.clear()


# ── AI / human tweak surface ──────────────────────────────────────────────────
# The instructions an AI (or a person) follows to add/adjust a field's knobs. The
# output is written to <USER_DATA_DIR>/industry_profiles.json under the field key.
AI_PROFILE_INSTRUCTIONS = f"""\
You are configuring a job-search app to work well for a specific FIELD/industry.
Return ONLY a JSON object for the given field with these keys:

  "muse_categories": array of 0+ category names, chosen ONLY from this exact list
      (any other string is ignored): {MUSE_CATEGORIES_ALL}
      Pick the 1-3 that best cover the field. Use [] if none fit (the app then
      searches ALL categories and filters by keyword).
  "jobicy_industry": one of engineering|business|marketing|design|finance|hr|
      sales|management|data-science|devops|product|legal|admin, or null if the
      field is not a remote-tech field (Jobicy is a tech-centric remote board).
  "query_synonyms": 0-5 short, BROAD field search terms to ADD for recall
      (e.g. for health informatics: ["clinical informatics","healthcare analytics"]).
      Do NOT include seniority words (VP/Director) — those are handled separately.
  "title_terms": 5-12 lowercase words that appear in RELEVANT job TITLES for this
      field (used to keep on-topic postings and drop off-topic ones).

Keep it broad (do not shrink reach). Field: """


def build_ai_prompt(industry: str) -> str:
    return AI_PROFILE_INSTRUCTIONS + json.dumps(industry)


def stub_for(industry: str) -> dict:
    """A fillable template (resolved seed/generic values) a human can edit into the
    user JSON without starting from scratch."""
    p = resolve(industry)
    return p.as_dict()


def save_override(industry: str, profile: dict) -> Path:
    """Write/replace one field's knobs in the user JSON (used by --generate-stub and
    by AI enrichment). Sanitizes Muse categories. Returns the path."""
    key = (industry or "").strip().lower()
    p = _user_json_path()
    data = _load_user_overrides()
    data[key] = {
        "muse_categories": _sanitize_muse(profile.get("muse_categories")),
        "jobicy_industry": profile.get("jobicy_industry"),
        "query_synonyms": list(profile.get("query_synonyms") or []),
        "title_terms": list(profile.get("title_terms") or []),
    }
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    clear_cache()
    return p


def enrich_via_ai(industry: str) -> Optional[dict]:
    """Ask Claude to produce a profile for `industry` and cache it to the user JSON.
    Returns the profile dict, or None if no API key / call failed (caller falls back
    to seed/generic — reach is never lost)."""
    import os
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=500,
            messages=[{"role": "user", "content": build_ai_prompt(industry)}])
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        text = text[text.find("{"): text.rfind("}") + 1]
        prof = json.loads(text)
        save_override(industry, prof)
        return prof
    except Exception:
        return None


def _main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Inspect/generate the genre profile for a field")
    ap.add_argument("--industry", required=True)
    ap.add_argument("--ai", action="store_true", help="Fill it via Claude (needs ANTHROPIC_API_KEY) and cache")
    ap.add_argument("--generate-stub", action="store_true",
                    help="Write an editable stub to the user JSON to hand-tweak")
    args = ap.parse_args(argv)
    if args.ai:
        got = enrich_via_ai(args.industry)
        print("AI profile cached." if got else "No API key / AI failed; using seed/generic.")
    if args.generate_stub:
        path = save_override(args.industry, stub_for(args.industry))
        print(f"Wrote editable stub to {path} — edit the '{args.industry.lower()}' entry.")
    p = resolve(args.industry)
    print(json.dumps({"industry": p.industry, "source": p.source, **p.as_dict()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
