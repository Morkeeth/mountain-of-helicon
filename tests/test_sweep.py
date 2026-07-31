"""helicon sweep — the doorway gate over many repos.

Hermetic: every case runs against a local directory (sweep_repo takes a path as
well as an owner/name), so nothing here touches the network. The engine reuses
`helicon.doorway.verdict`; these tests pin the aggregation, the classification,
and the honest exclusion of unscorable repos.
"""
import os
import subprocess

import pytest

from helicon import sweep


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
