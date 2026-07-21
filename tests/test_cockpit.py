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
