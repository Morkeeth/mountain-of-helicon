"""A dead name living inside the working tree of the dead-name detector.

148 .pyc files under tests/, scripts/, helicon/, helicon/api/ and
helicon/connectors/ carried the co_filename `/Users/morkeeth/CODE/helicon-v2` —
a directory that does not exist. Every traceback the suite produced, including
the R4 failure this night run started from, pointed at a phantom path.

Per the rename law, a dead name in a CURRENT claim is rot. A traceback is a
current claim about where code lives. That the tool built to catch this class of
rot was carrying it in its own tree is the point, so the purge got a guard
rather than just a `rm`.

The check is cheap and self-limiting: it reads only the co_filename strings
already in the tree's own bytecode, and asserts each names a directory that
exists. It cannot fire on a fresh checkout (bytecode is regenerated with correct
paths); it fires exactly when a directory has been renamed or moved out from
under stale artifacts, which is the case it exists for.
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
_SRC_PATH = re.compile(rb"(/[\w./ +-]{8,120}?\.py)\x00?")


def _referenced_dirs(pyc: pathlib.Path) -> set[pathlib.Path]:
    data = pyc.read_bytes()
    out = set()
    for m in _SRC_PATH.finditer(data):
        try:
            p = pathlib.Path(m.group(1).decode("utf-8"))
        except UnicodeDecodeError:
            continue
        if p.is_absolute() and "site-packages" not in str(p):
            out.add(p.parent)
    return out


def test_no_bytecode_points_at_a_directory_that_does_not_exist():
    dead = {}
    for pyc in ROOT.rglob("*.pyc"):
        if ".worktrees" in pyc.parts:
            continue
        for d in _referenced_dirs(pyc):
            if not d.exists():
                dead.setdefault(str(d), []).append(
                    str(pyc.relative_to(ROOT)))
    assert not dead, (
        "stale bytecode names directories that do not exist — every traceback "
        f"from these files points at a phantom path: "
        + "; ".join(f"{d} ({len(v)} file(s))" for d, v in dead.items())
        + ". Fix: find . -name __pycache__ -type d -exec rm -rf {} +")


def test_the_check_actually_fires_on_the_pattern_that_was_here(tmp_path):
    """A guard that has never been seen to fail is not a guard. This is the
    exact byte shape found in 148 files in this tree: a co_filename naming
    /Users/morkeeth/CODE/helicon-v2, a directory that does not exist."""
    fake = tmp_path / "stale.pyc"
    fake.write_bytes(b"\xcb\x0d\x0d\x0a"
                     b"/Users/morkeeth/CODE/helicon-v2/helicon/context_policy.py\x00"
                     b"junk")
    dirs = _referenced_dirs(fake)
    assert pathlib.Path("/Users/morkeeth/CODE/helicon-v2/helicon") in dirs
    assert [d for d in dirs if not d.exists()], "the dead path was not flagged"


def test_the_check_does_not_fire_on_a_live_path(tmp_path):
    """And it must not cry wolf on bytecode that names a real directory."""
    fake = tmp_path / "fresh.pyc"
    fake.write_bytes(b"\xcb\x0d\x0d\x0a" + str(ROOT / "helicon" / "rot.py").encode()
                     + b"\x00junk")
    assert not [d for d in _referenced_dirs(fake) if not d.exists()]
