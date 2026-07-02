import argparse
import json
import sys
import webbrowser
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import workspace
import applog
from config import DEFAULT_KEYWORDS, DEFAULT_LOCATION
from search.adzuna_client import AdzunaClient
from search.jsearch_client import JSearchClient
from search.usajobs_client import USAJobsClient
from search.base_client import JobAPIClient
from search.report_csv import generate_csv_report
from search.report_html import generate_html_report
from search.search_engine import SearchEngine

ALL_SOURCES = ["adzuna", "jsearch", "usajobs", "careeronestop", "careers",
               "themuse", "remoteok", "remotive", "jobicy", "himalayas", "hn",
               "arbeitnow", "jooble", "careerjet", "linkedin_guest", "serpapi",
               "socrata", "weworkremotely", "workingnomads",
               "higheredjobs", "rnjobsite", "jobsacuk"]

# Sources that must NOT run unless the user EXPLICITLY opts in (a truthy
# cfg_sources[<name>]), i.e. the on-by-default fallback `cfg_sources.get(s, True)`
# is flipped to `.get(s, False)` for exactly these. linkedin_guest is a logged-out
# scrape of a ToS-sensitive surface, so shipping it on-by-default inside friends'
# exes makes a legal judgment call for them; the documented contract is informed
# opt-in (review "legal posture"). Note --sources still honors an explicit list.
OPT_IN_SOURCES = frozenset({"linkedin_guest"})


def load_user_config(path=None) -> dict:
    """Load the active project's config (or root user_config.json pre-migration).
    Returns {} if file missing or unreadable."""
    target = Path(path) if path else workspace.config_path()
    if not target.exists():
        return {}
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except Exception as e:
        applog.get_logger("config").warning(
            f"  [config] Warning: could not load {target.name} - {e}")
        return {}


