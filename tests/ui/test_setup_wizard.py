"""First-run Setup wizard: the pure answers->contract transform, the on-disk
apply, and the onboarding marker."""
import json

import pytest

import config
import workspace
from ui import setup_wizard as sw


def test_build_preferences_shape():
    out = sw.build_preferences({
        "roles": ["controls engineer", " plc "],
        "location": "Cincinnati",
        "remote_ok": True,
        "salary_min": 90000,
        "about": "I love automation.",
    })
    hard = out["hard"]
    assert hard["target_roles"] == ["controls engineer", "plc"]   # trimmed
    assert hard["locations"] == ["Cincinnati"]
    assert hard["salary_min"] == 90000
    assert hard["remote_ok"] is True
    # md is a plain-English profile that mentions the user's inputs
    md = out["profile_md"]
    assert "controls engineer" in md
    assert "Cincinnati" in md
    assert "90,000" in md
    assert "I love automation." in md


def test_build_preferences_empty_is_permissive():
    out = sw.build_preferences({"roles": [], "location": "", "salary_min": None})
    hard = out["hard"]
    assert hard["target_roles"] == []
    assert hard["locations"] == []
    assert hard["salary_min"] is None
    assert hard["remote_ok"] is True   # default: keep remote postings


def test_search_config_preserves_existing():
    cfg = sw._search_config(
        {"roles": ["a", "b"], "location": "Remote", "salary_min": 50000},
        existing={"industry": "manufacturing", "keywords": ["old"]})
    assert cfg["industry"] == "manufacturing"   # preserved
    assert cfg["keywords"] == ["a", "b"]          # overwritten from roles
    assert cfg["location"] == "Remote"
    assert cfg["salary_min"] == 50000


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "USER_DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "PREFERENCES_JSON", tmp_path / "preferences.json")
    monkeypatch.setattr(config, "PREFERENCES_MD", tmp_path / "preferences.md")
    monkeypatch.setattr(workspace, "BASE_DIR", tmp_path)
    return tmp_path


def test_marker_roundtrip(isolated):
    assert sw.is_onboarded() is False
    sw.mark_onboarded()
    assert sw.is_onboarded() is True


def test_apply_writes_full_contract(isolated):
    sw.apply({
        "roles": ["controls engineer"],
        "location": "Cincinnati",
        "remote_ok": False,
        "salary_min": 80000,
        "resume_text": "# Experience\n\nBuilt machines.",
        "about": "",
    })
    hard = json.loads(config.PREFERENCES_JSON.read_text(encoding="utf-8"))
    assert hard["target_roles"] == ["controls engineer"]
    assert hard["remote_ok"] is False
    assert "controls engineer" in config.PREFERENCES_MD.read_text(encoding="utf-8")
    assert workspace.load_config()["keywords"] == ["controls engineer"]
    assert "Built machines." in workspace.experience_file().read_text(encoding="utf-8")
    assert sw.is_onboarded() is True


def test_apply_without_resume_keeps_experience_untouched(isolated):
    workspace.experience_file().write_text("ORIGINAL", encoding="utf-8")
    sw.apply({"roles": ["x"], "location": "", "salary_min": None,
              "resume_text": "   ", "about": ""})   # blank resume
    assert workspace.experience_file().read_text(encoding="utf-8") == "ORIGINAL"


def test_apply_writes_about_narrative(isolated):
    # The 'about' free-text is the most valuable AI-ranking input; the wizard
    # collects it and it must land in the profile the AI reads.
    sw.apply({"roles": ["controls engineer"], "location": "", "salary_min": None,
              "resume_text": "", "about": "I love motion control; avoid pure IT."})
    md = config.PREFERENCES_MD.read_text(encoding="utf-8")
    assert "About me" in md
    assert "I love motion control; avoid pure IT." in md


