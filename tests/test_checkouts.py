"""The checkouts gate: one repo, two working copies, two commits.

The tests pin the four ways this check lies. Three of them make it LOUD (grouping
local-only repos, flagging worktrees, flagging build output) and one makes it
QUIET, which is worse — a misclassification that empties the finding list while
the command still prints a confident summary.
"""
import subprocess

from helicon.checkouts import audit_checkouts


def _git(path, *args):
    subprocess.run(("git", "-C", str(path)) + args, check=True,
                   capture_output=True, text=True)


def _repo(root, name, remote=None, content="one"):
    d = root / name
    d.mkdir(parents=True)
    _git(d, "init", "-q", "-b", "main")
    _git(d, "config", "user.email", "t@t")
    _git(d, "config", "user.name", "t")
    (d / "f.txt").write_text(content)
    _git(d, "add", "f.txt")
    _git(d, "commit", "-qm", content)
    if remote:
        _git(d, "remote", "add", "origin", remote)
    return d


def test_two_clones_at_different_commits_are_flagged(tmp_path):
    _repo(tmp_path, "proj", remote="https://x/proj.git", content="one")
    _repo(tmp_path, "proj-copy", remote="https://x/proj.git", content="two")
    res = audit_checkouts(str(tmp_path))
    assert len(res["diverged"]) == 1
    assert {c["name"] for c in res["diverged"][0]["checkouts"]} == {"proj", "proj-copy"}
    assert not res["clean"]


def test_a_single_checkout_is_silent(tmp_path):
    """Silence has to be earned, not the default."""
    _repo(tmp_path, "proj", remote="https://x/proj.git")
    res = audit_checkouts(str(tmp_path))
    assert res["clean"] and res["diverged"] == []
    assert res["checkouts"] == 1


def test_local_only_repos_are_never_grouped(tmp_path):
    """21 unrelated repos with no remote share no key. Grouping them under a
    single '(none)' is the loudest false positive available here."""
    _repo(tmp_path, "alpha", content="a")
    _repo(tmp_path, "beta", content="b")
    res = audit_checkouts(str(tmp_path))
    assert res["diverged"] == []
    assert sorted(res["no_remote"]) == ["alpha", "beta"]
    assert res["clean"]


def test_a_worktree_is_not_a_diverged_clone(tmp_path):
    """THE ONE THAT WOULD HAVE GONE UNNOTICED. A worktree is a second checkout on
    purpose — the fleet makes them deliberately — and it sits at a different
    commit by design. Classifying clones as worktrees empties the finding list
    silently, which is how the first version of this check ran green on a
    directory that had a known divergence in it."""
    a = _repo(tmp_path, "proj", remote="https://x/proj.git", content="one")
    _git(a, "branch", "side")
    _git(a, "worktree", "add", str(tmp_path / "proj-side"), "side")
    (tmp_path / "proj-side" / "f.txt").write_text("changed")
    _git(tmp_path / "proj-side", "add", "f.txt")
    _git(tmp_path / "proj-side", "commit", "-qm", "on the worktree")
    res = audit_checkouts(str(tmp_path))
    assert res["diverged"] == [], "a worktree at another commit is by design"
    assert res["worktree_groups"], "and it must still be COUNTED, not dropped"


def test_two_clones_at_the_same_commit_are_counted_not_flagged(tmp_path):
    """Duplicated disk is not drift."""
    a = _repo(tmp_path, "proj", remote="https://x/proj.git")
    subprocess.run(["git", "clone", "-q", str(a), str(tmp_path / "proj-2")],
                   check=True, capture_output=True)
    _git(tmp_path / "proj-2", "remote", "set-url", "origin", "https://x/proj.git")
    res = audit_checkouts(str(tmp_path))
    assert res["diverged"] == []
    assert len(res["in_sync"]) == 1
    assert res["clean"]


def test_an_empty_repo_is_unreadable_not_different(tmp_path):
    """No HEAD means nothing to compare. Reporting it as a difference would be an
    unmeasured thing dressed as a measured one."""
    d = tmp_path / "empty"
    d.mkdir()
    _git(d, "init", "-q", "-b", "main")
    _git(d, "remote", "add", "origin", "https://x/empty.git")
    res = audit_checkouts(str(tmp_path))
    assert res["unreadable"] == ["empty"]
    assert res["clean"]
