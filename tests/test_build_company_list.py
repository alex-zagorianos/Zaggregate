"""build_company_list.py -- the one-command onboarding orchestrator. Every
sub-step is monkeypatched (this is a wiring/orchestration test, not a re-test of
enumerate_companies / discover.enumerate / dataset_seed / coverage, which already
have their own suites)."""
import sys
import types

import pytest

import build_company_list as bcl
import workspace
from scrape.company_registry import CompanyEntry


@pytest.fixture(autouse=True)
def _no_real_registry_io(monkeypatch):
    """Every test: never touch the real companies.json, never read the real
    (possibly large) hardcoded registry, never hit the real coverage cache."""
    monkeypatch.setattr(bcl, "_existing_names", lambda: [])
    monkeypatch.setattr(bcl, "save_companies", lambda entries, *a, **k: len(entries))
    monkeypatch.setattr(bcl, "registry_stats", lambda *a, **k: {"widgets": 3})
    monkeypatch.setattr(bcl, "loop_signal", lambda history, *a, **k: "rising")
    # No active project by default -- tests that need one stub workspace.load_config.
    monkeypatch.setattr(workspace, "load_config", lambda *a, **k: {})
    # Never run the REAL inbox harvester by default: it does live domain-guess +
    # probe HTTP over the machine's inbox (slow/networked/flaky). Tests that
    # assert harvest behavior override this with their own _stub_inbox().
    _stub_inbox(monkeypatch, lambda *, industry=None, dry_run=False, **kw: _Harvest())


def _stub_inbox(monkeypatch, fn):
    """Inject a fake discover.inbox_harvest module (the sibling module built in
    parallel; lazily imported, so this is how tests supply it)."""
    mod = types.ModuleType("discover.inbox_harvest")
    mod.harvest_inbox_companies = fn
    monkeypatch.setitem(sys.modules, "discover.inbox_harvest", mod)


class _Harvest:
    def __init__(self, candidates=(), already_in_registry=(), resolved=(),
                verified=(), added=0, entries=()):
        self.candidates = list(candidates)
        self.already_in_registry = list(already_in_registry)
        self.resolved = list(resolved)
        self.verified = list(verified)
        self.added = added
        self.entries = list(entries)


# ── (a) API key present -> auto enumerate branch, bridge NOT ───────────────────
def test_api_key_present_uses_auto_enumerate(monkeypatch):
    calls = []

    def fake_enumerate_via_api(metro, industries, **kw):
        calls.append((metro, list(industries)))
        return [{"name": "Acme", "domain": "acme.com"}]

    def fake_resolve_and_verify(cands, industries, **kw):
        return [(CompanyEntry("Acme", "greenhouse", "acme", list(industries)), 5)], []

    def fail_if_called(*a, **k):
        raise AssertionError("build_enumeration_prompt (bridge) must not be called")

    monkeypatch.setattr(bcl, "enumerate_via_api", fake_enumerate_via_api)
    monkeypatch.setattr(bcl, "resolve_and_verify", fake_resolve_and_verify)
    monkeypatch.setattr(bcl, "build_enumeration_prompt", fail_if_called)

    summary = bcl.build_company_list(industry="widgets", metro="Springfield",
                                     use_inbox=False, api_key="sk-fake-key")

    assert calls and calls[0][0] == "Springfield"
    assert summary["stages"]["enumerate"]["mode"] == "api"
    assert summary["stages"]["enumerate"]["verified"] == 1
    assert summary["stages"]["enumerate"]["added"] == 1


def test_detector_used_when_no_explicit_key(monkeypatch):
    """The api-key detector itself is consulted when api_key= isn't passed."""
    monkeypatch.setattr(bcl, "_detect_api_key", lambda explicit=None: "env-key")
    called = {}

    def fake_enumerate_via_api(metro, industries, **kw):
        called["hit"] = True
        return []

    monkeypatch.setattr(bcl, "enumerate_via_api", fake_enumerate_via_api)
    monkeypatch.setattr(bcl, "resolve_and_verify", lambda *a, **k: ([], []))

    bcl.build_company_list(industry="widgets", metro="Springfield", use_inbox=False)
    assert called.get("hit") is True


