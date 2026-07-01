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
import typing
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


def _fit_preference(prefs: dict | None) -> str:
    """The per-profile fit-preference bias sentence ('' = neutral). Read from the
    passed prefs, else preferences.load(). Empty when the profile sets none, so
    no bias is baked into the ranking (de-Alex'd default)."""
    if prefs is None:
        prefs = preferences.load()
    return (prefs.get("fit_preference") or "").strip()


def build_request(jobs, prefs: dict | None = None,
                  experience_summary: str | None = None) -> str:
    """The single ranking prompt, shared by the bridge / API / MCP routes. Weaves
    in the per-profile fit_preference ('' = neutral, no bias sentence)."""
    prefs = prefs if prefs is not None else preferences.load()
    profile = build_profile(prefs, experience_summary)
    return bridge.build_fit_prompt(jobs, profile_md=profile,
                                   preference=_fit_preference(prefs))


# ── Compact (decomposed) request — spec-2026-06-29 ────────────────────────────
# Streamlined AI integration: feed each job's compact extracted FACTS + a rubric
# instead of raw HTML descriptions, and gate out structural non-fits before any
# model call. Same parse_response contract; a future local model swaps in by
# changing only who runs the prompt.

def _facts_profile(cfg: dict | None):
    """(industry, skill_terms, soc_code) for facts extraction from the active
    search config. A tech/empty field keeps the engineering-tuned map + vocab
    (byte-identical for Alex); any other field merges universal role buckets
    and falls back to profile-derived skills (the eng vocab is useless there).
    Plan 1E. `soc_code` is the project's PERSISTED O*NET-SOC code (item 25,
    workspace.create_project) when one was resolved at creation — extra,
    optional cache-key entropy only (see match.facts._profile_sig); None when
    the project predates item 25 or has no industry, so behavior for every
    existing project is unchanged until it's re-created.

    Falls back to the active project's config when cfg is None — the live GUI
    "Ask AI to rank" buttons call through with no cfg, and without this fallback a
    non-tech project's industry would be dropped (1E never activates + the profile
    signature collapses to the shared job_key-only facts cache)."""
    from match import facts as _facts
    if cfg is None:
        import workspace
        try:
            cfg = workspace.load_config()
        except Exception:
            cfg = {}
    industry = (cfg or {}).get("industry") or ""
    soc_code = (cfg or {}).get("onet_soc_code") or None
    skill_terms = None
    if industry and not _facts.is_tech_industry(industry):
        from match import scorer as _scorer
        st = _scorer.extract_skill_terms()
        skill_terms = list(st) if st else None
    return industry, skill_terms, soc_code


def build_compact_request(jobs, prefs: dict | None = None,
                          cfg: dict | None = None) -> str:
    """A compact ranking prompt: per-job extracted facts (not descriptions) + a
    rubric (match.rubric). ~15x less context per job than build_request."""
    from match import facts as _facts, rubric as _rubric
    prefs = prefs if prefs is not None else preferences.load()
    industry, skill_terms, soc_code = _facts_profile(cfg)
    facts_list = [_facts.facts_for(j, skill_terms=skill_terms, industry=industry,
                                   soc_code=soc_code)
                  for j in jobs]
    rb = _rubric.build_rubric(prefs, cfg)
    return bridge.build_fit_prompt_compact(jobs, facts_list, _rubric.rubric_text(rb),
                                           preference=_fit_preference(prefs))


def prepare_compact(jobs, prefs: dict | None = None, cfg: dict | None = None) -> dict:
    """The streamlined entry point: extract facts -> deterministic gate -> compact
    prompt for the kept set. Returns
        {"kept": [(job, facts, gate)], "dropped": [(job, facts, gate)],
         "prompt": str, "rubric": dict}
    `dropped` are excluded from the AI batch (clear structural non-fits) but keep
    their local score in the inbox. Parse the model's reply for `kept` with
    parse_response, exactly as for build_request."""
    from match import facts as _facts, rubric as _rubric, gate as _gate
    prefs = prefs if prefs is not None else preferences.load()
    rb = _rubric.build_rubric(prefs, cfg)
    industry, skill_terms, soc_code = _facts_profile(cfg)
    pairs = [(j, _facts.facts_for(j, skill_terms=skill_terms, industry=industry,
                                  soc_code=soc_code))
             for j in jobs]
    kept, dropped = _gate.partition(pairs, rb)
    kept_jobs = [j for j, _f, _g in kept]
    kept_facts = [f for _j, f, _g in kept]
    prompt = (bridge.build_fit_prompt_compact(kept_jobs, kept_facts, _rubric.rubric_text(rb),
                                              preference=_fit_preference(prefs))
              if kept_jobs else "")
    return {"kept": kept, "dropped": dropped, "prompt": prompt, "rubric": rb}


