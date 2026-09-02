"""Review is the stranger front door — grade, exit code, and --json must stay stable."""
from __future__ import annotations

import json
import os
import tempfile

from helicon.review import format_review, main, review, review_summary


def _repo(files: dict[str, str]) -> str:
    d = tempfile.mkdtemp()
    for rel, body in files.items():
        p = os.path.join(d, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True) if os.path.dirname(p) else None
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(body)
    return d


def test_clean_repo_grades_a_and_exits_zero():
    d = _repo({
        "docs/SETUP.md": "# setup\n",
        "CLAUDE.md": "Read `docs/SETUP.md`.\n",
    })
    res = review(d)
    assert main([d]) == 0
    out = format_review(d, res)
    assert "GRADE A" in out
    assert "tells its agent the truth" in out


def test_broken_pointer_grades_low_and_exits_one():
    d = _repo({
        "CLAUDE.md": "Always read `docs/MISSING.md` first.\n",
    })
    res = review(d)
    assert main([d]) == 1
    out = format_review(d, res)
    assert "GRADE" in out
    assert "MISSING" in out
    assert "re-run" in out


def test_no_instruction_file_exits_two():
    d = _repo({"README.md": "# hi\n"})
    assert main([d]) == 2
    out = format_review(d, review(d))
    assert "No agent instruction file" in out
    assert "Add AGENTS.md" in out


def test_json_shape_for_ci():
    d = _repo({
        "CLAUDE.md": "See `gone/missing.py`.\n",
    })
    res = review(d)
    summary = review_summary(d, res)
    assert summary["broken"] >= 1
    assert summary["clean"] is False
    assert summary["findings"]
    assert summary["findings"][0]["tier"] == "pointer"
    payload = json.loads(json.dumps(summary))
    assert payload["grade"] in ("C", "D", "F")