# ── (b) no key / print_prompt=True -> prompt printed, enumerate_via_api NOT called ──
def test_no_api_key_falls_back_to_bridge_prompt(monkeypatch, capsys):
    monkeypatch.setattr(bcl, "_detect_api_key", lambda explicit=None: None)

    def fail_if_called(*a, **k):
        raise AssertionError("enumerate_via_api must not be called without a key")

    monkeypatch.setattr(bcl, "enumerate_via_api", fail_if_called)

    summary = bcl.build_company_list(industry="widgets", metro="Springfield",
                                     use_inbox=False)

    assert summary["stages"]["enumerate"]["mode"] == "bridge-prompt"
    out = capsys.readouterr().out
    assert "Paste the above into claude.ai" in out


def test_print_prompt_forces_bridge_even_with_a_key(monkeypatch, capsys):
    def fail_if_called(*a, **k):
        raise AssertionError("enumerate_via_api must not be called when print_prompt=True")

    monkeypatch.setattr(bcl, "enumerate_via_api", fail_if_called)

    summary = bcl.build_company_list(industry="widgets", metro="Springfield",
                                     use_inbox=False, api_key="sk-fake-key",
                                     print_prompt=True)

    assert summary["stages"]["enumerate"]["mode"] == "bridge-prompt"
    out = capsys.readouterr().out
    assert "Paste the above into claude.ai" in out


# ── (c) in_file given -> parse+resolve path called ──────────────────────────────
def test_in_file_uses_parse_and_resolve(monkeypatch, tmp_path):
    reply = tmp_path / "reply.json"
    reply.write_text('[{"name": "Acme", "domain": "acme.com"}]', encoding="utf-8")

    parse_calls = []
    resolve_calls = []

    def fake_parse(text):
        parse_calls.append(text)
        return [{"name": "Acme", "domain": "acme.com"}]

    def fake_resolve(cands, industries, **kw):
        resolve_calls.append((list(cands), list(industries)))
        return [(CompanyEntry("Acme", "greenhouse", "acme", list(industries)), 2)], []

    def fail_if_called(*a, **k):
        raise AssertionError("enumerate_via_api must not be called in --in mode")

    monkeypatch.setattr(bcl, "parse_enumeration_response", fake_parse)
    monkeypatch.setattr(bcl, "resolve_and_verify", fake_resolve)
    monkeypatch.setattr(bcl, "enumerate_via_api", fail_if_called)

    summary = bcl.build_company_list(industry="widgets", metro="Springfield",
                                     use_inbox=False, in_file=str(reply))

    assert parse_calls, "parse_enumeration_response was not called"
    assert resolve_calls, "resolve_and_verify was not called"
    assert summary["stages"]["enumerate"]["mode"] == "bridge-in"
    assert summary["stages"]["enumerate"]["added"] == 1


# ── (d) use_inbox=False skips harvest ───────────────────────────────────────────
def test_use_inbox_false_skips_harvest_stage(monkeypatch):
    def fail_if_called(**kw):
        raise AssertionError("harvest_inbox_companies must not be called")

    _stub_inbox(monkeypatch, fail_if_called)
    monkeypatch.setattr(bcl, "enumerate_via_api", lambda *a, **k: [])
    monkeypatch.setattr(bcl, "resolve_and_verify", lambda *a, **k: ([], []))

    summary = bcl.build_company_list(industry="widgets", metro="Springfield",
                                     use_inbox=False, api_key="sk-fake")

    assert summary["stages"]["inbox"] is None


def test_use_inbox_true_calls_harvest(monkeypatch):
    seen = {}

    def fake_harvest(*, industry=None, dry_run=False, **kw):
        seen["industry"] = industry
        seen["dry_run"] = dry_run
        return _Harvest(candidates=["a", "b"], already_in_registry=["a"],
                        resolved=["b"], verified=["b"], added=1)

    _stub_inbox(monkeypatch, fake_harvest)
    monkeypatch.setattr(bcl, "enumerate_via_api", lambda *a, **k: [])
    monkeypatch.setattr(bcl, "resolve_and_verify", lambda *a, **k: ([], []))

    summary = bcl.build_company_list(industry="widgets", metro="Springfield",
                                     api_key="sk-fake")

    assert seen["industry"] == "widgets"
    assert seen["dry_run"] is False
    inbox = summary["stages"]["inbox"]
    assert inbox == {"candidates": 2, "already_in_registry": 1, "resolved": 1,
                     "verified": 1, "added": 1}


