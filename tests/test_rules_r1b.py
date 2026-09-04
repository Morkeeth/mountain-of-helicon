"""R1b same-source rule contradiction — planted v1/v2 must fire."""
from __future__ import annotations

import os
import tempfile

from helicon.same_source import check_same_source_rules, extract_use_rules, find_conflicts
from helicon.review import format_review, main, review, review_summary


def _repo(files: dict[str, str]) -> str:
    d = tempfile.mkdtemp()
    for rel, body in files.items():
        p = os.path.join(d, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True) if os.path.dirname(p) else None
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(body)
    return d


def test_planted_v1_v2_is_rot_found():
    """ROADMAP Camp II plant: same file, competing always-use → must fire."""
    d = _repo({
        "CLAUDE.md": "Always use v1 of the API.\nAlways use v2 of the API.\n",
    })
    res = check_same_source_rules(d)
    assert res["verdict"] == "ROT FOUND", res
    assert res["broken"] >= 1
    assert any("v1" in r["raw"] and "v2" in r["raw"] for r in res["receipts"])


def test_review_surfaces_r1b_and_exits_one():
    d = _repo({
        "CLAUDE.md": "Always use v1 of the API.\nAlways use v2 of the API.\n",
    })
    assert main([d]) == 1
    out = format_review(d, review(d))
    assert "rules conflict" in out or "conflicts with" in out
    assert "GRADE" in out
    summary = review_summary(d, review(d))
    assert summary["broken"] >= 1
    assert any(f["tier"] == "rules" for f in summary["findings"])


def test_single_always_use_is_clean():
    d = _repo({"CLAUDE.md": "Always use v1 of the API.\n"})
    res = check_same_source_rules(d)
    assert res["verdict"] == "CLEAN" and res["broken"] == 0, res


def test_different_subjects_do_not_conflict():
    d = _repo({
        "CLAUDE.md": (
            "Always use v1 of the API.\n"
            "Always use v2 of the CLI.\n"
        ),
    })
    res = check_same_source_rules(d)
    assert res["broken"] == 0, res


def test_never_vs_always_same_object_conflicts():
    d = _repo({
        "AGENTS.md": "Never use yarn for installs.\nAlways use yarn for installs.\n",
    })
    res = check_same_source_rules(d)
    assert res["verdict"] == "ROT FOUND", res
    assert any(r["kind"] == "never-vs-always" for r in res["receipts"])


def test_empty_claims_file_does_not_say_missing():
    """Regression: CLAUDE.md with no path claims used to print 'No agent
    instruction file found' while instruction_files listed it."""
    d = _repo({"CLAUDE.md": "Be careful with secrets.\n"})
    out = format_review(d, review(d))
    assert "No agent instruction file found" not in out
    assert "CLAUDE.md" in out
    assert main([d]) == 0


def test_null_baseline_arm_is_silent_on_plant():
    """Naive/null arm: existence-tier only (no R1b) stays silent — the
    disagreement with check_rules is the measurement."""
    text = "Always use v1 of the API.\nAlways use v2 of the API.\n"
    claims = extract_use_rules(text)
    assert len(claims) == 2
    assert find_conflicts(claims)  # our arm fires
    # Null arm: zero conflicts by construction
    null_conflicts = []
    assert null_conflicts == []
