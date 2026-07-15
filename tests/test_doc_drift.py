"""Stale docs fail the build: doc claims must match source truth.

This is the dogfood check made permanent. On Jul 4 the README claimed 8 MCP
tools while source had 11, and that class of drift became a test failure.

On Jul 15 the same audit found the check had a blind spot wide enough to drive
the docs through: it read only README.md, only headline numbers, and compared
eval metrics against nothing. So CLAUDE.md drifted four numbers, "MCP Server (14
tools)" sat on top of a 12-row table, and ROT.md's 12-class catalogue rendered
11 rows, all while docdrift printed PASS. These tests pin the three shapes:
COUNT (number vs source), LIST (declared count vs the list beneath it), and EVAL
(metric vs data/eval-latest.json).

The mutation tests below are the important ones. A checker nobody has watched
fail is a checker nobody knows works, so each one reintroduces a real lie from
the Jul 15 audit into a temp copy of the repo and asserts the check catches it.
"""
import json
import os
import re
import shutil

import pytest

from helicon.docdrift import (
    REPO_ROOT,
    check_counts,
    check_docs,
    check_evals,
    check_lists,
    check_readme,
    count_cli_commands,
    count_mcp_tools,
    count_rot_classes,
    count_tables,
)

DOCS = ["README.md", "CLAUDE.md", "ARCHITECTURE.md", "ROT.md"]


def _drifted(results):
    return [r for r in results if not r["ok"]]


def _why(results):
    return "; ".join(f"{r['doc']} {r['claim']}: {r['why']}" for r in _drifted(results))


# --------------------------------------------------------------------------
# The live docs must be true. These are the checks that fail the build.
# --------------------------------------------------------------------------

def test_docs_match_source():
    results = check_docs()
    assert not _drifted(results), "docs drifted from source: " + _why(results)


def test_check_readme_alias_still_works():
    """rot.py's R2 calls check_readme(repo_root). Keep that contract."""
    assert not _drifted(check_readme(REPO_ROOT))


def test_every_doc_is_actually_checked():
    """The v1 bug was scope, not logic: CLAUDE.md drifted because nothing read it."""
    checked = {r["doc"] for r in check_docs()}
    for doc in DOCS:
        assert doc in checked, f"{doc} has claims but nothing checks it"


def test_all_three_shapes_are_covered():
    kinds = {r["kind"] for r in check_docs()}
    assert kinds == {"count", "list", "eval"}


# --------------------------------------------------------------------------
# Mutation tests: reintroduce a real Jul 15 lie, assert the check bites.
# --------------------------------------------------------------------------

@pytest.fixture
def repo(tmp_path):
    """A copy of the docs + data the checkers read, so we can lie to them safely."""
    for doc in DOCS:
        shutil.copy(os.path.join(REPO_ROOT, doc), tmp_path / doc)
    os.mkdir(tmp_path / "data")
    shutil.copy(os.path.join(REPO_ROOT, "data", "eval-latest.json"),
                tmp_path / "data" / "eval-latest.json")
    return tmp_path


def _mutate(repo, doc, old, new):
    path = repo / doc
    text = path.read_text()
    assert old in text, f"fixture drifted: {old!r} not in {doc}"
    path.write_text(text.replace(old, new, 1))


def _fails(results, claim, doc):
    hits = [r for r in results if r["claim"] == claim and r["doc"] == doc]
    assert hits, f"no claim {claim!r} checked in {doc}"
    return [r for r in hits if not r["ok"]]


def test_baseline_copy_is_clean(repo):
    """Every mutation below must be the only reason the check fails."""
    assert not _drifted(check_docs(str(repo))), _why(check_docs(str(repo)))


def test_count_drift_in_claude_md_is_caught(repo):
    """The real Jul 15 lie: CLAUDE.md said 11 MCP tools while source had 14."""
    _mutate(repo, "CLAUDE.md", "MCP Server (14 tools", "MCP Server (11 tools")
    assert _fails(check_counts(str(repo)), "MCP tools", "CLAUDE.md")


def test_count_drift_in_readme_still_caught(repo):
    """v1's one real skill must not regress."""
    _mutate(repo, "README.md", "MCP Server (14 tools)", "MCP Server (8 tools)")
    assert _fails(check_counts(str(repo)), "MCP tools", "README.md")


def test_word_number_drift_is_caught(repo):
    """README said 'the ten-class deterministic exam' while the exam runs 12."""
    _mutate(repo, "README.md", "12-class deterministic exam",
            "ten-class deterministic exam")
    assert _fails(check_counts(str(repo)), "rot classes", "README.md")


