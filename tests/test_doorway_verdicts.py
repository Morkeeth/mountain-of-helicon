"""Slice 2 — every loaded line carries a probe verdict, and demote-to-cold
makes the board counter fall.

Pins: a CLAUDE.md claim the running code disproves reads CONTRADICTED (with real
probe stdout); a claim no probe covers reads UNVERIFIABLE (a verdict, not a gap);
demoting a line to cold keeps it but drops it from the loaded total, so the board
counter falls; promoting restores it.
"""
import subprocess

import pytest

from helicon import doorway
from helicon.db import init_db


def _git(repo, *a):
    subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)


@pytest.fixture
def conn(tmp_path):
    return init_db(str(tmp_path / "d.db"))


def _favour(root):
    """A repo shaped like the real FAVOUR contradiction: the code enforces a
    retirement (CUSTODY_RETIRED + a 410 route) while CLAUDE.md still says the
    escrow is live."""
    repo = root / "favour"
    (repo / "src" / "routes").mkdir(parents=True)
    (repo / "CLAUDE.md").write_text(
        "# FAVOUR\n\n## Context\n"
        "The on-chain USDC escrow is a current capability and user self-funding is live.\n"
        "Keep replies terse.\n")
    (repo / "src" / "custody.ts").write_text(
        "// Custody was retired; the escrow no longer takes money.\n"
        "export const CUSTODY_RETIRED = true;\n")
    (repo / "src" / "routes" / "fund.ts").write_text(
        'import { CUSTODY_RETIRED } from "../custody";\n'
        "export function fund(req, res) {\n"
        "  if (CUSTODY_RETIRED) {\n"
        '    return res.status(410).json({ error: "on-chain USDC escrow custody retired" });\n'
        "  }\n}\n")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "retire")
    return repo


def test_contradicted_line_carries_real_probe_stdout(conn, tmp_path):
    _favour(tmp_path)
    detail = doorway.repo_detail(conn, str(tmp_path / "favour"))
    claim = next(l for doc in detail["docs"] for l in doc["lines"]
                 if "escrow is a current capability" in l["text"])
    assert claim["verdict"] == "CONTRADICTED"
    assert claim["probe"] and "CUSTODY_RETIRED" in claim["probe"]
    assert "CUSTODY_RETIRED = true" in (claim["output"] or "")
    assert detail["contradicted"] >= 1


def test_uncovered_line_is_unverifiable_not_a_gap(conn, tmp_path):
    _favour(tmp_path)
    detail = doorway.repo_detail(conn, str(tmp_path / "favour"))
    terse = next(l for doc in detail["docs"] for l in doc["lines"]
                 if "terse" in l["text"])
    assert terse["verdict"] == "UNVERIFIABLE"
    assert "not a gap" in terse["why"]


def test_demote_to_cold_drops_the_counter_but_keeps_the_line(conn, tmp_path):
    _favour(tmp_path)
    before = doorway.list_repos(root=str(tmp_path), conn=conn)
    favour_before = next(r for r in before["repos"] if r["name"] == "favour")
    assert favour_before["loaded_tokens"] > 0

    # demote the whole CLAUDE.md doc to cold (its full token weight)
    detail = doorway.repo_detail(conn, str(tmp_path / "favour"))
    doc = next(d for d in detail["docs"] if d["file"] == "CLAUDE.md")
    doorway.demote(conn, "favour", "CLAUDE.md", doc["tokens"], reason="rarely act here")

    after = doorway.list_repos(root=str(tmp_path), conn=conn)
    favour_after = next(r for r in after["repos"] if r["name"] == "favour")
    assert favour_after["loaded_tokens"] == 0                 # loads nothing
    assert favour_after["cold_tokens"] == doc["tokens"]       # kept, not deleted
    assert after["total_loaded_tokens"] < before["total_loaded_tokens"]  # counter fell

    # the line is still ON the board, marked cold
    d2 = doorway.repo_detail(conn, str(tmp_path / "favour"))
    doc2 = next(d for d in d2["docs"] if d["file"] == "CLAUDE.md")
    assert doc2["cold"] is True and doc2["loaded_tokens"] == 0
    assert doc2["lines"], "cold keeps every line, it just loads none of them"


def test_demote_one_line_only_subtracts_that_line(conn, tmp_path):
    _favour(tmp_path)
    detail = doorway.repo_detail(conn, str(tmp_path / "favour"))
    line = next(l for doc in detail["docs"] for l in doc["lines"]
                if "escrow is a current capability" in l["text"])
    doorway.demote(conn, "favour", line["ref"], line["tokens"], reason="unrecoverable? no")
    d2 = doorway.repo_detail(conn, str(tmp_path / "favour"))
    got = next(l for doc in d2["docs"] for l in doc["lines"] if l["ref"] == line["ref"])
    assert got["cold"] is True
    # the doc still loads its other (non-cold) lines
    doc2 = d2["docs"][0]
    assert 0 < doc2["loaded_tokens"] < doc2["tokens"]


def test_promote_restores_a_cold_line(conn, tmp_path):
    _favour(tmp_path)
    doorway.demote(conn, "favour", "CLAUDE.md", 999, reason="x")
    assert doorway.cold_refs(conn, "favour").get("CLAUDE.md") == 999
    doorway.promote(conn, "favour", "CLAUDE.md")
    assert "CLAUDE.md" not in doorway.cold_refs(conn, "favour")
