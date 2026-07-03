"""
Local Flask server that receives jobs from the browser extension.
Run with: py -m scrape.browser_receiver
Then click "Send to Tool" in the extension popup.
Report opens automatically in your browser.
"""
import hashlib
import re
import sys
import webbrowser
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flask import Flask, request, jsonify

from models import JobResult
from search.report_html import generate_html_report
from search.report_csv import generate_csv_report
import workspace
from config import PORT_RECEIVER

app = Flask(__name__)
# Cap request bodies so a runaway/oversized capture (a page with thousands of
# JSON-LD blocks, or a malformed multi-MB POST) can't exhaust memory before the
# handler even runs. 8 MB is far above any legitimate batch of job rows; Flask
# returns 413 automatically past this. Loopback-only + extension-origin gating
# already limits who can reach here — this bounds how much they can send.
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024
PORT = PORT_RECEIVER

# Only the unpacked browser extension talks to this server. A chrome-extension://
# origin is unguessable per-install, so we reflect exactly that scheme rather
# than the old wildcard, which let *any* site the user visited POST job data here.
_ALLOWED_ORIGIN_SCHEME = "chrome-extension"
# Loopback hosts allowed for local/manual testing (e.g. curl from the same box).
_ALLOWED_LOCALHOST_HOSTS = ("127.0.0.1", "localhost")
# Bind to loopback only. Binding all interfaces (0.0.0.0) exposed this
# side-effecting server to anything on the LAN.
HOST = "127.0.0.1"


def _origin_allowed(origin: str) -> bool:
    """True only for the unpacked extension's chrome-extension:// origin or a
    loopback http(s) origin. CORS reflection only governs whether the *browser*
    surfaces the response to a page's JS; it does NOT stop the request from
    reaching us and triggering side effects (file writes, inboxing, opening a
    browser tab). So the handlers themselves must reject foreign origins."""
    parsed = urlparse(origin)
    if parsed.scheme == _ALLOWED_ORIGIN_SCHEME:
        return True
    if parsed.scheme in ("http", "https") and parsed.hostname in _ALLOWED_LOCALHOST_HOSTS:
        return True
    return False


def _add_cors(response):
    origin = request.headers.get("Origin", "")
    if _origin_allowed(origin):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
    response.headers["Access-Control-Allow-Methods"] = "POST, GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response

app.after_request(_add_cors)


def _safe_http_url(url: str) -> bool:
    """Reject javascript:/data: and other non-web schemes before a URL is ever
    written into an HTML report's href."""
    try:
        return urlparse(url).scheme in ("http", "https")
    except ValueError:
        return False


# A card's innerText leaks the visual separators between entity-lockup spans —
# LinkedIn's newer layout hands back "Control Systems Engineer |" / "GrayMatter |"
# (live 2026-07-02). content.js sanitizeField already strips these client-side;
# we mirror the EXACT cleanup here so a stale extension version can't slip a junk
# row past the server either (same JS-grabs / Python-owns contract as salary).
# Strip leading/trailing pipe/dash/bullet/colon/whitespace runs, collapse
# internal whitespace.
_EDGE_JUNK_RE = re.compile(r"^[\s|·•\-–—:]+|[\s|·•\-–—:]+$")
# A title shorter than this after sanitizing is a mid-hydration placeholder
# (a virtualized card whose title link painted a single glyph — "T"/"C" in the
# live run), not a real posting — rejected on both /track and /harvest.
_MIN_TITLE_LEN = 3


def _sanitize_field(s) -> str:
    """Trim separator artifacts and collapse whitespace. Mirror of content.js
    sanitizeField (kept in lockstep). Tolerant of None/non-str."""
    if not s:
        return ""
    s = re.sub(r"\s+", " ", _EDGE_JUNK_RE.sub("", str(s)))
    return s.strip()


def _direct_slug(url: str) -> str:
    """Origin-rooted slug for a browser-only 'direct' save (S34): keep scheme +
    host + path, drop the query/fragment noise (the `?unit=mile&radius=50&page=1
    &search=1` a Vincere search URL carries), and drop a bare trailing slash so
    'https://careers.x.com/' and 'https://careers.x.com' dedup to one board.
    A `direct` entry's slug IS the URL the direct scraper fetches, so it must
    stay a clean, stable page URL."""
    from urllib.parse import urlsplit, urlunsplit
    u = url if "://" in url else "https://" + url
    p = urlsplit(u)
    # Drop the path entirely when it's a bare "/" (origin only), and strip a
    # trailing slash otherwise, so ".../careers/" and ".../careers" — and
    # "https://x.com/" and "https://x.com" — dedup to one board.
    path = (p.path or "").rstrip("/")
    return urlunsplit((p.scheme, p.netloc, path, "", ""))


def _direct_name(url: str) -> str:
    """Human name for a browser-only 'direct' board from its host: strip a
    leading www/careers/jobs label + the TLD (careers.acme.com -> 'Acme')."""
    from urllib.parse import urlsplit
    host = urlsplit(url if "://" in url else "https://" + url).netloc.lower()
    for pre in ("www.", "careers.", "jobs.", "apply."):
        if host.startswith(pre):
            host = host[len(pre):]
            break
    core = host.split(".")[0]
    return core.replace("-", " ").title() or host


