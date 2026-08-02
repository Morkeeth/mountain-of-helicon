"""The doorway as a GATE — a live session refused, not a board reviewed.

Slices 1–2 measure a repo's context and rule on each line. This is the slice
where the ruling ACTS: a Claude Code UserPromptSubmit hook refuses to let a run
start against a repo whose loaded docs the running code disproves.

Pins, in the order they matter:
- a CONTRADICTED repo blocks, and the banner names the exact file:line
- a CLEAN repo is silent — the gate must be invisible when it has nothing to say
- demoting the offending line to cold UNBLOCKS (the sanctioned exit is real)
- an override needs a stated reason, and the reason is logged verbatim
- the verdict caches on a fingerprint, and every way the repo can change
  (commit, doc edit, demotion) invalidates it
- a private path is never probed
- every failure fails OPEN
"""
import json
import subprocess

import pytest

from helicon import capture, doorway
from helicon.db import init_db


def _git(repo, *a):
    subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)


def _commit(repo, msg="c"):
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", msg)


@pytest.fixture
def conn(tmp_path):
    return init_db(str(tmp_path / "d.db"))


def _contradicted_repo(root, name="favour"):
    """A repo whose CLAUDE.md claims a capability the code has retired."""
    repo = root / name
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
    _commit(repo, "retire")
    return repo


def _clean_repo(root, name="calm"):
    repo = root / name
    repo.mkdir(parents=True)
    (repo / "CLAUDE.md").write_text("# Calm\n\nKeep replies terse.\n")
    _git(repo, "init", "-q")
    _commit(repo, "init")
    return repo


# --------------------------------------------------------------------------
# the block itself
# --------------------------------------------------------------------------

def test_contradicted_repo_blocks_and_names_the_line(conn, tmp_path):
    repo = _contradicted_repo(tmp_path)
    v = doorway.verdict(conn, str(repo))
    d = doorway.decide(v, "fix the nav")

    assert d["action"] == "block"
    banner = doorway.format_block(v, d)
    assert "has not earned the right to start" in banner
    # the operator is told WHICH line, not merely that something is wrong
    assert "CLAUDE.md:4" in banner
    assert "escrow is a current capability" in banner
    # and both exits are on screen
    assert "--demote" in banner
    assert doorway.OVERRIDE_PREFIX in banner


def test_clean_repo_is_silent(conn, tmp_path):
    repo = _clean_repo(tmp_path)
    v = doorway.verdict(conn, str(repo))
    assert v["contradicted"] == []
    assert doorway.decide(v, "anything")["action"] == "allow"


def test_demoting_the_line_to_cold_unblocks(conn, tmp_path):
    """The exit the banner offers has to actually work. A cold line is kept
    forever and loads nothing, so it cannot poison a run — and therefore must
    not stop one. Without this the only way past the gate is an override, and a
    gate with one exit is a gate people uninstall."""
    repo = _contradicted_repo(tmp_path)
    v = doorway.verdict(conn, str(repo))
    assert doorway.decide(v, "go")["action"] == "block"

    ref = v["contradicted"][0]["ref"]
    doorway.demote(conn, "favour", ref, tokens=12, reason="stale line, rewriting the doc")

    v2 = doorway.verdict(conn, str(repo))
    assert v2["contradicted"] == []
    assert doorway.decide(v2, "go")["action"] == "allow"


# --------------------------------------------------------------------------
# override — the one human moment, and it must cost a sentence
# --------------------------------------------------------------------------

def test_override_requires_a_stated_reason():
    assert doorway.parse_override("helicon-override: shipping the doc fix itself") \
        == "shipping the doc fix itself"
    assert doorway.parse_override("HELICON-OVERRIDE: caps still count") == "caps still count"
    assert doorway.parse_override("  helicon-override: leading space ok") == "leading space ok"
    # the bare prefix is a gesture, not an override
    assert doorway.parse_override("helicon-override:") is None
    assert doorway.parse_override("helicon-override:   ") is None
    # and an ordinary prompt is never mistaken for one
    assert doorway.parse_override("please helicon-override: not at the front") is None
    assert doorway.parse_override("fix the nav") is None
    assert doorway.parse_override("") is None


