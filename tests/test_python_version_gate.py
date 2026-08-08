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


def test_readme_runs_preflight_before_install():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    first_demo = readme.index("python3 scripts/check_python.py")
    first_install = readme.index("python3 -m pip install -e .")
    assert first_demo < first_install


def test_demo_is_allowed_without_user_config():
    source = inspect.getsource(cli.main)
    allowlist = source.split("SELF_CONFIGURING =", 1)[1].split("\n", 1)[0]
    assert '"demo"' in allowlist
