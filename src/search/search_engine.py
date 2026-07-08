import re
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Optional

import applog
from config import SEARCH_MAX_WORKERS
from dateparse import parse_flex_iso
from models import JobResult, normalize_url
from search.base_client import JobAPIClient

# Per-source fetch failures used to print() to a console the frozen exe throws
# away, so an expired key / throttled board looked identical to a thin market
# (review #2). Route them through the framework so they PERSIST to the rotating
# app.log. Logged at INFO so the console text is byte-identical to the old
# print() lines (the bare-message console formatter adds no prefix).
_log = applog.get_logger("search_engine")

_STATE_ABBREVS = {
    "alabama": "al", "alaska": "ak", "arizona": "az", "arkansas": "ar",
    "california": "ca", "colorado": "co", "connecticut": "ct", "delaware": "de",
    "florida": "fl", "georgia": "ga", "hawaii": "hi", "idaho": "id",
    "illinois": "il", "indiana": "in", "iowa": "ia", "kansas": "ks",
    "kentucky": "ky", "louisiana": "la", "maine": "me", "maryland": "md",
    "massachusetts": "ma", "michigan": "mi", "minnesota": "mn",
    "mississippi": "ms", "missouri": "mo", "montana": "mt", "nebraska": "ne",
    "nevada": "nv", "new hampshire": "nh", "new jersey": "nj",
    "new mexico": "nm", "new york": "ny", "north carolina": "nc",
    "north dakota": "nd", "ohio": "oh", "oklahoma": "ok", "oregon": "or",
    "pennsylvania": "pa", "rhode island": "ri", "south carolina": "sc",
    "south dakota": "sd", "tennessee": "tn", "texas": "tx", "utah": "ut",
    "vermont": "vt", "virginia": "va", "washington": "wa",
    "west virginia": "wv", "wisconsin": "wi", "wyoming": "wy",
    "district of columbia": "dc",
}

_EPOCH = datetime.min.replace(tzinfo=timezone.utc)

# A remote LABEL that names a non-US region ("Remote - Czech Republic", "Remote,
# EMEA", "UK only"). Country-blind remote credit (returning full marks for ANY
# 'remote' string) let a Czech/UK/Canada-only remote outrank a real local US job
# (review #2 / QW-2). When the target is a US metro and no US signal is present,
# such a row gets REDUCED remote credit instead of full marks. Conservative +
# word-bounded so a plain "Remote" or a US label ("Remote - US", "Remote, TX") is
# never capped. Mirrors match.facts._NON_US_REMOTE_LABEL / _US_SIGNAL.
_NON_US_REMOTE_RE = re.compile(
    r"\bczech(?:ia|\s*republic)?\b|\bemea\b|\blatam\b|\bapac\b|"
    r"\buk\b|united kingdom|\beu\b|\beurope(?:an)?\b|\bcanada\b|\bcanadian\b|"
    r"\baustralia\b|\bindia\b|\bgermany\b|\bmexico\b|\bbrazil\b|\bireland\b|"
    r"\bnetherlands\b|\bpoland\b|\bportugal\b|\bspain\b|\bfrance\b|\blatin america\b",
    re.I)
_US_SIGNAL_RE = re.compile(
    r"\bu\.?s\.?a?\b|\bunited states\b|\bus[- ]?based\b|\bus only\b|\bnorth america\b",
    re.I)


def _target_is_us(target: str) -> bool:
    """Best-effort: is the search target a US metro? True when the target names a US
    state (full name or 2-letter abbrev). A bare city / empty target -> False (so we
    don't cap remote for a user whose target we can't place in the US)."""
    tl = (target or "").lower()
    if not tl.strip():
        return False
    toks = [t.strip().rstrip(",.") for t in tl.replace(",", " ").split()]
    for full, ab in _STATE_ABBREVS.items():
        if ab in toks or full in tl:
            return True
    return False


