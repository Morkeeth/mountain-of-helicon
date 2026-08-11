"""A MOOT finding must not gate CI, and must not read as a contradiction.

probes.py already draws the distinction, and states the rule in its own words:

    "Obsolete is not false, and a gate that refuses a run over the difference
     is crying wolf. Detected the same, weighted differently: moot findings
     never gate."

A sequencing rule — "do NOT open user self-funding until the upgrade authority
is off the hot wallet" — is deferred to a condition that can no longer arrive,
because the code closed the door for good. The rule and the switch AGREE. The
rule is obsolete, not wrong, and nobody should be woken up for it.

The flag is set correctly (`moot: True`) and `doorway.py` honours it. Two other
consumers never learned about it:

  * rot.py counted every CONTRADICTED verdict as rot, moot included, which set
    R13 to ROT FOUND and made `helicon ci` exit 1 on an obsolete rule.
  * format_probes printed it as CONTRADICTED, indistinguishable from a live
    contradiction.

So the promise "moot findings never gate" was true of one caller out of three.
That inflates every count a human reads and is the same disease as the
false-positive cascade: a number that overstates teaches the reader to discount
the tool.
"""
import os
import subprocess

import pytest

from helicon.probes import CONTRADICTED, format_probes, probe_docs


# The ONLY bindable sentence here is the deferred sequencing rule, so anything
# that fires is the moot one — no other finding can muddy the assertions.
DOC = """# WIDGET

## Rules
**Sequencing rule this creates:** do NOT open user self-funding into the escrow
until the upgrade authority is off the hot wallet.
"""

CUSTODY = """/**
 * CUSTODY IS RETIRED. Real money still moves: the campaign unlock pays by
 * plain ERC-20 transfer, and that is not custody. Points are untouched.
 */
export const CUSTODY_RETIRED = true;
"""

ROUTE = """import { CUSTODY_RETIRED } from "@/lib/custody";

export async function POST(req) {
  if (CUSTODY_RETIRED) {
    return Response.json({
      error: "Custody retired",
      detail: "WIDGET no longer holds funds in escrow. Points are unaffected.",
    }, { status: 410 });
  }
}
"""


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "src" / "lib").mkdir(parents=True)
    (tmp_path / "src" / "app" / "api" / "agent" / "fund").mkdir(parents=True)
    (tmp_path / "CLAUDE.md").write_text(DOC)
    (tmp_path / "src" / "lib" / "custody.ts").write_text(CUSTODY)
    (tmp_path / "src" / "app" / "api" / "agent" / "fund" / "route.ts").write_text(ROUTE)
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    for cmd in (["git", "init", "-q"], ["git", "add", "-A"],
                ["git", "commit", "-qm", "fixture"]):
        subprocess.run(cmd, cwd=tmp_path, env=env, check=True,
                       capture_output=True)
    return str(tmp_path)


def _conn(repo):
    from helicon.db import init_db
    return init_db(os.path.join(repo, ".helicon-test.db"))


def test_the_fixture_really_is_the_moot_class(repo):
    """Guard the guard: if this stops being moot, the tests below prove nothing."""
    hits = [r for r in probe_docs(None, repo) if r["kind"] == "killswitch"]
    assert len(hits) == 1, f"expected exactly the sequencing rule, got {hits}"
    assert hits[0]["moot"] is True
    assert "no longer arrive" in hits[0]["why"]


def test_an_obsolete_rule_does_not_fail_ci(repo):
    """`helicon ci` exiting 1 over a rule the code already agrees with is the
    crying-wolf failure this repo exists to catch."""
    from helicon.rot import run_rot_exam
    res = run_rot_exam(_conn(repo), repo_root=repo)
    r13 = next(c for c in res["checks"] if c["id"] == "R13")
    assert r13["verdict"] != "ROT FOUND", (
        "a moot sequencing rule gated CI — probes.py promises moot never "
        f"gates: {r13['receipt']}")


def test_a_moot_finding_is_not_printed_as_a_contradiction(repo):
    """The human reads the label. CONTRADICTED means 'the code says otherwise';
    this rule's code says the same thing."""
    out = format_probes(probe_docs(None, repo), repo)
    assert "MOOT" in out, f"moot finding was not labelled as such:\n{out}"
    body = [ln for ln in out.splitlines()
            if ln.strip().startswith(CONTRADICTED) and "self-funding" not in ln]
    assert not [ln for ln in out.splitlines()
                if ln.strip().startswith(f"{CONTRADICTED} ")], \
        f"moot finding still rendered under the CONTRADICTED label:\n{out}"
    assert body == []


def test_a_real_contradiction_still_gates(repo):
    """The other half: strip the deferral and the same sentence must bite."""
    with open(os.path.join(repo, "CLAUDE.md"), "a") as fh:
        fh.write("\n- The USDC escrow is live and takes user deposits today.\n")
    from helicon.rot import run_rot_exam
    res = run_rot_exam(_conn(repo), repo_root=repo)
    r13 = next(c for c in res["checks"] if c["id"] == "R13")
    assert r13["verdict"] == "ROT FOUND", \
        "a live availability claim against a retired switch must still gate"