def test_override_proceeds_and_is_logged_verbatim(conn, tmp_path, monkeypatch):
    repo = _contradicted_repo(tmp_path)
    monkeypatch.setenv("HELICON_OPERATOR", "oscar")

    g = capture.hook_gate(conn, str(repo), session="s1",
                          prompt="helicon-override: I am fixing that exact line")
    assert g["action"] == "override"

    row = conn.execute(
        "SELECT detail FROM run_events WHERE kind='gate_override'").fetchone()
    detail = json.loads(row["detail"])
    assert detail["reason"] == "I am fixing that exact line"
    assert detail["who"] == "oscar"
    assert any(r.startswith("CLAUDE.md:") for r in detail["contradicted"])


def test_block_is_recorded_as_an_event(conn, tmp_path):
    """Absence of a block proves nothing (the hook fails open), so a real block
    has to leave a record that distinguishes it from a hook that never ran."""
    repo = _contradicted_repo(tmp_path)
    g = capture.hook_gate(conn, str(repo), session="s2", prompt="build the thing")
    assert g["action"] == "block"

    detail = json.loads(conn.execute(
        "SELECT detail FROM run_events WHERE kind='gate_blocked'").fetchone()["detail"])
    assert detail["repo"] == "favour"
    assert detail["contradicted"]
    assert detail["fingerprint"]


def test_clean_repo_returns_none_from_the_hook(conn, tmp_path):
    repo = _clean_repo(tmp_path)
    assert capture.hook_gate(conn, str(repo), session="s3", prompt="hi") is None
    assert conn.execute("SELECT COUNT(*) FROM run_events "
                        "WHERE kind IN ('gate_blocked','gate_override')").fetchone()[0] == 0


# --------------------------------------------------------------------------
# the cache — fast, and never stale
# --------------------------------------------------------------------------

def test_verdict_caches_on_the_fingerprint(conn, tmp_path):
    repo = _contradicted_repo(tmp_path)
    first = doorway.verdict(conn, str(repo))
    assert first["cached"] is False
    assert doorway.verdict(conn, str(repo))["cached"] is True


def test_editing_the_doc_invalidates_the_cache(conn, tmp_path):
    """The cache exists so the hook is free on every prompt after the first. It
    must never be the reason a repo's verdict outlives the repo — that is the
    exact stale-memory failure this product is built to catch."""
    repo = _contradicted_repo(tmp_path)
    before = doorway.fingerprint(conn, str(repo))
    doorway.verdict(conn, str(repo))

    (repo / "CLAUDE.md").write_text("# FAVOUR\n\nThe escrow was retired.\n")
    assert doorway.fingerprint(conn, str(repo)) != before
    assert doorway.verdict(conn, str(repo))["cached"] is False


def test_new_commit_invalidates_the_cache(conn, tmp_path):
    repo = _contradicted_repo(tmp_path)
    doorway.verdict(conn, str(repo))
    before = doorway.fingerprint(conn, str(repo))
    (repo / "src" / "other.ts").write_text("export const x = 1;\n")
    _commit(repo, "more code")
    assert doorway.fingerprint(conn, str(repo)) != before


def test_demotion_invalidates_the_cache(conn, tmp_path):
    """Demoting is the fix the banner offers; if it did not invalidate, the
    operator would demote the line and stay blocked."""
    repo = _contradicted_repo(tmp_path)
    doorway.verdict(conn, str(repo))
    before = doorway.fingerprint(conn, str(repo))
    doorway.demote(conn, "favour", "CLAUDE.md#4", tokens=10, reason="rewriting")
    assert doorway.fingerprint(conn, str(repo)) != before


# --------------------------------------------------------------------------
# the precedence bug that hid a real contradiction
# --------------------------------------------------------------------------

