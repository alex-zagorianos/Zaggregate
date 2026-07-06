"""Metro company enumeration — the discovery layer that proposes LOCAL employers
to add to the registry.

The deterministic funnel already resolves a domain -> careers URL -> ATS board
-> verified entry (discover.funnel.harvest_from_domains + scrape.ats_detect.
probe_count). The missing piece is *enumerating which local companies to feed it*.
An LLM (Claude/Sonnet) is good at "list employers HQ'd near Cincinnati that hire
controls/software/mechanical engineers"; it also hallucinates — which is fine here
because every proposal is run through the probe-verify gate, so fake or dead
companies are simply dropped (they never resolve to a live board).

This module only does the LLM step, mirroring ranker.py's Bridge/Api duality:
  - API (auto) when an Anthropic key is present (ranker.api_key()).
  - Clipboard bridge otherwise: build a prompt, the user pastes it into claude.ai
    and pastes the JSON reply back.
The resolve + verify + save pipeline lives in enumerate_companies.py.
"""
from __future__ import annotations

import json
import re
from urllib.parse import urlsplit

import config
from claude_bridge import _extract_json

# Default enumeration angles — several focused asks cover more of the metro than
# one generic prompt (a single call under-returns and skews to famous names).
DEFAULT_ANGLES = [
    "",  # generic
    "Focus on large employers, manufacturers, and industrials.",
    "Focus on startups, small, and mid-size engineering firms.",
    "Focus on automation, robotics, controls, and systems-integration shops.",
    "Focus on software, AI/ML, data, and product companies.",
]

# Industry tags that the eng-flavored DEFAULT_ANGLES already cover well. When the
# resolved industry is one of these (or empty), angles_for_industry returns
# DEFAULT_ANGLES *byte-identically* — so the default controls flow is unchanged.
_ENG_INDUSTRY_TOKENS = {
    "controls", "control", "engineering", "engineer", "software", "robotics",
    "robot", "embedded", "mechanical", "mechatronics", "automation", "hardware",
    "electrical", "manufacturing", "industrial", "aerospace", "systems",
    "ai", "ml", "applied",
}


def _industry_tokens(industry: str):
    return [t for t in re.split(r"[\s_\-/,]+", (industry or "").lower()) if t]


def is_eng_like(industry: str) -> bool:
    """True when the eng-flavored DEFAULT_ANGLES fit this industry (or it's empty)."""
    return any(t in _ENG_INDUSTRY_TOKENS for t in _industry_tokens(industry))


def humanize_industry(industry: str, keywords=None) -> str:
    """A readable field label for prompts ('health_informatics' -> 'health
    informatics'); falls back to the first keyword, then a neutral phrase."""
    label = (industry or "").replace("_", " ").replace("-", " ").strip()
    if label:
        return label
    for k in keywords or []:
        if (k or "").strip():
            return k.strip()
    return "engineering and software"


def _national_angles(industry: str, keywords=None):
    field = ("engineering and software" if (not (industry or "").strip()
             or is_eng_like(industry)) else humanize_industry(industry, keywords))
    return [
        "",
        f"Focus on large national employers and enterprises hiring for {field} roles anywhere in the US.",
        f"Focus on remote-first and fully-distributed companies hiring {field} roles.",
        f"Focus on well-known, market-leading {field} employers that hire nationwide.",
        f"Focus on {field} companies likely to run an online applicant tracking system.",
    ]


def angles_for_industry(industry: str = "", keywords=None, *, scope: str = "metro"):
    """Enumeration angles tuned to a field.

    - scope='national' -> nationwide/remote-first angle set (plan P5).
    - empty or eng-like industry -> DEFAULT_ANGLES byte-identically (default profile unchanged).
    - any other field -> neutral size/type-spread angles NAMING that field, so a
      health-informatics (or nursing, legal, finance…) seeker gets the same breadth.
    """
    if scope == "national":
        return _national_angles(industry, keywords)
    if not (industry or "").strip() or is_eng_like(industry):
        return list(DEFAULT_ANGLES)
    field = humanize_industry(industry, keywords)
    return [
        "",
        f"Focus on large employers, enterprises, and market leaders in {field}.",
        f"Focus on startups and small-to-mid-size {field} companies.",
        f"Focus on the most specialized and niche {field} employers.",
        f"Focus on {field} companies likely to run an online applicant tracking system.",
    ]


