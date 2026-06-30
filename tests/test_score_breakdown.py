from match.scorer import score_breakdown


def test_parses_full_notes_string():
    notes = ("title 80% | skills 60% | salary 0% | loc 33% | new 50% | conf 3/5 "
             "| size +8 (12 on board) | title-miss -12 | PENALTY: remote, contract")
    bd = score_breakdown(notes)
    comps = {c["key"]: c for c in bd["components"]}
    assert comps["title"]["pct"] == 0.80 and comps["title"]["weight"] == 35
    assert comps["skills"]["pct"] == 0.60 and comps["skills"]["weight"] == 25
    assert comps["salary"]["pct"] == 0.0
    assert comps["loc"]["label"] == "Location"
    assert comps["new"]["label"] == "Recency" and comps["new"]["weight"] == 10
    assert bd["confidence"] == {"present": 3, "total": 5}
    assert bd["size_adj"] == 8 and bd["board_count"] == 12
    labels = {p["label"]: p["value"] for p in bd["penalties"]}
    assert labels["title-miss"] == -12
    assert labels["remote"] == -30 and labels["contract"] == -30


def test_negative_size_and_exclude_title_penalty():
    notes = "title 100% | skills 50% | loc 100% | new 100% | conf 4/5 | size -6 (300 on board) | excl-title(ai,ml) -45"
    bd = score_breakdown(notes)
    assert bd["size_adj"] == -6 and bd["board_count"] == 300
    assert {"label": "excl-title(ai,ml)", "value": -45} in bd["penalties"]
    # only 4 components present (no salary) — must not crash
    assert len(bd["components"]) == 4


def test_forgiving_on_empty_or_partial():
    assert score_breakdown("") == {"components": [], "confidence": None,
                                   "size_adj": None, "board_count": None, "penalties": []}
    bd = score_breakdown("title 70% | loc 0%")
    assert len(bd["components"]) == 2 and bd["confidence"] is None