def _location_score(job_location: str, target: str, *, remote_ok: bool = True,
                    remote_regions_ok: bool = False) -> int:
    """Score how closely a job's location matches the search target. Higher = closer.

    A pure-remote posting (one carrying 'remote' but not the target metro) used to
    score 0, which capped remote roles at 85/100 and buried them below local jobs.
    When remote is acceptable (``remote_ok``), credit it as a full match instead:
    the location component means 'somewhere I'd take the job' = local OR
    acceptable-remote. With ``remote_ok=False`` a remote-only role still scores 0,
    so local-only users are unaffected.

    Country-blind remote (review #2): a remote row whose label names a non-US region
    (and no US signal), when the target is a US metro, gets REDUCED credit (1 not 3)
    instead of full marks -- unless ``remote_regions_ok`` (the user genuinely can work
    those regions). A plain "Remote" or a US-signal label is unaffected."""
    jl = (job_location or "").lower()
    tl = target.lower().strip()
    if "remote" in jl and tl not in jl:
        if not remote_ok:
            return 0
        # Country-blind cap: a non-US-only remote label for a US target seeker.
        if (not remote_regions_ok and _target_is_us(target)
                and not _US_SIGNAL_RE.search(jl) and _NON_US_REMOTE_RE.search(jl)):
            return 1   # reduced remote credit (l≈0.33) -- non-US-only remote
        return 3       # acceptable-remote -> full marks (l=1.0)
    target_tokens = [t.strip().rstrip(",") for t in tl.replace(",", " ").split()]
    score = 0
    for token in target_tokens:
        if token in jl:
            score += 2 if len(token) > 3 else 1
        for full, abbrev in _STATE_ABBREVS.items():
            if (token == abbrev and full in jl) or (token == full and abbrev in jl):
                score += 1
    return score


def _parse_created(value: str) -> datetime:
    """Parse heterogeneous source date strings (ISO with/without tz, ``Z`` suffix,
    or date-only) into an aware datetime so sorting is chronological, not
    lexicographic. Unparseable/empty sinks to the epoch."""
    return parse_flex_iso(value) or _EPOCH


