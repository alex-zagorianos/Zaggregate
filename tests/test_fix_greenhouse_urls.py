"""Repair existing inbox rows: rewrite Greenhouse links to the server-rendered
hosted application URL (built from slug + id)."""
import sqlite3

from scripts.fix_greenhouse_urls import fix


def _seed(db_path, rows):
    """rows = list of (norm_url, company, url, source)."""
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE inbox (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "norm_url TEXT UNIQUE NOT NULL, title TEXT DEFAULT '', company TEXT, "
        "url TEXT, source TEXT)"
    )
    for nu, company, url, source in rows:
        conn.execute(
            "INSERT INTO inbox (norm_url, company, url, source) VALUES (?,?,?,?)",
            (nu, company, url, source),
        )
    conn.commit()
    conn.close()


def _urls(db_path):
    conn = sqlite3.connect(str(db_path))
    out = {r[0]: r[1] for r in conn.execute("SELECT company, url FROM inbox")}
    conn.close()
    return out


# company -> greenhouse slug, so a gh_jid embed (no slug in the URL) is resolvable.
_RESOLVE = {"nuro": "nuro", "acme": "acme"}.get


def test_rewrites_company_embed_gh_jid(tmp_path):
    db = tmp_path / "t.db"
    _seed(db, [
        ("nuro.ai/careersitem?gh_jid=6916236", "Nuro",
         "https://nuro.ai/careersitem?gh_jid=6916236", "careers"),
    ])
    fixed, skipped, dropped = fix(db_path=db, resolve_slug=_RESOLVE)
    assert fixed == 1
    assert _urls(db)["Nuro"] == (
        "https://job-boards.greenhouse.io/embed/job_app?for=nuro&token=6916236"
    )


def test_rewrites_hosted_board_path(tmp_path):
    db = tmp_path / "t.db"
    _seed(db, [
        ("boards.greenhouse.io/acme/jobs/123", "Acme",
         "https://boards.greenhouse.io/acme/jobs/123", "careers"),
    ])
    fixed, _, _ = fix(db_path=db, resolve_slug=_RESOLVE)
    assert fixed == 1
    assert _urls(db)["Acme"] == (
        "https://job-boards.greenhouse.io/embed/job_app?for=acme&token=123"
    )


def test_idempotent_and_leaves_non_greenhouse(tmp_path):
    db = tmp_path / "t.db"
    _seed(db, [
        ("job-boards.greenhouse.io/embed/job_app?for=acme&token=1", "Done",
         "https://job-boards.greenhouse.io/embed/job_app?for=acme&token=1", "careers"),
        ("jobs.lever.co/acme/a1", "Lever",
         "https://jobs.lever.co/acme/a1", "careers"),
        ("nuro.ai/careersitem?gh_jid=9", "Unknownco",   # slug not resolvable
         "https://nuro.ai/careersitem?gh_jid=9", "careers"),
    ])
    fixed, skipped, dropped = fix(db_path=db, resolve_slug=lambda c: None if "unknown" in c else {"nuro": "nuro"}.get(c))
    assert fixed == 0
    assert skipped == 3           # already-embed, non-greenhouse, unresolvable
    urls = _urls(db)
    assert urls["Lever"] == "https://jobs.lever.co/acme/a1"


def test_collapses_duplicate_into_existing(tmp_path):
    db = tmp_path / "t.db"
    _seed(db, [
        # canonical row already present
        ("job-boards.greenhouse.io/embed/job_app?for=nuro&token=5", "Nuro-canon",
         "https://job-boards.greenhouse.io/embed/job_app?for=nuro&token=5", "careers"),
        # stale embed of the SAME posting -> would collide on rewrite
        ("nuro.ai/careersitem?gh_jid=5", "Nuro-stale",
         "https://nuro.ai/careersitem?gh_jid=5", "careers"),
    ])
    fixed, skipped, dropped = fix(db_path=db, resolve_slug=lambda c: "nuro")
    assert dropped == 1
    # the stale duplicate is gone; the canonical row remains
    assert set(_urls(db)) == {"Nuro-canon"}
