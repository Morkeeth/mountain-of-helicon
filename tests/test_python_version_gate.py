import inspect
from pathlib import Path

from helicon import cli
from scripts import check_python


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_python_39_gets_clear_upgrade_path_without_traceback(capsys):
    assert check_python.main((3, 9, 25)) == 1

    output = capsys.readouterr().out
    assert "requires Python 3.10 or newer" in output
    assert "found Python 3.9" in output
    assert "brew install python@3.12" in output
    assert "Traceback" not in output


def test_supported_python_reports_success(capsys):
    assert check_python.main((3, 10, 0)) == 0
    assert "Python 3.10 is supported" in capsys.readouterr().out


def test_an_ancient_pip_is_rejected_too(capsys):
    """THE BUG THIS PINS, found on a cold clone. A stranger who skips this
    preflight and runs the README's install line with stock macOS python3 gets:

        ERROR: File "setup.py" or "setup.cfg" not found.
        Directory cannot be installed in editable mode

    That is macOS's bundled pip 21.2.4 predating PEP 660, but it reads as "this
    project is missing its setup.py" — so the stranger concludes the REPO is
    broken and leaves. A supported Python with an ancient pip fails just as hard
    as an unsupported Python and looks like an entirely different problem.
    """
    assert check_python.check_pip((21, 2)) == 1
    out = capsys.readouterr().out
    assert "setup.py" in out, "name the error they will actually see"
    assert "not that anything is missing here" in out


def test_a_modern_pip_passes():
    assert check_python.check_pip((24, 0)) == 0


def test_an_unreadable_pip_version_does_not_block_the_install():
    """Refusing to install because a version string could not be parsed would be
    worse than the problem it guards."""
    assert check_python.check_pip(None) == 0


def test_readme_runs_preflight_before_install():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    first_demo = readme.index("python3 scripts/check_python.py")
    first_install = readme.index("python3 -m pip install -e .")
    assert first_demo < first_install


def test_demo_is_allowed_without_user_config():
    source = inspect.getsource(cli.main)
    block = source.split("SELF_CONFIGURING =", 1)[1].split(")", 1)[0]
    assert '"demo"' in block