@app.route("/status")
def status():
    return jsonify({"status": "ok", "port": PORT})


def _active_industry() -> str:
    """The active project's industry field (raw text, e.g. 'mechanical
    engineering'), '' if none. Tags clipped boards so the token-aware registry
    matcher (_industry_tag_match) surfaces them in this campaign's 'careers'
    searches — the same tag the '+ Add Companies' dialog writes from the active
    project. An empty industry saves the board UNTAGGED, which get_registry
    treats as visible to every search (company_registry: `not e.industries or
    ...`), so a keyless/eng-agnostic user's clip still shows up everywhere."""
    try:
        return (workspace.load_config().get("industry") or "").strip()
    except Exception:
        return ""


def _valid_browser_evidence(evidence):
    """Return a sanitized browser-evidence dict, or None when the evidence is
    absent/junk. Shape: {"job_count": int>=0|None, "via": "jsonld"|"dom",
    "page_url": str}. Defensive by contract (S33 SECURITY): evidence only ever
    upgrades a board's REACHABILITY — it can never influence ats_type/slug/name,
    which come solely from resolve_board(url). So we validate types strictly and
    treat anything malformed as 'no evidence' (fall back to today's behavior).

    A present-but-count-None evidence (the counting script ran but honestly
    couldn't count) is still valid evidence of a live page: `job_count` None is
    accepted, but a non-int / negative count is rejected as junk."""
    if not isinstance(evidence, dict):
        return None
    jc = evidence.get("job_count")
    # bool is an int subclass — reject True/False masquerading as a count.
    if jc is not None and (isinstance(jc, bool) or not isinstance(jc, int) or jc < 0):
        return None
    via = evidence.get("via")
    if via not in ("jsonld", "dom"):
        via = None
    page_url = evidence.get("page_url")
    if not isinstance(page_url, str):
        page_url = ""
    return {"job_count": jc, "via": via, "page_url": page_url}


