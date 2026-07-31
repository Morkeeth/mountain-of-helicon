"""The two false-positive classes that made the live gate unusable.

Found by dogfooding: with the gate wired into a real terminal, Helicon's OWN
repo reported 10 CONTRADICTED lines. All 10 were wrong. A gate that blocks a
real session on ten false accusations gets uninstalled the same hour, so these
are pinned as hard as the true positives.

Class 1 — a committed fixture corpus treated as the running code.
  HELICON-BENCH ships miniature repos under `bench/repos/`; one declares
  `CUSTODY_RETIRED = true` because that IS the fixture. Nothing excluded it, so
  the switch was read as a live retirement in the host repo and went on to
  contradict seven unrelated sentences of AGENTS.md prose about a flaky test.

Class 2 — "git does not track it" read as disproof.
  `config-demo.json` is WRITTEN by scripts/demo_seed.py and gitignored. The doc
  said exactly that, and the probe called it a lie three times. Same bug hit
  people-radar's `intel-cache.json` ("written by radar.py each run").
  Untracked is UNVERIFIABLE. Git is the wrong witness for a generated file.
"""
import os
import subprocess

import pytest

from helicon import probes
from helicon.probes import CONTRADICTED, UNVERIFIABLE, UPHELD


def _repo(root, files, ignore=""):
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    if ignore:
        (root / ".gitignore").write_text(ignore)
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    for cmd in (["git", "init", "-q"], ["git", "add", "-A"],
                ["git", "commit", "-qm", "fixture"]):
        subprocess.run(cmd, cwd=root, env=env, check=True, capture_output=True)
    return str(root)


# --------------------------------------------------------------------------
# class 1 — a fixture corpus is not the running code
# --------------------------------------------------------------------------

@pytest.mark.parametrize("path", [
    "bench/repos/escrow-retired/src/custody.ts",
    "tests/fixtures/demo/src/custody.ts",
    "examples/retired-app/src/custody.ts",
    "testdata/x/custody.ts",
    ".worktrees/wt1/src/custody.ts",
])
def test_a_kill_switch_inside_a_fixture_is_not_a_live_retirement(tmp_path, path):
    """The switch exists, is committed, and says `= true` — and still says
    nothing about its host repo, because the fixture's whole job is to contain
    it."""
    repo = _repo(tmp_path, {
        path: "export const CUSTODY_RETIRED = true;\n",
        "src/main.ts": "export const ok = 1;\n",
    })
    names = [s["name"] for s in probes.find_kill_switches(repo)]
    assert "CUSTODY_RETIRED" not in names


def test_a_real_kill_switch_outside_a_fixture_is_still_found(tmp_path):
    """The guard above must not be a blanket amnesty — the true positive that
    the whole class exists for has to survive it."""
    repo = _repo(tmp_path, {
        "src/lib/custody.ts": "export const CUSTODY_RETIRED = true;\n",
        "src/api/fund.ts": (
            'import { CUSTODY_RETIRED } from "../lib/custody";\n'
            "if (CUSTODY_RETIRED) { return res.status(410).json({}); }\n"),
    })
    assert "CUSTODY_RETIRED" in [s["name"] for s in probes.find_kill_switches(repo)]


def test_fixture_paths_are_excluded_from_grep_evidence(tmp_path):
    """Even when a switch is legitimately live, its EVIDENCE must not be a
    fixture — pasting a bench corpus line as proof about the host repo is how
    the seven AGENTS.md sentences got contradicted."""
    repo = _repo(tmp_path, {
        "src/lib/custody.ts": "export const CUSTODY_RETIRED = true;\n",
        "bench/repos/other/src/custody.ts": "export const CUSTODY_RETIRED = true;\n",
    })
    _cmd, out = probes._grep(repo, "CUSTODY_RETIRED", git=True)
    assert "bench/repos" not in out


# --------------------------------------------------------------------------
# class 2 — untracked is not disproved
# --------------------------------------------------------------------------

def test_generated_gitignored_file_is_unverifiable_not_contradicted(tmp_path):
    """The exact shape of `config-demo.json` and `intel-cache.json`: the doc
    says a script writes it, the file is on disk, git deliberately ignores it.
    Absence from git is what the doc PREDICTED, so it cannot be the disproof."""
    repo = _repo(tmp_path, {"src/main.ts": "export const ok = 1;\n"},
                 ignore="config-demo.json\n")
    (tmp_path / "config-demo.json").write_text("{}\n")

    r = probes._probe_path(repo, "config-demo.json", git=True)
    assert r["verdict"] == UNVERIFIABLE
    assert "git cannot settle" in r["why"]


def test_gitignored_file_absent_from_disk_is_also_unverifiable(tmp_path):
    """Not yet generated is still not disproved — the repo has declared it does
    not track this path, so git has no standing to rule either way."""
    repo = _repo(tmp_path, {"src/main.ts": "export const ok = 1;\n"},
                 ignore="config-demo.json\n")
    r = probes._probe_path(repo, "config-demo.json", git=True)
    assert r["verdict"] == UNVERIFIABLE


def test_a_file_that_is_simply_missing_is_still_contradicted(tmp_path):
    """The guard must not swallow the true positive: a doc naming a path that
    is neither tracked, nor ignored, nor on disk is still wrong."""
    repo = _repo(tmp_path, {"src/main.ts": "export const ok = 1;\n"})
    r = probes._probe_path(repo, "src/does-not-exist.ts", git=True)
    assert r["verdict"] == CONTRADICTED
    assert "not on disk" in r["why"]


def test_a_tracked_file_is_still_upheld(tmp_path):
    repo = _repo(tmp_path, {"src/main.ts": "export const ok = 1;\n"})
    assert probes._probe_path(repo, "src/main.ts", git=True)["verdict"] == UPHELD
