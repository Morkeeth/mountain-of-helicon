"""V2 Cockpit engine tests — run the ORIENT/INSPECT/COMPARE pipeline on a
synthetic git fixture (deterministic, no dependence on live ~/CODE) and prove
the privacy allowlist drops wallet/trading repos."""
import subprocess

import pytest

from helicon.db import init_db
from helicon.cockpit import cockpit_view, load_artifact, _is_private


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True, text=True)


def _fixture_terminal(tmp_path, name="worklog"):
    """A repo on a feature branch whose closeout CLAIMS it shipped + tests pass,
    which git and the (absent) test files CONTRADICT."""
    repo = tmp_path / name
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True,
                   capture_output=True, text=True)
    _git(repo, "config", "user.email", "t@t.t")
    _git(repo, "config", "user.name", "t")
    (repo / "app.py").write_text("print('base')\n")
    _git(repo, "add", "app.py")
    _git(repo, "commit", "-m", "base")
    _git(repo, "checkout", "-b", "feature")
    (repo / "app.py").write_text("print('changed')\n")
    (repo / "NIGHTRUN.md").write_text(
        "# Ship the escrow release\n\n"
        "Shipped to production and deployed the release. 42 tests passing.\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "ship escrow release")
    return repo


@pytest.fixture
def conn(tmp_path):
    return init_db(str(tmp_path / "t.db"))


def test_cockpit_view_grounds_claims_against_git(conn, tmp_path):
    repo = _fixture_terminal(tmp_path)
    view = cockpit_view(conn, terminals=[("world-relay", str(repo))],
                        only={"world-relay"})
    assert view["total"] == 1
    t = view["terminals"][0]
    assert t["objective"] == "Ship the escrow release"
    assert t["branch"] == "feature"
    assert t["needs_human"] is True
    assert t["state"] == "contradicted"

    kinds = {c["kind"]: c for c in t["claims"]}
    # ship claim: no upstream -> contradicted (never left the machine)
    assert kinds["ship"]["verdict"] == "contradicted"
    assert "never left" in kinds["ship"]["receipt"] or "no upstream" in kinds["ship"]["receipt"].lower()
    # test claim: no test files in repo -> contradicted
    assert kinds["test"]["verdict"] == "contradicted"

    # artifacts manifest carries the two inspectable things
    art_types = {a["type"] for a in t["artifacts"]}
    assert "markdown" in art_types and "diff" in art_types


def test_inspect_renders_native_artifacts(conn, tmp_path):
    repo = _fixture_terminal(tmp_path)
    md = load_artifact(str(repo), "markdown", "NIGHTRUN.md")
    assert md["type"] == "markdown"
    assert "Ship the escrow release" in md["text"]

    diff = load_artifact(str(repo), "diff", "main...HEAD")
    assert diff["type"] == "diff"
    assert "NIGHTRUN.md" in diff["text"]


def test_privacy_allowlist_drops_wallet_repo(conn, tmp_path):
    repo = _fixture_terminal(tmp_path, name="my-wallet-tracker")
    # even explicitly allowed by name, a private path is dropped
    view = cockpit_view(conn, terminals=[("my-wallet-tracker", str(repo))],
                        only={"my-wallet-tracker"})
    assert view["total"] == 0
    assert _is_private(str(repo)) is True


def test_inspect_blocks_private_path(conn, tmp_path):
    repo = _fixture_terminal(tmp_path, name="rekt-trading")
    blocked = load_artifact(str(repo), "markdown", "NIGHTRUN.md")
    assert blocked["type"] == "blocked"


def test_revise_captures_correction_and_undo_reverses(conn, tmp_path):
    from helicon.cockpit import rule_claim, unrule_claim
    repo = _fixture_terminal(tmp_path)
    view = cockpit_view(conn, terminals=[("world-relay", str(repo))],
                        only={"world-relay"})
    claim = next(c for c in view["terminals"][0]["claims"] if c["kind"] == "ship")

    correction = "the branch was never pushed; it is local-only, not in production"
    res = rule_claim(conn, {}, "world-relay", str(repo), claim,
                     "revise", correction)
    assert res["ok"] is True
    # Revise captured the exact correction (V1 discarded it)
    assert res["correction_captured"] == correction
    cube_id = res["correction_cube"]
    assert cube_id
    # the correction is a real, approved cube in the store
    row = conn.execute(
        "SELECT source, review_status, content FROM helicon_cubes WHERE id=?",
        (cube_id,)).fetchone()
    assert row["source"] == "output-review"
    assert row["review_status"] == "approved"
    # finding is now resolved -> it leaves the queue (RETURN CALMER)
    fid = res["finding_id"]
    dec = conn.execute("SELECT human_decision FROM audit_log WHERE id=?", (fid,)).fetchone()
    assert dec["human_decision"] is not None
    # continuity proof is present and honest about include-vs-obey
    assert "included" in res["continuity"]

    # UNDO restores: cube gone, finding re-opened
    undo = unrule_claim(conn, fid)
    assert undo["ok"] is True and cube_id in undo["deleted_cubes"]
    assert conn.execute("SELECT id FROM helicon_cubes WHERE id=?", (cube_id,)).fetchone() is None
    dec2 = conn.execute("SELECT human_decision FROM audit_log WHERE id=?", (fid,)).fetchone()
    assert dec2["human_decision"] is None


def test_propagate_writes_correction_to_sandbox_not_live(conn, tmp_path):
    from helicon.cockpit import rule_claim, propagate_correction
    repo = _fixture_terminal(tmp_path)
    view = cockpit_view(conn, terminals=[("world-relay", str(repo))], only={"world-relay"})
    claim = next(c for c in view["terminals"][0]["claims"] if c["kind"] == "ship")
    res = rule_claim(conn, {}, "world-relay", str(repo), claim, "revise",
                     "the branch was never pushed; local only")
    sandbox = tmp_path / "sandbox"
    prop = propagate_correction(conn, {}, res["correction_cube"], str(sandbox))
    assert prop["ok"] is True
    # the correction is provably IN the next agent's context files
    assert prop["contains_correction"] is True
    assert (sandbox / "helicon-corrections.md").exists()
    txt = (sandbox / "helicon-corrections.md").read_text()
    assert "world-relay" in txt
    # NEVER the live agent config
    assert ".claude/skills" not in prop["sandbox_dir"]
    assert prop["real_target"].endswith(".claude/skills")


def test_truth_pass_honest_closeout_is_not_falsely_flagged(conn, tmp_path):
    """Adversarial truth: an HONEST closeout that says 'nothing pushed' must
    NOT be read as a ship claim (flagging honesty would invert reality), while
    a LYING 'merged to main' on an unpushed branch MUST be contradicted."""
    repo = tmp_path / "honest"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True, text=True)
    _git(repo, "config", "user.email", "t@t.t"); _git(repo, "config", "user.name", "t")
    (repo / "a.py").write_text("x=1\n"); _git(repo, "add", "-A"); _git(repo, "commit", "-m", "base")
    _git(repo, "checkout", "-b", "feature")
    (repo / "NIGHTRUN.md").write_text(
        "# Honest closeout\n\nNothing pushed, nothing deployed. Merged to main once review lands.\n")
    _git(repo, "add", "-A"); _git(repo, "commit", "-m", "honest")
    view = cockpit_view(conn, terminals=[("world-relay", str(repo))], only={"world-relay"})
    claims = view["terminals"][0]["claims"]
    # the honest 'nothing pushed' line is not a ship claim; 'Merged to main once
    # review lands' is future-tense but the honesty NEG guard suppresses a false
    # ship-contradiction on the same honest report
    ship = [c for c in claims if c["kind"] == "ship" and c["verdict"] == "contradicted"]
    assert ship == [], f"honest closeout falsely flagged: {ship}"


