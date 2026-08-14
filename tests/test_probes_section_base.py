"""R13 read section-relative routes as broken ones.

From openai/codex at 8630bb3, 2026-08-14. AGENTS.md:262 says

    These guidelines apply to app-server protocol work in `codex-rs`, especially:

and lists three routes beneath it. All three files exist under codex-rs/.
R13 resolved every documented path against the repo root, so it reported three
of them CONTRADICTED — 1-in-4 precision on the one file we were about to put in
front of a stranger, in a PR that would have asked them to apply the fix.

The tell was inside the document: line 265 is identical in form to 264 and 266
and was not flagged, so the rule was inconsistent within a single list. A
finding that disagrees with itself three bullets apart is a pattern match, not
a reading.

The rules these tests defend:
  a route under a declared base is UPHELD, not contradicted;
  a base is only believed when the directory is really there;
  a subsection inherits its parent's base, a sibling heading does not.
"""
import subprocess

import pytest

from helicon.probes import probe_docs, split_assertions


def _repo(tmp_path, name, files, doc):
    repo = tmp_path / name
    repo.mkdir()
    for rel in files:
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x\n")
    (repo / "CLAUDE.md").write_text(doc)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.email=a@a", "-c", "user.name=a",
                    "commit", "-qm", "planted"], cwd=repo, check=True)
    return str(repo)


def _paths(conn, repo):
    return [r for r in probe_docs(conn, repo) if r["kind"] == "path"]


@pytest.fixture
def conn(tmp_path):
    from helicon.db import init_db
    return init_db(str(tmp_path / "t.db"))


CODEX_SHAPE = """# Rules

## Protocol work

These guidelines apply to protocol work in `sub`, especially:

- `pkg/src/one.rs`
- `pkg/src/two.rs`
- `pkg/README.md`
"""


def test_routes_under_a_declared_base_are_upheld(conn, tmp_path):
    repo = _repo(tmp_path, "declared",
                 ["sub/pkg/src/one.rs", "sub/pkg/src/two.rs", "sub/pkg/README.md"],
                 CODEX_SHAPE)
    verdicts = [r["verdict"] for r in _paths(conn, repo)]
    assert verdicts.count("CONTRADICTED") == 0, verdicts
    assert verdicts.count("UPHELD") == 3, verdicts


def test_a_base_the_repo_does_not_have_is_not_believed(conn, tmp_path):
    """A sentence must not be able to invent a base and launder a dead route."""
    doc = CODEX_SHAPE.replace("`sub`", "`nowhere`")
    repo = _repo(tmp_path, "invented", ["sub/pkg/src/one.rs"], doc)
    verdicts = [r["verdict"] for r in _paths(conn, repo)]
    assert "UPHELD" not in verdicts, verdicts


def test_a_genuinely_dead_route_still_fires_under_a_base(conn, tmp_path):
    """The fix must not buy precision by making R13 unable to contradict."""
    doc = CODEX_SHAPE + "\nAlso read `pkg/src/gone.rs` before changing it.\n"
    repo = _repo(tmp_path, "still-fires",
                 ["sub/pkg/src/one.rs", "sub/pkg/src/two.rs", "sub/pkg/README.md"],
                 doc)
    assert any(r["verdict"] == "CONTRADICTED" and "gone.rs" in r["sentence"]
               for r in _paths(conn, repo))


def test_a_subsection_inherits_the_base_a_sibling_does_not(conn, tmp_path):
    """codex re-routes to the same base under '### Core Rules' 38 lines later.
    Clearing on every heading left that bullet broken while its two identical
    neighbours were fixed — the inconsistency that started this."""
    doc = CODEX_SHAPE + """
### Core Rules

- Update the docs, at minimum `pkg/README.md`.

## Something Else

- The changelog lives at `pkg/CHANGELOG.md`.
"""
    repo = _repo(tmp_path, "nesting",
                 ["sub/pkg/src/one.rs", "sub/pkg/src/two.rs", "sub/pkg/README.md",
                  "sub/pkg/CHANGELOG.md"],
                 doc)
    by_sentence = {r["sentence"]: r["verdict"] for r in _paths(conn, repo)}
    sub = next(v for s, v in by_sentence.items() if "Update the docs" in s)
    sibling = next(v for s, v in by_sentence.items() if "changelog" in s)
    assert sub == "UPHELD", by_sentence
    assert sibling != "UPHELD", by_sentence


def test_split_assertions_reports_heading_depth():
    """The depth has to survive the sentence-splitting pass at the end of
    split_assertions, which rebuilds every block dict from scratch. The first
    version of this fix set heading_level on the intermediate blocks and that
    pass silently dropped it, so the base never cleared and a sibling heading
    inherited. Caught here, not in review."""
    blocks = split_assertions(
        "# A\n\nThe service reads its config at start.\n\n"
        "## B\n\nThe worker retries three times.\n")
    depths = {b["text"]: b["heading_level"] for b in blocks}
    assert depths["The service reads its config at start."] == 1
    assert depths["The worker retries three times."] == 2