def test_count_right_but_list_short_is_caught(repo):
    """The headline bug: 'MCP Server (14 tools)' above a 12-row table passed v1.

    The count still matches source, so only the LIST check can see this.
    """
    text = (repo / "README.md").read_text()
    rows = re.findall(r"^\| `helicon_\w+` \|.*$", text, re.M)
    assert len(rows) == count_mcp_tools()
    (repo / "README.md").write_text(text.replace(rows[-1] + "\n", "", 1))

    assert not _fails(check_counts(str(repo)), "MCP tools", "README.md"), \
        "the count alone still matches: this is exactly why v1 missed it"
    assert _fails(check_lists(str(repo)), "MCP tools table", "README.md")


def test_cli_list_short_is_caught(repo):
    """README said 43 commands and listed 39."""
    _mutate(repo, "README.md", "`volatility` `guard` ", "")
    assert _fails(check_lists(str(repo)), "CLI commands list", "README.md")


def test_claude_md_table_list_drift_is_caught(repo):
    """CLAUDE.md declared 18 tables and listed 18, while source had 24."""
    _mutate(repo, "CLAUDE.md", ", route_evidence, run_cards, judge_runs)", ")")
    _mutate(repo, "CLAUDE.md", "(25 tables:", "(23 tables:")
    assert _fails(check_lists(str(repo)), "tables list", "CLAUDE.md")


def test_rot_catalogue_row_loss_is_caught(repo):
    """The bug found by counting rows: R11 glued onto R10 rendered 11 of 12."""
    text = (repo / "ROT.md").read_text()
    assert text.count("\n| R11 |") == 1
    (repo / "ROT.md").write_text(text.replace("**TESTED** |\n| R11 |", "**TESTED** | R11 |", 1))
    assert _fails(check_lists(str(repo)), "rot catalogue rows", "ROT.md")


def test_eval_drift_against_json_is_caught(repo):
    """CLAUDE.md claimed decay AUC 0.877; eval-latest.json says 0.781."""
    _mutate(repo, "CLAUDE.md", "rank-AUC 0.781", "rank-AUC 0.877")
    assert _fails(check_evals(str(repo)), "decay rank-AUC", "CLAUDE.md")


def test_eval_follows_the_json_not_a_hardcoded_copy(repo):
    """Move the source of truth: the docs, unchanged, must now be wrong.

    This is the property that matters. If the expected value were hardcoded in
    docdrift, this test could not fail, and the check would be a second copy of
    the number rather than a check on it.
    """
    path = repo / "data" / "eval-latest.json"
    blob = json.loads(path.read_text())
    blob["sub_goals"]["efficient_storage_retrieval"]["mrr"] = 0.123
    path.write_text(json.dumps(blob))
    assert _fails(check_evals(str(repo)), "retrieval MRR", "README.md")
    assert _fails(check_evals(str(repo)), "retrieval MRR", "CLAUDE.md")


def test_honest_rounding_is_allowed_but_wrong_rounding_is_not(repo):
    """README rounds 0.692 to 0.69, which is honest. 0.71 is not."""
    assert not _fails(check_evals(str(repo)), "retrieval P@3", "README.md")
    _mutate(repo, "README.md", "P@3 0.69,", "P@3 0.71,")
    assert _fails(check_evals(str(repo)), "retrieval P@3", "README.md")


def test_deleting_a_claim_is_not_a_way_to_pass(repo):
    """The cheapest fake fix is removing the number. It must fail, not pass."""
    _mutate(repo, "CLAUDE.md", "- 23 routers (~92 endpoints), 14 MCP tools", "- routers, MCP tools")
    drift = _fails(check_counts(str(repo)), "API routers", "CLAUDE.md")
    assert drift and "not found" in drift[0]["why"]


# --------------------------------------------------------------------------
# The counters themselves: a checker is only as good as its source of truth.
# --------------------------------------------------------------------------

def test_counters_agree_with_the_running_system():
    from helicon.mcp_server import TOOLS
    assert count_mcp_tools() == len(TOOLS)
    assert count_rot_classes() == 12, "rot.py should define R1..R12"
    assert count_tables() > 20
    assert count_cli_commands() > 40


def test_cli_aliases_are_not_counted_as_commands():
    """battery/rot/heal/gold are second names for check/audit/repair/policy.

    Counting them would inflate the CLI number by four and make the README's
    list wrong in the other direction.
    """
    src = open(os.path.join(REPO_ROOT, "helicon", "cli.py")).read()
    aliased = re.findall(r'add_parser\("([a-z-]+)", aliases=\[([^\]]+)\]', src)
    assert aliased, "expected aliased subparsers"
    names = {a.strip().strip('"') for _p, group in aliased for a in group.split(",")}
    assert names == {"battery", "rot", "heal", "gold"}
    readme = open(os.path.join(REPO_ROOT, "README.md")).read()
    listed = re.search(r"## CLI \(\d+ commands\)\n\n(.+?)\n\n", readme, re.S).group(1)
    for alias in names:
        assert f"`{alias}`" not in listed, f"{alias} is an alias, not a command"