def clip_board(url, page_title="", *, industry="", json_path=None, probe_fn=None,
               browser_evidence=None, vincere_probe=None):
    """Pure core of the /clip endpoint (HTTP-free, unit-testable).

    Resolve a clipped job-posting/board URL to its board root, probe it live,
    and — only if it verifies — persist it to the registry tagged with the
    active project's industry. Returns a verdict dict the extension renders:

        {"status": "added"|"duplicate"|"failed",
         "ats_type": str, "company": str, "slug": str,
         "live_count": int|None, "industry": str, "reason": str,
         "browser_only": bool}   # browser_only present only on a browser-verified add

    Verdict paths (P0-6, but stricter — a one-click clip never saves an
    unverified board; the whole value of clip-to-seed is that the user is on the
    *real* live board, so we can and must verify at clip time):

      * resolvable ATS board, probe live  -> "added"   (saved, tagged)
      * resolvable ATS board, already in registry (dedup by ats_type/slug or
        name) -> "duplicate" (nothing written)
      * resolvable ATS board, server probe FAILS but the caller supplied
        ``browser_evidence`` of a live page (S33) -> "added" reason=browser_verified,
        browser_only=True (saved with BROWSER_ONLY_FLAG: real+live from the user's
        browser, kept out of server scraping). This is the FedEx/Banner case —
        Cloudflare/CSRF-walled Workday tenants the server can't read (422) but the
        user's logged-in browser is looking at a live board full of jobs.
      * resolvable ATS board, probe fails, NO browser evidence -> "failed"
        reason=unreachable (NOT saved — exactly as today; an unreachable board
        with no browser proof is the dead slug the gate exists to keep out)
      * unresolvable page ('direct' fallback / junk / off-board) -> "failed"
        reason=unresolvable (NOT saved)

    SECURITY: server probe wins. A server-REACHABLE board saves normally
    (verified, scraped) and the browser evidence is ignored — evidence only ever
    upgrades REACHABILITY of a board whose identity (ats_type/slug/name) came
    from resolve_board(url); it never overrides resolution.

    S34 — honest fallback for an UNRECOGNIZED-but-live board: when the URL is
    unresolvable as a known ATS BUT the caller supplied valid ``browser_evidence``
    (the extension's "Verify from this tab" counting saw a live page), the board
    is saved as ats_type ``direct`` (slug = the origin-rooted page URL, query
    noise stripped) flagged BROWSER_ONLY, verdict added / browser_verified_direct.
    The app can't scrape it, so the popup tells the user to revisit it with the
    extension. The ToS-blocked-host guard runs BEFORE this (and before resolution
    and probing), so this can never seed a fetch target for a blocked host.

    ``probe_fn`` (defaults to ats_detect.probe_board), ``vincere_probe`` (the
    fingerprint probe resolve_board uses for URL-opaque Vincere boards; host->bool),
    and ``json_path`` are injectable so tests never touch the network or the real
    companies.json. ``browser_evidence`` is the sanitized dict from
    _valid_browser_evidence (the /clip route validates the raw POST body first)."""
    from scrape.ats_detect import (resolve_board, probe_board, ProbeResult,
                                   is_tos_blocked_host)
    from scrape.company_registry import (BROWSER_ONLY_FLAG, CompanyEntry,
                                         get_registry, is_browser_only,
                                         is_unverified, save_companies)
    if probe_fn is None:
        probe_fn = probe_board
    evidence = _valid_browser_evidence(browser_evidence)

    url = (url or "").strip()
    if not url or not _safe_http_url(
            url if "://" in url else "https://" + url):
        return {"status": "failed", "reason": "unresolvable", "ats_type": "",
                "company": "", "slug": "", "live_count": None,
                "industry": industry}

    # ToS/aggregator guard runs FIRST — before resolution, probing, OR the S34
    # browser-verified-direct fallback. A board on a ToS-blocked or aggregator
    # host (Indeed/LinkedIn/NEOGOV/…) can never legitimately enter the registry:
    # the direct scraper would issue a bare requests.get() against it with no
    # allowlist, and browser evidence must not be a backdoor around that. This
    # wins even over a would-be-Vincere page hosted on a blocked host.
    if is_tos_blocked_host(url if "://" in url else "https://" + url):
        return {"status": "failed", "reason": "tos_blocked", "ats_type": "",
                "company": "", "slug": "", "live_count": None,
                "industry": industry}

    board = resolve_board(url, page_title, vincere_probe=vincere_probe)
    ats, slug, company = board["ats_type"], board["slug"], board["name"]
    verdict = {"ats_type": ats, "company": company, "slug": slug,
               "live_count": None, "industry": industry}

    if not board["resolvable"]:
        # A generic careers page / search result / non-board page: we can't
        # resolve it to a probeable ATS board. S34 honest fallback: if the POST
        # carries valid browser evidence (the extension's "Verify from this tab"
        # counting saw a live page), don't dead-end — save it as a `direct`
        # BROWSER-ONLY board (a real, live page the app can't scrape) so the user
        # keeps it and can refresh it by browsing. The ToS-blocked-host guard
        # already ran above, so this can never seed a fetch target for a blocked
        # host. Without evidence, this is exactly today's failed/unresolvable.
        if evidence is not None:
            dslug = _direct_slug(url)
            # Name from the page title if the extension sent one, else derive it
            # from the host (careers.northwind.com -> "Northwind"). We ignore the
            # slug-derived board["name"] here — for an unresolvable 'direct' page
            # that's just the first host label ("Careers"), not the company.
            name = (page_title or "").strip() or _direct_name(dslug)
            entry = CompanyEntry(
                name=name, ats_type="direct", slug=dslug,
                industries=[industry] if industry else [],
                extra={BROWSER_ONLY_FLAG: True})
            live_count = evidence["job_count"]
            verdict.update(ats_type="direct", company=name, slug=dslug,
                           live_count=live_count)
            added = save_companies([entry], json_path=json_path)
            if added:
                verdict.update(status="added", reason="browser_verified_direct",
                               browser_only=True)
            else:
                verdict.update(status="duplicate", reason="already_in_registry")
            return verdict
        verdict.update(status="failed", reason="unresolvable")
        return verdict

    entry = CompanyEntry(name=company, ats_type=ats, slug=slug,
                         industries=[industry] if industry else [])

    # Duplicate re-clip: already in the registry by (ats_type, slug) or name?
    # save_companies would no-op it, but the user deserves an explicit
    # "already have this" rather than a silent "added 0". EXCEPTION (P0-6
    # re-verify): a stored board that is currently flagged UNVERIFIED is NOT a
    # dead-end duplicate — re-clipping means the user is on the real live board,
    # so we fall through to the live probe and let save_companies upgrade it
    # (clearing the flag) instead of reporting a misleading "duplicate" that
    # would leave it permanently unscraped.
    #
    # A stored BROWSER-ONLY board (S33), by contrast, IS a plain duplicate: it's
    # already saved as confirmed-real-but-unscrapeable, and a re-clip (even one
    # carrying fresh browser evidence) is not a SERVER read, so there's nothing to
    # upgrade — reporting "duplicate" is honest. (If the server-side wall later
    # comes down, a server-reachable re-clip below upgrades it via save_companies,
    # which clears BROWSER_ONLY_FLAG.)
    reclip_unverified = False
    for existing in get_registry(include_unverified=True, user_json=json_path):
        if ((existing.ats_type, existing.slug) == (ats, slug)
                or existing.name.lower() == company.lower()):
            if is_unverified(existing):
                reclip_unverified = True
                break
            verdict.update(status="duplicate", reason="already_in_registry")
            return verdict

    # Verify live at clip time. The default probe (ats_detect.probe_board) returns
    # a ProbeResult(count, reachable): reachable is True only when the board was
    # actually READ this probe. A resolvable ATS that can't be read — an
    # unreachable/uncountable board, OR a CSRF/Cloudflare-walled workday_cxs tenant
    # (HTTP 422) — is NOT saved: a one-click clip must land the user on a board we
    # can actually verify, and "verified" for a board the scraper can never read is
    # the exact dead-slug case this gate exists to keep out. A live board with 0
    # open jobs is reachable and IS saved.
    # `probe_fn` is injectable; accept either a ProbeResult or the legacy int|None
    # count contract so existing callers/tests keep working.
    result = probe_fn(entry)
    if isinstance(result, ProbeResult):
        reachable, count = result.reachable, result.count
    else:
        count = result
        reachable = count is not None
    if not reachable:
        # S33 browser-verified fallback: the SERVER can't read this board (a
        # Cloudflare/CSRF-walled Workday tenant — FedEx/Banner 422 the public
        # wday/cxs API), but the user's logged-in browser IS on a live board. If
        # the caller supplied browser evidence of a live page (a plausible
        # job_count, int >= 0, OR an honest count=None from a page that clearly
        # had postings), save the board flagged BROWSER_ONLY: a real, live
        # company kept out of server scraping (the extension refreshes it). The
        # server probe already failed here, so evidence never overrides a
        # server-reachable verdict — it only rescues the boards the wall blocks.
        if evidence is not None:
            entry.extra = dict(getattr(entry, "extra", None) or {})
            entry.extra[BROWSER_ONLY_FLAG] = True
            live_count = evidence["job_count"]
            verdict["live_count"] = live_count
            added = save_companies([entry], json_path=json_path)
            if added:
                verdict.update(status="added", reason="browser_verified",
                               browser_only=True)
            else:
                # Name/slug already present as a plain (server-verified or
                # browser-only) record — an honest duplicate, not a new save.
                verdict.update(status="duplicate", reason="already_in_registry")
            return verdict
        # No browser proof -> exactly today's behavior: a dead/unreachable slug.
        verdict.update(status="failed", reason="unreachable")
        return verdict

    verdict["live_count"] = count if count is not None else 0
    added = save_companies([entry], json_path=json_path)
    # `added` counts a fresh insert OR an unverified->verified upgrade; a
    # re-clip that cleared the flag is a "re-verified" success, not a duplicate.
    if added:
        reason = "re_verified" if reclip_unverified else "verified_live"
        verdict.update(status="added", reason=reason)
    else:
        verdict.update(status="duplicate", reason="already_in_registry")
    return verdict


