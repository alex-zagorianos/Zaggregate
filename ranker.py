"""Preference-aware AI ranking.

Orders pre-scored jobs against the user's preferences profile. One request is
built once (build_request) and parsed once (parse_response), shared across three
routes so a job ranked by paste, by API, or by an MCP/Claude-Code caller gets
identical treatment:

  * bridge (default, no key): build_request -> user pastes into claude.ai ->
    pastes the reply back -> parse_response
  * api (auto, if a key is present): rank_via_api runs the same prompt + parser
  * mcp / claude code: build_request is exposed as a tool; Claude Code ranks

The profile fed to the model is the preferences profile (what the user WANTS,
from preferences.md) plus a condensed background summary (what they CAN do, from
experience.md) — so ranking weighs desire and fit together. The cheap
preferences hard-gate (gate) runs first, before any AI call is spent.
"""
import config
import preferences
import claude_bridge as bridge


def build_profile(prefs: dict | None = None, experience_summary: str | None = None) -> str:
    """Combine the NL preferences ('what I want', from preferences.md) with a
    condensed experience summary ('what I can do'). Either may be empty;
    experience-read errors are swallowed so a fresh data folder still ranks
    against preferences alone."""
    prefs = prefs if prefs is not None else preferences.load()
    profile_md = (prefs.get("profile_md") or "").strip()
    if experience_summary is None:
        try:
            experience_summary = bridge.profile_summary()
        except Exception:
            experience_summary = ""
    parts = []
    if profile_md:
        parts.append("## WHAT I'M LOOKING FOR (my preferences)\n\n" + profile_md)
    if (experience_summary or "").strip():
        parts.append("## MY BACKGROUND\n\n" + experience_summary.strip())
    return "\n\n".join(parts) if parts else "(no profile provided)"


def build_request(jobs, prefs: dict | None = None,
                  experience_summary: str | None = None) -> str:
    """The single ranking prompt, shared by the bridge / API / MCP routes."""
    profile = build_profile(prefs, experience_summary)
    return bridge.build_fit_prompt(jobs, profile_md=profile)


def parse_response(text: str, jobs) -> list:
    """Parse a model reply into [(job, fit_score, rationale)] in jobs order,
    mapping by echoed token (falling back to index). Skips unmatched entries."""
    parsed = bridge.parse_fit_response(text)
    return bridge.match_fit_to_jobs(jobs, parsed)


def gate(jobs, prefs: dict | None = None) -> list:
    """Apply the cheap preferences hard-gate before any ranking, so no AI call is
    spent on a job that fails a hard constraint (salary/location/dealbreaker)."""
    prefs = prefs if prefs is not None else preferences.load()
    return preferences.hard_gate(jobs, prefs.get("hard", {}))


# ── API auto-route ────────────────────────────────────────────────────────────

def _secrets_key_path():
    return config.SECRETS_DIR / "anthropic_key"


def api_key() -> str | None:
    """The Anthropic key for the auto route: the ANTHROPIC_API_KEY env var first,
    then a secrets/anthropic_key file in the data folder. None if neither."""
    if config.ANTHROPIC_API_KEY:
        return config.ANTHROPIC_API_KEY
    try:
        key = _secrets_key_path().read_text(encoding="utf-8").strip()
        return key or None
    except OSError:
        return None


def has_api_key() -> bool:
    return api_key() is not None


def rank_via_api(jobs, prefs: dict | None = None,
                 experience_summary: str | None = None, model: str | None = None) -> list:
    """Rank jobs by calling the API directly (auto route), using the SAME prompt
    and parser as the bridge. Returns [(job, fit_score, rationale)]. Raises
    RuntimeError when no key is configured."""
    key = api_key()
    if not key:
        raise RuntimeError(
            "No Anthropic API key for the auto route — set ANTHROPIC_API_KEY or "
            "put the key in secrets/anthropic_key, or use the clipboard bridge."
        )
    prompt = build_request(jobs, prefs, experience_summary)
    import anthropic
    client = anthropic.Anthropic(api_key=key)
    msg = client.messages.create(
        model=model or config.ANTHROPIC_MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(getattr(b, "text", "") for b in msg.content
                   if getattr(b, "type", None) == "text")
    return parse_response(text, jobs)