def build_clients(
    sources: list[str],
    cache_enabled: bool,
    top_n: int = 20,
    industry_filter: str | None = None,
    discovery_enabled: bool = True,
    companies_file: Path | None = None,
    tiered_careers: bool = False,
    skipped_keyless: list[str] | None = None,
) -> list[JobAPIClient]:
    """Build the requested source clients.

    skipped_keyless (optional out-param): if a list is passed, the source names
    that were skipped/inert THIS build because their FREE key was missing are
    appended to it — from the ACTUAL skip conditions (the ValueError raised by a
    key-gated client, or a registered client reporting keyless() is True), never
    a hardcoded source list. The caller surfaces this so a user learns which
    sources are contributing zero for lack of a key (review: silent self-skip).
    """
    clients: list[JobAPIClient] = []

    def _note_keyless(name: str) -> None:
        if skipped_keyless is not None and name not in skipped_keyless:
            skipped_keyless.append(name)
    # Route per-source init failures/skips through the logging framework so a
    # keyless-skip or throttle finally PERSISTS to <data>/logs/app.log (a friend
    # can send it) instead of print()-ing to a console the frozen exe discards.
    # These log at INFO so the console text stays byte-identical to the old
    # print() lines (the bare-message console formatter adds no prefix).
    slog = applog.get_logger("sources")

    for source in sources:
        if source == "adzuna":
            try:
                clients.append(AdzunaClient(cache_enabled=cache_enabled))
            except ValueError as e:
                slog.info(f"  [adzuna] Skipping — {e}")
                _note_keyless("adzuna")

        elif source == "jsearch":
            try:
                clients.append(JSearchClient(cache_enabled=cache_enabled))
                slog.info(
                    "  [jsearch] NOTE: Free tier is 200 req/month. "
                    "Each keyword/page costs 1 request."
                )
            except ValueError as e:
                slog.info(f"  [jsearch] Skipping — {e}")
                _note_keyless("jsearch")

        elif source == "usajobs":
            try:
                clients.append(USAJobsClient(cache_enabled=cache_enabled))
            except ValueError as e:
                slog.info(f"  [usajobs] Skipping — {e}")
                _note_keyless("usajobs")

        elif source == "careeronestop":
            from search.careeronestop_client import CareerOneStopClient
            try:
                clients.append(CareerOneStopClient(cache_enabled=cache_enabled))
            except ValueError as e:
                slog.info(f"  [careeronestop] Skipping — {e}")
                _note_keyless("careeronestop")

        elif source == "themuse":
            from search.themuse_client import TheMuseClient
            clients.append(TheMuseClient(cache_enabled=cache_enabled))

        elif source == "remoteok":
            from search.remoteok_client import RemoteOKClient
            clients.append(RemoteOKClient(cache_enabled=cache_enabled))

        elif source == "remotive":
            from search.remotive_client import RemotiveClient
            clients.append(RemotiveClient(cache_enabled=cache_enabled))

        elif source == "jobicy":
            from search.jobicy_client import JobicyClient
            clients.append(JobicyClient(cache_enabled=cache_enabled))

        elif source == "himalayas":
            from search.himalayas_client import HimalayasClient
            clients.append(HimalayasClient(cache_enabled=cache_enabled))

        elif source == "hn":
            from search.hn_client import HNClient
            clients.append(HNClient(cache_enabled=cache_enabled))

        elif source == "careers":
            from scrape.careers_client import CareersClient
            clients.append(CareersClient(
                cache_enabled=cache_enabled,
                top_n=top_n,
                industry_filter=industry_filter,
                discovery_enabled=discovery_enabled,
                companies_file=companies_file,
                tiered=tiered_careers,
            ))

        elif source == "arbeitnow":
            from search.arbeitnow_client import ArbeitnowClient
            clients.append(ArbeitnowClient(cache_enabled=cache_enabled))

        elif source == "jooble":
            from search.jooble_client import JoobleClient
            c = JoobleClient(cache_enabled=cache_enabled)
            clients.append(c)
            # Registers unconditionally then self-skips at fetch time when
            # unkeyed; ask the client's OWN key predicate so the count tracks the
            # real skip condition, not a source list here.
            if getattr(c, "keyless", lambda: False)():
                slog.info("  [jooble] JOOBLE_API_KEY unset — will self-skip "
                          "(free key at jooble.org/api/about).")
                _note_keyless("jooble")

        elif source == "careerjet":
            from search.careerjet_client import CareerjetClient
            c = CareerjetClient(cache_enabled=cache_enabled)
            clients.append(c)
            if getattr(c, "keyless", lambda: False)():
                slog.info("  [careerjet] CAREERJET_AFFID unset — will self-skip "
                          "(free affiliate id at careerjet.com/partners).")
                _note_keyless("careerjet")

        elif source == "linkedin_guest":
            from search.linkedin_guest_client import LinkedInGuestClient
            slog.info("  [linkedin_guest] NOTE: logged-out PUBLIC guest endpoint only — "
                      "no login/cookies. Review LinkedIn ToS before enabling.")
            clients.append(LinkedInGuestClient(cache_enabled=cache_enabled))

        elif source == "serpapi":
            from search.serpapi_client import SerpApiClient
            try:
                clients.append(SerpApiClient(cache_enabled=cache_enabled))
                slog.info(f"  [serpapi] BYO Google-Jobs backend active "
                          f"(free tier {__import__('config').SERPAPI_MONTHLY_LIMIT}/month).")
            except ValueError as e:
                slog.info(f"  [serpapi] Skipping — {e}")
                _note_keyless("serpapi")

        elif source == "weworkremotely":
            from search.weworkremotely_client import WeWorkRemotelyClient
            clients.append(WeWorkRemotelyClient(cache_enabled=cache_enabled))

        elif source == "workingnomads":
            from search.workingnomads_client import WorkingNomadsClient
            clients.append(WorkingNomadsClient(cache_enabled=cache_enabled))

        elif source == "higheredjobs":
            # Sector RSS: education/faculty/admin. Self-skips (fetches nothing)
            # for a non-education field via its industry gate — safe to always
            # register. industry_filter is the active project's field.
            from search.higheredjobs_client import HigherEdJobsClient
            c = HigherEdJobsClient(cache_enabled=cache_enabled,
                                   industry=industry_filter)
            if not c.cat_ids:
                slog.info(f"  [higheredjobs] Inert for industry "
                          f"{industry_filter or '(none)'!r} — no education categories map.")
            clients.append(c)

        elif source == "rnjobsite":
            # Sector RSS: registered-nurse specialties. Self-skips for a
            # non-nursing field via its industry gate.
            from search.rnjobsite_client import RNJobSiteClient
            c = RNJobSiteClient(cache_enabled=cache_enabled,
                                industry=industry_filter)
            if not c.active:
                slog.info(f"  [rnjobsite] Inert for industry "
                          f"{industry_filter or '(none)'!r} — not a nursing field.")
            clients.append(c)

        elif source == "jobsacuk":
            # Sector RSS: UK academic/health. OPT-IN only (config flag or non-US
            # country); inert in a default US run. PROVISIONAL endpoint.
            from search.jobsacuk_client import JobsAcUkClient
            c = JobsAcUkClient(cache_enabled=cache_enabled,
                               industry=industry_filter)
            if not c.active:
                slog.info("  [jobsacuk] Inert — UK academic feeds are opt-in "
                          "(set 'jobsacuk' in config or a non-US country).")
            clients.append(c)

        elif source == "socrata":
            from search.socrata_client import SocrataClient
            from config import SOCRATA_APP_TOKEN, SOCRATA_CITIES
            clients.append(SocrataClient(
                cities=SOCRATA_CITIES, app_token=SOCRATA_APP_TOKEN,
                cache_enabled=cache_enabled,
            ))
            if not SOCRATA_CITIES:
                slog.info("  [socrata] No SOCRATA_CITIES configured — client is inert "
                          "(add a city key, e.g. 'nyc', to config.SOCRATA_CITIES).")

        else:
            slog.warning(f"  Unknown source {source!r} — ignoring.")

    return clients