@app.route("/clip", methods=["POST", "OPTIONS"])
def clip():
    """One-click 'Add this employer's board to my registry' from the browser.

    Body: {"url": <job-posting or board URL>, "page_title": <optional>}.
    Resolves the board root, verifies it's live, and saves it (tagged with the
    active project's industry) — or returns a clear failure verdict. Assisted,
    never auto: this ADDS A BOARD to the registry; it never applies or submits
    anything."""
    if request.method == "OPTIONS":
        return jsonify({}), 200

    # Same origin gate as /harvest: this writes to companies.json and probes the
    # network, so only our extension or a loopback caller may reach it.
    if not _origin_allowed(request.headers.get("Origin", "")):
        return jsonify({"error": "Forbidden origin"}), 403

    data = request.get_json(force=True, silent=True)
    # Coerce to str: a client sending a non-string url/page_title (e.g. a number
    # or null) must yield a clean 400/verdict, not a 500 from .strip() on a non-
    # string. get() default only covers an ABSENT key, not a present non-string.
    if not isinstance(data, dict) or not str(data.get("url") or "").strip():
        return jsonify({"error": "Expected JSON with a 'url'"}), 400

    # Optional S33 browser evidence: the extension's two-step "Verify from this
    # tab" re-POSTs with {"evidence": {job_count, via, page_url}} after counting
    # postings client-side. clip_board sanitizes it defensively (junk -> treated
    # as absent, so behavior is exactly as before). It only ever upgrades a
    # board's reachability; the origin gate above already restricts callers.
    verdict = clip_board(str(data.get("url") or ""),
                         str(data.get("page_title") or ""),
                         industry=_active_industry(),
                         browser_evidence=data.get("evidence"))
    # A failure to resolve/verify is a normal verdict, not a server error —
    # the extension renders {status: failed, reason: ...} the same way it
    # renders success. Keep HTTP 200 so the JS stays thin (no status-code
    # branching); the payload carries the outcome.
    print(f"[receiver] clip {verdict['status']} — {verdict.get('company') or '?'} "
          f"({verdict['ats_type'] or '?'}) reason={verdict.get('reason')}")
    return jsonify(verdict)


