"""Breadth regression floor — pins two numbers so JobScout's "wide net" can't
silently shrink in a future PR.

Design philosophy (docs/KNOWN_ISSUES.md, CLAUDE.md): inclusion over precision —
get as many potential jobs in front of the user as possible and let the user do
the final dropping. Two levers quietly control how wide that net is: (1) how
many sources work with ZERO API keys configured (a fresh install/friend's copy
with no keys still gets real breadth from these), and (2) the size of the
starter companies.json registry the careers/ATS-discovery source scrapes. If
either number ever drops, it means a source silently became key-gated (or was
removed) or the starter registry was trimmed — both are breadth regressions
that deserve a deliberate decision, not a silent PR. This module is the
standing CI tripwire for both (docs/KNOWN_ISSUES.md "Zero-key regression
floor", follow-up to finding #8).
"""
from pathlib import Path

import config
from search import cli

REPO_ROOT = Path(__file__).resolve().parent.parent

# Sources that self-report a missing FREE key (raise ValueError during
# construction, or register then self-skip via a `keyless()` predicate) when
# NO credentials are configured. Computed against cli.ALL_SOURCES with a
# zero-key environment (see `zero_key_env` fixture below) as of this writing:
# adzuna, jsearch, usajobs, careeronestop, jooble, careerjet, serpapi (7 of the
# 24 registered sources). Everything else in ALL_SOURCES needs no key at all.
#
# THE FLOOR: 17 keyless-usable sources. This is the CURRENT count, hardcoded
# deliberately — if a future change makes one of today's free sources require
# a key (or removes a keyless source outright) without adding a replacement,
# this number goes down and the test FAILS. That failure is the point: it
# forces a conscious decision ("is this breadth loss acceptable?") instead of
# a silent shrink. Raising the floor (adding a new keyless source) is
# encouraged and just means bumping this constant up.
MIN_KEYLESS_SOURCES = 17

# companies.json ships as the starter ATS-discovery seed registry (tracked in
# git, CLAUDE.md: "companies.json IS tracked (ships as starter registry)").
# Floor mirrors docs/KNOWN_ISSUES.md's "N keyless sources / companies.json >=
# 400" suggestion — pin the CURRENT size as a floor so the seeded list can only
# grow, never silently shrink.
MIN_COMPANIES = 400


def _clear_all_key_signals(monkeypatch, tmp_path):
    """Zero out every credential JobScout's key-gated sources can read, using
    the SAME mechanics as tests/search/test_keyless_skip_surfacing.py's
    `keyless_env` fixture (env delenv + fresh empty SECRETS_DIR), PLUS the two
    sources (jsearch, serpapi) whose key is a frozen module-level constant
    read at import time rather than resolved live via config.resolve_secret —
    those need their owning module's attribute patched directly or a real
    .env-configured key on the machine running this test would mask them as
    non-keyless and silently deflate the count this test is pinning."""
    monkeypatch.setattr(config, "SECRETS_DIR", tmp_path / "secrets")
    for var in ("ADZUNA_APP_ID", "ADZUNA_APP_KEY", "USAJOBS_API_KEY",
                "USAJOBS_EMAIL", "USAJOBS_USER_AGENT", "JOOBLE_API_KEY",
                "CAREERJET_AFFID", "CAREERONESTOP_USER_ID", "CAREERONESTOP_TOKEN",
                "JSEARCH_RAPIDAPI_KEY", "SERPAPI_KEY"):
        monkeypatch.delenv(var, raising=False)

    import search.jsearch_client as jsearch_client
    monkeypatch.setattr(jsearch_client, "JSEARCH_RAPIDAPI_KEY", None)

    import search.serpapi_client as serpapi_client
    monkeypatch.setattr(serpapi_client, "SERPAPI_KEY", None)
    monkeypatch.setattr(serpapi_client.config, "SECRETS_DIR", tmp_path / "secrets")


def test_keyless_source_floor_does_not_shrink(monkeypatch, tmp_path):
    """With every key/credential wiped, build_clients() over the FULL
    cli.ALL_SOURCES list must still register at least MIN_KEYLESS_SOURCES
    sources. This is the "breadth can't silently shrink" tripwire: a PR that
    quietly moves a free source behind a required key (or deletes one without
    replacement) drops this count and fails the build."""
    _clear_all_key_signals(monkeypatch, tmp_path)

    skipped_keyless: list[str] = []
    clients = cli.build_clients(
        cli.ALL_SOURCES,
        cache_enabled=False,
        skipped_keyless=skipped_keyless,
        industry_filter=None,
    )
    keyless_usable = sorted(set(cli.ALL_SOURCES) - set(skipped_keyless))

    assert len(keyless_usable) >= MIN_KEYLESS_SOURCES, (
        f"Only {len(keyless_usable)} of {len(cli.ALL_SOURCES)} sources are "
        f"usable with zero keys configured (floor={MIN_KEYLESS_SOURCES}); "
        f"keyless-usable={keyless_usable}, key-gated={sorted(skipped_keyless)}. "
        "A source moved behind a required key, or was removed, without a "
        "replacement — see docs/KNOWN_ISSUES.md 'Zero-key regression floor'."
    )
    # Sanity: the registered clients list itself isn't hollow (every keyless
    # source that self-reports usable actually produced a live client object).
    assert len(clients) >= MIN_KEYLESS_SOURCES


def test_companies_json_floor_does_not_shrink():
    """The starter companies.json seed registry (tracked in git, ships with
    every install) must keep at least MIN_COMPANIES entries under its
    "companies" key. Shrinking this list silently narrows the careers/
    ATS-discovery source's reach for every user who hasn't customized it."""
    import json
    data = json.loads((REPO_ROOT / "companies.json").read_text(encoding="utf-8"))
    companies = data["companies"]
    assert isinstance(companies, list)
    assert len(companies) >= MIN_COMPANIES, (
        f"companies.json has only {len(companies)} entries "
        f"(floor={MIN_COMPANIES}) — the starter registry shrank."
    )
