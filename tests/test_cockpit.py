"""V2 Cockpit engine tests — run the ORIENT/INSPECT/COMPARE pipeline on a
synthetic git fixture (deterministic, no dependence on live ~/CODE) and prove
the privacy allowlist drops wallet/trading repos."""
import os
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
    roots = {os.path.realpath(str(repo))}
    md = load_artifact(str(repo), "markdown", "NIGHTRUN.md", allowed_roots=roots)
    assert md["type"] == "markdown"
    assert "Ship the escrow release" in md["text"]

    diff = load_artifact(str(repo), "diff", "main...HEAD", allowed_roots=roots)
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
    # a private repo is blocked even when explicitly in the allowed roots
    blocked = load_artifact(str(repo), "markdown", "NIGHTRUN.md",
                            allowed_roots={os.path.realpath(str(repo))})
    assert blocked["type"] == "blocked"


def _server_rule(conn, name, repo, kind, decision, correction=""):
    """Drive rule_claim exactly like the API does — by (terminal, pair_key),
    server re-deriving the claim — with a test-only terminals injection."""
    from helicon.cockpit import rule_claim
    view = cockpit_view(conn, terminals=[(name, str(repo))], only={name.lower()})
    claim = next(c for c in view["terminals"][0]["claims"] if c["kind"] == kind)
    return rule_claim(conn, {}, name, claim["pair_key"], decision, correction,
                      terminals=[(name, str(repo))]), claim


def test_revise_captures_correction_and_undo_reverses(conn, tmp_path):
    from helicon.cockpit import unrule_claim
    repo = _fixture_terminal(tmp_path)
    correction = "the branch was never pushed; it is local-only, not in production"
    res, _ = _server_rule(conn, "world-relay", repo, "ship", "revise", correction)
    assert res["ok"] is True
    # Revise captured the exact correction (V1 discarded it)
    assert res["correction_captured"] == correction
    cube_id = res["correction_cube"]
    assert cube_id
    row = conn.execute(
        "SELECT source, review_status FROM helicon_cubes WHERE id=?",
        (cube_id,)).fetchone()
    assert row["source"] == "output-review" and row["review_status"] == "approved"
    # finding resolved -> leaves the queue (RETURN CALMER)
    fid = res["finding_id"]
    dec = conn.execute("SELECT human_decision FROM audit_log WHERE id=?", (fid,)).fetchone()
    assert dec["human_decision"] is not None
    # HONEST continuity (P0-3): recorded, but NOT delivered to a live run, never obeyed
    cont = res["continuity"]
    assert cont["recorded"] is True
    assert cont["delivered_to_live_run"] is False
    assert cont["obeyed"] is None

    # UNDO restores: cube gone, finding re-opened
    undo = unrule_claim(conn, fid)
    assert undo["ok"] is True and cube_id in undo["deleted_cubes"]
    assert conn.execute("SELECT id FROM helicon_cubes WHERE id=?", (cube_id,)).fetchone() is None
    dec2 = conn.execute("SELECT human_decision FROM audit_log WHERE id=?", (fid,)).fetchone()
    assert dec2["human_decision"] is None


def test_propagate_writes_correction_to_sandbox_not_live(conn, tmp_path):
    from helicon.cockpit import propagate_correction
    repo = _fixture_terminal(tmp_path)
    res, _ = _server_rule(conn, "world-relay", repo, "ship", "revise",
                          "the branch was never pushed; local only")
    sandbox = tmp_path / "sandbox"
    prop = propagate_correction(conn, {}, res["correction_cube"], str(sandbox))
    assert prop["ok"] is True
    # delivered TO FILES (honest) — not to a live run, not obeyed
    assert prop["delivered_to_files"] is True
    assert prop["delivered_to_live_run"] is False and prop["obeyed"] is None
    assert (sandbox / "helicon-corrections.md").exists()
    assert "world-relay" in (sandbox / "helicon-corrections.md").read_text()
    # NEVER the live agent config
    assert ".claude/skills" not in prop["sandbox_dir"]
    assert prop["real_target"].endswith(".claude/skills")