def normalize_domain(value: str) -> str:
    """Bare registrable host for dedup: lowercased, no scheme/www/path/port."""
    if not value:
        return ""
    v = value.strip().lower()
    if "//" not in v:
        v = "//" + v  # let urlsplit treat it as a netloc, not a path
    host = urlsplit(v).netloc or urlsplit("//" + value.strip().lower()).netloc
    host = host.split("@")[-1].split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    return host.strip("/")


def build_enumeration_prompt(metro: str, industries, *, exclude_names=(),
                             angle: str = "", limit: int = 40) -> str:
    """A prompt asking for a JSON array of {name, domain} employers in/near the
    metro for the given industries, excluding already-known companies."""
    inds = ", ".join(i for i in industries if i) or "engineering and software"
    excl = sorted({(n or "").strip() for n in exclude_names if (n or "").strip()})
    excl_block = ""
    if excl:
        # Cap the exclusion list so the prompt stays small; the save step dedups
        # the rest of the way regardless.
        shown = excl[:150]
        excl_block = ("\nDo NOT include these companies (already known):\n"
                      + ", ".join(shown) + "\n")
    focus = f"\n{angle}\n" if angle else "\n"
    return (
        f"List up to {limit} real employers headquartered in or near the "
        f"{metro} metro area (within about 50 miles, including nearby suburbs and "
        f"adjacent states) that hire for {inds} roles.{focus}"
        "Prefer companies likely to run an online careers page or applicant "
        "tracking system. Include a healthy mix of company sizes.\n"
        "Return ONLY a JSON array, no prose, where each item is "
        '{"name": "<company>", "domain": "<primary website domain, e.g. acme.com>"}. '
        "Use the company's real primary domain (no http://, no www, no paths)."
        f"{excl_block}"
    )


def parse_enumeration_response(text: str) -> list[dict]:
    """Parse a pasted/returned reply into a deduped [{name, domain}] list.
    Tolerant of code fences / prose (reuses claude_bridge._extract_json)."""
    if not text or not text.strip():
        return []
    try:
        payload = json.loads(_extract_json(text, prefer="array"))
    except (json.JSONDecodeError, ValueError):
        return []
    if isinstance(payload, dict):  # {"companies": [...]} or similar
        for v in payload.values():
            if isinstance(v, list):
                payload = v
                break
        else:
            return []
    if not isinstance(payload, list):
        return []
    out, seen = [], set()
    for item in payload:
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or "").strip()
        domain = normalize_domain(item.get("domain") or "")
        if not name or not domain or domain in seen:
            continue
        seen.add(domain)
        out.append({"name": name, "domain": domain})
    return out


def dedupe_candidates(candidates, *, exclude_domains=()) -> list[dict]:
    """Dedup by domain and drop any already-known domains."""
    excl = {normalize_domain(d) for d in exclude_domains if d}
    out, seen = [], set()
    for c in candidates or []:
        d = normalize_domain(c.get("domain", ""))
        if not d or d in seen or d in excl:
            continue
        seen.add(d)
        out.append({"name": (c.get("name") or "").strip(), "domain": d})
    return out


def enumerate_via_api(metro: str, industries, *, exclude_names=(),
                      exclude_domains=(), model: str | None = None,
                      angles=None, limit: int = 40) -> list[dict]:
    """Call the Anthropic API once per angle and return a deduped candidate list.
    Reuses ranker.api_key() (ANTHROPIC_API_KEY or secrets/anthropic_key). Raises
    RuntimeError when no key is configured (caller should fall back to the bridge)."""
    import ranker
    key = ranker.api_key()
    if not key:
        raise RuntimeError(
            "No Anthropic API key — set ANTHROPIC_API_KEY or secrets/anthropic_key, "
            "or use the clipboard bridge (--bridge)."
        )
    import anthropic
    client = anthropic.Anthropic(api_key=key, base_url=config.anthropic_base_url())
    angles = DEFAULT_ANGLES if angles is None else angles
    all_candidates: list[dict] = []
    for angle in angles:
        prompt = build_enumeration_prompt(metro, industries, exclude_names=exclude_names,
                                          angle=angle, limit=limit)
        msg = client.messages.create(
            model=model or config.ANTHROPIC_MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(getattr(b, "text", "") for b in msg.content
                       if getattr(b, "type", None) == "text")
        all_candidates.extend(parse_enumeration_response(text))
    return dedupe_candidates(all_candidates, exclude_domains=exclude_domains)