def test_apply_colocates_preferences_with_active_project(isolated):
    # Once projects exist, apply() must write preferences BESIDE the active
    # project (not the root) so they don't desync from its config/resume, and
    # preferences.load() must read them back from there.
    import preferences
    slug = workspace.create_project("Controls", make_active=True)
    sw.apply({"roles": ["plc engineer"], "location": "Cincinnati",
              "salary_min": 95000, "resume_text": "", "about": "automation"})
    pj, _ = workspace.preferences_paths()
    assert slug in str(pj) and pj.exists()
    assert not config.PREFERENCES_JSON.exists()      # nothing stranded at root
    loaded = preferences.load()                      # bare -> active project
    assert loaded["hard"]["target_roles"] == ["plc engineer"]
    assert "automation" in loaded["profile_md"]


# ── Item 4: wizard pre-populate ───────────────────────────────────────────────

def test_prefill_from_existing_uses_prefs_and_cfg():
    """prefill_from_existing() correctly reads roles/location/salary/about
    from the preferences dict and the search-config dict (pure, no I/O)."""
    prefs = {
        "hard": {
            "target_roles": ["controls engineer", "plc programmer"],
            "locations": ["Cincinnati, OH"],
            "remote_ok": False,
            "salary_min": 95000,
        },
        "profile_md": (
            "# My Job Preferences\n\n"
            "Target roles / keywords: controls engineer\n\n"
            "## About me / what I'm looking for\n\n"
            "I love motion control and automation.\n"
        ),
    }
    cfg = {"keywords": ["old keyword"], "location": "Columbus"}
    out = sw.prefill_from_existing(prefs=prefs, cfg=cfg)
    # roles come from hard.target_roles (not cfg.keywords)
    assert "controls engineer" in out["roles"]
    assert "plc programmer" in out["roles"]
    # location comes from hard.locations[0]
    assert out["location"] == "Cincinnati, OH"
    # remote_ok
    assert out["remote_ok"] is False
    # salary_min as string
    assert out["salary_min"] == "95000"
    # about extracted from profile_md
    assert "I love motion control" in out["about"]


def test_prefill_falls_back_to_cfg_when_no_hard_roles():
    """When hard.target_roles is empty, prefill falls back to cfg.keywords."""
    prefs = {"hard": {"target_roles": [], "locations": [], "remote_ok": True,
                      "salary_min": None}, "profile_md": ""}
    cfg = {"keywords": ["mechanical engineer"], "location": "Remote"}
    out = sw.prefill_from_existing(prefs=prefs, cfg=cfg)
    assert "mechanical engineer" in out["roles"]
    assert out["location"] == "Remote"


def test_prefill_empty_when_nothing_configured():
    """prefill with no data returns safe empty defaults."""
    out = sw.prefill_from_existing(prefs={}, cfg={})
    assert out["roles"] == ""
    assert out["location"] == ""
    assert out["remote_ok"] is True
    assert out["salary_min"] == ""
    assert out["about"] == ""


def test_prefill_about_not_contaminated_by_other_sections():
    """The 'about' extraction stops after the marker; other md sections are not
    included (they would confuse the user seeing a long pre-filled block)."""
    prefs = {
        "hard": {},
        "profile_md": (
            "# Prefs\n\n"
            "Target roles: foo\n\n"
            "## About me / what I'm looking for\n\n"
            "Just the about text here.\n"
        ),
    }
    out = sw.prefill_from_existing(prefs=prefs, cfg={})
    assert "Just the about text here." in out["about"]
    assert "Target roles" not in out["about"]


# ── P0-2b: wizard keys step ───────────────────────────────────────────────────

