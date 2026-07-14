"""helicon leaderboard - population model reliability from git history.

Hermetic: no real repos. The git-touching parts (scan_repo) are thin; the parse,
attribution, and aggregation are pure and tested here. Invariants: a commit with
no agent trailer is never attributed, task-class comes from the conventional
prefix, and the ranking is Wilson-scored so evidence volume is respected.
"""
from helicon.leaderboard import (task_of_subject, parse_commits, aggregate_commits,
                                  _US, _RS)


def test_task_of_subject_from_conventional_prefix():
    assert task_of_subject("feat: add x") == "feature"
    assert task_of_subject("fix(api): bug") == "bugfix"
    assert task_of_subject("test: more") == "testing"
    assert task_of_subject("docs: readme") == "docs"
    assert task_of_subject("random subject") == "other"


def _blob(*records):
    # each record: (sha, subject, trailers)
    return _RS.join(_US.join(r) for r in records) + _RS


def test_parse_attributes_agent_and_skips_unauthored():
    raw = _blob(
        ("aaa111", "feat: thing", "Claude Opus 4.8 (1M context) <noreply@anthropic.com>"),
        ("bbb222", "fix: bug", "Cursor Agent <agent@cursor.sh>"),
        ("ccc333", "chore: no trailer", ""),          # no author -> skipped
    )
    got = parse_commits(raw)
    assert len(got) == 2                               # ccc333 dropped, never guessed
    assert got[0]["model"] == "opus-4.8" and got[0]["harness"] == "claude-code"
    assert got[1]["harness"] == "cursor" and got[1]["task_class"] == "bugfix"


def test_first_agent_trailer_wins_over_human_coauthor():
    raw = _blob(("d1", "feat: x",
                 "Claude Fable 5 <noreply@anthropic.com>\nJane Dev <jane@x.com>"))
    got = parse_commits(raw)
    assert got[0]["model"] == "fable-5" and got[0]["harness"] == "claude-code"


def test_aggregate_ranks_by_wilson_survival():
    commits = (
        [{"model": "opus-4.8", "harness": "claude-code", "task_class": "feature",
          "reverted": False}] * 50
        + [{"model": "cursor", "harness": "cursor", "task_class": "feature",
            "reverted": False}] * 3
    )
    rows = aggregate_commits(commits)
    # both 100% survival, but 50 commits outranks 3 on Wilson lower bound
    assert rows[0]["model"] == "opus-4.8"
    assert rows[0]["survival_lb"] > rows[1]["survival_lb"]


def test_reverts_lower_the_rate_and_rank():
    commits = (
        [{"model": "A", "harness": "h", "reverted": False}] * 18
        + [{"model": "A", "harness": "h", "reverted": True}] * 2       # 2/20 reverted
        + [{"model": "B", "harness": "h", "reverted": False}] * 20     # 0/20 reverted
    )
    rows = aggregate_commits(commits)
    by_model = {r["model"]: r for r in rows}
    assert by_model["A"]["revert_rate"] == 0.1
    assert by_model["B"]["revert_rate"] == 0.0
    assert rows[0]["model"] == "B"        # cleaner record ranks first at equal n
