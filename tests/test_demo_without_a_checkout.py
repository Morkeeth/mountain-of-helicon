"""`helicon demo` installed from a wheel must not send you somewhere you can't go.

THE BUG THIS PINS. `uvx --from git+... helicon demo` — the install path the
README now leads with — answered:

    The visual demo needs the dashboard bundle, but it is not built.
      source checkout: install Node.js, then run `helicon demo` again
      terminal demo:  bash scripts/demo.sh

Both exits are unavailable to that user. There is no web/ to build and no
scripts/ to run, because web/ is a frontend build and never enters the wheel.
A dead end with two dead exits, on the front door.

The message was correct when it was written, when a source checkout was the only
way in. uvx changed the object it was describing without changing the words.
"""
import pytest

from helicon.cli import _ensure_demo_dashboard


@pytest.fixture
def no_checkout(monkeypatch, tmp_path):
    """A wheel install: the package exists, the repo tree around it does not."""
    monkeypatch.setattr("helicon.cli.__file__", str(tmp_path / "helicon" / "cli.py"))
    return tmp_path


def test_a_wheel_install_is_not_told_to_build_a_tree_it_does_not_have(no_checkout):
    with pytest.raises(SystemExit) as e:
        _ensure_demo_dashboard()

    message = str(e.value.code)
    assert "scripts/demo.sh" not in message, (
        "a wheel install has no scripts/ — offering it is a dead exit")
    assert "install Node.js" not in message, (
        "there is no web/ to build; Node.js would not help")


def test_it_offers_something_that_actually_works_from_a_wheel(no_checkout):
    with pytest.raises(SystemExit) as e:
        _ensure_demo_dashboard()

    message = str(e.value.code)
    assert "helicon ci --path" in message, (
        "name the command that DOES work with no clone — that is the whole product")
    assert "git clone" in message, "and how to get the dashboard if they want it"


def test_the_node_missing_case_still_says_install_node(monkeypatch, tmp_path):
    """The other branch is unchanged and still correct: a real checkout WITH a
    web/package.json but no npm genuinely does want Node.js."""
    repo = tmp_path / "repo"
    (repo / "web").mkdir(parents=True)
    (repo / "web" / "package.json").write_text("{}")
    monkeypatch.setattr("helicon.cli.__file__", str(repo / "helicon" / "cli.py"))
    monkeypatch.setattr("helicon.cli.shutil.which", lambda _: None)

    with pytest.raises(SystemExit) as e:
        _ensure_demo_dashboard()

    assert "install Node.js" in str(e.value.code)
