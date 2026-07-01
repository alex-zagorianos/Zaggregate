"""P1 — bulk ATS-slug dataset seed: parse, ATS-vocab map, probe-verify gate, merge."""
import json

from discover import dataset_seed as ds
from scrape.company_registry import CompanyEntry, get_registry


# ── parsing / column auto-detection ─────────────────────────────────────────

def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def test_load_csv_autodetects_columns_and_maps_ats(tmp_path):
    csv_text = (
        "company,platform,board_token\n"
        "Acme,greenhouse,acme\n"
        "Globex,Lever,globex\n"
        "Initech,AshbyHQ,initech\n"
        "Umbrella,myworkdayjobs,umbrella:5:External\n"
    )
    boards = ds.load_ats_dataset(_write(tmp_path, "d.csv", csv_text))
    assert boards["greenhouse"] == {"acme"}
    assert boards["lever"] == {"globex"}
    assert boards["ashby"] == {"initech"}          # AshbyHQ -> ashby
    assert boards["workday"] == {"umbrella:5:External"}  # myworkdayjobs -> workday


def test_normalize_ats_vocab():
    assert ds.normalize_ats("Greenhouse.io") == "greenhouse"
    assert ds.normalize_ats("smart-recruiters") == "smartrecruiters"
    assert ds.normalize_ats("SAPSF") == "successfactors"
    assert ds.normalize_ats("nonsense") == ""


def test_ats_filter_restricts(tmp_path):
    csv_text = "name,ats,slug\nA,greenhouse,a\nB,lever,b\nC,ashby,c\n"
    boards = ds.load_ats_dataset(_write(tmp_path, "d.csv", csv_text),
                                 ats_filter=["greenhouse", "ashby"])
    assert set(boards) == {"greenhouse", "ashby"}


def test_column_map_override(tmp_path):
    csv_text = "employer,sys,tok\nA,greenhouse,aa\n"
    boards = ds.load_ats_dataset(_write(tmp_path, "d.csv", csv_text),
                                 column_map={"ats": "sys", "slug": "tok"})
    assert boards == {"greenhouse": {"aa"}}


def test_ndjson_parsing_and_limit(tmp_path):
    nd = "\n".join(json.dumps(o) for o in [
        {"company": "A", "ats_type": "greenhouse", "slug": "a"},
        {"company": "B", "ats_type": "lever", "slug": "b"},
        {"company": "C", "ats_type": "ashby", "slug": "c"},
    ])
    boards = ds.load_ats_dataset(_write(tmp_path, "d.ndjson", nd), limit=2)
    total = sum(len(s) for s in boards.values())
    assert total == 2  # limit stops after 2 rows


def test_url_fallback_column(tmp_path):
    # No ats/slug columns — only a board URL; detect_ats must recover it.
    csv_text = "name,careers_url\nAcme,https://boards.greenhouse.io/acmeco\n"
    boards = ds.load_ats_dataset(_write(tmp_path, "d.csv", csv_text))
    assert boards == {"greenhouse": {"acmeco"}}


def test_bad_rows_dropped(tmp_path):
    csv_text = ("name,ats,slug\n"
                "Good,greenhouse,good\n"
                "NoSlug,greenhouse,\n"
                "BadAts,notarealats,x\n")
    boards = ds.load_ats_dataset(_write(tmp_path, "d.csv", csv_text))
    assert boards == {"greenhouse": {"good"}}


# ── the probe-verify gate ────────────────────────────────────────────────────

def _probe(entry):
    return {"live": 7, "empty": 0, "bad": None}.get(entry.slug, 0)


def test_verify_keeps_live_drops_dead_known_unprobeable():
    boards = {
        "greenhouse": {"live", "empty", "bad"},
        "direct": {"somesite"},        # unprobeable ats
    }
    verified, dropped = ds.verify_boards(
        boards, "controls_engineering", probe=_probe,
        existing={("greenhouse", "known")})
    assert [e.slug for e, _ in verified] == ["live"]
    assert verified[0][0].industries == ["controls_engineering"]
    reasons = {slug: r for _, slug, r in dropped}
    assert reasons["empty"] == "no live jobs"
    assert reasons["bad"].startswith("unverifiable")
    assert reasons["somesite"].startswith("unprobeable")


def test_verify_skips_known_without_probing():
    calls = []

    def spy(entry):
        calls.append(entry.slug)
        return 5

    boards = {"greenhouse": {"known", "fresh"}}
    verified, dropped = ds.verify_boards(
        boards, "", probe=spy, existing={("greenhouse", "known")})
    assert calls == ["fresh"]                     # 'known' never probed
    assert [e.slug for e, _ in verified] == ["fresh"]
    assert verified[0][0].industries == ["discovered"]  # no industry -> discovered
    assert ("greenhouse", "known", "already known") in dropped


def test_verify_classify_seam_filters_offindustry():
    boards = {"greenhouse": {"live", "empty"}}
    # classify keeps only the boards it is handed back — drop 'live' too, to prove
    # the seam actually gates verified boards.
    verified, dropped = ds.verify_boards(
        boards, "controls_engineering", probe=lambda e: 3,
        classify=lambda entries: set())
    assert verified == []
    assert any(r == "off-industry (classify)" for _, _, r in dropped)


# ── seed_from_dataset end-to-end (injected probe, real merge) ─────────────────

def _companies_json(tmp_path):
    p = tmp_path / "companies.json"
    p.write_text(json.dumps({"companies": []}), encoding="utf-8")
    return p


def test_seed_end_to_end_dry_run_writes_nothing(tmp_path):
    csv_text = "name,ats,slug\nLive,greenhouse,live\nEmpty,greenhouse,empty\n"
    dpath = _write(tmp_path, "d.csv", csv_text)
    cj = _companies_json(tmp_path)
    res = ds.seed_from_dataset(dpath, "controls_engineering", probe=_probe,
                               companies_json_path=cj, dry_run=True, existing=set())
    assert res["added"] == 0
    assert [e.slug for e, _ in res["verified"]] == ["live"]
    assert json.loads(cj.read_text())["companies"] == []  # untouched


def test_seed_end_to_end_saves_and_is_idempotent(tmp_path):
    csv_text = "name,ats,slug\nLive,greenhouse,live\nEmpty,greenhouse,empty\n"
    dpath = _write(tmp_path, "d.csv", csv_text)
    cj = _companies_json(tmp_path)

    res1 = ds.seed_from_dataset(dpath, "controls_engineering", probe=_probe,
                                companies_json_path=cj, existing=set())
    assert res1["added"] == 1
    saved = get_registry(user_json=cj)
    assert any(e.slug == "live" and e.ats_type == "greenhouse" for e in saved)

    # Re-run: the live board is now known -> lift-only, nothing added.
    res2 = ds.seed_from_dataset(dpath, "controls_engineering", probe=_probe,
                                companies_json_path=cj)
    assert res2["added"] == 0
    assert res2["skipped_known"] >= 1
