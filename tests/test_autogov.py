"""Auto-governance — every session becomes a REVIEWABLE run, unasked.

Built to the operator's own account of the failure: "whenever I use an agent
full out, I feel like I lost things because I didn't review it."

So the tests that matter are not "does it capture a run". They are:
  - does an unreviewed run actually surface, and
  - does the ledger refuse to claim more than it can prove.

An auto-opened run had no acceptance frozen before the work. If it were allowed
to look governed, the ledger would lie about the single thing the product asks
to be trusted on.
"""
import json

import pytest

from helicon import autogov, capture, taskrun
from helicon.db import init_db


@pytest.fixture
def conn(tmp_path):
    return init_db(str(tmp_path / "ag.db"))


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A repo inside the safe set. `_safe_repo_root` allowlists direct children
    of ~/CODE, so the gate is pointed at a temp root instead of being bypassed —
    testing with the privacy gate disabled would test nothing."""
    import helicon.cockpit as ck
    root = tmp_path / "CODE"
    proj = root / "helicon-test-proj"
    proj.mkdir(parents=True)
    monkeypatch.setattr(ck, "CODE_ROOT", str(root.resolve()))
    return str(proj)


def _session(conn, repo, sid="s1", files=("CLAUDE.md",), transcript=""):
    autogov.session_start(conn, repo, sid)
    autogov.instructions_loaded(conn, sid, list(files))
    return autogov.session_stop(conn, sid, transcript)


# ------------------------------------------------- the surface that was missing

def test_an_unwatched_session_surfaces_as_needing_review(conn, repo):
    _session(conn, repo)
    rows = autogov.unreviewed(conn)
    assert len(rows) == 1
    assert rows[0]["observed"] is True


def test_a_stopped_run_is_never_auto_accepted(conn, repo):
    """Auto-accepting would recreate the exact failure this exists to fix: work
    nobody looked at, now carrying a machine's approval."""
    _session(conn, repo)
    rid = autogov.unreviewed(conn)[0]["id"]
    assert conn.execute("SELECT human_acceptance FROM task_runs WHERE id=?",
                        (rid,)).fetchone()[0] == "pending"


def test_ruling_on_a_run_clears_it_from_the_queue(conn, repo):
    _session(conn, repo)
    rid = autogov.unreviewed(conn)[0]["id"]
    taskrun.accept_run(conn, rid, "accepted", note="looked at it")
    assert autogov.unreviewed(conn) == []


# ------------------------------------------------- the honesty properties

def test_an_observed_run_never_claims_a_frozen_acceptance(conn, repo):
    _session(conn, repo)
    rid = autogov.unreviewed(conn)[0]["id"]
    acceptance = conn.execute("SELECT acceptance_test FROM task_runs WHERE id=?",
                              (rid,)).fetchone()[0]
    assert "no acceptance was frozen" in acceptance
    assert "hindsight" in acceptance


def test_an_observed_run_never_promotes_its_prompt(conn, repo):
    """Promotion is gated on an accepted outcome against a FROZEN contract. An
    observed run has no contract, so accepting it must not teach the next run.
    Otherwise unreviewed work silently becomes the template for future work."""
    _session(conn, repo)
    rid = autogov.unreviewed(conn)[0]["id"]
    taskrun.accept_run(conn, rid, "accepted", note="")
    # Exercise the real promotion gate (API/CLI Accept both call this).
    res = capture.promote_prompt(conn, rid)
    assert res["ok"] is False
    assert "frozen contract" in res["error"]
    assert capture.suggest_prompt(conn, "unnamed session") == []
    assert conn.execute(
        "SELECT COUNT(*) FROM prompt_library WHERE task_run_id=?", (rid,)
    ).fetchone()[0] == 0


def test_observed_run_is_not_labeled_forward_in_cockpit(conn, repo, monkeypatch):
    """Auto-observed must never render as provenance=forward — that header
    claims a frozen contract the run never had."""
    import asyncio
    from helicon.api import runs2

    _session(conn, repo)
    rid = autogov.unreviewed(conn)[0]["id"]
    monkeypatch.setattr(runs2, "get_conn", lambda: conn)
    listed = asyncio.run(runs2.run_list())
    run = next(r for r in listed["runs"] if r["task_run_id"] == rid)
    assert run["provenance"] == "observed"
    assert run["governed"]["task_class"] == "auto-observed"
    detailed = asyncio.run(runs2.run_detail(task_run_id=rid))
    assert detailed["run"]["provenance"] == "observed"


