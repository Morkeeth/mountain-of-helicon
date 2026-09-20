"""Optional packages, and the one line to say when one is missing.

The default install is the deterministic review and imports nothing outside the
standard library. The web app, the model-backed commands and the retrieval lab need
packages that live behind extras in pyproject.toml. A command that reaches one of
them without it installed must say which extra provides it, once, and stop: a
ModuleNotFoundError traceback tells a stranger the tool is broken when it is only
smaller than the command they typed.
"""
from __future__ import annotations

import importlib
import importlib.util
import sys
from typing import NoReturn

# import name -> the extra that provides it. tests/test_slim_install.py fails when a
# third-party import in helicon/ is declared in no extra, so this cannot silently
# fall behind pyproject.toml.
EXTRA_FOR_MODULE = {
    "fastapi": "web",
    "starlette": "web",
    "uvicorn": "web",
    "pydantic": "web",
    "openai": "model",
    "numpy": "retrieval",
    "requests": "retrieval",
    "sentence_transformers": "embeddings",
}

# What each extra must provide before a command that needs it may start. One module
# per extra is enough: the extra installs its packages together.
_PROBE = {"web": "uvicorn", "model": "openai", "retrieval": "numpy",
          "embeddings": "sentence_transformers"}

# Exit status for "this command needs a package that is not installed". 1 is a
# contradiction found and review's own 2 is "nothing to check", so this one is 3.
EXIT_MISSING_EXTRA = 3


def install_line(extra: str) -> str:
    return f'pip install "mountain-of-helicon[{extra}]"'


def extra_for(module_name: str | None) -> str | None:
    """The extra that provides `module_name` (or a submodule of it), if we know one."""
    if not module_name:
        return None
    return EXTRA_FOR_MODULE.get(module_name.split(".")[0])


def refuse(extra: str, command: str | None) -> NoReturn:
    """Say which extra the command needs, on stderr, and exit. Never returns."""
    who = f"helicon {command}" if command else "this command"
    print(f"{who} needs the {extra} extra: {install_line(extra)}", file=sys.stderr)
    raise SystemExit(EXIT_MISSING_EXTRA)


def require(extra: str, command: str) -> None:
    """Refuse up front, before the command does any work or prints a banner."""
    try:
        present = importlib.util.find_spec(_PROBE[extra]) is not None
    except ImportError:  # a finder that refuses the import outright
        present = False
    if not present:
        refuse(extra, command)


class LazyModule:
    """Stands in for an optional module until an attribute is first used.

    A module that does `import numpy as np` at the top cannot be imported at all
    without numpy, even for the functions in it that never touch an array.
    embeddings.py holds the keyword-only context policy that every retrieval path
    ends in, so the default install has to be able to import it. Using the proxy
    changes no call site: `np.float32` still reads `np.float32`, and the missing
    package surfaces as the same ModuleNotFoundError, at the first real use."""

    def __init__(self, name: str):
        self._name = name

    def __getattr__(self, attr: str):
        value = getattr(importlib.import_module(self._name), attr)
        setattr(self, attr, value)  # resolved once per attribute
        return value
