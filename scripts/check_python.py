#!/usr/bin/env python3
"""Fail clearly before installation on unsupported system Python versions.

Two ways a stranger's install dies on a stock Mac, and neither error names the
real cause:

  Python 3.9  ->  TypeError: unsupported operand type(s) for |
  pip 21.2.4  ->  ERROR: File "setup.py" or "setup.cfg" not found.
                  Directory cannot be installed in editable mode

The second one is the nastier of the two. It is macOS's bundled pip being too
old for PEP 660 editable installs from pyproject.toml, but it reads as "this
project is missing its setup.py" — so the stranger concludes the REPO is broken
and leaves. Both are checked here, before anything is installed.
"""

import sys


MINIMUM = (3, 10)
# PEP 660 (editable installs from pyproject.toml, no setup.py) landed in pip 21.3.
MINIMUM_PIP = (21, 3)


def _pip_version():
    try:
        import pip
    except ImportError:
        return None
    parts = []
    for chunk in pip.__version__.split("."):
        digits = "".join(c for c in chunk if c.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts[:2]) or None


def check_pip(version=None):
    """Reported separately from the interpreter check: a supported Python with
    an ancient pip fails just as hard and looks like a different problem."""
    version = version or _pip_version()
    if version is None or version >= MINIMUM_PIP:
        return 0
    print(
        "pip {0}.{1} is too old to install this project (need {2}.{3}+)."
        .format(version[0], version[1], MINIMUM_PIP[0], MINIMUM_PIP[1])
    )
    print("It will fail with 'File \"setup.py\" or \"setup.cfg\" not found', which")
    print("means your pip predates PEP 660 — not that anything is missing here.")
    print("")
    print("  python3 -m pip install --upgrade pip")
    return 1


def main(version=None):
    version = version or sys.version_info
    current = (version[0], version[1])
    current_text = ".".join(str(part) for part in current)
    minimum_text = ".".join(str(part) for part in MINIMUM)

    if current < MINIMUM:
        print(
            "Mountain of Helicon requires Python {0} or newer; found Python {1}."
            .format(minimum_text, current_text)
        )
        print("The Python 3.9 bundled with older macOS releases is not supported.")
        print("")
        print("Install a current Python, then repeat the README command:")
        print("  brew install python@3.12")
        print("  python3.12 scripts/check_python.py")
        print("  python3.12 -m pip install -e .")
        return 1

    print(
        "Python {0} is supported (minimum {1})."
        .format(current_text, minimum_text)
    )
    return check_pip()


if __name__ == "__main__":
    raise SystemExit(main())