class SearchEngine:
    def __init__(self, clients: list[JobAPIClient]):
        self.clients = clients
        # Raw (pre-dedup) results of the most recent run_full_search, kept so the
        # coverage/reach estimator can see the cross-source membership that dedup
        # discards. Empty until a search runs. Read-only for callers.
        self.last_raw_results: list[JobResult] = []
        # Per-source first-error map from the most recent run (source -> message),
        # consumed by the daily run beacon (last_run.json errors[]). Read-only.
        self.last_source_errors: dict[str, str] = {}

    def source_errors(self) -> dict:
        """Per-source first-error map from the most recent run_full_search."""
        return dict(self.last_source_errors)

    def run_full_search(
        self,
        keywords: list[str],
        location: str = "",
        salary_min: Optional[int] = None,
        max_pages_per_keyword: int = 2,
        sort_by: str = "date",
        progress=None,
        cancel=None,
    ) -> list[JobResult]:
        """Run every client concurrently and return the de-duplicated results.

        ``progress`` (optional) is a callback invoked from worker threads with a
        single dict event so a GUI can show determinate per-source feedback
        without this engine importing Tk. It MUST be thread-safe (the GUI marshals
        onto the Tk thread). Events:
          {"phase": "start",  "total": N}                       once, before work
          {"phase": "source_start", "source": str}             each client begins
          {"phase": "source_done",  "source": str, "count": n, "ok": bool,
           "error": str, "done": k, "total": N}                 each client ends
          {"phase": "done",   "raw": n, "deduped": m}          once, after dedup
        ``cancel`` (optional) is a threading.Event checked between clients and (in
        _run_client) between keywords/pages; when set, in-flight units finish but
        no new work starts and the partial results collected so far are returned.
        Both default to None = today's behavior exactly (no callback, no cancel).
        """
        all_results: list[JobResult] = []
        cancelled = bool(cancel and cancel.is_set())

        def _emit(**event):
            if progress:
                try:
                    progress(event)
                except Exception:
                    pass  # a UI callback must never break the search

        # Build the fetch work-list. Every client runs concurrently (the rate
        # limiter and file cache are thread-safe), and a keyword-parameterized
        # client (parallel_keywords=True: Adzuna/JSearch/SerpApi/USAJobs) is
        # ALSO split into one unit per keyword so its keywords fetch in parallel
        # instead of serially — the old engine capped at 4 client tasks and ran
        # each client's keywords one-by-one, so a multi-keyword search serialized
        # most of its work. Keyword-blind feeds (SingleFeedClient: The Muse,
        # RemoteOK, …) stay a single unit: they fetch once and filter every
        # keyword client-side, and some carry per-instance paging state
        # (_raw_exhausted) that concurrent keywords on one instance would race.
        units: list[tuple[JobAPIClient, list[str]]] = []
        for client in self.clients:
            if getattr(client, "parallel_keywords", False) and len(keywords) > 1:
                units.extend((client, [kw]) for kw in keywords)
            else:
                units.append((client, list(keywords)))

        agg_n: dict[str, int] = defaultdict(int)
        agg_t: dict[str, float] = defaultdict(float)
        agg_err: dict[str, str] = {}   # first per-keyword error string per source
        # Determinate progress is per distinct SOURCE (not per unit): a
        # keyword-parameterized client is split into several units but is one
        # source in the UI's "source k/N" counter.
        sources_all = sorted({type(c).__name__ for c, _ in units})
        _emit(phase="start", total=len(sources_all))
        started_sources: set[str] = set()
        done_sources: set[str] = set()

        def _run_unit(client, kws):
            src = type(client).__name__
            # source_start fires once per source (the first unit to begin it).
            if progress and src not in started_sources:
                started_sources.add(src)
                _emit(phase="source_start", source=src)
            return self._timed_run_client(client, kws, location,
                                          salary_min, max_pages_per_keyword,
                                          cancel=cancel)

        max_workers = min(len(units), SEARCH_MAX_WORKERS) or 1
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_run_unit, client, kws): type(client).__name__
                for client, kws in units
            }
            for future in as_completed(futures):
                source = futures[future]
                try:
                    res, elapsed, unit_err = future.result()
                    agg_n[source] += len(res)
                    # Units of one source run concurrently → its wall-clock is the
                    # slowest unit, not their sum.
                    agg_t[source] = max(agg_t[source], elapsed)
                    all_results.extend(res)
                    # _run_client swallows per-keyword errors (prints + breaks) so
                    # a 429'd source returns [] and would LOOK like an empty market
                    # — the review's finding #2. Surface the first such error so
                    # the progress layer can mark the source throttled/failed, not
                    # "ok, 0 results".
                    if unit_err and source not in agg_err:
                        agg_err[source] = unit_err
                except Exception as e:
                    if source not in agg_err:
                        from applog import redact
                        agg_err[source] = redact(str(e))
                    _log.info(f"[{source}] failed: {e}")
                # A source is "done" once its LAST unit resolves; a multi-unit
                # source reports once, when the final unit lands.
                remaining = sum(1 for f, s in futures.items()
                                if s == source and not f.done())
                if remaining == 0 and source not in done_sources:
                    done_sources.add(source)
                    src_err = agg_err.get(source, "")
                    # "ok" = the source ran and either returned rows or a clean
                    # empty (no error). A source that returned rows AND errored on
                    # some keyword still counts ok (it produced results).
                    ok = not src_err or agg_n[source] > 0
                    _emit(phase="source_done", source=source,
                          count=agg_n[source], ok=ok, error=src_err,
                          done=len(done_sources), total=len(sources_all))
                if cancel and cancel.is_set():
                    cancelled = True

        # Per-source summary with timing (no per-source instrumentation existed
        # before, so a slow source couldn't be identified without guessing).
        for source in sorted(agg_n):
            print(f"[{source}] {agg_n[source]} results in ~{agg_t[source]:.1f}s")

        # CareersClient's per-company scraper failures are fail-soft BY DESIGN
        # (one broken ATS tenant must not sink the whole 'careers' source) and so
        # never raise out of search_and_parse -- last_source_errors above only
        # sees an error when a client's search_and_parse itself raises. Surface
        # the aggregate here instead, once per run, through the SAME logging
        # framework daily_run surfaces (S35 #6). Generic hasattr check (like
        # finalize_tiering) so this isn't a CareersClient-specific special case.
        for client in self.clients:
            company_errors = getattr(client, "company_errors", None)
            if not callable(company_errors):
                continue
            errs = company_errors()
            failed_names = errs.get("failed", [])
            if not failed_names:
                continue
            # Distinct boards that errored at least once this run (not the raw
            # error count, which double-counts a board that fails on >1 keyword).
            total = len(getattr(client, "_base_companies", []) or []) or len(failed_names)
            shown = ", ".join(failed_names[:8])
            more = f" (+{len(failed_names) - 8} more)" if len(failed_names) > 8 else ""
            _log.warning(
                f"[careers] {len(failed_names)}/{total} board(s) failed this run: "
                f"{shown}{more} (see app.log)")

        self.last_raw_results = all_results  # for coverage/reach (membership)
        self.last_source_errors = dict(agg_err)  # for the run beacon (last_run.json)
        deduped = self._deduplicate(all_results)
        if sort_by == "location":
            deduped.sort(key=lambda j: _location_score(j.location, location), reverse=True)
        else:
            deduped.sort(key=lambda j: _parse_created(j.created), reverse=True)

        print(f"\nTotal: {len(all_results)} raw -> {len(deduped)} after dedup")
        _emit(phase="done", raw=len(all_results), deduped=len(deduped),
              cancelled=cancelled)
        return deduped

    def _timed_run_client(self, client, keywords, location, salary_min, max_pages,
                          cancel=None):
        """_run_client wrapped with a wall-clock measurement (for the per-source
        timing summary). Returns (results, elapsed_seconds, error_str). error_str
        is '' unless a per-keyword fetch raised (used to distinguish a throttled/
        broken source from a genuinely empty market)."""
        t0 = time.perf_counter()
        res, err = self._run_client(client, keywords, location, salary_min,
                                    max_pages, cancel=cancel)
        return res, time.perf_counter() - t0, err

    def _run_client(
        self,
        client: JobAPIClient,
        keywords: list[str],
        location: str,
        salary_min: Optional[int],
        max_pages: int,
        cancel=None,
    ) -> tuple[list[JobResult], str]:
        source = type(client).__name__
        out: list[JobResult] = []
        first_error = ""
        for keyword in keywords:
            if cancel and cancel.is_set():
                break  # cooperative cancel: stop before the next keyword
            for page in range(1, max_pages + 1):
                if cancel and cancel.is_set():
                    break  # and before the next page
                try:
                    results = client.search_and_parse(
                        keyword=keyword, location=location,
                        salary_min=salary_min, page=page,
                    )
                except Exception as e:
                    # Transient errors are already retried in the session; a
                    # failure here stops paging this keyword but not the run.
                    # redact(): HTTPError messages embed the full request URL,
                    # which for Jooble/Adzuna/Careerjet carries the credential —
                    # this string flows to last_run.json + the source-health UI.
                    if not first_error:
                        from applog import redact
                        first_error = redact(str(e))
                    _log.info(f"  [{source}] {keyword!r} page {page} error: {e}")
                    break
                if not results:
                    # A keyword-blind feed (e.g. The Muse) can return a page with
                    # raw postings but zero client-side keyword matches; keep
                    # paging until its RAW feed is spent. Other clients have no
                    # _raw_exhausted flag -> default True -> stop on empty (as before).
                    if getattr(client, "_raw_exhausted", True):
                        break  # genuine end-of-results for this keyword
                    continue
                out.extend(results)
                if getattr(client, "_last_page_short", False):
                    break  # client saw a short raw page — no further page exists
        return out, first_error

    def _deduplicate(self, results: list[JobResult]) -> list[JobResult]:
        # URL is the fast path: normalized-url variants of the same posting
        # collapse, and distinct reqs at distinct URLs stay separate. job_key adds
        # cross-source collapsing for postings with NO usable URL: we key those on
        # the canonicalized company + title_core (the location-free part of job_key)
        # so formatting variants ("Acme, Inc." vs "Acme Inc"; "Cincinnati, OH" vs
        # "Cincinnati"/"Remote") merge while distinct roles/companies stay apart.
        seen_urls: set[str] = set()
        seen_keyless: set[str] = set()
        unique: list[JobResult] = []
        for job in results:
            u = normalize_url(job.url)
            if u:
                if u in seen_urls:
                    continue
                seen_urls.add(u)
            else:
                key = keyless_identity(job)
                if key in seen_keyless:
                    continue
                seen_keyless.add(key)
            unique.append(job)
        return unique