def main():
    parser = argparse.ArgumentParser(description="Job Search Scraper — multi-source")
    parser.add_argument(
        "--keywords",
        type=str,
        default=None,
        help="Comma-separated keywords (overrides user_config.json and defaults)",
    )
    parser.add_argument(
        "--location",
        type=str,
        default=None,
        help=f"Location to search (default: user_config.json or {DEFAULT_LOCATION})",
    )
    parser.add_argument(
        "--salary-min",
        type=int,
        default=None,
        help="Minimum salary filter (overrides user_config.json)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=2,
        help="Max pages per keyword per source (default: 2)",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable response caching",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output directory (default: ./output)",
    )
    parser.add_argument(
        "--sources",
        type=str,
        default=",".join(ALL_SOURCES),
        help=f"Comma-separated sources to query (default: {','.join(ALL_SOURCES)})",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=20,
        help="Max auto-discovered companies to add per keyword; the curated "
             "registry is always scraped in full (default: 20)",
    )
    parser.add_argument(
        "--industry",
        type=str,
        default=None,
        help="Filter career page registry by industry (e.g. 'health_informatics', 'controls_engineering')",
    )
    parser.add_argument(
        "--no-discover",
        action="store_true",
        help="Skip Brave Search company auto-discovery; use only the curated registry",
    )
    parser.add_argument(
        "--show-tracked",
        action="store_true",
        help="Include jobs already in the tracker or dismissed (hidden by default)",
    )
    parser.add_argument(
        "--save-discovered",
        action="store_true",
        help="Persist auto-discovered companies that returned matching jobs to "
             "companies.json, building a permanent watchlist across runs",
    )
    parser.add_argument(
        "--prune-companies",
        action="store_true",
        help="Maintenance: probe companies.json and remove entries that 404 or "
             "have an empty board for --prune-threshold consecutive runs, then exit",
    )
    parser.add_argument(
        "--prune-threshold",
        type=int,
        default=2,
        help="Consecutive failed probes before a company is pruned (default: 2)",
    )
    parser.add_argument(
        "--prune-inbox",
        action="store_true",
        help="Maintenance: probe the active project's inbox career links and "
             "remove postings that now 404 (dead links), then exit. Pair with "
             "--dry-run to preview.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="With --prune-inbox: report what would be removed without deleting.",
    )
    parser.add_argument(
        "--discover",
        action="store_true",
        help="Maintenance: run the discovery funnel (Common Crawl CDX slug "
             "harvest + careers-link finding) to find new ATS boards and merge "
             "them into companies.json, then exit. Additive only.",
    )
    parser.add_argument(
        "--discover-domains",
        type=str,
        default=None,
        help="Comma-separated company domains for the funnel to resolve to "
             "careers URLs and detect ATS boards (e.g. acme.com,globex.io)",
    )
    parser.add_argument(
        "--discover-limit",
        type=int,
        default=200,
        help="Max CDX records per ATS host in the discovery funnel (default: 200)",
    )
    parser.add_argument(
        "--discover-host-level",
        action="store_true",
        help="Use the host-level (registered-domain) CDX harvest — spans all "
             "subdomains/tenants under each ATS host, paginated (plan P6).",
    )
    parser.add_argument(
        "--discover-enterprise",
        action="store_true",
        help="Also harvest enterprise ATS domains (Workday/iCIMS/Taleo/SF) where "
             "big health systems & industrials live. Implies --discover-host-level.",
    )
    parser.add_argument(
        "--discover-max-pages",
        type=int,
        default=None,
        help="Max CDX pages per host on the host-level path (default: 1).",
    )
    parser.add_argument(
        "--companies-file",
        type=str,
        default=None,
        help="Path to a companies.json file to merge with the built-in registry",
    )
    parser.add_argument(
        "--user-config",
        type=str,
        default=None,
        help="Path to a config file (default: the active project's config / "
             "user_config.json). Overrides --project.",
    )
    parser.add_argument(
        "--project",
        type=str,
        default=None,
        help="Run against this project workspace (its config + inbox). "
             "Default: the active project. See --list-projects.",
    )
    parser.add_argument(
        "--list-projects",
        action="store_true",
        help="List job-search projects and exit.",
    )
    parser.add_argument(
        "--add-keyword",
        type=str,
        default=None,
        help="Append one keyword to the resolved list for this run (does not persist)",
    )
    parser.add_argument(
        "--sort-by",
        choices=["score", "date", "location"],
        default="score",
        help="Sort results by match 'score' (default), 'date', or 'location' proximity",
    )
    parser.add_argument(
        "--min-score",
        type=int,
        default=None,
        help="Hide results scoring below this (0-100). Default: user_config "
             "'min_score' or 0 (show all)",
    )
    parser.add_argument(
        "--edit-csv",
        action="store_true",
        help="Open output CSV in default app after search completes (Windows only)",
    )
    args = parser.parse_args()

    if args.list_projects:
        active = workspace.active_slug()
        projs = workspace.list_projects()
        if not projs:
            print("No projects yet (pre-migration: using root data).")
        for p in projs:
            print(f"  {'*' if p['slug'] == active else ' '} {p['slug']:28} {p['name']}")
        sys.exit(0)

    # Scope this run to a project workspace (unless an explicit --user-config wins).
    if args.project and not args.user_config:
        workspace.set_active(args.project)

    # Maintenance mode: prune dead/empty companies and exit (no search).
    if args.prune_companies:
        from scrape.company_health import prune_companies
        cf = Path(args.companies_file) if args.companies_file else None
        removed = prune_companies(threshold=args.prune_threshold, json_path=cf)
        if removed:
            print(f"Pruned {len(removed)} dead/empty company(ies): {', '.join(removed)}")
        else:
            print("No companies pruned (all reachable with postings, or below threshold).")
        sys.exit(0)

    # Maintenance mode: remove dead (404) postings from the inbox and exit.
    if args.prune_inbox:
        from scrape.inbox_health import prune_inbox
        removed = prune_inbox(dry_run=args.dry_run)
        tag = "Would remove" if args.dry_run else "Removed"
        if removed:
            print(f"{tag} {len(removed)} dead inbox link(s):")
            for r in removed:
                print(f"  - {r['company']}: {r['title']}")
        else:
            print("No dead inbox links found (all reachable, or not probeable).")
        sys.exit(0)

    # Maintenance mode: run the discovery funnel and exit (no search). Additive —
    # only adds newly found ATS boards to companies.json (user-wins, dedup).
    if args.discover:
        from discover.funnel import run_funnel
        cf = Path(args.companies_file) if args.companies_file else None
        domains = [d.strip() for d in (args.discover_domains or "").split(",") if d.strip()]
        summary = run_funnel(domains=domains or None, companies_json_path=cf,
                             limit=args.discover_limit,
                             host_level=args.discover_host_level,
                             enterprise=args.discover_enterprise,
                             max_pages=args.discover_max_pages)
        print(f"Discovery funnel: harvested {summary['harvested']} -> "
              f"added {summary['added']} new board(s) to companies.json.")
        sys.exit(0)

    # --- Resolve values: CLI flag > user_config.json > hardcoded defaults ---
    user_cfg = load_user_config(args.user_config)

    if args.keywords:
        keywords = [k.strip() for k in args.keywords.split(",")]
    elif user_cfg.get("keywords"):
        keywords = list(user_cfg["keywords"])
    else:
        # Genre-safe fallback: a non-eng project without keywords derives from its
        # field, not the engineering DEFAULT_KEYWORDS.
        from search.keyword_strategy import effective_keywords
        keywords = effective_keywords(user_cfg)
    if args.add_keyword:
        keywords.append(args.add_keyword.strip())

    location = args.location or user_cfg.get("location") or DEFAULT_LOCATION

    if args.salary_min is not None:
        salary_min = args.salary_min
    elif user_cfg.get("salary_min") is not None:
        salary_min = int(user_cfg["salary_min"])
    else:
        salary_min = None

    industry = args.industry or user_cfg.get("industry") or None

    # Broaden the QUERY keywords for API recall (search broad, score narrow). Job
    # APIs phrase-match, so narrow seniority-laden titles return ~0; the field term
    # returns far more. Original `keywords` stay the scoring set. No-op for eng IC
    # titles, so Alex's flow is byte-identical. Opt out with "broaden_keywords": false.
    from search.keyword_strategy import broad_query_keywords
    if user_cfg.get("broaden_keywords", True):
        import industry_profile
        _syn = industry_profile.resolve(industry or "").query_synonyms
        query_keywords = broad_query_keywords(keywords, industry or "", synonyms=_syn)
    else:
        query_keywords = keywords

    default_sources_str = ",".join(ALL_SOURCES)
    cfg_sources = user_cfg.get("sources", {})
    if args.sources != default_sources_str:
        # An explicit --sources list is a stronger opt-in than field gating —
        # honor it exactly as requested.
        sources = [s.strip().lower() for s in args.sources.split(",")]
    else:
        # OPT_IN_SOURCES default OFF (must be explicitly enabled); everything
        # else defaults ON. linkedin_guest is the only opt-in source today.
        sources = [s for s in ALL_SOURCES
                   if cfg_sources.get(s, s not in OPT_IN_SOURCES)]
        # Drop tech/remote-skewed boards for a non-knowledge-work field (no-op
        # for eng/knowledge-work fields; an explicit cfg_sources override wins).
        from search.keyword_strategy import gate_tech_sources
        sources = gate_tech_sources(sources, industry or "", cfg_sources)

    output_dir = Path(args.output_dir) if args.output_dir else workspace.output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    companies_file = Path(args.companies_file) if args.companies_file else None

    today = date.today().isoformat()

    print(f"Sources requested: {sources}")

    # Warn before a manual run spends the JSearch 200/month free tier. A bare
    # run can use up to (keywords x max_pages) requests, so surface the balance.
    if "jsearch" in sources:
        from config import CACHE_DIR, JSEARCH_MONTHLY_LIMIT
        from search.http_util import MonthlyQuota
        _q = MonthlyQuota(CACHE_DIR / "jsearch_usage.json", JSEARCH_MONTHLY_LIMIT)
        _left = _q.remaining()
        _est = len(keywords) * max(1, args.max_pages)
        print(
            f"  [jsearch] {_left} of {JSEARCH_MONTHLY_LIMIT} requests left this "
            f"month (this run may use up to ~{_est})"
        )

    clients = build_clients(
        sources,
        cache_enabled=not args.no_cache,
        top_n=args.top_n,
        industry_filter=industry,
        discovery_enabled=not args.no_discover,
        companies_file=companies_file,
    )

    if not clients:
        print("Error: no sources could be initialized. Check your .env credentials.")
        sys.exit(1)

    active = [type(c).__name__ for c in clients]
    print(f"Active sources: {active}\n")

    engine = SearchEngine(clients)
    results = engine.run_full_search(
        keywords=query_keywords,
        location=location,
        salary_min=salary_min,
        max_pages_per_keyword=args.max_pages,
        sort_by="date" if args.sort_by == "score" else args.sort_by,
    )

    # Persist discovered "winner" companies (returned >=1 matching job) so they
    # become a permanent part of the watchlist on future runs.
    if args.save_discovered:
        careers = next((c for c in clients if type(c).__name__ == "CareersClient"), None)
        if careers is not None:
            added = careers.persist_discovered(companies_file)
            if added:
                print(f"Saved {added} new discovered company(ies) to companies.json.")
            else:
                print("No new discovered companies to save (none new, or discovery off).")

    if not results:
        print("No results found.")
        sys.exit(0)

    # Cross-run dedup: hide jobs already tracked or explicitly dismissed so each
    # search surfaces only genuinely new postings.
    if not args.show_tracked:
        from tracker.db import init_db, normalize_url, seen_urls
        init_db()
        seen = seen_urls()
        before = len(results)
        results = [r for r in results if normalize_url(r.url) not in seen]
        # Also hide URL-less postings that match an already-tracked posting by
        # their canonical company+title (the location-free job_key component), so
        # a cross-source re-harvest of the same role is treated as seen. Mirrors
        # the URL check above. Best-effort: any failure falls back to URL-only.
        try:
            from coverage import entity
            from tracker.db import get_all
            tracked = {
                (entity.canonicalize_company(a.get("company") or ""),
                 entity.title_core(a.get("title") or ""))
                for a in get_all()
            }
            if tracked:
                results = [
                    r for r in results
                    if r.url or (entity.canonicalize_company(r.company or ""),
                                 entity.title_core(r.title or "")) not in tracked
                ]
        except Exception:
            pass
        hidden = before - len(results)
        if hidden:
            print(f"Hid {hidden} already-tracked/dismissed job(s) (use --show-tracked to include).")
        if not results:
            print("All matches were already tracked or dismissed. Use --show-tracked to see them.")
            sys.exit(0)

    # Match scoring: rank everything against the user's profile, then apply
    # the floor. Scoring happens after the tracked/dismissed filter so the
    # skill-extraction work isn't spent on jobs that will be hidden anyway.
    from match.scorer import score_jobs
    try:
        import preferences as _prefs
        _remote_regions_ok = bool(_prefs.load().get("hard", {}).get("remote_regions_ok", False))
    except Exception:
        _remote_regions_ok = False
    results = score_jobs(
        results,
        keywords=keywords,
        location=location,
        salary_floor=salary_min,
        exclude_keywords=user_cfg.get("exclude_keywords", []),
        exclude_titles=user_cfg.get("exclude_titles"),
        title_miss_penalty=user_cfg.get("title_miss_penalty"),
        seniority_exclude=user_cfg.get("seniority_exclude"),
        seniority_target=user_cfg.get("seniority_target"),
        years_cap=user_cfg.get("years_cap"),
        remote_regions_ok=_remote_regions_ok,
        title_context_required=user_cfg.get("title_context_required"),
    )
    min_score = args.min_score
    if min_score is None:
        min_score = int(user_cfg.get("min_score", 0))
    if min_score > 0:
        before = len(results)
        results = [r for r in results if r.score >= min_score]
        dropped = before - len(results)
        if dropped:
            print(f"Hid {dropped} job(s) scoring below {min_score} (--min-score).")
        if not results:
            print(f"No jobs scored >= {min_score}. Lower --min-score to see more.")
            sys.exit(0)
    if args.sort_by != "score":  # score_jobs sorted best-first; restore request
        from search.search_engine import _location_score, _parse_created
        if args.sort_by == "location":
            results.sort(key=lambda j: _location_score(j.location, location), reverse=True)
        else:
            results.sort(key=lambda j: _parse_created(j.created), reverse=True)

    search_params = {
        "date": today,
        "location": location,
        "keywords": keywords,
        "salary_min": salary_min,
        "sources": active,
    }

    html_path = output_dir / f"job_search_{today}.html"
    csv_path = output_dir / f"job_search_{today}.csv"

    generate_html_report(results, html_path, search_params)
    generate_csv_report(results, csv_path)

    print(f"\nHTML report: {html_path}")
    print(f"CSV report:  {csv_path}")

    if args.edit_csv:
        import os
        try:
            os.startfile(str(csv_path))  # Windows only
        except Exception:
            print(f"  [output] Could not open CSV automatically — find it at: {csv_path}")

    webbrowser.open(html_path.as_uri())


if __name__ == "__main__":
    main()
