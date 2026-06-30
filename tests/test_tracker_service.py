"""Tests for tracker/service.py — the intent-verb service layer the GUI calls
instead of reaching into tracker.db directly. Exercised against a temp DB."""
import pytest

import tracker.db as db
import tracker.service as svc
from models import JobResult


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "tracker.db")
    db.init_db()
    return db.DB_PATH


def _job(title="Controls Engineer", company="Acme", url="https://x.com/1",
         score=70):
    return JobResult(
        title=title, company=company, location="Cincinnati, OH",
        salary_min=90000, salary_max=120000, description="A controls role.",
        url=url, source_keyword="controls", created="2026-06-01",
        source_api="adzuna", score=score)


# ── tracker mutations ─────────────────────────────────────────────────────────

def test_add_update_status_get(tmp_db):
    jid = svc.add_manual_job(title="Eng", company="Acme",
                             location="Cincinnati")
    assert svc.get_job(jid)["title"] == "Eng"
    svc.set_status(jid, "applied")
    assert svc.get_job(jid)["status"] == "applied"
    svc.update_job(jid, salary_text="$100k")
    assert svc.get_job(jid)["salary_text"] == "$100k"
    assert svc.counts()["all"] == 1
    assert svc.list_jobs("applied")[0]["id"] == jid


def test_archive_restore_delete(tmp_db):
    jid = svc.add_manual_job(title="Eng", company="Acme")
    svc.archive_job(jid)
    assert svc.counts()["archived"] == 1
    assert svc.list_jobs() == []  # hidden from active view
    svc.restore_job(jid)
    assert svc.counts()["archived"] == 0
    svc.delete_job(jid)
    assert svc.get_job(jid) is None


# ── inbox triage ──────────────────────────────────────────────────────────────

def test_track_job_promotes_inbox_row(tmp_db):
    db.inbox_add_many([_job(url="https://x.com/inbox/1")])
    rows = svc.list_inbox()
    assert svc.inbox_size() == 1
    app_id = svc.track_job(rows[0]["id"])
    assert app_id is not None
    assert svc.inbox_size() == 0
    job = svc.get_job(app_id)
    assert job["status"] == "interested"
    assert job["company"] == "Acme"


def test_dismiss_job_hides_url(tmp_db):
    db.inbox_add_many([_job(url="https://x.com/inbox/2")])
    rows = svc.list_inbox()
    svc.dismiss_job(rows[0]["id"])
    assert svc.inbox_size() == 0
    assert db.normalize_url("https://x.com/inbox/2") in svc.seen_urls()


def test_set_inbox_fit(tmp_db):
    db.inbox_add_many([_job(url="https://x.com/inbox/3")])
    rid = svc.list_inbox()[0]["id"]
    svc.set_inbox_fit(rid, 88, "great match")
    row = next(r for r in svc.list_inbox() if r["id"] == rid)
    assert row["fit"] == 88
    assert row["fit_why"] == "great match"


# ── search-side dedup + track ─────────────────────────────────────────────────

def test_dedup_new_jobs_filters_seen(tmp_db):
    svc.add_manual_job(title="Old", company="Acme", url="https://x.com/seen/1")
    jobs = [_job(url="https://x.com/seen/1"),       # already tracked
            _job(url="https://x.com/fresh/2")]
    new, skipped = svc.dedup_new_jobs(jobs)
    assert skipped == 1
    assert len(new) == 1 and new[0].url == "https://x.com/fresh/2"


def test_track_search_results_adds_and_skips(tmp_db):
    db.dismiss_url("https://x.com/dismissed/9")
    jobs = [_job(url="https://x.com/dismissed/9"),  # dismissed -> skip
            _job(title="New Role", company="Beta", url="https://x.com/new/10")]
    added, skipped = svc.track_search_results(jobs)
    assert added == 1 and skipped == 1
    tracked = svc.list_jobs("interested")
    assert any(j["company"] == "Beta" for j in tracked)


# ── fit-scoring bridge ────────────────────────────────────────────────────────

def test_fit_prompt_for_rows_returns_prompt_and_jobs(tmp_db):
    db.inbox_add_many([_job(url="https://x.com/p/1"),
                       _job(title="Mech Eng", company="Beta",
                            url="https://x.com/p/2")])
    rows = svc.list_inbox()
    prompt, jobs = svc.fit_prompt_for_rows(rows)
    assert isinstance(prompt, str) and "CANDIDATE PROFILE" in prompt
    # Each rebuilt JobResult carries its inbox row id so token-verified scores
    # can be written back to the right row.
    assert [j.job_id for j in jobs] == [str(r["id"]) for r in rows]
    # Salary text is prepended into the description so a rebuilt JobResult
    # doesn't report "Not listed".
    assert "Salary:" in prompt


