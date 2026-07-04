"""Registry-driven per-source client builders for search.cli.build_clients.

WHY: build_clients() used to be a single ~400-line if/elif chain that every
new-source PR had to insert itself into. Because every feature wave touches
the SAME function body, parallel branches collide there constantly (S35 #23's
landing alone took a 4-region merge conflict just inside this one function).
Converting it to a registry means adding a job source is "write one function +
one SOURCE_BUILDERS entry" instead of editing a shared 400-line chain --
independent source additions stop conflicting with each other at the text
level.

Each builder is a small `def _name(ctx: BuildContext) -> JobAPIClient | None`
function: given the shared BuildContext, it constructs (or skips) its one
source and returns the client instance, or None if the source is skipped this
run (a country gate, a missing key it self-reports via ctx.note_keyless, etc).
build_clients() in cli.py does the appending, the outer S35 #23 per-source
try/except Exception guard, and the "unknown source" fallback -- this module
holds ONLY the per-source construction logic, moved verbatim from the old
elif chain (log strings unchanged, byte-for-byte).

Each builder keeps its lazy, function-local `from search.X import Y` import --
that laziness is deliberate (a keyless client's module shouldn't import until
the source is actually requested), and it also lets tests monkeypatch the
client class on its defining module (e.g. `search.themuse_client.TheMuseClient`)
before build_clients constructs it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from search.base_client import JobAPIClient


@dataclass
class BuildContext:
    """Everything a per-source builder might need, gathered once per
    build_clients() call. Fields mirror build_clients' own parameters plus the
    values it derives (the resolved country, its logger, the keyless-out-param
    callback) so a builder never has to re-derive them."""

    cache_enabled: bool
    top_n: int = 20
    industry_filter: str | None = None
    discovery_enabled: bool = True
    companies_file: Path | None = None
    tiered_careers: bool = False
    location: str | None = None
    country: str = "us"
    slog: object = None  # logging.Logger-like (applog.get_logger("sources"))
    note_keyless: Callable[[str], None] = field(default=lambda name: None)
    # Records a source that self-skipped because it is US-ONLY and the project's
    # country isn't 'us' (distinct from a missing key). Surfaced structurally so the
    # web UI can render an honest "US-only sources skipped for your country" badge
    # instead of leaving it only in the free-text run log. (scenario finding #3)
    note_country_skip: Callable[[str], None] = field(default=lambda name: None)


# A builder either returns a constructed client (to be appended), or None if
# this source is inert/skipped for THIS run (already logged by the builder
# itself, mirroring the old chain's `continue` / no-append paths).
SourceBuilder = Callable[[BuildContext], Optional[JobAPIClient]]


def _adzuna(ctx: BuildContext) -> JobAPIClient | None:
    # Resolved via the search.cli module attribute (not a fresh
    # `from search.adzuna_client import AdzunaClient`) so
    # `monkeypatch.setattr(cli, "AdzunaClient", ...)` -- the pinned patch
    # point from the pre-registry chain -- still take effect.
    import search.cli as cli
    try:
        # Route to the user's country (one free key covers ~19). Without
        # this, a non-US user (e.g. "London, United Kingdom") always hit
        # the /us/ endpoint and got US-only jobs. adzuna_country_for is a
        # no-op for US locations (returns the module default).
        return cli.AdzunaClient(cache_enabled=ctx.cache_enabled, country=ctx.country)
    except ValueError as e:
        ctx.slog.info(f"  [adzuna] Skipping — {e}")
        ctx.note_keyless("adzuna")
        return None


def _jsearch(ctx: BuildContext) -> JobAPIClient | None:
    from search.jsearch_client import JSearchClient
    try:
        c = JSearchClient(cache_enabled=ctx.cache_enabled)
        ctx.slog.info(
            "  [jsearch] NOTE: Free tier is 200 req/month. "
            "Each keyword/page costs 1 request."
        )
        return c
    except ValueError as e:
        ctx.slog.info(f"  [jsearch] Skipping — {e}")
        ctx.note_keyless("jsearch")
        return None


def _usajobs(ctx: BuildContext) -> JobAPIClient | None:
    # US-federal-jobs-only API: a non-US project gets 0 every run
    # (wrong country entirely), burning the free-tier quota/cache
    # slot and adding runtime for zero payoff. Self-report inert
    # instead of registering. US users (country == 'us', including
    # a blank/unresolvable location, which resolves to the 'us'
    # default): unchanged.
    if ctx.country != "us":
        ctx.slog.info(f"  [usajobs] US-only source — skipped for "
                       f"{ctx.location or '(no location)'!r} (country={ctx.country}).")
        ctx.note_country_skip("usajobs")
        return None
    from search.usajobs_client import USAJobsClient
    try:
        return USAJobsClient(cache_enabled=ctx.cache_enabled)
    except ValueError as e:
        ctx.slog.info(f"  [usajobs] Skipping — {e}")
        ctx.note_keyless("usajobs")
        return None


def _careeronestop(ctx: BuildContext) -> JobAPIClient | None:
    # US DOL / National Labor Exchange — US-only, same reasoning as
    # usajobs above. Non-US projects never register it.
    if ctx.country != "us":
        ctx.slog.info(f"  [careeronestop] US-only source — skipped for "
                       f"{ctx.location or '(no location)'!r} (country={ctx.country}).")
        ctx.note_country_skip("careeronestop")
        return None
    from search.careeronestop_client import CareerOneStopClient
    try:
        return CareerOneStopClient(cache_enabled=ctx.cache_enabled)
    except ValueError as e:
        ctx.slog.info(f"  [careeronestop] Skipping — {e}")
        ctx.note_keyless("careeronestop")
        return None


def _themuse(ctx: BuildContext) -> JobAPIClient | None:
    from search.themuse_client import TheMuseClient
    return TheMuseClient(cache_enabled=ctx.cache_enabled)


def _remoteok(ctx: BuildContext) -> JobAPIClient | None:
    from search.remoteok_client import RemoteOKClient
    return RemoteOKClient(cache_enabled=ctx.cache_enabled)


def _remotive(ctx: BuildContext) -> JobAPIClient | None:
    from search.remotive_client import RemotiveClient
    return RemotiveClient(cache_enabled=ctx.cache_enabled)


def _jobicy(ctx: BuildContext) -> JobAPIClient | None:
    from search.jobicy_client import JobicyClient
    return JobicyClient(cache_enabled=ctx.cache_enabled)


def _himalayas(ctx: BuildContext) -> JobAPIClient | None:
    from search.himalayas_client import HimalayasClient
    return HimalayasClient(cache_enabled=ctx.cache_enabled)


def _hn(ctx: BuildContext) -> JobAPIClient | None:
    from search.hn_client import HNClient
    return HNClient(cache_enabled=ctx.cache_enabled)


def _careers(ctx: BuildContext) -> JobAPIClient | None:
    from scrape.careers_client import CareersClient
    return CareersClient(
        cache_enabled=ctx.cache_enabled,
        top_n=ctx.top_n,
        industry_filter=ctx.industry_filter,
        discovery_enabled=ctx.discovery_enabled,
        companies_file=ctx.companies_file,
        tiered=ctx.tiered_careers,
    )


def _arbeitnow(ctx: BuildContext) -> JobAPIClient | None:
    from search.arbeitnow_client import ArbeitnowClient
    return ArbeitnowClient(cache_enabled=ctx.cache_enabled)


def _jooble(ctx: BuildContext) -> JobAPIClient | None:
    from search.jooble_client import JoobleClient
    # Route to the user's country-scoped Jooble host (uk.jooble.org
    # etc.) — a no-op for 'us'/unmapped countries (bare jooble.org,
    # same URL as before this was added).
    c = JoobleClient(cache_enabled=ctx.cache_enabled, country=ctx.country)
    # Registers unconditionally then self-skips at fetch time when
    # unkeyed; ask the client's OWN key predicate so the count tracks the
    # real skip condition, not a source list here.
    if getattr(c, "keyless", lambda: False)():
        ctx.slog.info("  [jooble] JOOBLE_API_KEY unset — will self-skip "
                       "(free key at jooble.org/api/about).")
        ctx.note_keyless("jooble")
    return c


def _careerjet(ctx: BuildContext) -> JobAPIClient | None:
    from search.careerjet_client import CareerjetClient
    # Route to the user's Careerjet locale_code — a no-op for 'us'/
    # unmapped countries (param omitted, same request as before).
    c = CareerjetClient(cache_enabled=ctx.cache_enabled, country=ctx.country)
    if getattr(c, "keyless", lambda: False)():
        ctx.slog.info("  [careerjet] CAREERJET_AFFID unset — will self-skip "
                       "(free affiliate id at careerjet.com/partners).")
        ctx.note_keyless("careerjet")
    return c


def _linkedin_guest(ctx: BuildContext) -> JobAPIClient | None:
    from search.linkedin_guest_client import LinkedInGuestClient
    ctx.slog.info("  [linkedin_guest] NOTE: logged-out PUBLIC guest endpoint only — "
                  "no login/cookies. Review LinkedIn ToS before enabling.")
    return LinkedInGuestClient(cache_enabled=ctx.cache_enabled)


def _serpapi(ctx: BuildContext) -> JobAPIClient | None:
    from search.serpapi_client import SerpApiClient
    try:
        c = SerpApiClient(cache_enabled=ctx.cache_enabled)
        ctx.slog.info(f"  [serpapi] BYO Google-Jobs backend active "
                      f"(free tier {__import__('config').SERPAPI_MONTHLY_LIMIT}/month).")
        return c
    except ValueError as e:
        ctx.slog.info(f"  [serpapi] Skipping — {e}")
        ctx.note_keyless("serpapi")
        return None


def _weworkremotely(ctx: BuildContext) -> JobAPIClient | None:
    from search.weworkremotely_client import WeWorkRemotelyClient
    return WeWorkRemotelyClient(cache_enabled=ctx.cache_enabled)


def _workingnomads(ctx: BuildContext) -> JobAPIClient | None:
    from search.workingnomads_client import WorkingNomadsClient
    return WorkingNomadsClient(cache_enabled=ctx.cache_enabled)


def _higheredjobs(ctx: BuildContext) -> JobAPIClient | None:
    # Sector RSS: education/faculty/admin. Self-skips (fetches nothing)
    # for a non-education field via its industry gate — safe to always
    # register. industry_filter is the active project's field.
    from search.higheredjobs_client import HigherEdJobsClient
    c = HigherEdJobsClient(cache_enabled=ctx.cache_enabled,
                           industry=ctx.industry_filter)
    if not c.cat_ids:
        ctx.slog.info(f"  [higheredjobs] Inert for industry "
                      f"{ctx.industry_filter or '(none)'!r} — no education categories map.")
    return c


def _rnjobsite(ctx: BuildContext) -> JobAPIClient | None:
    # Sector RSS: registered-nurse specialties. Self-skips for a
    # non-nursing field via its industry gate.
    from search.rnjobsite_client import RNJobSiteClient
    c = RNJobSiteClient(cache_enabled=ctx.cache_enabled,
                        industry=ctx.industry_filter)
    if not c.active:
        ctx.slog.info(f"  [rnjobsite] Inert for industry "
                      f"{ctx.industry_filter or '(none)'!r} — not a nursing field.")
    return c


def _jobsacuk(ctx: BuildContext) -> JobAPIClient | None:
    # Sector RSS: UK academic/health. OPT-IN only (config flag or non-US
    # country); inert in a default US run. PROVISIONAL endpoint.
    from search.jobsacuk_client import JobsAcUkClient
    # Pass the run's location through so opt_in_active's own
    # non-US-country check (config.adzuna_country_for) can see it —
    # build_clients doesn't carry a full cfg dict, so a minimal one
    # is synthesized here.
    c = JobsAcUkClient(cache_enabled=ctx.cache_enabled,
                       industry=ctx.industry_filter,
                       cfg={"location": ctx.location})
    if not c.active:
        ctx.slog.info("  [jobsacuk] Inert — UK academic feeds are opt-in "
                      "(set 'jobsacuk' in config or a non-US country).")
    return c


def _reap(ctx: BuildContext) -> JobAPIClient | None:
    # Sector: K-12 education, per-STATE public REAP portals. Self-skips
    # for a non-education field OR a state REAP doesn't cover (routes by
    # the user's location). robots.txt is honored live before any fetch.
    from search.reap_client import ReapClient
    c = ReapClient(cache_enabled=ctx.cache_enabled,
                   industry=ctx.industry_filter, location=ctx.location)
    if not c.active:
        if not c.portal and ctx.industry_filter and __import__(
                "search.reap_client", fromlist=["_is_education"]
                )._is_education(ctx.industry_filter):
            ctx.slog.info(f"  [reap] Inert — no REAP portal for location "
                          f"{ctx.location or '(none)'!r} (covered states: "
                          f"CT/MO/NM/OH/PA).")
        else:
            ctx.slog.info(f"  [reap] Inert for industry "
                          f"{ctx.industry_filter or '(none)'!r} — not an education field.")
    return c


def _edjoin(ctx: BuildContext) -> JobAPIClient | None:
    # Sector: K-12 education, EdJoin public JSON search (California-centric;
    # graceful 0 for non-CA metros). Self-skips for a non-education field.
    from search.edjoin_client import EdjoinClient
    c = EdjoinClient(cache_enabled=ctx.cache_enabled,
                     industry=ctx.industry_filter, location=ctx.location)
    if not c.active:
        ctx.slog.info(f"  [edjoin] Inert for industry "
                      f"{ctx.industry_filter or '(none)'!r} — not an education field.")
    return c


def _socrata(ctx: BuildContext) -> JobAPIClient | None:
    from search.socrata_client import SocrataClient
    from config import SOCRATA_APP_TOKEN, SOCRATA_CITIES
    c = SocrataClient(
        cities=SOCRATA_CITIES, app_token=SOCRATA_APP_TOKEN,
        cache_enabled=ctx.cache_enabled,
    )
    if not SOCRATA_CITIES:
        ctx.slog.info("  [socrata] No SOCRATA_CITIES configured — client is inert "
                      "(add a city key, e.g. 'nyc', to config.SOCRATA_CITIES).")
    return c


# name -> builder. Adding a source is exactly: write one `_name(ctx)` function
# above + one entry here. build_clients() in cli.py loops `sources`, looks up
# the name here, and falls through to the "Unknown source" warning if absent.
SOURCE_BUILDERS: dict[str, SourceBuilder] = {
    "adzuna": _adzuna,
    "jsearch": _jsearch,
    "usajobs": _usajobs,
    "careeronestop": _careeronestop,
    "themuse": _themuse,
    "remoteok": _remoteok,
    "remotive": _remotive,
    "jobicy": _jobicy,
    "himalayas": _himalayas,
    "hn": _hn,
    "careers": _careers,
    "arbeitnow": _arbeitnow,
    "jooble": _jooble,
    "careerjet": _careerjet,
    "linkedin_guest": _linkedin_guest,
    "serpapi": _serpapi,
    "weworkremotely": _weworkremotely,
    "workingnomads": _workingnomads,
    "higheredjobs": _higheredjobs,
    "rnjobsite": _rnjobsite,
    "jobsacuk": _jobsacuk,
    "reap": _reap,
    "edjoin": _edjoin,
    "socrata": _socrata,
}
