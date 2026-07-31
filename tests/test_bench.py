"""HELICON-BENCH — memory scored against commands that execute.

Pins the property no conversation-only benchmark (LOCOMO, LongMemEval, STALE,
PersistBench) can: a claim the running code disproves scores CONTRADICTED, with
the executed command's stdout as the receipt. Deterministic over the shipped
corpus — the same repos + probes give the same verdicts anywhere.
"""
from helicon import bench


def test_bench_runs_over_the_shipped_corpus():
    sc = bench.run_bench()
    assert sc["exists"] and sc["executed"]
    assert sc["repo_count"] >= 3           # the moonshot bar: >= 3 governed repos
    assert sc["totals"]["probes"] > 0


def test_a_killswitch_repo_scores_contradicted_with_real_stdout():
    sc = bench.run_bench()
    escrow = next(r for r in sc["repos"] if r["repo"] == "escrow-retired")
    assert escrow["contradicted"] >= 1
    rec = escrow["receipts"][0]
    assert "CUSTODY_RETIRED" in (rec["probe"] or "")
    assert any("CUSTODY_RETIRED = true" in ln for ln in rec["stdout"])


def test_a_missing_path_claim_scores_contradicted():
    sc = bench.run_bench()
    stale = next(r for r in sc["repos"] if r["repo"] == "stale-paths")
    assert stale["contradicted"] >= 1
    assert any("settings.yaml" in (rec["claim"] or "") for rec in stale["receipts"])


def test_the_honest_repo_has_no_contradiction():
    sc = bench.run_bench()
    honest = next(r for r in sc["repos"] if r["repo"] == "honest-service")
    assert honest["contradicted"] == 0


def test_an_elided_address_is_unverifiable_not_contradicted():
    sc = bench.run_bench()
    chain = next(r for r in sc["repos"] if r["repo"] == "chain-authority")
    assert chain["contradicted"] == 0
    assert chain["unverifiable"] >= 1      # no RPC / elided address -> unverifiable


def test_bench_is_deterministic():
    a, b = bench.run_bench()["totals"], bench.run_bench()["totals"]
    assert a == b, "same corpus + same probes must score the same anywhere"