def test_missing_inbox_module_is_skipped_not_fatal(monkeypatch):
    """discover/inbox_harvest.py may not be importable -- ImportError must be a
    graceful, logged skip, never a crash. Setting sys.modules[name] = None makes
    `import` raise ImportError even though the file now exists on disk."""
    monkeypatch.setitem(sys.modules, "discover.inbox_harvest", None)
    monkeypatch.setattr(bcl, "enumerate_via_api", lambda *a, **k: [])
    monkeypatch.setattr(bcl, "resolve_and_verify", lambda *a, **k: ([], []))

    summary = bcl.build_company_list(industry="widgets", metro="Springfield",
                                     api_key="sk-fake")

    assert summary["stages"]["inbox"] == {"skipped": "module not available"}


# ── (e) industry/metro derived from a stubbed project config ───────────────────
def test_industry_and_metro_derived_from_project_config(monkeypatch):
    monkeypatch.setattr(workspace, "load_config",
                        lambda *a, **k: {"industry": "legal", "location": "Columbus"})
    monkeypatch.setattr(bcl, "enumerate_via_api", lambda *a, **k: [])
    monkeypatch.setattr(bcl, "resolve_and_verify", lambda *a, **k: ([], []))

    summary = bcl.build_company_list(use_inbox=False, api_key="sk-fake")

    assert summary["industry"] == "legal"
    assert summary["metro"] == "Columbus"


def test_explicit_args_override_project_config(monkeypatch):
    monkeypatch.setattr(workspace, "load_config",
                        lambda *a, **k: {"industry": "legal", "location": "Columbus"})
    monkeypatch.setattr(bcl, "enumerate_via_api", lambda *a, **k: [])
    monkeypatch.setattr(bcl, "resolve_and_verify", lambda *a, **k: ([], []))

    summary = bcl.build_company_list(industry="nursing", metro="Toledo",
                                     use_inbox=False, api_key="sk-fake")

    assert summary["industry"] == "nursing"
    assert summary["metro"] == "Toledo"


# ── (f) missing industry+metro raises a clear error ─────────────────────────────
def test_no_field_or_location_raises_clear_error():
    with pytest.raises(ValueError, match=r"--industry|--metro"):
        bcl.build_company_list()


def test_no_field_or_location_from_empty_project_config_raises(monkeypatch):
    monkeypatch.setattr(workspace, "load_config", lambda *a, **k: {"industry": "", "location": ""})
    with pytest.raises(ValueError):
        bcl.build_company_list(project="some-project")


# ── (g) dry_run propagates ──────────────────────────────────────────────────────
def test_dry_run_skips_save_and_forwards_to_inbox(monkeypatch):
    seen_dry_run = {}

    def fake_harvest(*, industry=None, dry_run=False, **kw):
        seen_dry_run["inbox"] = dry_run
        return _Harvest()

    _stub_inbox(monkeypatch, fake_harvest)

    def fake_enumerate_via_api(metro, industries, **kw):
        return [{"name": "Acme", "domain": "acme.com"}]

    def fake_resolve_and_verify(cands, industries, **kw):
        return [(CompanyEntry("Acme", "greenhouse", "acme", list(industries)), 5)], []

    def save_should_not_be_called(entries, *a, **k):
        raise AssertionError("save_companies must not be called with dry_run=True")

    monkeypatch.setattr(bcl, "enumerate_via_api", fake_enumerate_via_api)
    monkeypatch.setattr(bcl, "resolve_and_verify", fake_resolve_and_verify)
    monkeypatch.setattr(bcl, "save_companies", save_should_not_be_called)

    summary = bcl.build_company_list(industry="widgets", metro="Springfield",
                                     api_key="sk-fake", dry_run=True)

    assert seen_dry_run["inbox"] is True
    assert summary["stages"]["enumerate"]["added"] == 0


