"""Slice 1: Qwen-as-judge benchmark scoring (ruling-derived probes).

Hermetic: the live judge (Qwen) is behind the CLI; here we test the PURE scorer
and probe construction. Ground truth is the operator's human rulings; positives
are real contradictions (measure recall), negatives are consistent restatements
(measure specificity). No divide-by-zero, no fabricated numbers.
"""
from helicon.judge_bench import build_probes, score_tiers, RULED_CONTRADICTIONS


def test_build_probes_pairs_each_ruling_positive_and_negative():
    probes = build_probes()
    assert len(probes) == 2 * len(RULED_CONTRADICTIONS)
    assert sum(1 for p in probes if p["is_contradiction"]) == len(RULED_CONTRADICTIONS)
    assert sum(1 for p in probes if not p["is_contradiction"]) == len(RULED_CONTRADICTIONS)
    # a positive pairs the true value against the ruled-wrong one
    pos = next(p for p in probes if p["is_contradiction"])
    assert pos["a"] != pos["b"]
    # a negative restates the same value
    neg = next(p for p in probes if not p["is_contradiction"])
    assert "Confirmed again" in neg["b"]


def test_score_recall_specificity_accuracy():
    # 2 real contradictions + 2 consistent controls
    probes = [
        {"is_contradiction": True, "a": "x", "b": "y", "subject": "s1"},
        {"is_contradiction": True, "a": "x", "b": "y", "subject": "s2"},
        {"is_contradiction": False, "a": "x", "b": "x", "subject": "s3"},
        {"is_contradiction": False, "a": "x", "b": "x", "subject": "s4"},
    ]
    judged = {"deep": {"model": "qwen3.7-max", "latency_s": 4.0,
                       # catches 2/2 contradictions, passes 1/2 controls (1 false positive)
                       "verdicts": [True, True, False, True]}}
    r = score_tiers(probes, judged)["rows"]["deep"]
    assert r["recall"] == 1.0            # 2/2 contradictions caught
    assert r["specificity"] == 0.5       # 1/2 controls passed
    assert r["accuracy"] == 0.75         # 3/4 correct


def test_cross_provider_gated_on_key(monkeypatch):
    from helicon import judge_bench
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert judge_bench._openrouter_client() is None       # no key -> no competitor, never faked
    judges, notes = judge_bench.build_judges({}, ["fast"])  # no Qwen key either
    assert judges == []
    assert any("OPENROUTER_API_KEY" in n for n in notes)   # honest "add a key" note


def test_score_skips_notes_key():
    # judged may carry a "_notes" entry; it must not be scored as a judge
    probes = [{"is_contradiction": True, "a": "x", "b": "y", "subject": "s"}]
    judged = {"_notes": ["hi"], "qwen3.6-flash": {"model": "qwen3.6-flash", "verdicts": [True]}}
    rows = score_tiers(probes, judged)["rows"]
    assert list(rows) == ["qwen3.6-flash"]


def test_inter_tier_agreement_and_no_divide_by_zero():
    probes = [{"is_contradiction": True, "a": "x", "b": "y", "subject": "s"},
              {"is_contradiction": False, "a": "x", "b": "x", "subject": "s"}]
    judged = {
        "fast": {"model": "qwen3.6-flash", "verdicts": [True, False]},
        "deep": {"model": "qwen3.7-max", "verdicts": [True, True]},
    }
    s = score_tiers(probes, judged)
    assert s["inter_tier_agreement"] == 0.5     # agree on probe 0, differ on 1
    # all-positive or all-negative edge does not crash
    only_pos = [{"is_contradiction": True, "a": "x", "b": "y", "subject": "s"}]
    r = score_tiers(only_pos, {"deep": {"model": "m", "verdicts": [False]}})["rows"]["deep"]
    assert r["specificity"] is None and r["recall"] == 0.0