@app.route("/harvest", methods=["POST", "OPTIONS"])
def harvest():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    # Side effects below (report files, inbox writes, opening a browser tab) must
    # only run for our extension or a loopback caller. An origin-less or foreign
    # POST is rejected before any of that happens.
    if not _origin_allowed(request.headers.get("Origin", "")):
        return jsonify({"error": "Forbidden origin"}), 403

    data = request.get_json(force=True, silent=True)
    if not data or "jobs" not in data:
        return jsonify({"error": "Expected JSON with 'jobs' array"}), 400

    # Manual sends (the popup's Send button) open the HTML report in a browser
    # tab; the auto-send path passes open_report=false so a background flush
    # never throws a surprise tab up mid-scroll. Default True keeps manual
    # behavior unchanged for any caller that omits the flag.
    open_report = data.get("open_report", True) is not False

    raw_jobs = data["jobs"]
    if not isinstance(raw_jobs, list) or len(raw_jobs) == 0:
        return jsonify({"error": "No jobs received"}), 400

    results = [_to_job_result(j) for j in raw_jobs]
    results = [r for r in results if r is not None]

    if not results:
        return jsonify({"error": "No valid jobs could be parsed"}), 400

    today = date.today().isoformat()
    sources_used = sorted({r.source_api for r in results})
    search_params = {
        "date": today,
        "location": "Browser harvest",
        "keywords": ["(collected while browsing)"],
        "salary_min": None,
        "sources": sources_used,
    }

    html_path = workspace.output_dir() / f"browser_harvest_{today}.html"
    csv_path  = workspace.output_dir() / f"browser_harvest_{today}.csv"

    generate_html_report(results, html_path, search_params)
    generate_csv_report(results, csv_path)

    # Route harvested jobs into the same scored-inbox funnel as daily_run, so
    # browse-collected postings get triaged alongside API results instead of
    # living only in this one-off report. No min-score floor: the user picked
    # these by hand while browsing. (Note: descriptions are empty — card
    # scraping can't see the posting body — so the skill component scores 0
    # and the Claude fit prompt is the better ranking signal for these.)
    inboxed = 0
    try:
        from match.scorer import score_jobs
        from search.cli import load_user_config
        from search.keyword_strategy import effective_keywords
        from tracker.db import inbox_add_many, init_db
        cfg = load_user_config()
        try:
            import preferences
            _hard = preferences.load().get("hard", {})
            remote_ok = bool(_hard.get("remote_ok", True))
            remote_regions_ok = bool(_hard.get("remote_regions_ok", False))
        except Exception:
            remote_ok = True
            remote_regions_ok = False
        scored = score_jobs(
            results,
            # Use the project's EFFECTIVE keywords (industry-derived for a non-eng
            # field), not the engineering DEFAULT_KEYWORDS -- a browser harvest for
            # a nurse was being scored against controls-engineer terms. (P3)
            keywords=effective_keywords(cfg),
            location=cfg.get("location") or "",
            salary_floor=cfg.get("salary_min"),
            exclude_keywords=cfg.get("exclude_keywords", []),
            exclude_titles=cfg.get("exclude_titles"),
            title_miss_penalty=cfg.get("title_miss_penalty"),
            seniority_exclude=cfg.get("seniority_exclude"),
            remote_ok=remote_ok,
            seniority_target=cfg.get("seniority_target"),
            years_cap=cfg.get("years_cap"),
            remote_regions_ok=remote_regions_ok,
            title_context_required=cfg.get("title_context_required"),
        )
        init_db()
        inboxed = inbox_add_many(scored)
    except Exception as e:
        # The report already saved; a scoring/DB hiccup shouldn't lose the run.
        print(f"[receiver] inbox routing failed - {e}")

    if open_report:
        webbrowser.open(html_path.as_uri())

    _bump_capture(len(results))
    print(f"\n[receiver] {len(results)} jobs received -> {html_path.name} "
          f"({inboxed} new to inbox)")

    return jsonify({
        "received": len(results),
        "inboxed": inboxed,
        "html": str(html_path),
        "csv":  str(csv_path),
    })


@app.route("/track", methods=["POST", "OPTIONS"])
def track():
    """Add the popup's collected jobs straight into the tracker as 'interested',
    so a general user never needs the separate `py -m tracker.app` (port 5001)
    server running. Body: {"jobs": [...]} in the SAME job-dict shape as /harvest.

    Writes to the tracker DB via the tracker's own add path (tracker.db.add_job,
    exactly what tracker.app's /api/add uses) — no hand-rolled SQL. Per the
    embedded-receiver rule (module comment): this resolves the ACTIVE project
    per-request (init_db opens the active project's DB) and takes NO process-wide
    pin, so tracked jobs land in the project the user is looking at. Returns
    {added, failed}."""
    if request.method == "OPTIONS":
        return jsonify({}), 200

    # Same origin gate as /harvest — this mutates the tracker DB, so an
    # origin-less or foreign POST is rejected before any row is written.
    if not _origin_allowed(request.headers.get("Origin", "")):
        return jsonify({"error": "Forbidden origin"}), 403

    data = request.get_json(force=True, silent=True)
    if not data or "jobs" not in data:
        return jsonify({"error": "Expected JSON with 'jobs' array"}), 400

    raw_jobs = data["jobs"]
    if not isinstance(raw_jobs, list) or len(raw_jobs) == 0:
        return jsonify({"error": "No jobs received"}), 400

    from tracker.db import add_job, init_db, url_is_tracked
    init_db()  # resolve + migrate the ACTIVE project's DB per-request (no pin)

    added = 0
    failed = 0
    skipped = 0
    for j in raw_jobs:
        if not isinstance(j, dict):
            failed += 1
            continue
        # Sanitize the same way the extension does (defense in depth: a stale
        # client version, or a hand-rolled caller, can't slip a "GrayMatter |"
        # row through). A degenerate title ("T") is rejected, not filed.
        title = _sanitize_field(j.get("title"))
        company = _sanitize_field(j.get("company"))
        # Mirror tracker.app /api/add: title+company are the minimum to file a
        # row, plus a min-title floor so a mid-hydration 1-char placeholder can't
        # enter the tracker.
        if len(title) < _MIN_TITLE_LEN or not company:
            failed += 1
            continue
        url = str(j.get("url") or "").strip()
        # Dedup: the applications table has no UNIQUE norm_url, so re-tracking the
        # same posting (e.g. 'Track All' pressed twice) would insert a duplicate
        # row. Skip a URL that's already tracked — mirrors /harvest's inbox dedup.
        if url and url_is_tracked(url):
            skipped += 1
            continue
        try:
            add_job(
                title=title,
                company=company,
                location=_sanitize_field(j.get("location")),
                url=url,
                salary_text=str(j.get("salary_text") or "").strip(),
                source=j.get("source", "browser"),
                status="interested",
            )
            added += 1
        except Exception as e:
            print(f"[receiver] track: failed to add '{title}' — {e}")
            failed += 1

    print(f"[receiver] track: {added} added, {failed} failed, {skipped} skipped")
    return jsonify({"added": added, "failed": failed, "skipped": skipped})


