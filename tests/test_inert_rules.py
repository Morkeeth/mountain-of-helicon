"""The inert-rule class: a rule nobody ever acted on.

Every class in the exam asks whether a rule is still TRUE. None asks whether it
CHANGED WHAT ANYONE DID. A rule that is correct, current, and that no code,
comment, commit or other doc has ever referenced is invisible to all thirteen.

Written before the detector exists, from the class description alone, so the
assertions do not come from the implementation. The fixture is the whole claim:
two rules that look identical in the instruction file, one enacted in code and
one stated and never used. The detector must separate them.

The guard is the half that matters. "Flag rules nobody acted on" and "flag every
rule" are the same function until a test says the enacted one must NOT fire.
"""
import subprocess
from pathlib import Path

import pytest

from helicon.inert import find_inert_rules

# Both rules MUST carry a searchable token, or the guard below passes for the
# wrong reason. The first version of this fixture used "Format Python with black
# at line length 100.", which yields no token at all — so the detector skipped it
# and "did not flag the enacted rule" was true because it never looked. Green,
# and proving nothing. test_the_guard_is_not_vacuous exists so that cannot
# recur silently.
ENACTED = "Every timestamp goes through the now_utc() helper in src/clock.py."
INERT = "All timestamps must be stored in UTC through the iso_utc() helper."


@pytest.fixture
def repo(tmp_path):
    """One rule the code enacts, one rule the code has never heard of."""
    r = tmp_path / "project"
    (r / "src").mkdir(parents=True)
    (r / "CLAUDE.md").write_text(
        f"# Rules\n\n- {ENACTED}\n- {INERT}\n")
    # now_utc really exists and is really called, so the first rule acted on
    # something. iso_utc appears nowhere.
    (r / "src" / "clock.py").write_text(
        "import datetime\n\n\ndef now_utc():\n"
        "    return datetime.datetime.now(datetime.timezone.utc)\n")
    (r / "src" / "main.py").write_text(
        "from clock import now_utc\n\n\ndef stamp():\n    return now_utc()\n")
    subprocess.run(["git", "init", "-q"], cwd=r, check=True)
    subprocess.run(["git", "add", "-A"], cwd=r, check=True)
    subprocess.run(["git", "-c", "user.email=a@a", "-c", "user.name=a",
                    "commit", "-qm", "set up black formatting"], cwd=r, check=True)
    return str(r)


def _texts(results):
    return [r["rule"] for r in results]


def test_the_unused_rule_is_flagged(repo):
    assert any(INERT[:40] in t for t in _texts(find_inert_rules(repo)))


def test_the_enacted_rule_is_not_flagged(repo):
    """The guard. Without it, a detector that flags everything passes."""
    assert not any(ENACTED[:40] in t for t in _texts(find_inert_rules(repo)))


def test_the_guard_is_not_vacuous(repo):
    """The enacted rule must be something the detector actually LOOKED at.

    A rule with no searchable token is skipped by design, so a guard built on
    one would pass without the detector ever running — which is what the first
    version of this file did. This asserts the token exists and is genuinely
    present in the repo, so "not flagged" means "found to be enacted"."""
    from helicon.inert import _tokens
    tokens = _tokens(ENACTED)
    assert tokens, "the enacted rule must name something searchable"
    assert "now_utc" in tokens, tokens
    assert "now_utc" in (Path(repo) / "src" / "clock.py").read_text()


def test_every_finding_carries_the_tokens_it_searched_for(repo):
    """A verdict without its probe is an opinion. A reader has to be able to
    rerun the search that produced the claim."""
    for r in find_inert_rules(repo):
        assert r["tokens"], r
        assert r["file"] and r["line"], r


def test_a_rule_referenced_only_by_another_instruction_file_is_still_inert(tmp_path):
    """Two docs agreeing is not evidence that anything was done. This is the
    failure mode the class exists to catch: a rule that reads as well-supported
    because it is repeated, and that no code has ever obeyed."""
    r = tmp_path / "echo"
    r.mkdir()
    (r / "CLAUDE.md").write_text(f"# Rules\n\n- {INERT}\n")
    (r / "AGENTS.md").write_text(f"# Rules\n\n- {INERT}\n")
    (r / "main.py").write_text("print('hello')\n")
    subprocess.run(["git", "init", "-q"], cwd=r, check=True)
    subprocess.run(["git", "add", "-A"], cwd=r, check=True)
    subprocess.run(["git", "-c", "user.email=a@a", "-c", "user.name=a",
                    "commit", "-qm", "init"], cwd=r, check=True)
    assert any(INERT[:40] in t for t in _texts(find_inert_rules(str(r))))


def test_a_rule_with_no_distinctive_token_is_not_guessed_at(tmp_path):
    """"Be careful." has nothing to search for. Reporting it as inert would be
    a verdict manufactured from the absence of a probe — UNMEASURED, not rot."""
    r = tmp_path / "vague"
    r.mkdir()
    (r / "CLAUDE.md").write_text("# Rules\n\n- Be careful and use good judgement.\n")
    (r / "main.py").write_text("print('hello')\n")
    subprocess.run(["git", "init", "-q"], cwd=r, check=True)
    subprocess.run(["git", "add", "-A"], cwd=r, check=True)
    subprocess.run(["git", "-c", "user.email=a@a", "-c", "user.name=a",
                    "commit", "-qm", "init"], cwd=r, check=True)
    flagged = _texts(find_inert_rules(str(r)))
    assert not any("careful" in t for t in flagged), flagged


@pytest.mark.xfail(reason="prohibitions are the open gap: absence is compliance, "
                          "not inertness, and the detector cannot yet tell them apart",
                   strict=True)
def test_a_prohibition_is_not_inert(tmp_path):
    """The named false-positive class, measured on openai/codex 2026-08-14.

    Two of the three surviving candidates were rules of the form "Do NOT use X".
    For a prohibition, X being absent from the codebase is the rule WORKING. The
    detector reads absence as never-acted-on, which is exactly backwards.

    Marked xfail rather than deleted: an open gap with a failing test attached is
    a gap someone can close. A gap described in a docstring is a gap nobody sees.
    """
    r = tmp_path / "prohibition"
    r.mkdir()
    (r / "CLAUDE.md").write_text(
        "# Rules\n\n- Do not use the deprecated `legacy_fetch()` helper anywhere.\n")
    (r / "main.py").write_text("print('hello')\n")
    subprocess.run(["git", "init", "-q"], cwd=r, check=True)
    subprocess.run(["git", "add", "-A"], cwd=r, check=True)
    subprocess.run(["git", "-c", "user.email=a@a", "-c", "user.name=a",
                    "commit", "-qm", "init"], cwd=r, check=True)
    flagged = _texts(find_inert_rules(str(r)))
    assert not any("legacy_fetch" in t for t in flagged), flagged
