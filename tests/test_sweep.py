"""helicon sweep — the doorway gate over many repos.

Hermetic: every case runs against a local directory (sweep_repo takes a path as
well as an owner/name), so nothing here touches the network. The engine reuses
`helicon.doorway.verdict`; these tests pin the aggregation, the classification,
and the honest exclusion of unscorable repos.
"""
import os
import re
import subprocess
from pathlib import Path

import pytest

from helicon import sweep


ROOT = Path(__file__).resolve().parents[1]


def _repo(root, files):
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    for cmd in (["git", "init", "-q"], ["git", "add", "-A"],
                ["git", "commit", "-qm", "fx"]):
        subprocess.run(cmd, cwd=root, env=env, check=True, capture_output=True)
    return str(root)


def test_classify_kind_reads_the_probe_command():
    assert sweep.classify_kind("git ls-files -- config/x.yaml") == "named-path-gone"
    assert sweep.classify_kind('git grep -n -- "CUSTODY_RETIRED"') == "retired-capability-advertised"
    assert sweep.classify_kind("git log -1 --format=%s") == "quoted-command-output-disagrees"
    assert sweep.classify_kind(None) == "other"


def test_a_missing_path_claim_is_contradicted(tmp_path):
    repo = _repo(tmp_path, {
        "CLAUDE.md": "The config file is `config/settings.yaml`.\n",
        "src/main.py": "x = 1\n"})
    r = sweep.sweep_repo(repo)
    assert r["status"] == "scored"
    assert r["contradicted"] == 1
    assert r["findings"][0]["kind"] == "named-path-gone"
    assert r["findings"][0]["probe"] and r["findings"][0]["stdout"] is not None


def test_a_repo_whose_docs_agree_is_clean(tmp_path):
    repo = _repo(tmp_path, {
        "CLAUDE.md": "The entry point is `src/main.py`.\n",
        "src/main.py": "x = 1\n"})
    r = sweep.sweep_repo(repo)
    assert r["status"] == "scored"
    assert r["contradicted"] == 0


def test_one_probe_on_a_long_physical_line_publishes_one_finding(tmp_path):
    """A result belongs to the assertion that earned it, not every sentence on
    the same physical Markdown line.

    Real corpus shape: BenjaminBenetti/fmwk-pwr and joemooney/aida keep long
    multi-sentence paragraphs on one line. `repo_detail` indexed probes by
    (file, line), then painted the one path contradiction onto all five
    assertions on that line — 18 duplicate findings across the scorecard even
    though the loader and raw prober each saw the document once.
    """
    repo = _repo(tmp_path, {
        "CLAUDE.md": (
            "Entry point is `src/missing.ts`. "
            "It starts the server. "
            "The server handles requests. "
            "Tests exercise the API. "
            "Deployments use containers.\n"
        ),
        "src/present.ts": "export const ok = 1;\n",
    })

    result = sweep.sweep_repo(repo)

    assert result["contradicted"] == 1
    assert len(result["findings"]) == 1
    assert result["findings"][0]["probe"] == "git ls-files -- src/missing.ts"


def test_a_directory_without_a_rules_file_is_excluded_not_clean(tmp_path):
    repo = _repo(tmp_path, {"src/main.py": "x = 1\n"})
    r = sweep.sweep_repo(repo)
    assert r["status"] == "no-rules-file"
    assert r["contradicted"] == 0


def test_run_sweep_aggregates_and_only_scored_repos_are_the_denominator(tmp_path):
    bad = _repo(tmp_path / "bad", {
        "CLAUDE.md": "Config lives in `config/gone.yaml`.\n", "a.py": "x=1\n"})
    good = _repo(tmp_path / "good", {
        "CLAUDE.md": "The entry point is `a.py`.\n", "a.py": "x=1\n"})
    norules = _repo(tmp_path / "norules", {"a.py": "x=1\n"})

    sc = sweep.run_sweep([bad, good, norules], jobs=2)
    assert sc["scored"] == 2          # norules is excluded from the denominator
    assert sc["flagged"] == 1
    assert sc["rate"] == 0.5
    assert sc["by_status"]["no-rules-file"] == 1
    assert sc["by_kind"].get("named-path-gone") == 1