def test_contradiction_survives_a_passing_probe_on_the_same_line():
    """Regression. One doc line can carry several probeable claims, so several
    probe results land on it. Building that map with a dict comprehension kept
    whichever ran LAST — and world-relay's CLAUDE.md:35, which probes
    CONTRADICTED then UPHELD, was rendered upheld on the real board.

    The error was in the only direction that matters: a claim the running code
    disproves shown as fine. Disproof wins.
    """
    results = [
        {"file": "CLAUDE.md", "line": 35, "verdict": "CONTRADICTED", "sentence": "a"},
        {"file": "CLAUDE.md", "line": 35, "verdict": "UPHELD", "sentence": "b"},
    ]
    assert doorway._by_line(results)[("CLAUDE.md", 35)]["verdict"] == "CONTRADICTED"
    # order-independent: the last-wins bug would pass one ordering and fail the other
    assert doorway._by_line(results[::-1])[("CLAUDE.md", 35)]["verdict"] == "CONTRADICTED"
    # UNVERIFIABLE outranks UPHELD too — "no probe covers this" must not be
    # overwritten by an unrelated passing claim on the same line
    mixed = [
        {"file": "CLAUDE.md", "line": 9, "verdict": "UPHELD", "sentence": "a"},
        {"file": "CLAUDE.md", "line": 9, "verdict": "UNVERIFIABLE", "sentence": "b"},
    ]
    assert doorway._by_line(mixed)[("CLAUDE.md", 9)]["verdict"] == "UNVERIFIABLE"


# --------------------------------------------------------------------------
# privacy and fail-open
# --------------------------------------------------------------------------

def test_private_path_is_never_probed(conn, tmp_path):
    repo = _contradicted_repo(tmp_path, name="journal-notes")
    assert capture.hook_gate(conn, str(repo), session="s4", prompt="anything") is None
    assert conn.execute("SELECT COUNT(*) FROM run_events "
                        "WHERE kind='gate_blocked'").fetchone()[0] == 0


def test_a_path_that_is_not_a_repo_allows(conn, tmp_path):
    plain = tmp_path / "not-a-repo"
    plain.mkdir()
    assert capture.hook_gate(conn, str(plain), session="s5", prompt="hi") is None
    assert capture.hook_gate(conn, "/nonexistent/path", session="s5", prompt="hi") is None


def test_gate_fails_open_when_probing_explodes(conn, tmp_path, monkeypatch):
    """A gate that bricks the terminal when it breaks gets uninstalled within a
    day, and then it governs nothing. Every failure path allows the prompt."""
    repo = _contradicted_repo(tmp_path)

    def boom(*a, **k):
        raise RuntimeError("probe host died")

    monkeypatch.setattr(doorway, "verdict", boom)
    with pytest.raises(RuntimeError):
        capture.hook_gate(conn, str(repo), session="s6", prompt="hi")
    # hook_gate itself propagates; cmd_hook is the layer that swallows it, and
    # that contract is pinned in test_hook.py. What must hold here is that the
    # explosion never leaves a half-written verdict behind.
    assert conn.execute("SELECT COUNT(*) FROM run_events "
                        "WHERE kind='gate_blocked'").fetchone()[0] == 0


# --------------------------------------------------------------------------
# warn mode — the default after 2026-08-02
#
# Three days of world-relay prompts were refused by a banner Claude Code never
# rendered ("blocked by hook: No stderr output"), naming lines the operator
# could not see, offering a `--demote` flag that did not exist. A gate can only
# spend an interruption it can explain. These pin the way out.
# --------------------------------------------------------------------------

def test_warn_mode_does_not_block_and_still_names_the_line(conn, tmp_path):
    repo = _contradicted_repo(tmp_path)
    v = doorway.verdict(conn, str(repo))
    d = doorway.decide(v, "fix the nav")
    banner = doorway.format_block(v, d, mode="warn")

    assert "has not earned the right to start" not in banner
    assert "running anyway" in banner
    assert "CLAUDE.md:4" in banner          # the line is still named
    # retyping the prompt is busywork once the prompt has already run
    assert doorway.OVERRIDE_PREFIX not in banner


