"""Slice 3 — the gate refuses a run against a CONTRADICTED repo, and the only
human moment (an override) is logged with who + why.

Product rule: the machine applies every rule it can prove. A probe proved the
running code disproves the loaded doc, so the gate BLOCKS on its own — no human
asked. A human is pulled in only to override, and that override is auditable.
"""
import json
import subprocess

import pytest

from helicon import intervention, taskrun
from helicon.db import init_db


def _git(repo, *a):
    subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)


@pytest.fixture
def conn(tmp_path):
    return init_db(str(tmp_path / "g.db"))


def _favour(root):
    repo = root / "favour"
    (repo / "src" / "routes").mkdir(parents=True)
    (repo / "CLAUDE.md").write_text(
        "# FAVOUR\n\n## Context\n"
        "The on-chain USDC escrow is a current capability and user self-funding is live.\n")
    (repo / "src" / "custody.ts").write_text(
        "export const CUSTODY_RETIRED = true;\n")
    (repo / "src" / "routes" / "fund.ts").write_text(
        'import { CUSTODY_RETIRED } from "../custody";\n'
        "export function fund(req, res) {\n"
        "  if (CUSTODY_RETIRED) {\n"
        '    return res.status(410).json({ error: "on-chain USDC escrow custody retired" });\n'
        "  }\n}\n")
    _git(repo, "init", "-q"); _git(repo, "add", "-A")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x")
    return repo


def _clean(root):
    repo = root / "clean"
    repo.mkdir()
    (repo / "CLAUDE.md").write_text("# Clean\nKeep replies terse. Run tests with pytest.\n")
    _git(repo, "init", "-q"); _git(repo, "add", "-A")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x")
    return repo


def _full_contract():
    return {"beneficiary": "Oscar", "observable_change": "x", "evidence_source": "y"}


def test_gate_blocks_a_run_against_a_contradicted_repo(conn, tmp_path):
    repo = _favour(tmp_path)
    g = intervention.gate(conn, objective="ship the escrow flow",
                          acceptance_test="the escrow flow ships",
                          outcome_contract=_full_contract(), repo=str(repo))
    assert g["verdict"] == "blocked"
    assert "repo context" in g["blockers"]
    rc = next(c for c in g["checks"] if c["name"] == "repo context")
    assert "CONTRADICTED" in rc["reason"]


def test_gate_passes_repo_context_when_nothing_is_contradicted(conn, tmp_path):
    repo = _clean(tmp_path)
    g = intervention.gate(conn, objective="tidy the readme",
                          acceptance_test="the readme is tidy",
                          outcome_contract=_full_contract(), repo=str(repo))
    rc = next(c for c in g["checks"] if c["name"] == "repo context")
    assert rc["status"] == "ok"
    assert "repo context" not in g["blockers"]


def test_no_repo_means_no_repo_context_check(conn):
    g = intervention.gate(conn, objective="obj", acceptance_test="acceptance stated",
                          outcome_contract=_full_contract())
    assert not any(c["name"] == "repo context" for c in g["checks"])


def test_override_is_logged_with_who_and_why(conn):
    rid = taskrun.open_run(conn, "obj", "acceptance stated")
    ov = intervention.record_override(conn, rid, who="Oscar",
                                      reason="escrow is being rebuilt this run; the doc is intentionally ahead",
                                      blockers=["repo context"])
    assert ov["ok"] and ov["who"] == "Oscar"
    row = conn.execute(
        "SELECT actor, detail FROM run_events WHERE task_run_id=? AND kind='gate-override'",
        (rid,)).fetchone()
    assert row["actor"] == "Oscar"
    d = json.loads(row["detail"])
    assert d["reason"].startswith("escrow is being rebuilt")
    assert d["overrode"] == ["repo context"]


def test_override_without_a_reason_is_refused(conn):
    rid = taskrun.open_run(conn, "obj", "acceptance stated")
    assert intervention.record_override(conn, rid, who="Oscar", reason="  ",
                                        blockers=["repo context"])["ok"] is False
    assert conn.execute(
        "SELECT COUNT(*) FROM run_events WHERE kind='gate-override'").fetchone()[0] == 0