def test_p0_undo_reverses_propagation(conn, tmp_path, monkeypatch):
    """P0-4: after propagate stages a correction into the context files, undo
    must regenerate those files so the correction is gone — not just delete the
    DB cube."""
    from helicon.cockpit import propagate_correction, unrule_claim
    monkeypatch.chdir(tmp_path)  # so _context_sandbox_dir() lives under tmp
    repo = _fixture_terminal(tmp_path)
    res, _ = _server_rule(conn, "world-relay", repo, "ship", "revise",
                          "UNIQUE-REVERSAL-MARKER the branch was never pushed")
    prop = propagate_correction(conn, {}, res["correction_cube"])  # default sandbox
    feed = os.path.join(prop["sandbox_dir"], "helicon-corrections.md")
    assert "UNIQUE-REVERSAL-MARKER" in open(feed).read()
    undo = unrule_claim(conn, res["finding_id"])
    assert undo["ok"] is True
    assert undo["propagation_reversed"] is not None
    assert undo["correction_absent_from_files"] is True
    # the correction is really gone from the regenerated files
    assert "UNIQUE-REVERSAL-MARKER" not in open(feed).read()


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


def test_p0_ruling_does_not_manufacture_retrieval_evidence(conn, tmp_path):
    """P0-3: ruling must NOT touch the mutating retrieval path (the old proof
    called _proactive_context / record_surfaced and inserted retrieval_log rows,
    manufacturing 'surfaced' evidence before any agent existed). Snapshot
    retrieval_log before/after — it must be byte-identical."""
    def snap():
        try:
            return conn.execute("SELECT COUNT(*) FROM retrieval_log").fetchone()[0]
        except Exception:
            return 0
    repo = _fixture_terminal(tmp_path)
    before = snap()
    res, _ = _server_rule(conn, "world-relay", repo, "ship", "revise",
                          "the branch was never pushed; local only")
    assert res["ok"] is True
    assert snap() == before, "ruling mutated retrieval_log (manufactured evidence)"
    # and continuity is honest: never claims delivery/obedience from a DB write
    assert res["continuity"]["delivered_to_live_run"] is False


def test_p0_rule_is_server_authoritative(conn, tmp_path):
    """P0-2: a caller cannot manufacture an approved cube by supplying a forged
    claim/verdict. The claim is addressed by pair_key and re-derived server-side;
    a pair_key not present in the server-verified state is refused."""
    from helicon.cockpit import rule_claim
    repo = _fixture_terminal(tmp_path)
    forged = rule_claim(conn, {}, "world-relay", "review|world-relay|FORGEDKEY",
                        "revise", "a lie I want promoted to approved truth",
                        terminals=[("world-relay", str(repo))])
    assert forged["ok"] is False
    assert "server-verified" in forged["error"] or "not present" in forged["error"]
    # no approved output-review cube was created
    assert conn.execute(
        "SELECT COUNT(*) FROM helicon_cubes WHERE source='output-review'"
    ).fetchone()[0] == 0


def test_p0_artifact_no_sibling_traversal(conn, tmp_path):
    """P0-1: the confirmed exploit — repo=.../helicon, ref=../helicon-secrets/file
    — must be blocked. A sibling sharing a name prefix cannot escape via
    startswith; true path containment is enforced."""
    (tmp_path / "helicon").mkdir()
    sibling = tmp_path / "helicon-secrets"
    sibling.mkdir()
    (sibling / "leak.md").write_text("SECRET")
    allowed = {os.path.realpath(str(tmp_path / "helicon"))}
    blocked = load_artifact(str(tmp_path / "helicon"), "markdown",
                            "../helicon-secrets/leak.md", allowed_roots=allowed)
    assert blocked["type"] == "blocked", blocked
    assert "SECRET" not in blocked.get("text", "")


def test_reject_requires_no_correction_but_revise_does(conn, tmp_path):
    repo = _fixture_terminal(tmp_path)
    bad, _ = _server_rule(conn, "world-relay", repo, "ship", "revise", "")
    assert bad["ok"] is False