def test_scorecard_never_publishes_when_own_output_names_an_existing_file(
        tmp_path, monkeypatch):
    """Publication invariant, independent of whichever probe produced the row.

    The glob branch had a local strict-mode guard, but five grep findings still
    published their own existing source path. Basename and non-git path branches
    are included here so the invariant cannot regress one branch at a time.
    """
    repo = _repo(tmp_path, {
        "CLAUDE.md": "The old API remains available.\n",
        "packages/server/src/main.ts": "export const main = 1;\n",
        "public/config.js": "window.config = {};\n",
        "src/api.ts": "export const status = 410;\n",
    })

    def verdict(*_args, **_kwargs):
        rows = [
            ("git ls-files -- *main.ts", "packages/server/src/main.ts"),
            ("test -f config.js", "public/config.js"),
            ("git grep -n -- 410", "src/api.ts:1:export const status = 410;"),
        ]
        return {
            "contradicted": [
                {
                    "file": "CLAUDE.md",
                    "line": index,
                    "text": f"claim {index}",
                    "probe": probe,
                    "output": output,
                    "why": "fixture contradiction",
                }
                for index, (probe, output) in enumerate(rows, 1)
            ],
        }

    monkeypatch.setattr(sweep.doorway, "verdict", verdict)

    scorecard = sweep.run_sweep([repo], jobs=1)

    assert scorecard["findings_total"] == 0
    assert scorecard["flagged"] == 0
    assert scorecard["results"][0]["findings"] == []


def test_scorecard_still_publishes_when_probe_found_no_file(tmp_path, monkeypatch):
    repo = _repo(tmp_path, {
        "CLAUDE.md": "Config lives in `config/missing.yaml`.\n",
        "src/main.py": "x = 1\n",
    })
    monkeypatch.setattr(
        sweep.doorway,
        "verdict",
        lambda *_args, **_kwargs: {
            "contradicted": [{
                "file": "CLAUDE.md",
                "line": 1,
                "text": "Config lives in `config/missing.yaml`.",
                "probe": "git ls-files -- config/missing.yaml",
                "output": "(no output)",
                "why": "not tracked and not on disk",
            }],
        },
    )

    scorecard = sweep.run_sweep([repo], jobs=1)

    assert scorecard["findings_total"] == 1
    assert scorecard["flagged"] == 1


def test_a_merely_mentioned_path_does_not_flag_a_repo(tmp_path):
    """The class-3 false-positive guard, seen through the sweep: a doc that only
    NAMES a file (an example, a generated file) must not make the repo flagged."""
    repo = _repo(tmp_path, {
        "CLAUDE.md": "Generates `graph.json` from the code. e.g. `foo.ln.json`.\n",
        "src/main.py": "x = 1\n"})
    r = sweep.sweep_repo(repo)
    assert r["status"] == "scored"
    assert r["contradicted"] == 0


def test_load_corpus_ignores_comments_and_blanks(tmp_path):
    f = tmp_path / "corpus.txt"
    f.write_text("# header\n\nowner/one\nowner/two  # trailing\n\n")
    assert sweep.load_corpus(str(f)) == ["owner/one", "owner/two"]


def test_frozen_corpus_is_591_unique_repository_names():
    repos = sweep.load_corpus(str(ROOT / "bench/corpus/agent-context-2026-08.txt"))
    assert len(repos) == 591
    assert len(set(repos)) == 591
    assert all(re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo)
               for repo in repos)


def test_verified_report_matches_complete_survivor_ledger():
    ledger = (ROOT / "docs/agent-context-verification-2026-08-09.md").read_text()
    report = (ROOT / "docs/agent-context-report-2026-08.md").read_text()
    rows = [line for line in ledger.splitlines()
            if re.match(r"^\|\s*\d+\s*\|", line)]

    assert len(rows) == 30
    assert sum("**TRUE**" in row for row in rows) == 9
    assert sum("**FALSE**" in row for row in rows) == 21
    assert "6 / 577 = **1.04%**" in report
    assert "**Input:** 591" in report
    assert "**Scored:** 577" in report
    assert "**Excluded:** 14" in report
    for stale in ("26.6%", "1.74%", "precision 16/47 = 0.34"):
        assert stale not in report


def test_format_sweep_is_stable_and_shows_evidence():
    sc = {"n_input": 2, "scored": 2, "flagged": 1, "rate": 0.5,
          "findings_total": 1, "by_status": {"scored": 2},
          "by_kind": {"named-path-gone": 1}, "distribution": {"0": 1, "1": 1},
          "results": [{"repo": "o/x", "status": "scored", "contradicted": 1,
                       "findings": [{"where": "CLAUDE.md:4", "kind": "named-path-gone",
                                     "claim": "Config lives in `c.yaml`.",
                                     "probe": "git ls-files -- c.yaml",
                                     "stdout": ["(no output)"], "why": "gone"}]},
                      {"repo": "o/y", "status": "scored", "contradicted": 0,
                       "findings": []}]}
    out = sweep.format_sweep(sc)
    assert "1 contain a claim their code disproves (50.0%)" in out
    assert "git ls-files -- c.yaml" in out
    assert "o/x" in out and "o/y" not in out   # only flagged repos are detailed
