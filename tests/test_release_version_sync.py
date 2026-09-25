"""Every release script, CI artifact name and served version matches pyproject.toml.

0.2.3 was first staged with three release scripts still naming 0.2.2. The package
tests passed, because none of them read the scripts that build and check the release.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSIONED = re.compile(
    r"mountain[-_]of[-_]helicon[-_ ](\d+\.\d+\.\d+)"
    r"|version != \"(\d+\.\d+\.\d+)\""
    r"|\"version\": \"(\d+\.\d+\.\d+)\""
    r"|Expected installed version (\d+\.\d+\.\d+)"
)
FILES = (
    "scripts/build_release.sh",
    "scripts/cold_install_check.sh",
    "scripts/launch_check.py",
    ".github/workflows/memory-ci.yml",
    "helicon/mcp_server.py",
)


def _version() -> str:
    text = (ROOT / "pyproject.toml").read_text()
    return re.search(r'(?m)^version = "([^"]+)"$', text).group(1)


def test_release_files_name_the_current_version():
    want = _version()
    stale = []
    seen = 0
    for rel in FILES:
        for n, line in enumerate((ROOT / rel).read_text().splitlines(), 1):
            for m in VERSIONED.finditer(line):
                seen += 1
                got = next(g for g in m.groups() if g)
                if got != want:
                    stale.append(f"{rel}:{n} says {got}, pyproject says {want}")
    assert seen >= 5, f"only {seen} version mentions found; the pattern no longer reads these files"
    assert not stale, "\n".join(stale)