def test_warn_banner_points_at_a_demote_ref_that_exists(conn, tmp_path):
    """The banner used to print a literal `<file#line>` placeholder against a
    flag the CLI never defined. It must now quote a real ref."""
    repo = _contradicted_repo(tmp_path)
    v = doorway.verdict(conn, str(repo))
    d = doorway.decide(v, "go")
    banner = doorway.format_block(v, d, mode="warn")

    ref = v["contradicted"][0]["ref"]
    assert f"--demote {ref}" in banner
    assert "<file#line>" not in banner


def test_board_demote_flag_is_a_real_command():
    """The exit the banner advertises has to be reachable from a terminal, not
    only from Python. `doorway.demote()` shipped tested while nothing on the CLI
    could call it, so the banner's `fix:` line named a flag argparse rejected —
    and the only working way past the gate was the override it listed second.

    Asserted against the real CLI, because the bug was never in the function.
    """
    import sys as _sys
    out = subprocess.run([_sys.executable, "-m", "helicon", "board", "--help"],
                         capture_output=True, text=True, timeout=60).stdout
    assert "--demote" in out, "the banner's sanctioned exit is not a real flag"
    assert "--promote" in out, "a demotion you cannot undo is a doc edit"


def test_a_moot_rule_is_reported_but_never_gates(conn, tmp_path):
    """Obsolete is not false. A sequencing rule whose condition can no longer
    arrive AGREES with the code that made it unreachable — the code does not
    disprove it. world-relay's "do NOT open user self-funding until the upgrade
    authority is off the hot wallet" gated three days of prompts on that
    conflation."""
    from helicon import probes
    # world-relay's real shape: the gate MESSAGE says "funds", so "fund" is a
    # named token, not a path artefact. The binding is genuine; the verdict
    # drawn from it was not.
    repo = tmp_path / "relay"
    (repo / "src" / "routes").mkdir(parents=True)
    (repo / "CLAUDE.md").write_text(
        "# RELAY\n\n## Context\n"
        "Keep replies terse.\n"
        "Sequencing rule: do NOT open user self-funding until the upgrade "
        "authority is off the hot wallet.\n")
    (repo / "src" / "custody.ts").write_text(
        "export const CUSTODY_RETIRED = true;\n")
    (repo / "src" / "routes" / "r.ts").write_text(
        'import { CUSTODY_RETIRED } from "../custody";\n'
        "export function h(req, res) {\n"
        "  if (CUSTODY_RETIRED) {\n"
        '    return res.status(410).json({ error: '
        '"Custody retired. RELAY no longer holds funds in escrow." });\n'
        "  }\n}\n")
    _git(repo, "init", "-q")
    _commit(repo, "sequencing")

    hits = [r for r in probes.probe_docs(conn, str(repo))
            if r["kind"] == "killswitch" and "self-funding" in r["sentence"]]
    assert len(hits) == 1, "still detected — the finding is real, its weight is not"
    assert hits[0]["moot"] is True
    assert "MOOT, not disproved" in hits[0]["why"]

    # and the gate stays out of the way
    v = doorway.verdict(conn, str(repo), fresh=True)
    assert v["contradicted"] == []
    assert doorway.decide(v, "go")["action"] == "allow"


def test_editing_the_prober_invalidates_a_cached_verdict(conn, tmp_path, monkeypatch):
    """The cache watched the commit, the docs and the cold set — but not the
    code that decides. A false positive fixed in probes.py kept being served
    against an untouched repo, which is the exact staleness class this product
    exists to catch."""
    repo = _contradicted_repo(tmp_path)
    before = doorway.fingerprint(conn, str(repo))

    real_stat = doorway.os.stat

    def newer(path, *a, **k):
        st = real_stat(path, *a, **k)
        from helicon import probes
        if path == probes.__file__:
            class S:
                st_size = st.st_size + 1
                st_mtime_ns = st.st_mtime_ns + 1
            return S()
        return st

    monkeypatch.setattr(doorway.os, "stat", newer)
    assert doorway.fingerprint(conn, str(repo)) != before