def test_the_empty_packet_says_helicon_supplied_no_context(conn, repo):
    """The packet must not imply Helicon chose this run's context. It didn't —
    the harness did."""
    _session(conn, repo)
    rid = autogov.unreviewed(conn)[0]["id"]
    row = conn.execute("SELECT token_estimate, excluded_relevant FROM context_packets "
                       "WHERE task_run_id=?", (rid,)).fetchone()
    assert row["token_estimate"] == 0
    assert "supplied no context" in json.loads(row["excluded_relevant"])[0]["reason"]


def test_context_event_records_its_own_blind_spot(conn, repo):
    """InstructionsLoaded covers CLAUDE.md/rules only. Recording the files
    without recording that limit would overstate the provenance."""
    _session(conn, repo, files=("CLAUDE.md", "GOLDEN_RULES.md"))
    rid = autogov.unreviewed(conn)[0]["id"]
    ev = conn.execute("SELECT detail FROM run_events WHERE task_run_id=? AND kind='context'",
                      (rid,)).fetchone()
    d = json.loads(ev["detail"])
    assert d["count"] == 2
    assert "not memory, MCP" in d["covers"]


def test_cost_is_unknown_not_zero_without_a_transcript(conn, repo):
    """A missing cost rendered as 0 would read as 'this run was free'."""
    res = _session(conn, repo)
    assert res["cost"]["status"] == "unknown"
    assert "total_tokens" not in res["cost"]


# ------------------------------------------------- privacy + fleet correctness

def test_an_unsafe_repo_is_not_observed_at_all(conn, tmp_path):
    assert autogov.session_start(conn, str(tmp_path / "wallet"), "s9")["ok"] is False
    assert autogov.unreviewed(conn) == []


def test_two_terminals_in_one_repo_are_two_runs(conn, repo):
    """The fleet case. Keying on repo alone would merge parallel sessions —
    which is the exact scenario this was built for."""
    autogov.session_start(conn, repo, "term-a")
    autogov.session_start(conn, repo, "term-b")
    assert len({r["id"] for r in autogov.unreviewed(conn)}) == 2


def test_observing_the_same_session_twice_does_not_double_open(conn, repo):
    autogov.session_start(conn, repo, "term-a")
    assert autogov.session_start(conn, repo, "term-a")["ok"] is False
    assert len(autogov.unreviewed(conn)) == 1


def test_observed_manifest_is_labelled_repo_state_not_session_output(conn, tmp_path, monkeypatch):
    """F-C04: the observed manifest is a REPO-WIDE diff, not session-scoped.

    Two sessions run in the same repo. A uniquely-named file is changed only by
    session B, yet session A's stop picks it up because `git diff`/`git status`
    see the whole working tree and the harness gives no per-file authorship. The
    honest fix is not to guess authorship but to LABEL every entry a repo-state
    observation and advertise the unverified attribution, so no surface presents
    a concurrent session's file as this run's proven output.
    """
    import subprocess

    import helicon.cockpit as ck

    root = tmp_path / "CODE"
    repo = root / "helicon-fc04"
    repo.mkdir(parents=True)
    monkeypatch.setattr(ck, "CODE_ROOT", str(root.resolve()))

    def git(*a):
        subprocess.run(["git", "-C", str(repo), *a], check=True,
                       capture_output=True, text=True)

    git("init", "-b", "main")
    git("config", "user.email", "t@t.t")
    git("config", "user.name", "t")
    (repo / "base.py").write_text("x = 1\n")
    git("add", "-A")
    git("commit", "-m", "base")

    # Session A opens against the current commit.
    started = autogov.session_start(conn, str(repo), "sess-A")
    assert started["ok"], started

    # A DIFFERENT concurrent session (B) commits a uniquely-named file. autogov
    # cannot tell it apart from A's own work — there is no per-file authorship.
    (repo / "only_session_b.py").write_text("print('B only')\n")
    git("add", "-A")
    git("commit", "-m", "session B work")

    # Stop A. Its manifest is built from a repo-wide diff.
    stop = autogov.session_stop(conn, "sess-A")
    assert stop["ok"], stop
    rid = stop["task_run_id"]
    manifest = json.loads(conn.execute(
        "SELECT artifact_manifest FROM task_runs WHERE id=?", (rid,)).fetchone()[0])
    paths = {m["path"] for m in manifest}

    # The bug this documents: B's file shows up in A's run.
    assert "only_session_b.py" in paths

    # The fix: every entry is a repo-state observation, never proven session
    # output — surfaced on the entry, the stop result, and the artifact event.
    assert manifest
    assert all(m.get("attribution") == "repo-state" for m in manifest)
    assert stop["attribution"] == "repo-state"
    ev = conn.execute(
        "SELECT detail FROM run_events WHERE task_run_id=? AND kind='artifact'",
        (rid,)).fetchone()
    assert json.loads(ev["detail"])["attribution"] == "repo-state"