def keyless_identity(job) -> str:
    """Stable STRING identity for a URL-less posting (company + title + location
    bucket). Location IS included so the same title at the same company in two
    different cities (e.g. 'Director of Clinical Informatics' open in Cincinnati
    AND Remote) does not silently collapse to one row — the earlier location-free
    key over-merged distinct postings.

    Returns a canonical string (not a tuple) so the SAME value can be stored as an
    inbox row's synthetic 'keyless:'-prefixed norm_url and compared for engine
    dedup - engine dedup and inbox identity MUST agree, else a URL-less posting
    that dedups in the engine would double-list in the inbox (or vice-versa).
    Falls back to a raw lowercased join if the coverage entity module isn't
    importable (e.g. a stripped frozen build)."""
    try:
        from coverage import entity
        parts = (entity.canonicalize_company(job.company or ""),
                 entity.title_core(job.title or ""),
                 entity.location_token(entity.normalize_location(job.location or "")))
    except ImportError:
        parts = ((job.company or "").lower().strip(),
                 (job.title or "").lower().strip(),
                 (job.location or "").lower().strip())
    return "\x1f".join(parts)


# Back-compat alias: some callers/tests reference the original private name. The
# engine now compares on the string form (keyless_identity); the tuple wrapper is
# retained so any external caller keeps working, but internal dedup uses the string.
def _keyless_key(job):
    return keyless_identity(job)