def _to_job_result(j) -> JobResult | None:
    if not isinstance(j, dict):
        return None
    # Sanitize + min-title guard, mirroring /track and the extension, so a
    # degenerate "T" card or a "…Engineer |" artifact can't reach the inbox
    # regardless of client version.
    title = _sanitize_field(j.get("title"))
    url   = (j.get("url")   or "").strip()
    if len(title) < _MIN_TITLE_LEN or not url or not _safe_http_url(url):
        return None

    company  = _sanitize_field(j.get("company"))
    location = _sanitize_field(j.get("location"))
    source   = j.get("source", "browser")

    salary_min = j.get("salary_min")
    salary_max = j.get("salary_max")

    # Fallback: try to parse salary from text if numerics weren't sent
    if salary_min is None:
        salary_min, salary_max = _parse_salary(j.get("salary_text", ""))

    # The detail pass forwards the real posting body — populate it so harvested
    # jobs score honestly (the 25-pt skill component is no longer always 0) and
    # skill-gap / comp / ghost in the inbox detail pane have something to work on.
    description = (j.get("description") or "").strip()

    # Parse the raw detail blob (employment type, work mode, seniority,
    # applicants, posted age, easy-apply) + the card's footer text (Promoted,
    # posted age) — one server-side parser, like salary.
    detail_blob = "\n".join(
        s for s in (j.get("details_text"), j.get("card_text")) if s
    )
    meta = parse_details(detail_blob)
    promoted = bool(re.search(r"\bpromoted\b", j.get("card_text") or "", re.I))
    external_id = (j.get("external_id") or "").strip()

    # `created` drives recency + ghost staleness. Prefer the posting's real age
    # (derived from "N days ago") over the capture timestamp, which would make
    # every browsed job look brand-new and defeat the staleness advisory.
    created = j.get("captured_at") or datetime.now(timezone.utc).isoformat()
    age_iso = _created_from_age(meta.get("posted_age_days"))
    if age_iso:
        created = age_iso
    # An explicit ISO `posted_iso` (schema.org JobPosting datePosted, forwarded by
    # the generic JSON-LD capture path) is the strongest signal — an exact posting
    # date beats both the capture timestamp and a coarse "N days ago" derivation —
    # so it wins the precedence when present and parseable.
    dated_iso = _iso_date_prefix(j.get("posted_iso"))
    if dated_iso:
        created = dated_iso

    uid = hashlib.md5(url.encode()).hexdigest()[:10]
    job_id = f"browser_{uid}"

    jr = JobResult(
        title=title,
        company=company,
        location=location,
        salary_min=salary_min,
        salary_max=salary_max,
        description=description,
        url=url,
        source_keyword="(browser harvest)",
        created=created,
        job_id=job_id,
        source_api=f"{source}_browser",
    )

    # Rich, schema-free metadata rides the inbox row's `extras` JSON (under a
    # "browse" key) — surfaced in the Inbox detail pane, never folded into the
    # honest 0-100 score. inbox_add_many stamps `_extras` at insert.
    browse = {k: v for k, v in {
        "work_mode": meta.get("work_mode"),
        "employment_type": meta.get("employment_type"),
        "seniority": meta.get("seniority"),
        "applicants": meta.get("applicants"),
        "posted_age_days": meta.get("posted_age_days"),
        "easy_apply": meta.get("easy_apply") or None,
        "promoted": promoted or None,
        "external_id": external_id or None,
        "detailed": bool(j.get("detailed")) or None,
    }.items() if v not in (None, "", False)}
    if browse:
        jr._extras = {"browse": browse}
    return jr


# Hourly only when a rate unit is actually attached to a number — anchored so
# stray "hr"/"hour" substrings in company/location text ("Pittsburgh", "Amherst",
# "HR Manager") can't trigger the x2080 annualization on real salaries.
_HOURLY_RE = re.compile(r"(?:/|\bper\s+)\s*(?:hr|hour)\b|\bhourly\b|/hr\b", re.I)
_MONEY = r"\$\s*\d[\d,]*(?:\.\d+)?\s*[Kk]?"
_MONEY_RE = re.compile(_MONEY)
# Prefer an explicit salary phrase over "first two $ in the blob": a ranged
# "$X - $Y" (en/em dash or 'to'), or a single amount carrying a period unit
# ("$X/yr", "$X a year", "$X per hour"). A promo/bonus "$" earlier in a card
# blob no longer hijacks the numbers because we anchor on these shapes first.
_RANGE_RE = re.compile(
    rf"({_MONEY})\s*(?:-|–|—|\bto\b)\s*({_MONEY})", re.I
)
_PERIOD = r"(?:/\s*(?:yr|hr|hour|year|mo|month)\b|\bper\b|\ba\s+(?:year|month|hour)\b|\bannually\b|\bannual\b)"
_SINGLE_PERIOD_RE = re.compile(rf"({_MONEY})\s*{_PERIOD}", re.I)


