"""Regression: colinhacks/zod false positives, 2026-09-25 stranger test.

`helicon review .` on a zod clone (PyPI 0.2.1) printed GRADE C with 24 contradictions.
Most were false:
  - CLAUDE.md and .cursorrules are symlinks to AGENTS.md, so every row was counted 3x;
  - `core/` and `core/regexes.ts` exist under packages/zod/src/v4/ (a monorepo package);
  - `--conditions=@zod/source` is a CLI flag;
  - the `//` in "stacked `//` comment lines" normalized to an empty target;
  - `.triage/` is gitignored, so a clone never has it.
tests/fixtures/zod-shaped vendors that shape, plus one real stale path (`docs/GONE.md`)
that must stay red, so the fix cannot buy precision with recall.
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from helicon import pointers as P
from helicon.review import format_review, review, review_summary

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "zod-shaped"

pytestmark = pytest.mark.skipif(os.name == "nt", reason="fixture uses symlinks")


def _copy() -> str:
    d = os.path.join(tempfile.mkdtemp(), "zod")
    shutil.copytree(FIXTURE, d, symlinks=True)
    P._TREE_CACHE.clear()
    P._WS_CACHE.clear()
    P._IGNORE_CACHE.clear()
    return d


def test_fixture_symlinks_survived_checkout():
    # If git or a copy flattened the links, the dedupe test below proves nothing.
    assert os.path.islink(FIXTURE / "CLAUDE.md")
    assert os.path.islink(FIXTURE / ".cursorrules")


def test_only_the_real_stale_path_is_red():
    res = P.check_pointers(_copy())
    assert [(r["receipt"].split(" — ")[0], r["raw"]) for r in res["receipts"]] == [
        ("AGENTS.md:22", "`docs/GONE.md`"),
    ]
    assert res["broken"] == 1


def test_symlinked_instruction_files_are_graded_once():
    repo = _copy()
    res = P.check_pointers(repo)
    assert res["files"] == ["AGENTS.md"]
    assert res["aliases"] == {"AGENTS.md": ["CLAUDE.md", ".cursorrules"]}
    # The other tiers read the same population: one file, not three.
    full = review(repo, execute=False)
    assert full["commands"]["files"] == ["AGENTS.md"]
    assert full["versions"]["files"] in ([], ["AGENTS.md"])
    out = format_review(repo, full)
    assert "CLAUDE.md, .cursorrules are links to AGENTS.md, graded once" in out
    assert "CLAUDE.md:" not in out and ".cursorrules:" not in out
    summary = review_summary(repo, full)
    assert summary["broken"] == 1
    assert summary["instruction_aliases"] == {"AGENTS.md": ["CLAUDE.md", ".cursorrules"]}


def test_monorepo_package_paths_resolve():
    res = P.check_pointers(_copy())
    got = {r["raw"] for r in res["receipts"]}
    assert "`core/`" not in got and "`core/regexes.ts`" not in got and "`src/`" not in got
    # `src/` only exists inside a workspace package, so it proves the workspace rule.
    assert any(b.startswith("package packages/zod/") for b in res["bases"])


def test_flags_and_empty_targets_are_never_graded():
    repo = _copy()
    text = (Path(repo) / "AGENTS.md").read_text()
    raws = [p.raw for p in P.extract_pointers(text, repo)]
    assert not any("conditions" in r or "zod/source" in r for r in raws)
    assert not any(r.strip("`@") in ("", "//") for r in raws)
    assert P._resolve(repo, "--out=dist/x.js") is None
    assert P._resolve(repo, "//") is None


def test_gitignored_paths_are_create_on_demand():
    res = P.check_pointers(_copy())
    ignored = [g for g in res["unverified_paths"] if g["reason"].startswith("gitignored")]
    assert {g["raw"] for g in ignored} == {
        "`.triage/`", "`.triage/issues/NNNN/results.md`", "`.triage/prs/NNNN/results.md`",
    }


def test_stale_path_still_red_when_monorepo_rules_apply():
    # Guard against the new bases turning everything green: a path that exists
    # nowhere, in no package, stays a contradiction.
    repo = _copy()
    assert P._resolve(repo, "core/gone.ts", "", ("packages/zod/src/v4",)) == ("core/gone.ts", False, "")
