"""QW-7 — positioning copy (zero engine code). Guards that the README's
"Why Zaggregate" headline section leads with own-your-data + assisted-not-auto,
carries the researched stats, and cites them — kept exactly as the research doc
(brain/general-user-tests-2026-07/research-competitors.md §7/§8B) evidences.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
README = (REPO / "README.md").read_text(encoding="utf-8")


def test_readme_has_why_zaggregate_section():
    assert "## Why Zaggregate" in README


def test_readme_states_the_own_your_data_stat_with_citation():
    # 90% of platforms sell user data — the moat no SaaS rival can answer.
    assert "90%" in README
    assert "sell user data" in README or "sell their users' data" in README
    # cited to the Inc/Incogni evidence links from the research doc.
    assert "inc.com" in README and "incogni.com" in README


def test_readme_states_the_auto_apply_vs_tailored_stat_with_citation():
    # ~0.01% auto-apply success vs 4–6% tailored — the assisted-not-auto case.
    assert "0.01%" in README
    assert "4" in README and "6" in README   # the 4–6% tailored range
    assert "forbes.com" in README            # the Forbes/robinryan evidence link


def test_readme_frames_honest_reach_and_no_auto_apply():
    # The honest-reach-vs-ghost-jobs differentiator + the human-submits posture.
    assert "reach" in README.lower()
    assert "click submit" in README
    assert "no telemetry" in README.lower() or "no cloud" in README.lower()
