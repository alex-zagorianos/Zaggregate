"""Discover — BYO-AI career/role recommendations (EXPERIMENTAL, S36c).

Builds a clipboard prompt from the user's experience + preferences + current
search targets + tracked-job signal, parses the AI's structured reply into
recommendation cards, and applies a card's keywords to the project's search
config (additive only). No AI API calls — the same paste-round-trip bridge the
rank/resume flows use.

Kept deliberately ISOLATED so the whole feature is one-commit removable:
this module + ``webui/api/recommend.py`` + ``webui/frontend/src/tabs/discover``
+ one registry line each. Persistence is a single JSON file in the project dir
(``recommendations.json``) — no tracker-db schema, no tk twin (web-only).

Import-safe (no tkinter, no network). Every path resolves the ACTIVE project
per call (S27 discipline — nothing cached at import).
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import workspace

_STATE_NAME = "recommendations.json"
_LANES = ("core", "adjacent", "stretch")
_MAX_KEYWORDS_PER_REC = 8
_MAX_SAMPLE_TITLES = 6
_MAX_RECS = 12
_EXPERIENCE_CHAR_CAP = 12_000     # keep the prompt paste-able into free tiers
_TRACKED_SAMPLE = 15


# ── persistence ───────────────────────────────────────────────────────────────

def _state_path(slug: str | None = None) -> Path:
    return Path(workspace.project_dir(slug)) / _STATE_NAME


def load_state(slug: str | None = None) -> dict:
    """The saved Discover state: ``{generated_at, interests, recommendations}``.
    Tolerant — a missing/corrupt file is an empty state, never an error."""
    try:
        raw = json.loads(_state_path(slug).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"generated_at": None, "interests": "", "recommendations": []}
    if not isinstance(raw, dict):
        return {"generated_at": None, "interests": "", "recommendations": []}
    return {
        "generated_at": raw.get("generated_at"),
        "interests": str(raw.get("interests") or ""),
        "recommendations": [r for r in (raw.get("recommendations") or [])
                            if isinstance(r, dict) and r.get("role")],
    }


def save_state(state: dict, slug: str | None = None) -> None:
    p = _state_path(slug)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n",
                 encoding="utf-8")


# ── prompt ────────────────────────────────────────────────────────────────────

def _experience_text(slug: str | None = None) -> str:
    """The raw experience.md (capped) — richer for an AI reader than the parsed
    section dict, and decoupled from the parser's heading rules."""
    try:
        text = Path(workspace.experience_file(slug)).read_text(encoding="utf-8")
    except OSError:
        return ""
    return text.strip()[:_EXPERIENCE_CHAR_CAP]


def _preferences_block() -> str:
    try:
        import preferences
        prefs = preferences.load()
    except Exception:
        return ""
    hard = prefs.get("hard") or {}
    lines = []
    if hard.get("salary_min"):
        lines.append(f"- Salary floor: ${hard['salary_min']:,}")
    if hard.get("locations"):
        lines.append(f"- Locations: {', '.join(map(str, hard['locations']))}")
    if hard.get("remote_ok") is not None:
        lines.append(f"- Remote OK: {bool(hard['remote_ok'])}")
    if hard.get("dealbreakers"):
        lines.append(f"- Dealbreakers: {', '.join(map(str, hard['dealbreakers']))}")
    profile = (prefs.get("profile_md") or "").strip()
    if profile:
        lines.append("")
        lines.append(profile[:3000])
    return "\n".join(lines)


def _current_targets_block(cfg: dict) -> str:
    lines = []
    kws = cfg.get("keywords") or []
    if kws:
        lines.append("Already searching for: " + "; ".join(map(str, kws)))
    if cfg.get("industry"):
        lines.append(f"Field: {cfg['industry']}")
    excl = (cfg.get("exclude_titles") or []) + (cfg.get("exclude_keywords") or [])
    if excl:
        lines.append("Explicitly NOT interested in: " + "; ".join(map(str, excl)))
    return "\n".join(lines)


def _tracked_block() -> str:
    """Titles the user chose to track = revealed interest. Best-effort ('' when
    the tracker is empty/unavailable) — the prompt must never be blocked."""
    try:
        from tracker import service
        rows = service.list_jobs() or []
    except Exception:
        return ""
    items = []
    for r in rows[:_TRACKED_SAMPLE]:
        t, c = (r.get("title") or "").strip(), (r.get("company") or "").strip()
        if t:
            items.append(f"- {t}" + (f" @ {c}" if c else ""))
    return "\n".join(items)


_OUTPUT_CONTRACT = """\
Reply with ONE fenced json block and nothing else, in exactly this shape:

```json
{
  "recommendations": [
    {
      "role": "Role or job-family name",
      "why": "2-3 sentences tying my experience AND interests to this role.",
      "fit": 82,
      "lane": "core | adjacent | stretch",
      "keywords": ["search keyword", "another"],
      "sample_titles": ["Real-world job title", "Another"]
    }
  ]
}
```

Rules: 6-10 recommendations. "fit" is 0-100 for how well the role matches BOTH
my experience and my interests. "lane": core = I could apply today; adjacent =
strong overlap, small gap; stretch = aspirational but reachable. "keywords" =
2-6 search-engine keywords that would surface these jobs. Do NOT recommend
roles I've excluded, and go BEYOND what I'm already searching for — the value
is directions I haven't considered."""