def _money_to_float(token: str, hourly: bool):
    n = token.replace("$", "").replace(",", "").replace(" ", "")
    try:
        if n[-1:].lower() == "k":
            return float(n[:-1]) * 1000
        val = float(n)
        if hourly and val < 500:  # looks like an hourly rate -> annualize
            val *= 2080
        return val
    except ValueError:
        return None


def _parse_salary(text: str):
    """Single source of truth for salary text -> (min, max) annual floats.
    The browser extension sends raw ``salary_text`` and lets this parse it, so
    the JS side no longer maintains a divergent numeric parser."""
    if not text:
        return None, None
    hourly = bool(_HOURLY_RE.search(text))

    # 1) Explicit ranged phrase wins ("$X - $Y" / "$X to $Y").
    m = _RANGE_RE.search(text)
    if m:
        lo = _money_to_float(m.group(1), hourly)
        hi = _money_to_float(m.group(2), hourly)
        if lo is not None and hi is not None:
            return lo, hi

    # 2) Single amount with a period unit ("$X/yr", "$X a year", "$X per hour").
    m = _SINGLE_PERIOD_RE.search(text)
    if m:
        val = _money_to_float(m.group(1), hourly)
        if val is not None:
            return val, None

    # 3) Fallback: first two bare $ amounts in the blob.
    parsed = []
    for token in _MONEY_RE.findall(text):
        val = _money_to_float(token, hourly)
        if val is not None:
            parsed.append(val)
    if len(parsed) >= 2:
        return parsed[0], parsed[1]
    if len(parsed) == 1:
        return parsed[0], None
    return None, None


# ── Detail-pane field extraction (one source of truth, like salary) ────────────
# The extension forwards the open job's full description plus a raw "details"
# blob (the LinkedIn/Indeed top-card metadata). The JS just grabs containers;
# all field extraction lives here so the two sides can't drift.
_WORK_MODE_RE = re.compile(r"\b(remote|hybrid|on-?site|in[- ]office)\b", re.I)
_EMP_TYPE_RE = re.compile(
    r"\b(full[- ]?time|part[- ]?time|contract|internship|temporary|freelance|volunteer)\b",
    re.I,
)
_SENIORITY_RE = re.compile(
    r"\b(internships?|entry[- ]level|associate|mid[- ]senior level|director|executive)\b",
    re.I,
)
# "47 applicants", "Over 200 applicants", "Be among the first 25 applicants".
_APPLICANTS_RE = re.compile(r"(?:over\s+)?(\d[\d,]*)\s*\+?\s*applicant", re.I)
_FIRST_N_RE = re.compile(r"first\s+(\d+)\s+applicant", re.I)
# Relative posting age: "3 days ago", "2 weeks ago", "30+ days ago", "1 hour ago".
_AGE_RE = re.compile(r"(\d+)\s*\+?\s*(hour|day|week|month)s?\s+ago", re.I)
_EASY_RE = re.compile(r"easy apply|easily apply|indeed apply", re.I)
_AGE_UNIT_DAYS = {"hour": 0, "day": 1, "week": 7, "month": 30}


def _canon_work_mode(s: str) -> str:
    s = s.lower().replace("-", "").replace(" ", "")
    if s.startswith("remote"):
        return "Remote"
    if s.startswith("hybrid"):
        return "Hybrid"
    return "On-site"  # onsite / inoffice


def _canon_emp(s: str) -> str:
    s = s.lower().replace("-", "").replace(" ", "")
    return {
        "fulltime": "Full-time", "parttime": "Part-time", "contract": "Contract",
        "internship": "Internship", "temporary": "Temporary",
        "freelance": "Freelance", "volunteer": "Volunteer",
    }.get(s, s.title())


def _canon_seniority(s: str) -> str:
    s = s.lower()
    if "intern" in s:
        return "Internship"
    if "entry" in s:
        return "Entry level"
    if "associate" in s:
        return "Associate"
    if "mid" in s:
        return "Mid-Senior level"
    if "director" in s:
        return "Director"
    if "executive" in s:
        return "Executive"
    return ""