@pytest.fixture
def no_source_keys(monkeypatch, tmp_path):
    """Isolate credential resolution: no env vars, secrets in an empty temp dir,
    so connected_source_labels() sees a truly keyless machine."""
    monkeypatch.setattr(config, "SECRETS_DIR", tmp_path / "secrets")
    for var in ("ADZUNA_APP_ID", "ADZUNA_APP_KEY", "USAJOBS_API_KEY",
                "USAJOBS_EMAIL", "USAJOBS_USER_AGENT", "JOOBLE_API_KEY",
                "CAREERJET_AFFID", "CAREERONESTOP_USER_ID", "CAREERONESTOP_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    return tmp_path


def test_connected_source_labels_empty_when_keyless(no_source_keys):
    assert sw.connected_source_labels() == []


def test_connected_source_labels_impact_ranked(no_source_keys, monkeypatch):
    """Adzuna must sort before CareerOneStop before the rest, and a source counts
    as connected only when ALL its credentials are present."""
    from ui import settings
    monkeypatch.setattr(settings.config, "SECRETS_DIR", no_source_keys / "secrets")
    # CareerOneStop needs BOTH id+token; only one -> not connected yet.
    settings.set_api_key("careeronestop_user_id", "u123")
    assert "CareerOneStop" not in sw.connected_source_labels()
    settings.set_api_key("careeronestop_token", "t456")
    # Adzuna both parts.
    settings.set_api_key("adzuna_app_id", "id")
    settings.set_api_key("adzuna_app_key", "key")
    settings.set_api_key("jooble_api_key", "j")
    labels = sw.connected_source_labels()
    assert labels[:3] == ["Adzuna", "CareerOneStop", "Jooble"]   # impact order


def test_connected_source_labels_honors_usajobs_user_agent_fallback(
        no_source_keys, monkeypatch):
    """USAJobs email resolves from the USAJOBS_USER_AGENT env fallback (what the
    client actually reads), not only USAJOBS_EMAIL."""
    monkeypatch.setenv("USAJOBS_API_KEY", "abc")
    monkeypatch.setenv("USAJOBS_USER_AGENT", "me@example.com")
    assert "USAJobs" in sw.connected_source_labels()


def test_wizard_has_keys_step_and_completes_with_zero_keys(no_source_keys,
                                                           isolated, monkeypatch):
    """The wizard must expose a keys step AND remain fully completable with no
    keys connected (the whole flow must never require a key)."""
    import tkinter as tk
    try:
        root = tk.Tk()
        root.withdraw()
    except tk.TclError:
        pytest.skip("no display")
    import gui  # noqa: F401  (ensures theme is importable in the same way GUI does)
    from ui import theme
    theme.apply_theme(root)
    try:
        w = sw.SetupWizard(root)
        # The new step is present, positioned before the closing 'keep going' step.
        names = [s.__name__ for s in w._steps]
        assert "_step_keys" in names
        assert names.index("_step_keys") < names.index("_step_keep_going")
        w._vars["roles"].set("registered nurse")
        # Walk forward with the real Next handler from step 0; the keys step must
        # NOT block advancing (no key required). Stop before the final Finish so
        # apply()/messageboxes (tested elsewhere) don't fire.
        w._step = 0
        w._render()
        for _ in range(len(w._steps) - 1):
            before = w._step
            w._next()
            w.update_idletasks()
            assert w._step == before + 1        # advanced past every step, incl. keys
        assert w._steps[w._step].__name__ == "_step_keep_going"   # reached the end
        w.destroy()
    finally:
        root.destroy()


# ── S32c: wizard ↔ AI-setup express-lane (§6.3) ───────────────────────────────

_AI_GOOD_PAYLOAD = {
    "field": "Data Analytics",
    "target_titles": ["Data Analyst", "BI Analyst"],
    "location": "Phoenix, AZ",
    "remote_ok": True,
    "radius_miles": 40,
    "salary_floor": 85000,
    "seniority": "mid",
    "preferences_md": "I want data analyst roles. I love SQL.",
}
_AI_GOOD_BLOCK = "Here you go!\n```json\n" + json.dumps(_AI_GOOD_PAYLOAD) + "\n```\n"


def _fresh_wizard(monkeypatch):
    """Build a real SetupWizard on a hidden root, or skip if there's no display.
    Isolates prefill so an already-configured machine can't seed the vars."""
    import tkinter as tk
    monkeypatch.setattr(sw, "prefill_from_existing",
                        lambda *a, **k: {"roles": "", "location": "",
                                         "remote_ok": True, "salary_min": "",
                                         "about": "", "industry": "", "level": ""})
    try:
        root = tk.Tk()
        root.withdraw()
    except tk.TclError:
        pytest.skip("no display")
    import gui  # noqa: F401  (same theme-import path the real GUI uses)
    from ui import theme
    theme.apply_theme(root)
    return root, sw.SetupWizard(root)


def test_wizard_has_ai_step_first_and_optional(monkeypatch):
    """The AI express-lane is present, sits right after Welcome and before the
    manual roles step, and does NOT block advancing when nothing is pasted."""
    root, w = _fresh_wizard(monkeypatch)
    try:
        names = [s.__name__ for s in w._steps]
        assert "_step_ai" in names
        assert names.index("_step_ai") == 1                     # right after welcome
        assert names.index("_step_ai") < names.index("_step_roles")
        # Render the AI step and advance with an EMPTY reply box: must not block.
        w._step = names.index("_step_ai")
        w._render()
        before = w._step
        w._next()
        w.update_idletasks()
        assert w._step == before + 1                            # advanced past it
    finally:
        root.destroy()


def test_wizard_ai_prefill_populates_subsequent_steps(monkeypatch):
    """Pasting a valid AI config block prefills the wizard vars (roles/location/
    salary/industry/level/about) so the following steps open pre-populated — the
    steps are NOT skipped; the user still reviews them."""
    root, w = _fresh_wizard(monkeypatch)
    try:
        w._step = [s.__name__ for s in w._steps].index("_step_ai")
        w._render()
        w._ai_reply.insert("1.0", _AI_GOOD_BLOCK)
        w._prefill_from_ai()
        assert w._vars["roles"].get() == "Data Analyst, BI Analyst"
        assert w._vars["location"].get() == "Phoenix, AZ"
        assert w._vars["salary_min"].get() == "85000"
        assert w._vars["industry"].get() == "data analytics"    # canonical token
        assert w._vars["level"].get() == "Mid"                  # seniority -> level
        # The field preset picker reflects the token (so the roles step shows it).
        assert w._vars["field_preset"].get() == "Data analytics / data science"
        # 'about' feeds the free-text cache the roles step reads.
        assert "SQL" in w._about_cache
        # And _collect() (what Finish applies) now carries the prefilled answers.
        collected = w._collect()
        assert collected["roles"] == ["Data Analyst", "BI Analyst"]
        assert collected["industry"] == "data analytics"
    finally:
        root.destroy()


def test_wizard_ai_prefill_bad_block_leaves_manual_path_intact(monkeypatch):
    """A garbage / unparseable reply must NOT crash or mutate the vars — the
    manual path is untouched and the wizard stays completable by hand."""
    root, w = _fresh_wizard(monkeypatch)
    try:
        w._step = [s.__name__ for s in w._steps].index("_step_ai")
        w._render()
        # Pre-set a manual value; a bad AI paste must not clobber it.
        w._vars["roles"].set("welder")
        w._ai_reply.insert("1.0", "sorry, I couldn't help with that")
        import tkinter.messagebox as mb
        monkeypatch.setattr(mb, "showwarning", lambda *a, **k: None)
        w._prefill_from_ai()                                    # must not raise
        assert w._vars["roles"].get() == "welder"              # manual value intact
        assert w._vars["industry"].get() == ""                 # nothing applied
    finally:
        root.destroy()


def test_wizard_completes_with_zero_ai(monkeypatch):
    """The whole wizard must be walkable start-to-finish without ever touching the
    AI step (parity with the zero-keys guarantee)."""
    root, w = _fresh_wizard(monkeypatch)
    try:
        w._vars["roles"].set("registered nurse")
        w._step = 0
        w._render()
        for _ in range(len(w._steps) - 1):
            before = w._step
            w._next()
            w.update_idletasks()
            assert w._step == before + 1
        assert w._steps[w._step].__name__ == "_step_keep_going"
    finally:
        root.destroy()
