import re
from pathlib import Path

from scripts import launch_check


ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = (ROOT / "pyproject.toml").read_text(encoding="utf-8")


def _declares(line: str) -> bool:
    return re.search(rf"(?m)^{re.escape(line)}$", PYPROJECT) is not None


def test_distribution_metadata_matches_release_contract():
    assert _declares('name = "helicon"')
    assert _declares('version = "0.2.0"')
    assert _declares(
        'description = "Check AGENTS.md and CLAUDE.md claims against the repository on disk"'
    )
    assert _declares('readme = "README.md"')
    assert _declares('license = "MIT"')
    assert '"Intended Audience :: Developers"' in PYPROJECT
    assert '"Topic :: Software Development :: Quality Assurance"' in PYPROJECT
    assert '"Programming Language :: Python :: 3.10"' in PYPROJECT
    assert '"Programming Language :: Python :: 3.11"' in PYPROJECT
    assert '"Programming Language :: Python :: 3.12"' in PYPROJECT


def test_documented_console_command_has_the_expected_entry_point():
    assert _declares('helicon = "helicon.cli:main"')
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "pip install helicon\nhelicon review ." in readme


def test_launch_gate_checks_the_ruled_distribution_name_and_version():
    package = next(
        check for check in launch_check.static_checks(ROOT)
        if check.key == "package-metadata"
    )
    assert package.ok is True
    assert package.detail.startswith("helicon 0.2.0")


def test_release_gate_builds_twice_and_cold_installs_the_wheel():
    build_script = (ROOT / "scripts/build_release.sh").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/memory-ci.yml").read_text(encoding="utf-8")
    assert "SOURCE_DATE_EPOCH" in build_script
    assert "for run in first second" in build_script
    assert 'cmp -s "$first" "$second"' in build_script
    assert "bash scripts/build_release.sh" in workflow
    assert "bash scripts/cold_install_check.sh" in workflow
