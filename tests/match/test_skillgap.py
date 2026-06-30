"""Offline skill-gap comparison for a JD: 'you have' (matched) vs 'the job also
wants' (missing). Pure logic, no AI/network. Mirrors match/scorer.py term style."""
from match import skillgap


# A small explicit user-skill set so these tests never read experience.md.
USER_SKILLS = frozenset({
    "python", "solidworks", "c++", ".net", "controls", "automation", "plc",
})

JD = (
    "We are looking for a Controls Engineer. Experience with Rust is required, "
    "and proficiency in Kubernetes is a strong plus. You will write Python and "
    "work with PLC systems and SolidWorks. Knowledge of CUDA and PyTorch helps. "
    "Bachelor degree required, 5 years of experience. PTO and benefits included."
)


def test_matched_contains_user_skill_overlap():
    out = skillgap.skill_gap(JD, skill_terms=USER_SKILLS)
    m = out["matched"]
    # User skills actually present in the JD.
    assert "python" in m
    assert "solidworks" in m
    assert "plc" in m
    assert "controls" in m
    # Skills the user has but the JD never mentions stay out of matched.
    assert ".net" not in m


def test_matched_is_sorted_and_deduped():
    out = skillgap.skill_gap(JD, skill_terms=USER_SKILLS)
    m = out["matched"]
    assert m == sorted(m)
    assert len(m) == len(set(m))


def test_missing_has_new_tech_not_owned_by_user():
    out = skillgap.skill_gap(JD, skill_terms=USER_SKILLS)
    miss = [x.lower() for x in out["missing"]]
    assert "kubernetes" in miss   # capitalized tech token + "proficiency in" trigger
    assert "rust" in miss         # "experience with Rust"
    assert "cuda" in miss         # ALL-CAPS acronym
    assert "pytorch" in miss      # CamelCase tech token


def test_missing_excludes_user_skills():
    out = skillgap.skill_gap(JD, skill_terms=USER_SKILLS)
    miss = [x.lower() for x in out["missing"]]
    # Things the user already has must not appear as gaps.
    assert "python" not in miss
    assert "solidworks" not in miss
    assert "plc" not in miss


def test_stoplist_removes_non_skills():
    out = skillgap.skill_gap(JD, skill_terms=USER_SKILLS)
    miss = [x.lower() for x in out["missing"]]
    for junk in ("bachelor", "degree", "years", "year", "experience",
                 "pto", "benefits", "strong"):
        assert junk not in miss


def test_explicit_skill_terms_does_not_read_experience(monkeypatch):
    # If skill_terms is passed, extract_skill_terms must never be invoked.
    def _boom(*a, **k):
        raise AssertionError("extract_skill_terms should not be called")
    monkeypatch.setattr(skillgap.scorer, "extract_skill_terms", _boom)
    out = skillgap.skill_gap("Experience with Go and Kubernetes.",
                             skill_terms=frozenset({"python"}))
    assert "go" in [x.lower() for x in out["missing"]]
    assert "kubernetes" in [x.lower() for x in out["missing"]]


def test_defaults_to_extract_skill_terms(monkeypatch):
    called = {}

    def _fake(experience_path=None):
        called["hit"] = experience_path
        return frozenset({"python"})

    monkeypatch.setattr(skillgap.scorer, "extract_skill_terms", _fake)
    out = skillgap.skill_gap("We use Python and Kubernetes here.",
                             experience_path="/some/path")
    assert called["hit"] == "/some/path"
    assert "python" in out["matched"]
    assert "kubernetes" in [x.lower() for x in out["missing"]]


def test_limit_caps_missing_length():
    jd = ("Experience with Rust, Kubernetes, Golang, Terraform, Ansible, "
          "Docker, Kafka, Redis, Postgres, MongoDB, GraphQL, Elixir, Haskell.")
    out = skillgap.skill_gap(jd, skill_terms=frozenset(), limit=3)
    assert len(out["missing"]) <= 3


def test_missing_most_frequent_first():
    jd = "Kubernetes Kubernetes Kubernetes. Also some Rust once."
    out = skillgap.skill_gap(jd, skill_terms=frozenset())
    miss = [x.lower() for x in out["missing"]]
    assert miss[0] == "kubernetes"
    assert "rust" in miss
    assert miss.index("kubernetes") < miss.index("rust")


def test_defensive_on_empty_and_none_description():
    for bad in (None, "", "   "):
        out = skillgap.skill_gap(bad, skill_terms=USER_SKILLS)
        assert out == {"matched": [], "missing": []}


def test_dotted_and_short_tokens():
    out = skillgap.skill_gap("Experience with .NET and SQL and ROS.",
                             skill_terms=frozenset())
    miss = [x.lower() for x in out["missing"]]
    assert ".net" in miss
    assert "sql" in miss
    assert "ros" in miss


def test_return_shape():
    out = skillgap.skill_gap(JD, skill_terms=USER_SKILLS)
    assert set(out.keys()) == {"matched", "missing"}
    assert isinstance(out["matched"], list)
    assert isinstance(out["missing"], list)
