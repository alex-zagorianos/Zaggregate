"""A4 slice: browser_receiver's inbox-routing scoring uses the project's
EFFECTIVE keywords (industry-derived for a non-eng field), not the engineering
DEFAULT_KEYWORDS. No network; the scorer + DB are monkeypatched so we assert
only on the keywords handed to scoring."""
import pytest

import scrape.browser_receiver as br
from search.keyword_strategy import effective_keywords


@pytest.fixture
def client():
    br.app.config["TESTING"] = True
    return br.app.test_client()


def test_effective_keywords_non_eng_field_not_default():
    # The fix's core: a health project with no explicit keywords derives health
    # terms, never the controls-engineer DEFAULT_KEYWORDS.
    from config import DEFAULT_KEYWORDS
    cfg = {"industry": "health informatics"}
    kw = effective_keywords(cfg)
    assert kw and kw != list(DEFAULT_KEYWORDS)
    assert any("informatics" in k or "clinical" in k or "health" in k for k in kw)


def test_effective_keywords_explicit_keywords_win():
    cfg = {"keywords": ["registered nurse"], "industry": "nursing"}
    assert effective_keywords(cfg) == ["registered nurse"]


def test_harvest_scores_with_effective_keywords(client, monkeypatch, tmp_path):
    """Drive /harvest end-to-end with a health cfg and assert score_jobs was
    called with the derived health keywords, not DEFAULT_KEYWORDS."""
    import workspace
    monkeypatch.setattr(workspace, "output_dir", lambda: tmp_path)

    captured = {}

    def fake_score_jobs(results, *, keywords, **kw):
        captured["keywords"] = list(keywords)
        for r in results:
            r.score, r.score_notes = 50, "test"
        return results

    monkeypatch.setattr("match.scorer.score_jobs", fake_score_jobs)
    monkeypatch.setattr("search.cli.load_user_config",
                        lambda: {"industry": "health informatics"})
    monkeypatch.setattr("tracker.db.init_db", lambda: None)
    monkeypatch.setattr("tracker.db.inbox_add_many", lambda scored: len(scored))
    # Keep report generation cheap / side-effect-free.
    monkeypatch.setattr(br, "generate_html_report", lambda *a, **k: None)
    monkeypatch.setattr(br, "generate_csv_report", lambda *a, **k: None)
    monkeypatch.setattr(br.webbrowser, "open", lambda *a, **k: None)

    resp = client.post(
        "/harvest",
        json={"jobs": [{"title": "Nurse", "url": "https://e.com/1",
                        "company": "Mercy"}]},
        headers={"Origin": "chrome-extension://abcdef"},
    )
    assert resp.status_code == 200
    from config import DEFAULT_KEYWORDS
    assert captured["keywords"] != list(DEFAULT_KEYWORDS)
    assert any("informatics" in k or "clinical" in k or "health" in k
               for k in captured["keywords"])