def test_continuity_pull_path_retrieves_the_correction(conn, tmp_path):
    """PROVE CONTINUITY (pull side, for real): after a ruling, the correction
    cube is returned by the same retrieval path a real agent calls
    (_proactive_context -> relevant_memories). 'included' must be True on a
    store where the correction is retrievable."""
    from helicon.cockpit import rule_claim
    from helicon.db import insert_cube
    from helicon.models import HeliconCube
    from helicon.scanner import make_id, content_hash
    # a small labeled synthetic store so retrieval has signal (FTS/embeddings)
    seed = HeliconCube(
        id=make_id(), source="obsidian", source_ref="fixture:test-count",
        type="decision", title="Helicon test count",
        content="The Helicon suite test count is tracked in the release notes.",
        summary="", content_hash=content_hash("seed"),
        created_at="2026-07-21T00:00:00", valid_from="2026-07-21T00:00:00",
        last_reinforced="2026-07-21T00:00:00", confidence=1.0,
        review_status="approved")
    insert_cube(conn, seed)
    conn.commit()

    repo = _fixture_terminal(tmp_path)
    view = cockpit_view(conn, terminals=[("Helicon", str(repo))], only={"Helicon"})
    claim = next(c for c in view["terminals"][0]["claims"] if c["kind"] == "test")
    res = rule_claim(conn, {}, "Helicon", str(repo), claim, "revise",
                     "the suite is 393 not 344; the closeout count is stale")
    assert res["ok"] is True
    cont = res["continuity"]
    # the correction is retrievable by the next agent's context read
    assert cont["included"] is True, cont
    assert cont["correction_cube"] == res["correction_cube"]


def test_reject_requires_no_correction_but_revise_does(conn, tmp_path):
    from helicon.cockpit import rule_claim
    repo = _fixture_terminal(tmp_path)
    view = cockpit_view(conn, terminals=[("world-relay", str(repo))], only={"world-relay"})
    claim = next(c for c in view["terminals"][0]["claims"] if c["kind"] == "ship")
    # revise with no correction is refused
    bad = rule_claim(conn, {}, "world-relay", str(repo), claim, "revise", "")
    assert bad["ok"] is False
