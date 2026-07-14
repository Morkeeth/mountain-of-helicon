"""Slice 1: benchmark Qwen as the memory-rot JUDGE against human-ruled ground truth.

The rot exam's contradiction judge (`helicon.qwen.detect_contradictions`) is
Qwen-powered and tier-swappable. This measures how well each Qwen tier judges
contradictions, and it is the keystone of the moonshot: the whole "Qwen is the
verification brain" claim rests on Qwen being a measurably good judge.

Ground truth = Oscar's OWN human rulings (compiled into GOLDEN_RULES): facts a
human settled, each with the true value AND the competing value that was ruled
wrong. That gives a clean labeled set with no selector in the loop:
  - a POSITIVE probe pairs the true value against the ruled-wrong value -> a real
    contradiction the judge SHOULD flag (measures recall).
  - a NEGATIVE probe pairs the true value against a consistent restatement of it
    -> NOT a contradiction, the judge should pass it (measures specificity).
The probe SENTENCES are minimal constructions of the ruled facts; the FACTS and
their verdicts are the human's, not invented. Real judge accuracy, no fabricated
numbers, cross-provider judges plug into the same harness in slice 3.

(An earlier design scored selector-produced pairs by file label; it conflated
file-label with pair-label and measured the selector, not the judge. Replaced.)
"""
import time

TIERS = ["fast", "default", "deep"]      # qwen3.6-flash / qwen3.6-plus / qwen3.7-max

# Human-ruled contradictions, from GOLDEN_RULES.md (the rulings + renames the
# operator settled). (subject, true_value, ruled_wrong_value). Stable facts.
RULED_CONTRADICTIONS = [
    ("the number of hackathon wins", "9 wins", "4 wins"),
    ("Avery's birthday", "May 18", "May 13"),
    ("the podcast episode this recording is", "episode 29", "episode 25"),
    ("what Yieldbound is", "a yield treasury", "a wallet tracker"),
    ("Casey's wedding date", "April 11 to 13", "March 14 to 22"),
    ("the RELAY to FAVOUR rebrand", "executed, FAVOUR is the current name",
     "still open, the project is called RELAY"),
    ("the release/2026-07-04 branch", "merged into main", "not merged, still unmerged"),
]


def build_probes() -> list[dict]:
    """Positive (true vs ruled-wrong = contradiction) and negative (true vs
    consistent restatement = not) probes from the human rulings."""
    probes = []
    for subject, true_v, wrong_v in RULED_CONTRADICTIONS:
        probes.append({
            "subject": subject, "is_contradiction": True,
            "a": f"Memory note: {subject} is {true_v}.",
            "b": f"Memory note: {subject} is {wrong_v}.",
        })
        probes.append({
            "subject": subject, "is_contradiction": False,
            "a": f"Memory note: {subject} is {true_v}.",
            "b": f"Confirmed again: {subject} is {true_v}.",
        })
    return probes


def judge_probes(config: dict, probes: list[dict], tiers) -> dict:
    """Run each tier's Qwen judge over every probe. Returns per-tier verdicts +
    wall-clock latency. Uses the Qwen cache so reruns are free."""
    from helicon.qwen import detect_contradictions, get_client, resolve_model
    client = get_client(config)
    if client is None:
        return {"error": "no Qwen key configured (set QWEN_API_KEY)"}
    out = {}
    for tier in tiers:
        model = resolve_model(tier, config)
        verdicts, latency = [], 0.0
        for p in probes:
            t0 = time.time()
            res = detect_contradictions(client, p["a"], p["b"], model=model)
            latency += time.time() - t0
            verdicts.append(bool(res and res.get("contradicts")))
        out[tier] = {"model": model, "verdicts": verdicts, "latency_s": round(latency, 1)}
    return out


def score_tiers(probes: list[dict], judged: dict) -> dict:
    """Pure scoring (no LLM): per tier recall (positives caught), specificity
    (negatives correctly passed), accuracy, plus inter-tier agreement."""
    pos = [i for i, p in enumerate(probes) if p["is_contradiction"]]
    neg = [i for i, p in enumerate(probes) if not p["is_contradiction"]]
    rows = {}
    for tier, d in judged.items():
        v = d["verdicts"]
        tp = sum(1 for i in pos if v[i])              # contradiction, flagged
        tn = sum(1 for i in neg if not v[i])          # consistent, passed
        rows[tier] = {
            "model": d["model"], "latency_s": d.get("latency_s"),
            "pos_n": len(pos), "neg_n": len(neg),
            "recall": round(tp / len(pos), 3) if pos else None,
            "specificity": round(tn / len(neg), 3) if neg else None,
            "accuracy": round((tp + tn) / (len(pos) + len(neg)), 3) if probes else None,
            "caught": tp, "passed": tn,
        }
    tiers = list(judged)
    inter = (round(sum(1 for i in range(len(probes))
                       if len({judged[t]["verdicts"][i] for t in tiers}) == 1) / len(probes), 3)
             if len(tiers) >= 2 and probes else None)
    return {"rows": rows, "inter_tier_agreement": inter, "probes": len(probes)}


def format_judge_bench(scored: dict) -> str:
    rows = scored["rows"]
    if not rows:
        return "\n  No probes to judge.\n"
    out = ["", f"  QWEN AS MEMORY JUDGE — vs human-ruled ground truth "
           f"({scored['probes']} probes: {scored['probes']//2} real contradictions + "
           f"{scored['probes']//2} consistent controls)", ""]
    out.append(f"  {'tier / model':22}  {'recall':>7}  {'specificity':>11}  "
               f"{'accuracy':>8}  {'latency':>8}")
    for r in rows.values():
        rec = f"{r['caught']}/{r['pos_n']}" if r["recall"] is not None else "n/a"
        spec = f"{r['passed']}/{r['neg_n']}" if r["specificity"] is not None else "n/a"
        out.append(f"  {r['model']:22}  {rec:>7}  {spec:>11}  "
                   f"{str(r['accuracy']):>8}  {str(r['latency_s'])+'s':>8}")
    if scored["inter_tier_agreement"] is not None:
        out.append("")
        out.append(f"  inter-tier agreement: {scored['inter_tier_agreement']} "
                   "(how often the cheap tier tracks the deep one)")
    out.append("")
    out.append("  recall = real contradictions caught; specificity = consistent pairs "
               "correctly passed.")
    out.append("  ground truth = the operator's own GOLDEN_RULES rulings; sentences "
               "constructed, verdicts human.")
    out.append("")
    return "\n".join(out)


def run_judge_bench(config: dict, tiers, limit: int = 24) -> dict:
    from helicon.qwen import get_client
    probes = build_probes()[: limit * 2 if limit else None]
    judged = judge_probes(config, probes, tiers=tiers)
    if "error" in judged:
        return judged
    return {"probes": probes, "judged": judged, "scored": score_tiers(probes, judged)}