def parse_details(text: str) -> dict:
    """Extract structured fields from the detail blob. All keys always present;
    values default to ''/None/False when not found."""
    out = {"work_mode": "", "employment_type": "", "seniority": "",
           "applicants": None, "posted_age_days": None, "easy_apply": False}
    if not text:
        return out
    m = _WORK_MODE_RE.search(text)
    if m:
        out["work_mode"] = _canon_work_mode(m.group(1))
    m = _EMP_TYPE_RE.search(text)
    if m:
        out["employment_type"] = _canon_emp(m.group(1))
    m = _SENIORITY_RE.search(text)
    if m:
        out["seniority"] = _canon_seniority(m.group(1))
    m = _APPLICANTS_RE.search(text) or _FIRST_N_RE.search(text)
    if m:
        try:
            out["applicants"] = int(m.group(1).replace(",", ""))
        except ValueError:
            pass
    # Take the smallest (most recent) age mentioned.
    days = None
    for n, unit in _AGE_RE.findall(text):
        d = int(n) * _AGE_UNIT_DAYS[unit.lower()]
        days = d if days is None else min(days, d)
    out["posted_age_days"] = days
    out["easy_apply"] = bool(_EASY_RE.search(text))
    return out


def _created_from_age(days):
    """An ISO date `days` before today, or None — so a browsed job's recency +
    staleness reflect the real posting age, not the moment it was scraped."""
    if days is None:
        return None
    from datetime import timedelta
    return (date.today() - timedelta(days=days)).isoformat()


# schema.org datePosted is ISO-8601, but real feeds carry it as "2026-06-30",
# "2026-06-30T09:00:00Z", "2026-06-30T09:00:00+02:00", or occasionally junk.
# We only need the calendar day for recency/staleness, so accept a leading
# YYYY-MM-DD and validate it's a real date; anything else falls back gracefully
# (caller keeps the capture timestamp / age-derived date).
_ISO_DATE_RE = re.compile(r"^\s*(\d{4})-(\d{2})-(\d{2})")


def _iso_date_prefix(value):
    """Return 'YYYY-MM-DD' from an ISO-8601 datePosted string, or None. Tolerant
    of a time/zone suffix and of junk (a non-date, an int, None) — never raises."""
    if not isinstance(value, str):
        return None
    m = _ISO_DATE_RE.match(value)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
    except ValueError:
        return None  # e.g. 2026-13-40 — a well-shaped but impossible date


# ── in-process embedding (GUI Tools toggle) ────────────────────────────────────
# The receiver was `py -m scrape.browser_receiver` only — dead in the frozen exe.
# start_in_thread() runs the SAME Flask app as a daemon thread inside the GUI
# process. IN-PROCESS RULE (review-fleet critical): the embedded receiver must
# NEVER take the process-wide workspace pin — the GUI owns that process, and a
# receiver pin silently overrides the project switcher for EVERY tab (the exact
# S27 cross-project misrouting it meant to prevent). Embedded captures therefore
# resolve per-request and land in the CURRENTLY ACTIVE project — i.e. the one
# the user is looking at, which is also the least surprising behavior. The
# standalone `py -m scrape.browser_receiver` process (which owns its whole
# process) pins at startup in __main__ instead. capture_count() surfaces how
# many jobs have been received so the GUI can show a live count.
import socket as _socket
import threading as _threading

_SERVER_THREAD = None
_CAPTURE_COUNT = 0


def capture_count() -> int:
    """Total jobs received since this process's receiver started."""
    return _CAPTURE_COUNT


def is_running() -> bool:
    return _SERVER_THREAD is not None and _SERVER_THREAD.is_alive()


def _bump_capture(n: int) -> None:
    global _CAPTURE_COUNT
    _CAPTURE_COUNT += int(n or 0)


def start_in_thread(project_slug=None):
    """Start the receiver as a daemon thread INSIDE the GUI process. Idempotent:
    a second call while already running is a no-op. Embedded captures resolve
    per-request to the CURRENTLY ACTIVE project (see the module comment — the
    embedded receiver must never take the process-wide pin, or it hijacks the
    GUI's project switcher). *project_slug* is accepted for signature stability
    but only informs the caller's UI copy. Returns the server thread."""
    global _SERVER_THREAD
    if is_running():
        return _SERVER_THREAD

    def _serve():
        app.run(host=HOST, port=PORT, debug=False, use_reloader=False)

    t = _threading.Thread(target=_serve, name="browser-receiver", daemon=True)
    t.start()
    _SERVER_THREAD = t
    return t


def wait_until_listening(timeout: float = 3.0) -> bool:
    """True once the receiver socket accepts connections, False after *timeout*.
    Lets the GUI distinguish 'capture is ON' from 'the daemon thread died on a
    port bind failure' (e.g. a second GUI instance already holds the port)."""
    import time as _time
    deadline = _time.monotonic() + timeout
    while _time.monotonic() < deadline:
        try:
            with _socket.create_connection((HOST, PORT), timeout=0.25):
                return True
        except OSError:
            if _SERVER_THREAD is not None and not _SERVER_THREAD.is_alive():
                return False  # thread already died (bind failure) — no point waiting
            _time.sleep(0.1)
    return False


if __name__ == "__main__":
    # Standalone process: the receiver OWNS this process, so pin once at startup
    # (the mcp_server/daily_run pattern) — a GUI project switch in another
    # process must not redirect this receiver's inbox writes mid-session.
    workspace.pin_active(workspace.active_slug())
    print(f"Job Harvester receiver running on http://{HOST}:{PORT}")
    print("Load the browser extension, browse LinkedIn/Indeed, then click 'Send to Tool'.\n")
    app.run(host=HOST, port=PORT, debug=False)
