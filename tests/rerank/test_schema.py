from rerank import schema


def test_columns_frozen_exact_order():
    assert schema.RERANK_CSV_COLUMNS == [
        "job_key", "title", "company", "location", "salary", "url",
        "local_score", "current_fit", "description_excerpt",
        "new_fit", "new_rank", "fit_rationale", "tags",
    ]


def test_in_out_partition():
    assert schema.IN_COLUMNS == ["new_fit", "new_rank", "fit_rationale", "tags"]
    # every column is either out-context or an AI-filled in-column
    assert set(schema.OUT_COLUMNS) | set(schema.IN_COLUMNS) == set(schema.RERANK_CSV_COLUMNS)
    assert set(schema.OUT_COLUMNS) & set(schema.IN_COLUMNS) == set()


def test_prompt_version_is_one():
    assert schema.PROMPT_VERSION == "1"


def test_csv_safe_neutralizes_formula_chars():
    assert schema.csv_safe("=HYPERLINK(1)") == "'=HYPERLINK(1)"
    assert schema.csv_safe("@SUM(A1)") == "'@SUM(A1)"
    assert schema.csv_safe("-2+3") == "'-2+3"
    assert schema.csv_safe("plain") == "plain"
    assert schema.csv_safe(7) == 7  # non-strings pass through


def test_row_from_inbox_maps_and_carries_job_key():
    r = {"id": 5, "title": "Software Developer", "company": "Acme",
         "location": "Cincinnati, OH", "salary_text": "$120k", "url": "https://x/1",
         "score": 70, "fit": -1, "description": "build motion control " * 200}
    out = schema.row_from_inbox(r)
    assert set(out.keys()) == set(schema.RERANK_CSV_COLUMNS)
    assert out["local_score"] == 70
    assert out["current_fit"] == -1
    assert out["new_fit"] == ""  # AI-filled columns start blank
    assert len(out["description_excerpt"]) <= 1200
    assert out["job_key"]  # non-empty join key derived from the row


def test_build_prompt_anchors_to_preferences_and_fit_instructions(monkeypatch):
    import preferences
    monkeypatch.setattr(preferences, "load",
                        lambda: {"profile_md": "I want controls + embedded roles.", "hard": {}})
    p = schema.build_prompt("I want controls + embedded roles.")
    assert "controls + embedded" in p
    assert "Scoring guide" in p          # reused from claude_bridge._FIT_INSTRUCTIONS
    assert "new_fit" in p and "job_key" in p
    assert "version 1" in p.lower()
