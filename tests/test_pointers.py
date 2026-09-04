"""Pointer check must fire on a stranger's false pointer and stay quiet on prose/URLs.

This is the roadmap's acceptance test for R13: a seeded false pointer in a repo Helicon
has never seen must move the verdict to ROT FOUND, naming the exact line and the
contradicting repo fact; a correct pointer must return CLEAN; and prose/URLs must not
be graded as broken pointers (the false-positive gate).
"""
from __future__ import annotations

import os
import tempfile

from helicon import pointers


def _repo(files: dict[str, str]) -> str:
    d = tempfile.mkdtemp()
    for rel, body in files.items():
        p = os.path.join(d, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True) if os.path.dirname(p) else None
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(body)
    return d


def test_clean_when_every_pointer_resolves():
    d = _repo({
        "docs/SETUP.md": "# setup\n",
        "run.py": "print(1)\n",
        "CLAUDE.md": "Read `docs/SETUP.md`.\nEntry `run.py`.\nSee [s](./docs/SETUP.md).\n",
    })
    res = pointers.check_pointers(d)
    assert res["verdict"] == "CLEAN", res
    assert res["checked"] == 3 and res["broken"] == 0


def test_seeded_false_pointer_is_rot_found_with_line_and_fact():
    d = _repo({
        "run.py": "print(1)\n",
        "CLAUDE.md": "Entry `run.py`.\nAlways read `docs/ARCHITECTURE.md` first.\n",
    })
    res = pointers.check_pointers(d)
    assert res["verdict"] == "ROT FOUND", res
    broken = res["receipts"]
    assert any("ARCHITECTURE" in r["raw"] for r in broken), broken
    # names the exact line and the contradicting repo fact
    hit = next(r for r in broken if "ARCHITECTURE" in r["raw"])
    assert hit["line_no"] == 2
    assert "not in repo" in hit["receipt"]


def test_import_and_wikilink_shapes():
    d = _repo({
        "config/settings.yml": "x: 1\n",
        "notes/Playbook.md": "# pb\n",
        "AGENTS.md": "@config/settings.yml is truth.\nSee [[Playbook]] and [[Missing Note]].\n",
    })
    res = pointers.check_pointers(d)
    assert res["verdict"] == "ROT FOUND", res
    raws = {r["raw"] for r in res["receipts"]}
    # the resolvable @import and the existing wikilink must NOT be flagged
    assert "@config/settings.yml" not in raws
    assert "[[Playbook]]" not in raws
    # the missing wikilink must be
    assert "[[Missing Note]]" in raws


def test_prose_and_urls_do_not_false_positive():
    d = _repo({
        "CLAUDE.md": (
            "See https://example.com/docs for help.\n"
            "Refactor the auth module carefully.\n"
            "Call the API and use the database.\n"
        ),
    })
    res = pointers.check_pointers(d)
    # nothing path-shaped and real → no broken pointers (UNMEASURED, never a false ROT)
    assert res["broken"] == 0, res


def test_unmeasured_not_silent_green_when_no_instruction_file():
    d = _repo({"main.py": "print(1)\n"})
    res = pointers.check_pointers(d)
    assert res["verdict"] == "UNMEASURED", res


def test_at_path_not_double_counted_as_bare():
    d = _repo({"AGENTS.md": "@config/missing.yml is the source.\n"})
    res = pointers.check_pointers(d)
    # one broken target, reported once as IMPORT — not also as BARE
    kinds = [r["kind"] for r in res["receipts"] if "missing.yml" in r["raw"]]
    assert kinds == ["IMPORT"], res["receipts"]


def test_tilde_and_absolute_paths_are_graded_on_the_real_filesystem():
    # A ~ or absolute reference is cross-repo, not an intra-repo pointer. If it exists
    # on disk it is NOT broken — R13 used to join it onto repo_root and cry wolf.
    import os
    home_sub = "~/" + os.path.relpath(os.path.expanduser("~/CODE"), os.path.expanduser("~")) if os.path.isdir(os.path.expanduser("~/CODE")) else "~"
    d = _repo({"CLAUDE.md": f"Repos live in `{home_sub}`.\n"})
    res = pointers.check_pointers(d)
    # a ~ path that exists on disk is a valid cross-repo reference, not broken
    assert res["broken"] == 0, res


def test_missing_tilde_path_is_machine_gap_not_repo_lie():
    """Cold-clone doctrine: lacking Oscar's ~/.helicon/config.json must not
    convict the instruction file of lying about the repo."""
    d = _repo({
        "helicon/config.py": "x\n",
        "AGENTS.md": (
            "Live connectors require the author's `~/.helicon-no-such-2026-09-05.json` "
            "(see `helicon/config.py`) and cannot run without it.\n"
        ),
    })
    res = pointers.check_pointers(d)
    assert res["broken"] == 0, res
    assert res["verdict"] == "CLEAN", res
    assert len(res["machine_gaps"]) == 1
    assert "~/.helicon-no-such-2026-09-05.json" in res["machine_gaps"][0]["raw"]


def test_a_described_absence_is_not_a_broken_pointer():
    # A line that says a path is NOT here is documentation about the absence, not a dead
    # reference. Real caught case: "`ci_gate.py` is NOT inherited here".
    d = _repo({"CLAUDE.md": (
        "`ci_gate.py` is NOT inherited here — it lives in the other repo.\n"
        "`witness.py` was moved to the engine package.\n"
    )})
    res = pointers.check_pointers(d)
    assert res["broken"] == 0, res


def test_a_plain_missing_pointer_is_still_flagged_after_the_precision_fix():
    # Regression: the fix must not silence a genuinely broken intra-repo pointer.
    d = _repo({"CLAUDE.md": "Always read `docs/ARCHITECTURE.md` first.\n"})
    res = pointers.check_pointers(d)
    assert res["verdict"] == "ROT FOUND" and res["broken"] == 1, res


def test_cold_home_self_review_does_not_convict_env_config(tmp_path, monkeypatch):
    """Control that was RED on main: HOME without ~/.helicon/config.json made
    `helicon review` on this product's AGENTS.md report a repo lie. Must stay green
    after the env-pointer fix — watch the control go RED under the naive arm in
    scripts/pointer_env_baseline.py."""
    from helicon.review import review, review_summary
    # Isolate HOME so expanduser("~/.helicon/config.json") cannot hit a real file.
    monkeypatch.setenv("HOME", str(tmp_path))
    # Also clear XDG if anything else expands home via environ.
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    agents = os.path.join(root, "AGENTS.md")
    if not os.path.isfile(agents):
        return  # not running inside the product checkout
    # Confirm the control input: AGENTS.md still names the env config.
    body = open(agents, encoding="utf-8").read()
    assert "`~/.helicon/config.json`" in body
    res = review(root)
    summary = review_summary(root, res)
    assert not any(
        "~/.helicon/config.json" in (f.get("raw") or "")
        for f in summary["findings"]
    ), summary["findings"]
    gaps = summary.get("machine_gaps") or []
    assert any("~/.helicon/config.json" in (g.get("raw") or "") for g in gaps), gaps
    # Grade must not be dragged by the env gap alone.
    ptr = res["pointers"]
    assert ptr["broken"] == 0 or not any(
        "~/.helicon/config.json" in r.get("raw", "") for r in ptr["receipts"]
    )


if __name__ == "__main__":
    import sys
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
