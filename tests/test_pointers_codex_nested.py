"""Regression: openai/codex false positives, 2026-09-24.

`helicon review .` on an openai/codex clone reported 10 dead pointers. 8 were false:
  - root AGENTS.md opens "In the codex-rs folder", and paths such as
    `app-server-protocol/src/protocol/v2/` exist under codex-rs/, not the repo root;
  - `thread/read`, `app/list` are RPC method names, `rawResponseItem/*` an event
    family, `/*param_name*/` a Rust comment. None is a path.
The fixture in tests/fixtures/codex-nested vendors that shape with `rs/` for
`codex-rs/`, plus a nested rs/AGENTS.md whose paths are relative to rs/. It keeps
the two TRUE misses from the real run (`core/context`, a stale `v2.rs`) and one stale
path in the nested file, so the fix cannot buy precision with recall.
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from helicon import pointers as P

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "codex-nested"


def _copy() -> str:
    d = os.path.join(tempfile.mkdtemp(), "repo")
    shutil.copytree(FIXTURE, d)
    P._TREE_CACHE.clear()
    return d


def _broken(res):
    return sorted((r["receipt"].split(" — ")[0], r["raw"]) for r in res["receipts"])


def test_codex_shape_flags_only_the_true_misses():
    res = P.check_pointers(_copy())
    assert res["files"] == ["AGENTS.md", "rs/AGENTS.md"]
    assert _broken(res) == [
        ("AGENTS.md:15", "`app-server-protocol/src/protocol/v2.rs`"),
        ("AGENTS.md:6", "`core/context`"),
        ("rs/AGENTS.md:5", "`tui/src/bottom_pane/legacy.rs`"),
    ]
    assert res["checked"] == 8 and res["broken"] == 3


def test_rpc_names_and_comment_tokens_are_not_graded():
    res = P.check_pointers(_copy())
    raws = {r["raw"] for r in res["receipts"]}
    for tok in ("thread/read", "app/list", "rawResponseItem/*", "/*param_name*/",
                "*param_name*/"):
        assert f"`{tok}`" not in raws, tok
    # `app` IS a directory in the fixture (rs/tui/src/app), as in codex. The evidence
    # test is anchored, so it must not rescue `app/list` as a path.
    assert os.path.isdir(os.path.join(FIXTURE, "rs/tui/src/app"))


def test_nested_file_resolves_from_its_own_directory_first():
    d = _copy()
    text = open(os.path.join(d, "rs/AGENTS.md")).read()
    got = {p.target: p for p in P.extract_pointers(text, d, "rs")}
    # docs/guide.md exists at the root AND under rs/. The nested file means rs/docs.
    assert got["docs/guide.md"].resolved
    assert got["docs/guide.md"].base == "own dir rs/"
    assert got["app-server-protocol/src/protocol/v2/"].base == "own dir rs/"


def test_root_file_falls_back_and_names_the_base():
    d = _copy()
    text = open(os.path.join(d, "AGENTS.md")).read()
    got = {p.target: p for p in P.extract_pointers(text, d)}
    assert got["app-server-protocol/src/protocol/v2/"].resolved
    assert got["app-server-protocol/src/protocol/v2/"].base == "under rs/"
    assert "resolved from under rs/" in got["app-server-protocol/src/protocol/v2/"].receipt


def test_stale_path_goes_red_and_turns_green_when_the_file_appears():
    # The check must be able to go both ways, or it is not a check.
    d = _copy()
    before = P.check_pointers(d)
    assert ("AGENTS.md:15", "`app-server-protocol/src/protocol/v2.rs`") in _broken(before)
    assert "tried repo root, tree suffix" in next(
        r["receipt"] for r in before["receipts"] if "v2.rs" in r["raw"])
    # A fixture copy elsewhere in the tree must NOT rescue the stale pointer.
    junk = os.path.join(d, "fixtures/junk/app-server-protocol/src/protocol")
    os.makedirs(junk)
    open(os.path.join(junk, "v2.rs"), "w").write("//\n")
    P._TREE_CACHE.clear()
    assert ("AGENTS.md:15", "`app-server-protocol/src/protocol/v2.rs`") in _broken(P.check_pointers(d))
    open(os.path.join(d, "rs/app-server-protocol/src/protocol/v2.rs"), "w").write("//\n")
    P._TREE_CACHE.clear()
    after = P.check_pointers(d)
    assert all("v2.rs" not in r["raw"] for r in after["receipts"])
    assert after["broken"] == before["broken"] - 1


def test_bare_noun_verb_is_skipped_but_real_prefix_dir_is_graded():
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "core"))
    P._TREE_CACHE.clear()
    broken = [p.target for p in P.extract_pointers(
        "Call `thread/read`, keep `core/stale_mod` in sync, see `docs/old/`.", d)
        if not p.resolved]
    assert broken == ["core/stale_mod", "docs/old/"]


def test_fixture_dirs_are_not_scanned_as_nested_instruction_files():
    # Helicon's own repo carries deliberately broken fixtures. They are not its setup.
    repo = str(Path(__file__).resolve().parents[1])
    P._TREE_CACHE.clear()
    nested = P.nested_instruction_files(repo)
    assert not any("fixtures/" in f or f.startswith("bench/") for f in nested), nested