# ── dataset + classify wiring ────────────────────────────────────────────────────
def test_dataset_stage_runs_seed_from_dataset(monkeypatch, tmp_path):
    ds = tmp_path / "dataset.csv"
    ds.write_text("ats,slug,name\ngreenhouse,acme,Acme\n", encoding="utf-8")
    seen = {}

    def fake_seed(path, industry="", classify=None, dry_run=False, **kw):
        seen["path"] = path
        seen["industry"] = industry
        seen["classify"] = classify
        seen["dry_run"] = dry_run
        return {"loaded": 1, "candidates": 1, "skipped_known": 0,
                "verified": [(1, 2)], "dropped": [], "added": 1}

    monkeypatch.setattr(bcl, "seed_from_dataset", fake_seed)
    monkeypatch.setattr(bcl, "enumerate_via_api", lambda *a, **k: [])
    monkeypatch.setattr(bcl, "resolve_and_verify", lambda *a, **k: ([], []))

    summary = bcl.build_company_list(industry="widgets", metro="Springfield",
                                     use_inbox=False, api_key="sk-fake",
                                     dataset=str(ds), classify=True)

    assert seen["path"] == str(ds)
    assert seen["industry"] == "widgets"
    assert seen["classify"] is not None      # make_classifier(...) was built
    ds_summary = summary["stages"]["dataset"]
    assert ds_summary["loaded"] == 1
    assert ds_summary["added"] == 1
    assert ds_summary["classified"] is True
    assert summary["stages"]["classify"] == {"applied": True}


def test_classify_without_dataset_is_a_noop(monkeypatch):
    monkeypatch.setattr(bcl, "enumerate_via_api", lambda *a, **k: [])
    monkeypatch.setattr(bcl, "resolve_and_verify", lambda *a, **k: ([], []))

    summary = bcl.build_company_list(industry="widgets", metro="Springfield",
                                     use_inbox=False, api_key="sk-fake", classify=True)

    assert summary["stages"]["dataset"] is None
    assert summary["stages"]["classify"] == {"skipped": "no dataset given"}


def test_no_dataset_no_classify_both_none(monkeypatch):
    monkeypatch.setattr(bcl, "enumerate_via_api", lambda *a, **k: [])
    monkeypatch.setattr(bcl, "resolve_and_verify", lambda *a, **k: ([], []))

    summary = bcl.build_company_list(industry="widgets", metro="Springfield",
                                     use_inbox=False, api_key="sk-fake")

    assert summary["stages"]["dataset"] is None
    assert summary["stages"]["classify"] is None


# ── report stage (registry_stats + loop_signal) ─────────────────────────────────
def test_report_stage_uses_registry_stats_and_loop_signal(monkeypatch):
    monkeypatch.setattr(bcl, "registry_stats", lambda *a, **k: {"widgets": 4, "gadgets": 1})
    monkeypatch.setattr(bcl, "loop_signal", lambda history, *a, **k: "plateau")
    monkeypatch.setattr(bcl, "enumerate_via_api", lambda *a, **k: [])
    monkeypatch.setattr(bcl, "resolve_and_verify", lambda *a, **k: ([], []))

    summary = bcl.build_company_list(industry="widgets", metro="Springfield",
                                     use_inbox=False, api_key="sk-fake")

    assert summary["registry_stats"] == {"widgets": 4, "gadgets": 1}
    assert summary["loop_signal"] == "plateau"


# ── national flag ────────────────────────────────────────────────────────────────
def test_national_flag_adds_a_second_pass(monkeypatch):
    calls = []

    def fake_enumerate_via_api(metro, industries, **kw):
        calls.append(metro)
        if metro == bcl.NATIONAL_METRO:
            return [{"name": "RemoteCo", "domain": "remoteco.com"}]
        return [{"name": "MetroCo", "domain": "metroco.com"}]

    def fake_resolve_and_verify(cands, industries, *, metro_tag=None, **kw):
        return [(CompanyEntry(c["name"], "greenhouse", c["name"].lower(),
                              list(industries)), 1) for c in cands], []

    monkeypatch.setattr(bcl, "enumerate_via_api", fake_enumerate_via_api)
    monkeypatch.setattr(bcl, "resolve_and_verify", fake_resolve_and_verify)

    summary = bcl.build_company_list(industry="widgets", metro="Springfield",
                                     use_inbox=False, api_key="sk-fake", national=True)

    assert len(calls) == 2
    assert summary["stages"]["enumerate"]["verified"] == 2


