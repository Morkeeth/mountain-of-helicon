"""The gate and the sweep are two profiles, and the profile has to ARRIVE.

`strict` was threaded verdict -> contradicted_lines -> repo_detail and then
dropped one call short of the prober: repo_detail accepted the argument and
called probe_docs without it. Every caller read as configured, the whole suite
passed, and `helicon sweep` ran the GATE profile over 574 strangers' repos —
reporting 29.09% flagged, the exact number the split was written to replace.

A parameter accepted and discarded is worse than one never added, because the
measurement then looks deliberate. These tests pin the profile at the only place
that proves it: the verdict a caller actually receives.
"""
import subprocess

import pytest

from helicon import doorway, probes
from helicon.db import init_db


@pytest.fixture
def conn(tmp_path):
    return init_db(str(tmp_path / "d.db"))


def _repo(root):
    """A doc naming a route that is genuinely gone, in the bare style that
    produced every TRUE find in the 11-repo gate sweep — and that carries no
    presence cue, so the sweep's allowlist declines to publish it."""
    repo = root / "stranger"
    (repo / "src").mkdir(parents=True)
    (repo / "CLAUDE.md").write_text(
        "# Stranger\n\n**MCP**: `src/services/mcp/McpHub.ts`.\n")
    (repo / "src" / "present.ts").write_text("export const ok = 1;\n")
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True,
                   capture_output=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c",
                    "user.name=t", "commit", "-qm", "base"], check=True,
                   capture_output=True)
    return repo


def test_the_gate_profile_probes_a_bare_path_claim(conn, tmp_path):
    """GATE (strict=False) reads one repo whose docs its own author wrote, to
    decide whether a run may start. A miss ships rot into a live session, so a
    bare `**MCP**: \\`path\\`` is probed and convicted. Recall-first."""
    repo = _repo(tmp_path)
    v = doorway.verdict(conn, str(repo), {}, strict=False)
    assert [c["file"] for c in v["contradicted"]] == ["CLAUDE.md"]


def test_the_sweep_profile_declines_to_publish_the_same_line(conn, tmp_path):
    """SWEEP (strict=True) reads strangers' repos to publish a number, where a
    false positive accuses someone else's project in public. The same sentence
    carries no presence cue, so it is not published. Precision-first.

    This is the assertion the missing thread broke: before the fix both calls
    returned the gate's answer and this test failed.
    """
    repo = _repo(tmp_path)
    v = doorway.verdict(conn, str(repo), {}, strict=True)
    assert v["contradicted"] == []


def test_the_two_profiles_do_not_share_a_cache_row(conn, tmp_path):
    """Same repo, same fingerprint, two profiles. If the cache key ignored the
    profile, whichever ran first would serve the other its answer — and a sweep
    would silently publish the gate's verdict."""
    repo = _repo(tmp_path)
    strict_first = doorway.verdict(conn, str(repo), {}, strict=True)
    gate_after = doorway.verdict(conn, str(repo), {}, strict=False)
    assert strict_first["contradicted"] == []
    assert [c["file"] for c in gate_after["contradicted"]] == ["CLAUDE.md"]


def test_repo_detail_hands_the_profile_to_the_prober(conn, tmp_path):
    """The exact call that dropped it. repo_detail is where `strict` stopped."""
    repo = _repo(tmp_path)
    gate = doorway.repo_detail(conn, str(repo), {}, strict=False)
    sweep = doorway.repo_detail(conn, str(repo), {}, strict=True)
    assert gate["verdict_counts"][probes.CONTRADICTED] == 1
    assert sweep["verdict_counts"][probes.CONTRADICTED] == 0


def _monorepo(root):
    """The 45.5% class: a doc writing a package-relative route in a monorepo.
    `src/main.ts` is not at the repo root, but git finds it one level down —
    identical in signature to a genuinely moved subtree."""
    repo = root / "mono"
    (repo / "packages" / "server" / "src").mkdir(parents=True)
    (repo / "packages" / "server" / "src" / "main.ts").write_text("export const x = 1;\n")
    (repo / "CLAUDE.md").write_text("# Mono\n\nThe server entry point is `src/main.ts`.\n")
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c",
                    "user.name=t", "commit", "-qm", "base"], check=True,
                   capture_output=True)
    return repo


def test_the_gate_still_names_a_moved_route(conn, tmp_path):
    """The gate keeps the moved-subtree finding — for your own repo, 'the doc
    routes somewhere that is gone, it now lives here' is a fix, not a complaint."""
    repo = _monorepo(tmp_path)
    r = probes._probe_path(str(repo), "src/main.ts", git=True, strict=False)
    assert r["verdict"] == probes.CONTRADICTED
    assert r["moved_to"] == "packages/server/src/main.ts"


def test_the_sweep_refuses_to_publish_a_path_git_can_still_find(conn, tmp_path):
    """40 of 88 findings on the frozen corpus were this. A moved subtree and a
    package-relative route are indistinguishable from the repo root, and only
    one of them is rot — so the survey drops the row rather than accuse."""
    repo = _monorepo(tmp_path)
    r = probes._probe_path(str(repo), "src/main.ts", git=True, strict=True)
    assert r["verdict"] == probes.UNVERIFIABLE
    assert "not published" in r["why"]
    v = doorway.verdict(conn, str(repo), {}, strict=True)
    assert v["contradicted"] == []


def test_the_sweep_still_convicts_a_path_that_is_simply_absent(conn, tmp_path):
    """The refusal is scoped to found-elsewhere. A path git cannot find at all
    is still published — otherwise the fix would buy precision with the whole
    point of the survey."""
    repo = _monorepo(tmp_path)
    r = probes._probe_path(str(repo), "src/nowhere.ts", git=True, strict=True)
    assert r["verdict"] == probes.CONTRADICTED
