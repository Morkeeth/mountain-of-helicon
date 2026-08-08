#!/usr/bin/env python3
"""Fail clearly before installation on unsupported system Python versions."""

import sys


MINIMUM = (3, 10)


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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
