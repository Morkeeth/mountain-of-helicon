"""R13 — document vs live system.

The fixture is a miniature of the FAVOUR failure: a repo whose instruction doc
asserts a capability the code has retired, holds a feature pending a condition,
names files that do exist, quotes a command with its result, and makes an
on-chain claim nothing here can check. The four verdicts must come out right
for the right reasons — especially the two negatives, because a class that
flags a true sentence teaches the human to ignore the feed, and a class that
passes an unrunnable probe is worse than no class at all.
"""
import os
import subprocess

import pytest

from helicon.probes import (CONTRADICTED, UNVERIFIABLE, UPHELD,
                            content_tokens, find_kill_switches, probe_docs,
                            split_assertions)


DOC = """# WIDGET (formerly SPROCKET)

## Context
- Next.js app, identity checks, on-chain USDC escrow (Chain 480)
- Rebrand in progress: SPROCKET -> WIDGET (copy only)

## Rules
- Board ranking lives in `src/lib/board-rank.ts` and its guard test.
- Campaign cash unlocks only through the clean gate: verified humans, no flags.
- The source no longer exists. `git log --all -S"fundTask" -- '*.sol'` = 0 commits;
  the contract is unverified on the explorer.
- **The upgrade authority is `owner()` = `0x1101...D70e` — the RELAYER HOT WALLET.**

**Sequencing rule this creates:** do NOT open user self-funding until the upgrade
authority is off the hot wallet.
"""

CUSTODY = """/**
 * CUSTODY IS RETIRED. Real money still moves: the campaign unlock pays by
 * plain ERC-20 transfer, and that is not custody. Points are untouched.
 */
export const CUSTODY_RETIRED = true;
"""

ROUTE = """import { CUSTODY_RETIRED } from "@/lib/custody";

export async function POST(req) {
  if (CUSTODY_RETIRED) {
    return Response.json({
      error: "Custody retired",
      detail: "WIDGET no longer holds funds in escrow. Points are unaffected.",
    }, { status: 410 });
  }
}
"""

RANK = "export function rankBoard(rows) { return rows; }\n"


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "src" / "lib").mkdir(parents=True)
    (tmp_path / "src" / "app" / "api" / "agent" / "fund").mkdir(parents=True)
    (tmp_path / "CLAUDE.md").write_text(DOC)
    (tmp_path / "src" / "lib" / "custody.ts").write_text(CUSTODY)
    (tmp_path / "src" / "lib" / "board-rank.ts").write_text(RANK)
    (tmp_path / "src" / "app" / "api" / "agent" / "fund" / "route.ts").write_text(ROUTE)
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    for cmd in (["git", "init", "-q"], ["git", "add", "-A"],
                ["git", "commit", "-qm", "fixture"]):
        subprocess.run(cmd, cwd=tmp_path, env=env, check=True,
                       capture_output=True)
    return str(tmp_path)


def _by_line(results):
    return {(r["line"], r["kind"]): r for r in results}


def test_kill_switch_scope_is_what_the_gate_closes(repo):
    """Scope comes from the gate's own message, not the module's prose. The
    docblock talks about campaign payouts and points precisely to protect
    them; a scope built from prose would claim them."""
    switches = find_kill_switches(repo)
    assert [s["name"] for s in switches] == ["CUSTODY_RETIRED"]
    scope = switches[0]["scope"]
    assert "escrow" in scope and "custody" in scope
    assert "campaign" not in scope, "the switch must not claim what it spared"
    assert "point" not in scope, "'Points are unaffected' is not territory"


def test_retired_capability_is_contradicted_with_real_output(repo):
    """The escrow sentence: asserted as current under a capability heading,
    retired in code. The receipt must be the probe's own stdout."""
    hit = [r for r in probe_docs(None, repo)
           if r["kind"] == "killswitch" and "USDC escrow" in r["sentence"]]
    assert len(hit) == 1
    r = hit[0]
    assert r["verdict"] == CONTRADICTED
    assert "escrow" in r["why"]
    assert "CUSTODY_RETIRED" in r["output"]
    assert any("410" in e["output"] for e in r["evidence"]), \
        "the 410 the route actually returns is the point"


def test_feature_held_pending_a_condition_that_will_never_come(repo):
    held = [r for r in probe_docs(None, repo)
            if r["kind"] == "killswitch" and "self-funding" in r["sentence"]]
    assert len(held) == 1 and held[0]["verdict"] == CONTRADICTED


def test_true_sentences_are_not_flagged(repo):
    """The failure mode that makes the whole class worthless."""
    flagged = {r["sentence"] for r in probe_docs(None, repo)
               if r["verdict"] == CONTRADICTED}
    for still_true in ("Campaign cash unlocks", "Rebrand in progress"):
        assert not any(still_true in s for s in flagged), \
            f"flagged a sentence that is still true: {still_true}"


def test_acknowledged_retirement_is_not_flagged(repo, tmp_path):
    """A doc that already says the thing is retired is not drifting."""
    doc = os.path.join(repo, "CLAUDE.md")
    with open(doc, "a") as fh:
        fh.write("\n- The USDC escrow is retired and no longer takes deposits.\n")
    flagged = [r for r in probe_docs(None, repo)
               if r["verdict"] == CONTRADICTED and "retired and no longer" in r["sentence"]]
    assert not flagged


