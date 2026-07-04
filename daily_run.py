"""Headless morning search: query the free sources with user_config.json,
score everything, and drop never-seen jobs above DAILY_MIN_SCORE into the
tracker inbox. The GUI then opens to a ranked list of fresh matches.

Run:        py daily_run.py  [--user-config config_dad.json] [--min-score 40]
Schedule:   setup_schedule.bat   (Windows Task Scheduler, 07:30 daily)

jsearch is deliberately excluded (see DAILY_SOURCES in config.py) so the
200/month free tier survives manual searches.
"""
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import workspace
from config import DAILY_MIN_SCORE, DAILY_SOURCES, DEFAULT_KEYWORDS, DEFAULT_LOCATION

# id of the open health-beacon run row for the current run, set in main() and
# read by run_main()'s except handler to close it 'failed'. None = no open run.
_RUN_ID = None


TIERED_DEFAULT_THRESHOLD = 200


def _tiered_default(cfg: dict, industry) -> bool:
    """Decide whether tiered scraping is on for this run. An explicit
    ``tiered_scrape`` in the config always wins (True or False); otherwise the
    default flips ON once the (industry-filtered) registry exceeds
    TIERED_DEFAULT_THRESHOLD companies, so a large registry doesn't trigger a
    slow, 429-prone O(N) daily scrape."""
    explicit = cfg.get("tiered_scrape")
    if explicit is not None:
        return bool(explicit)
    try:
        from scrape.company_registry import industry_company_count
        registry_size = industry_company_count(industry)
    except Exception:
        registry_size = 0
    return registry_size > TIERED_DEFAULT_THRESHOLD


def _maybe_auto_rank(cfg: dict) -> None:
    """Opt-in: after new jobs are inboxed, rank the top-K still-unscored ones via
    the direct API / local model so the user wakes up to a ranked inbox (P4).

    Gated three ways so Alex's run stays byte-identical:
      * config.auto_rank_enabled(cfg) — AUTO_RANK env or user_config 'auto_rank'.
      * a configured backend — an API key OR a base_url (local Ollama etc).
    Uses the SAME compact prompt + shared parser as the GUI's 'Ask AI to rank',
    applying with source='api' under one batch (fully undo-able). Wrapped so a
    backend hiccup NEVER kills the daily run."""
    import config
    if not config.auto_rank_enabled(cfg):
        return
    import ranker
    has_backend = ranker.has_api_key() or (config.anthropic_base_url() is not None)
    if not has_backend:
        log("auto-rank: enabled but no API key / base_url configured — skipped")
        return
    try:
        from tracker import db, service
        # Respect an explicit 0 (= rank nothing this run) instead of silently
        # falling back to the default (review finding). Only absent/None uses
        # the default; negatives are treated as 0.
        _raw_k = cfg.get("auto_rank_top_k", None)
        top_k = config.AUTO_RANK_TOP_K if _raw_k is None else max(0, int(_raw_k))
        if top_k == 0:
            log("auto-rank: auto_rank_top_k=0 — nothing to rank this run")
            return
        # Highest-local-score unscored rows first, capped at top_k.
        unscored = [r for r in db.inbox_all() if (r.get("fit", -1) or -1) < 0]
        unscored.sort(key=lambda r: -(r.get("score", 0) or 0))
        rows = unscored[:top_k]
        if not rows:
            log("auto-rank: no unscored inbox rows to rank")
            return
        prompt, jobs, dropped = service.compact_fit_prompt_for_rows(rows, cfg=cfg)
        if dropped:
            try:
                service.mark_inbox_gated(dropped)
            except Exception:
                pass
        if not jobs:
            log(f"auto-rank: all {len(rows)} candidates auto-filtered")
            return
        reply = _run_api_prompt(prompt)
        applied, missed = service.score_inbox_from_reply(jobs, reply, source="api")
        log(f"auto-rank: scored {applied}/{len(jobs)} new job(s) via API"
            + (f" ({len(missed)} not scored)" if missed else ""))
    except Exception as e:  # a backend hiccup must never fail the run
        log(f"WARN: auto-rank skipped: {type(e).__name__}: {e}")