# ── CLI wiring ────────────────────────────────────────────────────────────────────
def test_cli_json_flag_prints_json(monkeypatch, capsys):
    monkeypatch.setattr(bcl, "enumerate_via_api", lambda *a, **k: [])
    monkeypatch.setattr(bcl, "resolve_and_verify", lambda *a, **k: ([], []))

    rc = bcl.main(["--industry", "widgets", "--metro", "Springfield",
                  "--no-inbox", "--json"])
    assert rc == 0
    out = capsys.readouterr().out
    assert '"industry": "widgets"' in out


def test_cli_missing_field_returns_error_code(capsys):
    rc = bcl.main([])
    assert rc == 2
    assert "error:" in capsys.readouterr().out


# ── seed-my-area stage wiring (CareerOneStop Business Finder) ─────────────────
def _stub_seed_metro(monkeypatch, fn):
    """Inject a fake discover.seed_metro (lazily imported by the seed stage)."""
    mod = types.ModuleType("discover.seed_metro")
    mod.seed_my_metro = fn
    monkeypatch.setitem(sys.modules, "discover.seed_metro", mod)


class _SeedRes:
    def __init__(self, **kw):
        self._d = {"industry": "", "metro": "", "has_key": True, "discovered": 0,
                   "with_domain": 0, "already_known": 0, "verified": 0, "added": 0,
                   "drop_reasons": {}, "note": ""}
        self._d.update(kw)

    def as_dict(self):
        return dict(self._d)


def test_seed_metro_off_by_default(monkeypatch):
    def fail(*a, **k):
        raise AssertionError("seed_my_metro must not run unless seed_metro=True")

    _stub_seed_metro(monkeypatch, fail)
    monkeypatch.setattr(bcl, "enumerate_via_api", lambda *a, **k: [])
    monkeypatch.setattr(bcl, "resolve_and_verify", lambda *a, **k: ([], []))

    summary = bcl.build_company_list(industry="nursing", metro="Boise",
                                     use_inbox=False, api_key="sk-fake")
    assert summary["stages"]["seed_metro"] is None


def test_seed_metro_flag_runs_stage(monkeypatch):
    seen = {}

    def fake_seed(*, industry, metro, limit, dry_run, log):
        seen["industry"] = industry
        seen["metro"] = metro
        seen["limit"] = limit
        return _SeedRes(industry=industry, metro=metro, discovered=5,
                        verified=2, added=2)

    _stub_seed_metro(monkeypatch, fake_seed)
    monkeypatch.setattr(bcl, "enumerate_via_api", lambda *a, **k: [])
    monkeypatch.setattr(bcl, "resolve_and_verify", lambda *a, **k: ([], []))

    summary = bcl.build_company_list(industry="nursing", metro="Boise, ID",
                                     use_inbox=False, api_key="sk-fake",
                                     seed_metro=True, seed_limit=15)
    assert seen == {"industry": "nursing", "metro": "Boise, ID", "limit": 15}
    stage = summary["stages"]["seed_metro"]
    assert stage["added"] == 2 and stage["discovered"] == 5


def test_seed_metro_missing_module_is_skipped(monkeypatch):
    monkeypatch.setitem(sys.modules, "discover.seed_metro", None)
    monkeypatch.setattr(bcl, "enumerate_via_api", lambda *a, **k: [])
    monkeypatch.setattr(bcl, "resolve_and_verify", lambda *a, **k: ([], []))

    summary = bcl.build_company_list(industry="nursing", metro="Boise",
                                     use_inbox=False, api_key="sk-fake",
                                     seed_metro=True)
    assert summary["stages"]["seed_metro"] == {"skipped": "module not available"}


def test_cli_seed_metro_flag_threads_through(monkeypatch):
    seen = {}

    def fake_seed(*, industry, metro, limit, dry_run, log):
        seen["limit"] = limit
        return _SeedRes(added=1)

    _stub_seed_metro(monkeypatch, fake_seed)
    monkeypatch.setattr(bcl, "enumerate_via_api", lambda *a, **k: [])
    monkeypatch.setattr(bcl, "resolve_and_verify", lambda *a, **k: ([], []))

    rc = bcl.main(["--industry", "nursing", "--metro", "Boise", "--no-inbox",
                   "--seed-metro", "--seed-limit", "7"])
    assert rc == 0
    assert seen["limit"] == 7