def test_unrunnable_probe_is_unverifiable_never_upheld(repo):
    """No RPC and an elided address: the honest answer is 'I did not check'."""
    chain = [r for r in probe_docs(None, repo) if r["kind"] == "chain"]
    assert len(chain) == 1
    assert chain[0]["verdict"] == UNVERIFIABLE
    assert chain[0]["verdict"] != UPHELD
    assert "elides" in chain[0]["why"] or "RPC" in chain[0]["why"]


def test_network_probe_stays_off_by_default(repo):
    """allow_network defaults False, so no probe reaches the wire unasked."""
    for r in probe_docs(None, repo, allow_network=False):
        if r["kind"] == "chain":
            assert r["verdict"] == UNVERIFIABLE


def test_self_probing_command_is_run_and_upheld(repo):
    """`git log -S"fundTask" -- '*.sol'` = 0 commits — the doc quotes its own
    evidence, so the sentence carries a probe with no derivation needed."""
    cmds = [r for r in probe_docs(None, repo) if r["kind"] == "command"]
    assert len(cmds) == 1
    assert cmds[0]["verdict"] == UPHELD
    assert cmds[0]["output"] == "0"


def test_command_probe_catches_a_wrong_stated_result(repo):
    doc = os.path.join(repo, "CLAUDE.md")
    text = open(doc).read().replace("= 0 commits", "= 7 commits")
    open(doc, "w").write(text)
    cmds = [r for r in probe_docs(None, repo) if r["kind"] == "command"]
    assert cmds and cmds[0]["verdict"] == CONTRADICTED
    assert "7" in cmds[0]["why"] and "0" in cmds[0]["why"]


def test_named_file_present_is_upheld_missing_is_contradicted(repo):
    paths = [r for r in probe_docs(None, repo) if r["kind"] == "path"]
    assert any(p["verdict"] == UPHELD and "board-rank" in p["probe"] for p in paths)

    doc = os.path.join(repo, "CLAUDE.md")
    with open(doc, "a") as fh:
        fh.write("\n- Settlement rules live in `src/lib/settlement.ts`.\n")
    gone = [r for r in probe_docs(None, repo)
            if r["kind"] == "path" and "settlement.ts" in r["probe"]]
    assert gone and gone[0]["verdict"] == CONTRADICTED


def test_only_enforced_retirements_count(tmp_path):
    """A comment saying 'deprecated' changes no behaviour. Only a switch the
    code branches on is the running system speaking."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "thing.ts").write_text(
        "// DEPRECATED: we should really turn the escrow off one day\n"
        "export const ESCROW_ENABLED = true;\n")
    assert find_kill_switches(str(tmp_path)) == []


def test_tests_are_not_gates(tmp_path):
    """A guard test proves a switch works; its fixtures are not its territory."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "__tests__").mkdir()
    (tmp_path / "src" / "custody.ts").write_text("export const CUSTODY_RETIRED = true;\n")
    (tmp_path / "src" / "__tests__" / "guard.test.ts").write_text(
        'import { CUSTODY_RETIRED } from "../custody";\n'
        '// real money moves through this now and people rely on it\n'
        'expect(CUSTODY_RETIRED).toBe(true);\n')
    switches = find_kill_switches(str(tmp_path))
    assert all("money" not in s["scope"] for s in switches)


def test_assertions_carry_their_heading(repo):
    blocks = split_assertions(DOC)
    escrow = [b for b in blocks if "USDC escrow" in b["text"]]
    assert escrow and escrow[0]["heading"] == "Context"


def test_tokens_normalise_across_word_forms():
    assert "fund" in content_tokens("self-funding")
    assert "fund" in content_tokens("no longer holds funds")
    assert "escrow" in content_tokens("createEscrowTaskWithKey")


def test_probe_scan_files_once_and_is_idempotent(repo, tmp_path):
    from helicon.db import init_db
    from helicon.probes import probe_scan
    conn = init_db(str(tmp_path / "probe.db"))
    first = probe_scan(conn, repo)
    assert first["contradicted"] >= 2 and first["filed"]
    second = probe_scan(conn, repo)
    assert not second["filed"] and second["already_filed"]
    rows = conn.execute(
        "SELECT COUNT(*) FROM audit_log WHERE details LIKE '%probe_key%'"
    ).fetchone()[0]
    assert rows == len(first["filed"])


def test_rot_exam_reports_r13_and_says_when_it_cannot(tmp_path, repo):
    from helicon.db import init_db
    from helicon.rot import run_rot_exam
    conn = init_db(str(tmp_path / "exam.db"))

    res = run_rot_exam(conn)
    r13 = [c for c in res["checks"] if c["id"] == "R13"][0]
    assert r13["verdict"] == "UNMEASURED", "no repo means unmeasured, not clean"

    res = run_rot_exam(conn, repo_root=repo)
    r13 = [c for c in res["checks"] if c["id"] == "R13"][0]
    assert r13["verdict"] == "ROT FOUND"
    assert "contradicted by the running system" in r13["receipt"]