def _reach_probe(engine, results, keywords, location, cfg) -> int:
    """SerpApi reach probe (E2 / review P1 Tier A): issue 1-2 Google-Jobs queries
    on the broadest keyword + location, MERGE the parsed jobs into BOTH the run's
    scored `results` list (they are real postings) AND engine.last_raw_results (so
    capture-recapture sees the cross-family overlap that finally certifies reach).

    Returns the number of probe jobs merged. No-op (returns 0) when the probe is
    disabled, no SerpApi key is present, or nothing comes back. Wrapped by the
    caller so a probe failure NEVER kills the daily run.

    The probe is what turns the reach badge from "cannot certify" (f2=0) into a
    real percentage: SerpApi (family 'google_jobs') overlaps the free families on
    the same postings, giving the estimator recaptures. job_key inbox dedup (C1)
    absorbs any collisions, so double-listing is impossible."""
    import config
    if not config.reach_probe_enabled(cfg):
        return 0
    try:
        from search.serpapi_client import SerpApiClient
    except Exception:
        return 0
    try:
        probe_client = SerpApiClient(cache_enabled=True)
    except ValueError:
        # No SerpApi key -> the probe is simply unavailable (the badge keeps its
        # honest 'add a SerpApi key' hint). Not an error.
        return 0

    # Pick the broadest keywords: shortest first (a broad field term returns the
    # widest overlap with the other sources). Cap at the configured query budget.
    n_queries = int(cfg.get("reach_probe_queries", config.REACH_PROBE_QUERIES)
                    or config.REACH_PROBE_QUERIES)
    n_queries = max(1, min(n_queries, len(keywords) or 1))
    ordered = sorted((k for k in keywords if k), key=len)
    probe_keywords = ordered[:n_queries] or (keywords[:n_queries] if keywords else [])
    if not probe_keywords:
        return 0

    merged = 0
    for kw in probe_keywords:
        try:
            jobs = probe_client.search_and_parse(
                keyword=kw, location=location or "", salary_min=None, page=1)
        except Exception as e:
            log(f"WARN: reach probe query {kw!r} failed: {type(e).__name__}: {e}")
            continue
        if not jobs:
            continue
        results.extend(jobs)
        # Feed the SAME jobs into the raw membership set the reach estimator reads.
        # If a search already ran, last_raw_results is a real list; guard anyway.
        try:
            engine.last_raw_results = list(engine.last_raw_results) + list(jobs)
        except Exception:
            pass
        merged += len(jobs)
    if merged:
        log(f"reach probe | +{merged} SerpApi Google-Jobs posting(s) merged "
            f"({len(probe_keywords)} quer{'y' if len(probe_keywords) == 1 else 'ies'}) "
            f"— cross-family overlap for reach certification")
    return merged


def _run_api_prompt(prompt: str) -> str:
    """Send a pre-built prompt to the configured Anthropic-compatible backend and
    return the raw text reply. Mirrors gui._call_prompt_via_api (key + base_url)
    without importing tkinter into the headless run."""
    import config
    import ranker
    key = ranker.api_key()
    import anthropic
    client = anthropic.Anthropic(api_key=key, base_url=config.anthropic_base_url())
    msg = client.messages.create(
        model=config.ANTHROPIC_MODEL, max_tokens=4096,
        messages=[{"role": "user", "content": prompt}])
    return "".join(getattr(b, "text", "") for b in msg.content
                   if getattr(b, "type", None) == "text")


