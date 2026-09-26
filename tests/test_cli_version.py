"""`helicon --version` is the first command a stranger types. It must print the
package version and exit 0, not a usage error."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _pyproject_version() -> str:
    text = (ROOT / "pyproject.toml").read_text()
    return re.search(r'(?m)^version = "([^"]+)"$', text).group(1)


def test_version_flag_prints_the_package_version_and_exits_zero():
    out = subprocess.run([sys.executable, "-m", "helicon", "--version"], cwd=ROOT,
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == f"helicon {_pyproject_version()}"
