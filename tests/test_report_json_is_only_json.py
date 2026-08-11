"""`report --llm --json` must put ONLY JSON on stdout, even with no Qwen key.

THE BUG THIS PINS. `cmd_report` warned "No Qwen key; running deterministic-only."
with a bare `print()`, so the line landed on stdout at byte 0 of the document,
ahead of the JSON. `scripts/nightly.sh` pipes that stdout to a temp file and
guards it with `json.load` before promoting it to `data/eval-latest.json`. So
every night launchd ran without QWEN_API_KEY in its minimal environment:

    json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
    === nightly exit 1 ===

The guard was never the bug. It did its job and refused to promote a corrupt
baseline. The bug is that a command asked for machine-readable output and
emitted a human sentence into it.

WHY THIS TEST CAN GO RED, which is the point. The failing condition is not
"someone deletes the fix" — it is "someone adds any print() to this path".
Delete `file=sys.stderr` from cli.py:~2925 and test_no_key_stdout_parses fails
on the real decode, not on a mock. Verified red before being committed green.

Note the assertion is `json.loads(stdout)`, not `"No Qwen key" not in stdout`.
Naming the one known offender would let the next one through; parsing the
document is the property that actually matters.
"""

import json
import os
import subprocess
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run_report_without_key():
    """Run the real CLI in a subprocess with QWEN_API_KEY stripped.

    A subprocess, not an in-process call, because the defect lives in what
    reaches the stdout FILE DESCRIPTOR. capsys would capture a Python-level
    write and could pass while the real pipe stays corrupt.
    """
    env = dict(os.environ)
    env.pop("QWEN_API_KEY", None)
    return subprocess.run(
        [sys.executable, "-m", "helicon.cli", "report", "--llm", "--json"],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )


@pytest.fixture(scope="module")
def report_run():
    proc = _run_report_without_key()
    if proc.returncode != 0:
        pytest.fail(
            "report --llm --json exited {}; stderr:\n{}".format(
                proc.returncode, proc.stderr[-2000:]
            )
        )
    return proc


def test_no_key_stdout_parses(report_run):
    """stdout is a valid JSON document, with no key configured."""
    try:
        parsed = json.loads(report_run.stdout)
    except json.JSONDecodeError as exc:
        pytest.fail(
            "stdout is not valid JSON ({}). First 120 bytes were:\n{!r}\n"
            "Something on this code path printed to stdout instead of stderr; "
            "that is the nightly-killing bug.".format(exc, report_run.stdout[:120])
        )
    assert isinstance(parsed, dict), "expected a JSON object at the top level"
    assert "overall" in parsed, "report lost its 'overall' verdict key"


def test_the_warning_still_reaches_a_human(report_run):
    """The diagnostic is not deleted, just moved. Silence would be its own bug.

    Routing the warning to stderr is only correct if it still ARRIVES. A fix
    that made the nightly pass by muting the reason would trade a loud failure
    for a quiet one, which is the exact trade this repo exists to refuse.
    """
    assert "No Qwen key" in report_run.stderr, (
        "the no-key warning vanished entirely; it belongs on stderr, not nowhere"
    )


def test_stdout_starts_with_the_document(report_run):
    """No leading banner, blank line, or progress chatter before byte 0."""
    assert report_run.stdout.lstrip()[:1] == "{", (
        "stdout does not begin with a JSON object; first 80 bytes: "
        "{!r}".format(report_run.stdout[:80])
    )