def log(msg: str):
    """Emit one daily-run line. Routes through the applog framework (rotating
    <data>/logs/app.log + console) AND keeps the legacy per-project
    output/daily_run.log append so existing tooling/readers of that file are
    unaffected. The console text is byte-identical to before (the bracketed
    timestamp line), because we print it ourselves and suppress applog's own
    console echo for this message via a stdout-quiet path."""
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{stamp}] {msg}"
    print(line)
    # Persist to the framework's rotating file (support / "Report a problem").
    # file_only: applog already mirrors to console; we printed the legacy line
    # above, so ask applog to skip its console echo to avoid a doubled line.
    try:
        import applog
        applog.get_logger("daily_run").info(msg, extra={"_console": False})
    except Exception:
        pass  # framework logging must never kill the run
    try:
        with open(workspace.output_dir() / "daily_run.log", "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass  # logging must never kill the run


def main():
    parser = argparse.ArgumentParser(description="Headless daily job search -> inbox")
    parser.add_argument("--user-config", type=str, default=None)
    parser.add_argument("--project", type=str, default=None,
                        help="Run against this project workspace (default: active).")
    parser.add_argument("--min-score", type=int, default=None,
                        help=f"Inbox threshold (default: user_config or {DAILY_MIN_SCORE})")
    # Default lifted 1 -> 2: the paginated keyword clients (adzuna/usajobs/
    # careeronestop/jsearch...) fetch a 2nd page for free recall, and the engine
    # parallelizes per-keyword so wall-clock barely moves. Page-1-only feeds
    # (RemoteOK/The Muse/careers) are unaffected — they stop at their raw end
    # regardless of this cap. The page-2 contribution is logged below.
    parser.add_argument("--max-pages", type=int, default=2)
    args = parser.parse_args()

    # A scoped `--project` run must NOT rewrite projects.json 'active' as a side
    # effect (S32/L1): doing so silently flips which project the user's GUI opens
    # to next launch. We intentionally do NOT call workspace.set_active here — the
    # process-local pin below already resolves EVERY db/config/output path in this
    # process to the requested project regardless of projects.json, which is all a
    # scoped run needs. (A future "run AND make this active" behavior should be an
    # explicit flag, not the default for every --project run.)

    # Pin this run to ONE project for the whole process, so a concurrent
    # projects.json write — a second daily_run, or a GUI project switch — can't
    # redirect our inbox/output/config writes mid-run (DB path is resolved from
    # the global 'active' on every call). Pin the explicit --project, else
    # whatever is active now. run_main() unpins in its finally.
    workspace.pin_active(args.project or workspace.active_slug())

    # Reset the run-scoped "warn once" set so keyless-source skip + "verify
    # manually" notices print ONCE this run instead of per keyword/company per
    # pass (S32/L7) — presentation only, no scraping change.
    import applog
    applog.reset_run_warnings()
    # Reset discovery's in-run query memo (S35 #25) so a stale result from a
    # previous in-process run (tests, an embedding host, a prior GUI search)
    # isn't reused for a DIFFERENT run's (ats_site, keyword) pair.
    from scrape.discoverer import reset_run_memo
    reset_run_memo()

    from search.cli import build_clients, load_user_config
    from search.search_engine import SearchEngine
    from match.scorer import score_jobs
    from tracker.db import (init_db, inbox_add_many, inbox_count,
                            record_run_start, record_run_finish)

    import userdata
    userdata.bootstrap()  # first-run: seed the data folder + runtime dirs

    # Open the health-beacon row before any work so a crash anywhere below is
    # attributable. init_db first so the runs table exists. run_main()'s
    # top-level except closes it 'failed'; the success path closes it 'ok'/'zero'.
    globals()["_RUN_ID"] = None  # clear any stale id from a prior in-process run
    init_db()
    run_project = args.project or workspace.active_slug() or ""
    run_id = record_run_start(run_project)
    globals()["_RUN_ID"] = run_id  # handed to run_main's except for the failed path

    cfg = load_user_config(args.user_config)
    from search.keyword_strategy import effective_keywords
    keywords = effective_keywords(cfg)  # genre-safe: a non-eng project w/o keywords
    location = cfg.get("location") or DEFAULT_LOCATION  # won't silently search for engineers
    salary_min = int(cfg["salary_min"]) if cfg.get("salary_min") is not None else None
    min_score = args.min_score if args.min_score is not None else int(
        cfg.get("daily_min_score", DAILY_MIN_SCORE))

    cfg_sources = cfg.get("sources", {})
    sources = [s for s in DAILY_SOURCES if cfg_sources.get(s, True)]
    industry = cfg.get("industry") or None  # filters the careers registry

    # Drop the tech/remote-skewed boards (RemoteOK, Remotive, Himalayas,
    # Arbeitnow, HN) for a non-knowledge-work field — noise + wasted calls for a
    # plumber/nurse search. No-op for eng/knowledge-work fields (Alex unchanged);
    # an explicit cfg_sources[<name>]=True override always wins.
    from search.keyword_strategy import gate_tech_sources
    sources = gate_tech_sources(sources, industry or "", cfg_sources)

    # Broaden the QUERY keywords for API recall — job APIs phrase-match, so narrow
    # seniority-laden titles ("VP Clinical Informatics") return ~0 while the field
    # term ("clinical informatics") returns 20x more (measured 2026-07-01). The
    # ORIGINAL keywords stay the scoring/title-match set below; seniority is handled
    # in scoring/gate, not the query string. No-op for eng IC titles (Alex unchanged).
    from search.keyword_strategy import broad_query_keywords
    if cfg.get("broaden_keywords", True):
        import industry_profile
        _syn = industry_profile.resolve(cfg.get("industry") or "").query_synonyms
        query_keywords = broad_query_keywords(keywords, cfg.get("industry") or "", synonyms=_syn)
    else:
        query_keywords = keywords

    log(f"daily_run start | sources={sources} | {len(keywords)} keywords "
        f"({len(query_keywords)} broadened for query) | "
        f"location={location} | min_score={min_score} | industry={industry}")

    # Preflight reach check: warn when the career-page (registry) path has almost
    # no employers for this field, so a near-zero 'careers' contribution is visible
    # up front instead of a mystery (the eng-only registry has ~0 health cos).
    if industry and "careers" in sources:
        try:
            from scrape.company_registry import industry_company_count
            n_reg = industry_company_count(industry)
            if n_reg < 10:
                log(f"NOTE: only {n_reg} registry companies match industry "
                    f"'{industry}' — the 'careers' path will add few/no jobs. Build "
                    f"your employer list (seed_companies.py / Add Companies / discovery).")
        except Exception:
            pass

    # Tiered scraping: as the registry grows, scrape only the boards "due" this
    # run (active boards every run, quiet/dead ones less often) so the daily run
    # stays fast and doesn't hammer every ATS host. Explicit config wins; the
    # DEFAULT now flips ON above ~200 registry companies (a full O(N) daily
    # scrape of a large registry is both the speed problem and a 429 contributor).
    tiered = _tiered_default(cfg, industry)
    # Collect which sources are silently contributing zero for lack of a FREE key
    # this run, so the GUI can surface it (review: keyless self-skips leave only
    # console lines). Populated from the sources' own skip conditions.
    keyless_skipped: list[str] = []
    # US-only sources (usajobs/careeronestop) that self-skip because this project's
    # country isn't 'us' — surfaced separately from keyless so the UI can show an
    # honest "US-only sources skipped for your country" badge. (scenario finding #3)
    country_skipped: list[str] = []
    clients = build_clients(sources, cache_enabled=True, industry_filter=industry,
                            tiered_careers=tiered, skipped_keyless=keyless_skipped,
                            location=location, skipped_country=country_skipped)
    if not clients:
        log("ABORT: no sources could be initialized (check .env).")
        # Don't leave the beacon row stuck 'running' — this is a failed run.
        record_run_finish(run_id, "failed",
                          error="no sources could be initialized (check .env)")
        sys.exit(1)

    engine = SearchEngine(clients)
    # Page-2 recall measurement: when paging beyond 1, do a cache-priming page-1
    # pass first, then the full pass. With caching ON, page-1 fetches are shared
    # (the full pass reads them from cache), so the ONLY extra network is page 2 —
    # and the raw-count delta is an honest "page 2: +N" attributable to the paged
    # keyword clients (page-1-only feeds contribute 0 to the delta by definition).
    page1_raw = None
    if args.max_pages >= 2:
        try:
            engine.run_full_search(
                keywords=query_keywords, location=location, salary_min=salary_min,
                max_pages_per_keyword=1,
            )
            page1_raw = len(engine.last_raw_results)
        except Exception as e:  # never let the measurement pass kill the run
            log(f"WARN: page-1 baseline pass skipped: {type(e).__name__}: {e}")
            page1_raw = None
    results = engine.run_full_search(
        keywords=query_keywords, location=location, salary_min=salary_min,
        max_pages_per_keyword=args.max_pages,
    )
    if page1_raw is not None:
        delta = len(engine.last_raw_results) - page1_raw
        if delta > 0:
            log(f"page 2: +{delta} raw postings beyond page 1")
    # SerpApi reach probe: merge a tiny Google-Jobs sample into BOTH the scored
    # results and engine.last_raw_results so capture-recapture finally gets a
    # cross-family overlap (f2>0 -> certifiable reach %). Default ON when a
    # SerpApi key exists; self-skips otherwise. Wrapped so it never kills the run.
    try:
        _reach_probe(engine, results, query_keywords, location, cfg)
    except Exception as e:
        log(f"WARN: reach probe skipped: {type(e).__name__}: {e}")
    if tiered:
        for c in clients:
            if hasattr(c, "finalize_tiering"):
                c.finalize_tiering()
    # Preference hard-gate: drop jobs violating the user's hard constraints
    # (salary floor / location / dealbreakers) before scoring + inbox. No-op when
    # preferences.json is absent or permissive (a fresh data folder).
    import ranker
    _pre_gate = len(results)
    _gate_counts: dict = {}
    results = ranker.gate(results, counts=_gate_counts)
    if len(results) != _pre_gate:
        _dropped = ", ".join(f"{k} {v}" for k, v in _gate_counts.items() if v)
        log(f"preferences hard-gate | {_pre_gate} -> {len(results)}"
            + (f" (dropped: {_dropped})" if _dropped else ""))
    # Language guard: when armed (a non-US Adzuna country, or LANGUAGE_GUARD=1),
    # a posting that doesn't read as English is marked 'not scored (language)' and
    # held out of scoring, so the keyword matcher can't confidently mis-rank a
    # foreign-language listing. OFF by default -> byte-identical for Alex's US run
    # (the branch is skipped entirely and `results` is scored intact).
    import config as _cfg
    _lang_scored = results
    _lang_skipped = []
    if _cfg.language_guard_active():
        from match.language import is_probably_english
        _lang_scored, _lang_skipped = [], []
        for r in results:
            probe = f"{r.title or ''} {r.description or ''}"
            if is_probably_english(probe):
                _lang_scored.append(r)
            else:
                r.score = -1  # model's 'not scored' sentinel (kept < min_score)
                r.score_notes = "not scored (language)"
                _lang_skipped.append(r)
        if _lang_skipped:
            log(f"language guard | {len(_lang_skipped)} non-English posting(s) "
                f"held out of scoring ('not scored (language)')")

    # Remote-acceptable jobs get full location credit (not 0) so they rank fairly
    # when the user is open to remote — honors preferences.json remote_ok.
    try:
        import preferences
        _remote_ok = bool(preferences.load().get("hard", {}).get("remote_ok", True))
    except Exception:
        _remote_ok = True
    try:
        import preferences as _prefs_mod
        _remote_regions_ok = bool(_prefs_mod.load().get("hard", {}).get("remote_regions_ok", False))
    except Exception:
        _remote_regions_ok = False
    score_jobs(_lang_scored, keywords=keywords, location=location,
               salary_floor=salary_min,
               exclude_keywords=cfg.get("exclude_keywords", []),
               exclude_titles=cfg.get("exclude_titles"),
               title_miss_penalty=cfg.get("title_miss_penalty"),
               seniority_exclude=cfg.get("seniority_exclude"),
               remote_ok=_remote_ok,
               seniority_target=cfg.get("seniority_target"),
               years_cap=cfg.get("years_cap"),
               remote_regions_ok=_remote_regions_ok,
               title_context_required=cfg.get("title_context_required"))

    # Freshness deltas: mark jobs new since the last daily run for THIS project
    # (manual GUI/CLI searches don't move this baseline). Non-destructive — just
    # an annotation surfaced by the GUI "New only" filter and the log below.
    import search.freshness as freshness
    fresh_id = f"daily:{run_project or 'root'}"
    _prev_fresh = freshness.load_prev_keys(fresh_id)
    for r in results:
        r.is_new = r.job_key not in _prev_fresh
    # Repost/evergreen classification from the persisted presence history (C1),
    # read BEFORE save_keys advances the baseline. Threaded into match.ghost so a
    # re-listed/perpetual req reads staler in the view. Best-effort - a fresh
    # project (no history) yields an empty map = abstain.
    try:
        _repost_info = freshness.repost_info(fresh_id)
    except Exception:
        _repost_info = {}

    qualified = [r for r in results if r.score >= min_score]

    # Per-company cap: mega boards (Anduril, SpaceX) can match 300+ postings a
    # run and drown everyone else. Enforced against the PERSISTED inbox inside
    # inbox_add_many (not per-run) so a board can't accrue cap rows every run and
    # pile up over N days. score_jobs sorted best-first, so each company keeps its
    # top matches. 0/None disables.
    cap = int(cfg.get("max_per_company", 15) or 0)

    # init_db already ran at the top (for the runs table); this is idempotent.
    init_db()
    before = inbox_count()
    new_batch = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    # cap_overflow (C1): {company: n_capped} for boards whose per-company cap was
    # hit this run - surfaced so the single-dominant-employer jobs a user actually
    # wants (e.g. "Cincinnati Children's: 12 more capped") aren't silently lost.
    cap_overflow: dict = {}
    added = inbox_add_many(qualified, per_company_cap=cap, new_batch=new_batch,
                           overflow_out=cap_overflow)
    log(f"daily_run done | {len(results)} found | {len(qualified)} >= {min_score} | "
        f"{added} new -> inbox (inbox now {inbox_count()})")
    if cap_overflow:
        top = sorted(cap_overflow.items(), key=lambda kv: kv[1], reverse=True)
        log("capped: " + ", ".join(f"{c} {n}" for c, n in top))

    # Repost/evergreen visibility (C1): how many of this run's qualified jobs the
    # persisted history flags as re-listed or perpetual reqs.
    n_repost = sum(1 for r in qualified
                   if (_repost_info.get(r.job_key) or {}).get("repost"))
    n_evergreen = sum(1 for r in qualified
                      if (_repost_info.get(r.job_key) or {}).get("evergreen"))
    if n_repost or n_evergreen:
        log(f"repost/evergreen | {n_repost} reposted, {n_evergreen} evergreen "
            f"(of {len(qualified)} qualified)")

    # Advance the freshness baseline to this run's found set, and report how many
    # of the inboxed jobs are new since the last run.
    freshness.save_keys(fresh_id, {r.job_key for r in results})
    # n_new is counted over the QUALIFIED set (is_new is per-result); `added` is
    # the smaller post-cap/post-dedup insert count — don't mix them in one ratio
    # (a blank-canvas run logged "1162 of 685 newly-inboxed").
    n_new = sum(1 for r in qualified if r.is_new)
    log(f"freshness | {n_new} of {len(qualified)} qualified are new since last run; "
        f"{added} inboxed (baseline '{fresh_id}' now {len(results)} keys)")

    # Re-score the whole inbox for this project with the current config so edited
    # keywords/salary don't leave stale, incomparable scores on older rows.
    # Cost: one extra full pass over the inbox per run (recompute only, no fit).
    try:
        from scripts.rescore_inbox import rescore
        rs = rescore(cfg=cfg)
        log(f"re-scored {rs['n']} inbox rows with current config")
    except Exception as e:  # re-score is best-effort; never fail the run for it
        log(f"WARN: inbox re-score skipped: {type(e).__name__}: {e}")

    # Opt-in auto-rank: rank the top-K still-unscored inbox jobs via the direct
    # API / local model so the user wakes up to a ranked inbox. OFF by default
    # (byte-identical for Alex); wrapped so a backend hiccup never kills the run.
    _maybe_auto_rank(cfg)

    # Optionally remove dead (404) inbox links each run. OFF by default: it
    # re-probes every career link (~1 network call/row), which materially slows a
    # scheduled run; the GUI "Clean dead links" button and `cli --prune-inbox`
    # cover the on-demand case. Opt in with "prune_inbox_daily": true in config.
    if cfg.get("prune_inbox_daily"):
        try:
            from scrape.inbox_health import prune_inbox
            removed = prune_inbox()
            log(f"pruned {len(removed)} dead inbox link(s)")
        except Exception as e:  # best-effort; never fail the run for a prune
            log(f"WARN: inbox prune skipped: {type(e).__name__}: {e}")

    # Optionally grow the company registry from Common Crawl on the scheduled run
    # (additive, user-wins). OFF by default — it's network-heavy and the funnel's
    # own docstring says "occasional, not per-search"; opt in with
    # "discover_on_daily": true (or run `cli --discover` by hand).
    if cfg.get("discover_on_daily"):
        try:
            from discover.funnel import run_funnel
            summary = run_funnel()
            log(f"discovery funnel: harvested {summary.get('harvested', 0)} -> "
                f"added {summary.get('added', 0)} board(s)")
        except Exception as e:  # best-effort; never fail the run for discovery
            log(f"WARN: discovery skipped: {type(e).__name__}: {e}")

    # Inbox -> registry harvest: employer names we've ALREADY seen hiring in the
    # inbox but that aren't in the careers registry yet -> resolve to their board
    # -> live-probe -> add. Free, deterministic, compounds every run. Opt-in
    # ("harvest_inbox": true), default OFF so existing users' runs are unchanged.
    if cfg.get("harvest_inbox"):
        try:
            from discover.inbox_harvest import harvest_inbox_companies
            hr = harvest_inbox_companies(industry=industry or None)
            log(f"inbox harvest: {hr.candidates} candidate(s) -> {hr.added} new "
                f"board(s) added to the careers registry")
        except Exception as e:  # best-effort; never fail a run for harvesting
            log(f"WARN: inbox harvest skipped: {type(e).__name__}: {e}")

    # Reach certification: from the RAW pre-dedup multi-source results, estimate
    # what fraction of the reachable universe this run actually saw (capture-
    # recapture over independent source families). Read-only, best-effort — logs a
    # one-line honest verdict and persists a snapshot the GUI/CLI can surface. A
    # single-source run (or no overlap) honestly reports 'cannot certify'.
    try:
        from coverage.reach import estimate_reach, persist_reach
        reach = estimate_reach(engine.last_raw_results, area=location,
                               industry=industry or "")
        log(reach.summary_line())
        persist_reach(reach, project=run_project)
    except Exception as e:  # best-effort; coverage math must never kill a run
        log(f"WARN: reach estimate skipped: {type(e).__name__}: {e}")

    # Due follow-ups: surface how many tracked applications need attention today,
    # right in the daily log, so the nudge reaches a user who only ever reads the
    # scheduled run's output. Read-only COUNT; best-effort (never fail a run).
    followups_due = 0
    try:
        from tracker.db import count_followups_due
        followups_due = count_followups_due()
        if followups_due:
            log(f"{followups_due} follow-up(s) due — open the Job Tracker to act on them")
    except Exception as e:
        log(f"WARN: follow-up due count skipped: {type(e).__name__}: {e}")

    # Health beacon: 'zero' when nothing new landed, else 'ok', with per-source
    # counts of what the search returned this run.
    from collections import Counter
    source_counts = dict(Counter((r.source_api or "") for r in results))
    # Cap overflow rides the same source_counts JSON as a reserved sibling key
    # (C1) - no schema change. '__capped__' can't collide with a source_api name.
    if cap_overflow:
        source_counts["__capped__"] = cap_overflow
    status = "zero" if added == 0 else "ok"
    record_run_finish(run_id, status, source_counts=source_counts)

    # Last-run status: a machine-readable snapshot the GUI renders as
    # "Last updated: <when> - N new jobs" in the Inbox header and "Report a
    # problem" attaches. Errors (transient source failures + a sync-folder
    # warning) are captured so the 429-erosion class is finally visible.
    try:
        import applog
        errors = [f"{src}: {msg}" for src, msg in sorted(engine.source_errors().items())] \
            if hasattr(engine, "source_errors") else []
        try:
            import userdata
            _sync_warn = userdata.sync_folder_warning()
            if _sync_warn:
                errors.append(_sync_warn)
        except Exception:
            pass
        applog.write_last_run({
            "project": run_project,
            "added": added,
            "found": len(results),
            "qualified": len(qualified),
            "per_source_counts": {k: v for k, v in source_counts.items()
                                  if k != "__capped__"},
            "capped": cap_overflow,
            "followups_due": followups_due,
            "errors": errors,
            # Sources that self-skipped this run for a missing free key — the GUI
            # turns this into an actionable "N sources skipped (no key)" line.
            "keyless_skipped": list(keyless_skipped),
            # US-only sources skipped because this project's country isn't 'us' —
            # surfaced separately (different fix than a missing key). (finding #3)
            "country_skipped": list(country_skipped),
        }, project_slug=run_project or None)
    except Exception as e:  # status reporting must never kill a run
        log(f"WARN: last_run.json write skipped: {type(e).__name__}: {e}")

    # Auto-backup: after a successful run, snapshot the data folder (keep the last
    # 7, dated) so a friend's data survives corruption even if they never open the
    # Help menu. Reuses ui.help's backup helper. Guarded — a backup hiccup (e.g.
    # a locked file) must NEVER fail the run.
    try:
        from ui import help as _uihelp
        bpath = _uihelp.auto_backup(keep=7)
        if bpath:
            log(f"auto-backup | data snapshot saved (keeping last 7)")
    except Exception as e:
        log(f"WARN: auto-backup skipped: {type(e).__name__}: {e}")


def _gc_cache() -> None:
    """Cache GC: the cache/ tree (ATS payload blobs + per-source FileCaches) was
    write-mostly and never evicted -> hundreds of MB. Evict entries older than
    the GC window; anything still needed is re-fetched cheaply (and
    conditional-GET makes that a 304). Best-effort, never fatal -- called from
    run_main()'s finally: so an ABORTED run (any exception raised inside
    main()) still gets GC'd, not just a clean/successful one (S35 #36)."""
    try:
        from config import CACHE_DIR
        from scrape.cache_helpers import gc_cache_dir
        n_gc = gc_cache_dir(CACHE_DIR)
        if n_gc:
            log(f"cache GC | removed {n_gc} stale cache file(s)")
    except Exception as e:  # GC must never mask the run's real outcome
        log(f"WARN: cache GC skipped: {type(e).__name__}: {e}")


def run_main() -> int:
    """Run main() with a top-level guard so a scheduled run never dies silently:
    any exception is logged (with traceback) to the project log and returns 1.
    Also closes the health-beacon run row as 'failed' with the traceback."""
    import traceback
    try:
        main()
        return 0
    except SystemExit as e:
        return int(e.code or 0)
    except Exception as e:
        tb = traceback.format_exc()
        log(f"FATAL: daily_run crashed: {type(e).__name__}: {e}")
        log(tb)
        # Close the beacon row opened in main() (if we got that far) as failed.
        run_id = globals().get("_RUN_ID")
        if run_id is not None:
            try:
                from tracker.db import record_run_finish
                record_run_finish(run_id, "failed", error=tb)
            except Exception:
                pass  # beacon bookkeeping must never mask the original failure
        return 1
    finally:
        # Cache GC runs here (not at the tail of main()) so an ABORTED run --
        # main() raising anywhere before reaching its own end -- still trims
        # cache/ instead of skipping GC entirely (S35 #36). Ordering is
        # preserved: this still runs strictly AFTER everything main() did (or
        # attempted). _gc_cache() already has its own try/except, but this
        # finally: is unwinding from EITHER a return or an in-flight exception,
        # and an unguarded call here would let ANY escape from _gc_cache (a bug
        # in it, not just the GC operation itself) silently replace the
        # original outcome -- so this outer try/except is a hard guarantee,
        # not just defense in depth.
        try:
            _gc_cache()
        except Exception:
            pass  # a GC failure must never mask the run's real outcome
        # Always release the process-local project pin set in main(), so an
        # in-process caller (tests, an embedding host) isn't left pinned.
        workspace.unpin_active()


if __name__ == "__main__":
    sys.exit(run_main())
