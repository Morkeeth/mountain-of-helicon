"""R14 command check: fire on a command a stranger's repo does not have, stay quiet
on ones it does and on external commands it can't resolve."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from helicon.commands import check_commands


def _repo(files: dict) -> str:
    d = tempfile.mkdtemp()
    for rel, body in files.items():
        p = os.path.join(d, rel)
        if os.path.dirname(p):
            os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(body)
    return d


def test_missing_npm_script_and_make_target_fire():
    d = _repo({
        "package.json": json.dumps({"scripts": {"test": "vitest", "build": "tsc"}}),
        "CLAUDE.md": "Run `npm run test`, then `npm run deploy`.\n`make lint` checks style.\n",
    })
    res = check_commands(d)
    assert res["verdict"] == "ROT FOUND", res
    raws = {r["raw"] for r in res["receipts"]}
    assert "deploy" in raws and "lint" in raws
    assert "test" not in raws          # the real script is not flagged


def test_present_commands_are_clean():
    d = _repo({
        "package.json": json.dumps({"scripts": {"dev": "vite", "check": "tsc"}}),
        "AGENTS.md": "Use `npm run dev` and `npm run check`.\n",
    })
    res = check_commands(d)
    assert res["verdict"] == "CLEAN" and res["broken"] == 0, res


def test_python_and_shell_scripts_resolve_by_file():
    d = _repo({
        "scripts/seed.py": "x", "run.sh": "x",
        "CLAUDE.md": "Seed with `python3 scripts/seed.py`, then `./run.sh`. Also `python3 gone.py`.\n",
    })
    res = check_commands(d)
    raws = {r["raw"] for r in res["receipts"]}
    assert "gone.py" in raws                       # missing script fires
    assert "scripts/seed.py" not in raws and "run.sh" not in raws


def test_external_commands_are_unmeasured_not_false_alarms():
    # docker / npx create-* have no in-repo provider; absence proves nothing.
    d = _repo({"CLAUDE.md": "Start with `docker compose up` and `npx create-next-app`.\n"})
    res = check_commands(d)
    assert res["verdict"] == "UNMEASURED", res


def test_a_described_removal_is_not_a_broken_command():
    d = _repo({
        "package.json": json.dumps({"scripts": {"build": "tsc"}}),
        "CLAUDE.md": "The old `npm run compile` was removed — use `npm run build`.\n",
    })
    res = check_commands(d)
    raws = {r["raw"] for r in res["receipts"]}
    assert "compile" not in raws, res            # negated mention skipped
    assert res["broken"] == 0


def test_npm_test_lifecycle_alias_grades_like_npm_run():
    """`npm test` was invisible to R14 while `npm run test` fired — false GRADE –."""
    d = _repo({
        "package.json": json.dumps({"scripts": {"build": "tsc"}}),
        "CLAUDE.md": "Run `npm test` before commit.\n",
    })
    res = check_commands(d)
    assert res["verdict"] == "ROT FOUND", res
    assert any(r["raw"] == "test" for r in res["receipts"])


def test_negation_in_other_clause_does_not_silence_dead_command():
    """'missing web/dist; run `npm run build`' must still convict a missing script."""
    d = _repo({
        "package.json": json.dumps({"scripts": {}}),
        "CLAUDE.md": (
            "web/dist is NOT committed and is missing; run `npm run build` first.\n"
        ),
    })
    res = check_commands(d)
    assert res["verdict"] == "ROT FOUND", res
    assert any(r["raw"] == "build" for r in res["receipts"])


def test_cd_web_npm_run_resolves_subdir_package_json():
    """`cd web && npm run build` must check web/package.json, not the repo root."""
    d = _repo({
        "web/package.json": json.dumps({"scripts": {"build": "vite build", "dev": "vite"}}),
        "CLAUDE.md": "Frontend: `cd web && npm run build` then `cd web && npm run missing`.\n",
    })
    res = check_commands(d)
    assert res["verdict"] == "ROT FOUND", res
    raws = {r["raw"] for r in res["receipts"]}
    assert "missing" in raws
    assert "build" not in raws


def test_bare_npm_run_still_uses_root_package_json():
    d = _repo({
        "web/package.json": json.dumps({"scripts": {"dev": "vite"}}),
        "CLAUDE.md": "Run `npm run dev`.\n",  # no cd — root has no package.json
    })
    res = check_commands(d)
    assert res["verdict"] == "ROT FOUND", res
    assert any(r["raw"] == "dev" for r in res["receipts"])


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn(); print(f"PASS  {fn.__name__}")
        except AssertionError as e:
            failed += 1; print(f"FAIL  {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