def parse_response(text: str, jobs) -> list:
    """Parse a model reply into [(job, fit_score, rationale)] in jobs order,
    mapping by echoed token (falling back to index). Skips unmatched entries."""
    parsed = bridge.parse_fit_response(text)
    return bridge.match_fit_to_jobs(jobs, parsed)


def gate(jobs, prefs: dict | None = None, *, counts: dict | None = None) -> list:
    """Apply the cheap preferences hard-gate before any ranking, so no AI call is
    spent on a job that fails a hard constraint (salary/location/dealbreaker).
    `counts` passes through to hard_gate for per-reason drop tallies."""
    prefs = prefs if prefs is not None else preferences.load()
    return preferences.hard_gate(jobs, prefs.get("hard", {}), counts=counts)


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
    client = anthropic.Anthropic(api_key=key, base_url=config.anthropic_base_url())
    msg = client.messages.create(
        model=model or config.ANTHROPIC_MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(getattr(b, "text", "") for b in msg.content
                   if getattr(b, "type", None) == "text")
    return parse_response(text, jobs)


# ── Ranker protocol (WS-3) ────────────────────────────────────────────────────
# The three routes (bridge / API / file) share one shape so callers can pick a
# route without forking logic. The classes are thin wrappers over the module
# functions above — no behavior change (characterization-tested first).


@typing.runtime_checkable
class Ranker(typing.Protocol):
    """A ranking route: build one prompt, parse one reply into
    [(job, fit_score, rationale)]."""

    def build_request(self, jobs, prefs=None, experience_summary=None) -> str: ...

    def parse_response(self, text: str, jobs) -> list: ...


class BridgeRanker:
    """Clipboard bridge route: build_request -> user pastes into claude.ai ->
    pastes the reply back -> parse_response. Delegates to the module functions."""

    def build_request(self, jobs, prefs=None, experience_summary=None) -> str:
        return build_request(jobs, prefs, experience_summary)

    def parse_response(self, text: str, jobs) -> list:
        return parse_response(text, jobs)


class ApiRanker:
    """Auto API route: same prompt + parser as the bridge, executed via the
    Anthropic API (when a key is configured)."""

    def build_request(self, jobs, prefs=None, experience_summary=None) -> str:
        return build_request(jobs, prefs, experience_summary)

    def parse_response(self, text: str, jobs) -> list:
        return parse_response(text, jobs)

    def rank(self, jobs, prefs=None, experience_summary=None, model=None) -> list:
        return rank_via_api(jobs, prefs, experience_summary, model)


class FileRanker:
    """File round-trip route: export the inbox to a CSV/MD/prompt trio, the user
    hands it to any AI, then import the returned CSV/JSON. build_request renders
    the versioned export prompt so this route gives identical guidance."""

    def build_request(self, jobs, prefs=None, experience_summary=None) -> str:
        from rerank import schema
        if prefs is not None and prefs.get("profile_md") is not None:
            profile = prefs.get("profile_md") or ""
            fit_pref = prefs.get("fit_preference", "") or ""
        else:
            import preferences as _prefs_mod
            p = _prefs_mod.load() or {}
            profile = p.get("profile_md", "") or ""
            fit_pref = p.get("fit_preference", "") or ""
        return schema.build_prompt(profile, fit_pref)

    def parse_response(self, text: str, jobs) -> list:
        # The file route resolves scores by job_key via import_scores, not by the
        # bridge token; parse_response is unused for files. Kept for the Protocol.
        raise NotImplementedError(
            "FileRanker scores are applied by import_(); use export()/import_().")

    def export(self, rows, out_dir, *, fmt: str = "both") -> dict:
        from rerank.export import export_inbox
        return export_inbox(rows, out_dir, fmt=fmt)

    def import_(self, path, rows_by_key, *, policy: str = "overwrite", _apply=None):
        from rerank.import_ import import_scores
        return import_scores(path, rows_by_key, policy=policy, _apply=_apply)
