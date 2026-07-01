"""A4 slice: deseniorize junk-stem guard + knowledge-work gate fix."""
import industry_profile
from search import keyword_strategy as ks


# -- item 5: deseniorize guard against junk single-modifier stems ----------------
def test_deseniorize_guard_keeps_shift_supervisor_whole():
    # 'Shift Supervisor' must NOT broaden to the junk query 'shift'.
    assert ks.deseniorize("Shift Supervisor") == ""
    assert ks.broad_query_keywords(["Shift Supervisor"], "") == ["shift supervisor"]


def test_deseniorize_guard_covers_other_scope_modifiers():
    for title in ("Team Lead", "Night Manager", "Line Lead", "Floor Supervisor"):
        assert ks.deseniorize(title) == "", title
        out = ks.broad_query_keywords([title], "")
        assert out == [title.lower()], (title, out)


def test_deseniorize_guard_does_not_touch_real_fields():
    # Multi-token stems and real single-word fields survive unchanged.
    assert ks.deseniorize("Night Shift Nurse") == "night shift nurse"
    assert ks.deseniorize("Registered Nurse") == "registered nurse"
    assert ks.deseniorize("Senior Controls Engineer") == "controls engineer"
    assert ks.deseniorize("Clinical Informatics Manager") == "clinical informatics"


def test_deseniorize_engineering_byte_identical():
    # Alex's plain IC titles are returned unchanged (lowercased).
    for t in ("controls engineer", "embedded systems engineer",
              "mechatronics engineer", "test engineer"):
        assert ks.deseniorize(t) == t
        assert ks.broad_query_keywords([t], "") == [t]


# -- item 6: knowledge-work gate -------------------------------------------------
def test_knowledge_work_keeps_remote_boards_for_desk_health_and_education():
    for field in ("health informatics", "clinical informatics",
                  "healthcare analytics", "education", "teacher"):
        assert ks.is_knowledge_work(field) is True, field


def test_knowledge_work_gates_off_clinical_and_trades():
    for field in ("nursing", "registered nurse", "welding", "hvac",
                  "plumbing", "driver"):
        assert ks.is_knowledge_work(field) is False, field


def test_knowledge_work_empty_and_eng_byte_identical():
    # Empty (Alex default) + engineering stay True, so gate_tech_sources is a
    # no-op for the engineering flow.
    assert ks.is_knowledge_work("") is True
    assert ks.is_knowledge_work("controls engineering") is True
    assert ks.is_knowledge_work("software") is True


def test_gate_tech_sources_end_to_end():
    sources = ["adzuna", "remoteok", "remotive", "himalayas", "careers"]
    # Knowledge field keeps the remote boards.
    kept = ks.gate_tech_sources(sources, "health informatics")
    assert "remoteok" in kept and "remotive" in kept
    # Clinical field drops them.
    gated = ks.gate_tech_sources(sources, "nursing")
    assert "remoteok" not in gated and "himalayas" not in gated
    assert "adzuna" in gated and "careers" in gated
    # Engineering (empty) unchanged.
    assert ks.gate_tech_sources(sources, "") == sources


def test_gate_tech_sources_explicit_override_wins():
    # A user's explicit per-source True keeps a board on even for a clinical field.
    gated = ks.gate_tech_sources(["remoteok", "careers"], "nursing",
                                 cfg_sources={"remoteok": True})
    assert "remoteok" in gated


def test_text_signal_handson_beats_knowledge():
    # 'clinical nurse educator' has both an education (knowledge) and nurse
    # (hands-on) signal; hands-on wins.
    assert ks._text_knowledge_signal("clinical nurse educator") is False