def build_recommend_prompt(interests: str = "") -> str:
    """The full copy-to-your-AI prompt. Also persists ``interests`` so the note
    survives reloads (the caller shows it pre-filled next time)."""
    cfg = workspace.load_config()
    state = load_state()
    state["interests"] = (interests or "").strip()
    save_state(state)

    sections = [
        "You are a career advisor. Based on my experience, preferences, and "
        "interests below, recommend roles/job families I should be pursuing — "
        "especially strong-fit directions I may not have considered.",
    ]
    exp = _experience_text()
    if exp:
        sections += ["", "## MY EXPERIENCE (resume)", exp]
    prefs = _preferences_block()
    if prefs:
        sections += ["", "## MY PREFERENCES", prefs]
    targets = _current_targets_block(cfg)
    if targets:
        sections += ["", "## WHAT I ALREADY SEARCH FOR", targets]
    tracked = _tracked_block()
    if tracked:
        sections += ["", "## JOBS I'VE CHOSEN TO PURSUE (revealed interest)",
                     tracked]
    note = (interests or "").strip()
    if note:
        sections += ["", "## WHAT INTERESTS ME LATELY (my own words)", note]
    sections += ["", "## OUTPUT FORMAT", _OUTPUT_CONTRACT]
    return "\n".join(sections)


# ── reply parsing ─────────────────────────────────────────────────────────────

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def _json_candidates(text: str):
    """Fenced blocks first, then the largest brace-to-brace slice, then the raw
    text — the same tolerant posture as the setup/score parsers."""
    for m in _FENCE_RE.finditer(text):
        yield m.group(1)
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        yield text[start:end + 1]
    yield text


def _clean_str_list(raw, cap: int) -> list[str]:
    if not isinstance(raw, list):
        return []
    out, seen = [], set()
    for item in raw:
        s = str(item or "").strip()
        if s and s.lower() not in seen:
            seen.add(s.lower())
            out.append(s)
        if len(out) >= cap:
            break
    return out


def parse_recommendations_reply(text: str) -> list[dict]:
    """Parse the AI's paste into recommendation cards. Tolerant on wrapping
    (fenced / unfenced / chatter around the JSON) but strict on substance:
    raises ``ValueError`` with a user-facing message when no usable
    recommendations exist — a bad paste must be a clear error, never an empty
    success."""
    if not (text or "").strip():
        raise ValueError("The reply is empty — paste your AI's whole answer.")

    items = None
    for candidate in _json_candidates(text):
        try:
            data = json.loads(candidate.strip())
        except ValueError:
            continue
        if isinstance(data, dict) and isinstance(data.get("recommendations"), list):
            items = data["recommendations"]
            break
        if isinstance(data, list):
            items = data
            break
    if items is None:
        raise ValueError(
            "Couldn't find the recommendations JSON in that reply — make sure "
            "you pasted the AI's whole answer including the ```json block.")

    recs = []
    for item in items[:_MAX_RECS]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip()
        if not role:
            continue
        try:
            fit = max(0, min(100, int(item.get("fit"))))
        except (TypeError, ValueError):
            fit = None
        lane = str(item.get("lane") or "").strip().lower()
        recs.append({
            "id": uuid.uuid4().hex[:12],
            "role": role[:120],
            "why": str(item.get("why") or "").strip()[:1000],
            "fit": fit,
            "lane": lane if lane in _LANES else "adjacent",
            "keywords": _clean_str_list(item.get("keywords"),
                                        _MAX_KEYWORDS_PER_REC),
            "sample_titles": _clean_str_list(item.get("sample_titles"),
                                             _MAX_SAMPLE_TITLES),
            "applied": False,
            "dismissed": False,
        })
    if not recs:
        raise ValueError(
            "The reply parsed, but no usable recommendations were in it — "
            "each needs at least a \"role\".")
    return recs


def save_reply(text: str) -> dict:
    """Parse + persist a pasted reply; returns the fresh state."""
    recs = parse_recommendations_reply(text)
    state = load_state()
    state["recommendations"] = recs
    state["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    save_state(state)
    return state


# ── card actions ──────────────────────────────────────────────────────────────

def apply_keywords(rec_id: str) -> dict:
    """Merge a recommendation's keywords into the project's search keywords.
    ADDITIVE ONLY (inclusion over precision): existing keywords are never
    removed or reordered; duplicates (case-insensitive) are skipped. Returns
    ``{added, keywords}``."""
    state = load_state()
    rec = next((r for r in state["recommendations"] if r.get("id") == rec_id), None)
    if rec is None:
        raise KeyError(rec_id)
    cfg = workspace.load_config()
    kws = [str(k) for k in (cfg.get("keywords") or [])]
    have = {k.strip().lower() for k in kws}
    added = []
    for k in rec.get("keywords") or []:
        if k.strip().lower() not in have:
            kws.append(k)
            have.add(k.strip().lower())
            added.append(k)
    if added:
        cfg["keywords"] = kws
        workspace.save_config(cfg)
    rec["applied"] = True
    save_state(state)
    return {"added": added, "keywords": kws}


def dismiss(rec_id: str) -> bool:
    """Hide one card. Returns False when the id is unknown (already gone)."""
    state = load_state()
    rec = next((r for r in state["recommendations"] if r.get("id") == rec_id), None)
    if rec is None:
        return False
    rec["dismissed"] = True
    save_state(state)
    return True