def test_unscored_inbox_rows_caps_per_company(tmp_db):
    rows = [
        {"id": 1, "company": "MegaCorp", "fit": -1},
        {"id": 2, "company": "MegaCorp", "fit": -1},
        {"id": 3, "company": "MegaCorp", "fit": -1},  # 3rd from same co -> dropped
        {"id": 4, "company": "Beta", "fit": -1},
        {"id": 5, "company": "Gamma", "fit": 80},     # already scored -> dropped
    ]
    picked = svc.unscored_inbox_rows(rows, per_company=2)
    ids = [r["id"] for r in picked]
    assert ids == [1, 2, 4]


def test_score_inbox_from_reply_writes_token_verified(tmp_db):
    """End-to-end: build a real prompt, build a reply echoing each job's token,
    score back. Scores must land on the right row even when the reply reorders
    the jobs (token-verified, not positional)."""
    from claude_bridge import fit_token
    db.inbox_add_many([_job(url="https://x.com/a/1"),
                       _job(title="B", company="Beta", url="https://x.com/a/2")])
    rows = svc.list_inbox()
    _prompt, jobs = svc.fit_prompt_for_rows(rows)
    # Reply is REVERSED vs prompt order, but each entry echoes its token.
    reply = (
        f'[{{"i": 2, "token": "{fit_token(jobs[1])}", "fit": 55, '
        f'"why": "ok", "flags": "contract"}},'
        f' {{"i": 1, "token": "{fit_token(jobs[0])}", "fit": 91, '
        f'"why": "strong", "flags": ""}}]'
    )
    applied = svc.score_inbox_from_reply(jobs, reply)
    assert applied == 2
    by_id = {r["id"]: r for r in svc.list_inbox()}
    assert by_id[int(jobs[0].job_id)]["fit"] == 91
    assert by_id[int(jobs[1].job_id)]["fit"] == 55
    assert "contract" in by_id[int(jobs[1].job_id)]["fit_why"]


def test_score_applications_from_reply_writes_scores(tmp_db):
    from claude_bridge import fit_token
    j1 = svc.add_manual_job(title="A", company="Acme", status="interested",
                            url="https://x.com/q/1")
    j2 = svc.add_manual_job(title="B", company="Beta", status="interested",
                            url="https://x.com/q/2")
    rows = [svc.get_job(j1), svc.get_job(j2)]
    _prompt, jobs = svc.fit_prompt_for_rows(rows)
    reply = (
        f'[{{"i": 1, "token": "{fit_token(jobs[0])}", "fit": 77, '
        f'"why": "good", "flags": ""}},'
        f' {{"i": 2, "token": "{fit_token(jobs[1])}", "fit": 42, '
        f'"why": "meh", "flags": "clearance"}}]'
    )
    applied = svc.score_applications_from_reply(jobs, reply)
    assert applied == 2
    assert svc.get_job(j1)["fit_score"] == 77
    assert "clearance" in svc.get_job(j2)["fit_rationale"]


def test_parse_fit_reply_roundtrip(tmp_db):
    reply = '[{"i": 1, "fit": 90, "why": "great", "flags": ""}]'
    parsed = svc.parse_fit_reply(reply, 1)
    assert parsed[0]["fit_score"] == 90


def test_match_fit_falls_back_when_helper_absent(tmp_db, monkeypatch):
    import claude_bridge
    # Ensure the (bridge-cluster-provided) helper is treated as absent, so
    # match_fit() uses its positional fallback.
    monkeypatch.delattr(claude_bridge, "match_fit_to_jobs", raising=False)
    jobs = svc.jobs_from_rows([
        {"id": 10, "title": "A", "company": "Acme"},
        {"id": 11, "title": "B", "company": "Beta"}])
    parsed = [{"fit_score": 80, "rationale": "x"},
              {"fit_score": 60, "rationale": "y"}]
    out = svc.match_fit(jobs, parsed)
    assert [(j.job_id, fs) for j, fs, _ in out] == [("10", 80), ("11", 60)]


def test_match_fit_uses_helper_when_present(tmp_db, monkeypatch):
    import claude_bridge
    sentinel = [("J", 99, "mapped")]
    monkeypatch.setattr(claude_bridge, "match_fit_to_jobs",
                        lambda jobs, parsed: sentinel, raising=False)
    assert svc.match_fit([], []) is sentinel
