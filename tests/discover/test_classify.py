"""P3 — relevance classification gate: deterministic-first, AI on ambiguous only,
cached, never drops a no-sample board."""
import json

from discover import classify as C
from scrape.company_registry import CompanyEntry


def _entry(name, slug, titles=None):
    e = CompanyEntry(name, "greenhouse", slug, [])
    if titles is not None:
        e.sample_titles = titles
    return e


def test_title_keywords_from_keywords_and_industry():
    kw = C.title_keywords_for("health_informatics", ["clinical informatics specialist"])
    assert "informatics" in kw and "clinical" in kw and "health" in kw
    assert "the" not in kw and "senior" not in kw   # generic dropped


def test_deterministic_true_false_none():
    kw = {"informatics", "clinical"}
    assert C.is_relevant_deterministic("X", ["Clinical Informatics Analyst"], kw) is True
    assert C.is_relevant_deterministic("X", ["Sales Account Executive"], kw) is False
    assert C.is_relevant_deterministic("X", [], kw) is None       # no sample
    assert C.is_relevant_deterministic("X", ["anything"], set()) is None  # no keywords


def test_keep_match_and_nosample_drop_only_offtopic_with_ai():
    boards = [
        _entry("Relevant Co", "rel", ["Clinical Informatics Manager"]),   # match -> keep
        _entry("Unknown Co", "unk", []),                                  # no sample -> keep
        _entry("Marketing Co", "mkt", ["SEO Specialist", "Brand Manager"]),  # off -> AI
    ]

    def fake_ai(items, industry):
        # Reject anything whose titles clearly aren't the field.
        return [{"relevant": False, "subsector": ""} for _ in items]

    kept = C.classify_boards(boards, "health_informatics",
                             ["clinical informatics"], ai=fake_ai)
    assert ("greenhouse", "rel") in kept
    assert ("greenhouse", "unk") in kept          # never drop no-sample
    assert ("greenhouse", "mkt") not in kept      # AI rejected off-topic


def test_no_ai_keeps_ambiguous_by_default():
    boards = [_entry("Marketing Co", "mkt", ["SEO Specialist"])]
    kept = C.classify_boards(boards, "health_informatics", ["clinical"])
    assert ("greenhouse", "mkt") in kept          # conservative: keep without AI
    # ...but drop_ambiguous flips it
    kept2 = C.classify_boards(boards, "health_informatics", ["clinical"],
                              drop_ambiguous=True)
    assert ("greenhouse", "mkt") not in kept2


def test_ai_result_cached_no_second_call(tmp_path):
    cache = tmp_path / "classify.json"
    boards = [_entry("Marketing Co", "mkt", ["SEO Specialist"])]
    calls = []

    def fake_ai(items, industry):
        calls.append(len(items))
        return [{"relevant": False, "subsector": "marketing"}]

    C.classify_boards(boards, "health_informatics", ["clinical"], ai=fake_ai,
                      cache_path=cache)
    assert calls == [1]
    assert cache.exists()
    # Second run: cache hit, AI not called again, verdict (reject) preserved.
    kept = C.classify_boards(boards, "health_informatics", ["clinical"], ai=fake_ai,
                             cache_path=cache)
    assert calls == [1]                           # no second AI call
    assert ("greenhouse", "mkt") not in kept


def test_sample_fn_overrides_attached_titles():
    boards = [_entry("Co", "co", ["Sales"])]      # attached titles say off-topic
    kept = C.classify_boards(
        boards, "health_informatics", ["informatics"],
        sample_fn=lambda e: ["Clinical Informatics Lead"])  # live fetch says relevant
    assert ("greenhouse", "co") in kept


def test_make_classifier_seam_and_funnel_filter():
    from discover import funnel
    boards = {"greenhouse": {"keepme", "dropme"}}

    def fake_ai(items, industry):
        out = []
        for it in items:
            out.append({"relevant": it["name"].lower().startswith("keep"),
                        "subsector": ""})
        return out

    # sample_fn returns off-topic titles for both -> both go to AI, which keeps
    # only the one whose derived name starts with "keep".
    clf = C.make_classifier("health_informatics", ["clinical"], ai=fake_ai,
                            sample_fn=lambda e: ["Sales Rep"])
    out = funnel._apply_classify({"greenhouse": {"keepme", "dropme"}}, clf)
    assert out == {"greenhouse": {"keepme"}}
