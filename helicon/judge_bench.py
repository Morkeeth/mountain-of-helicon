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


# The HARD set: contradictions with no shared keywords (paraphrase), overlapping
# ranges, a dead name asserted as current, and unit drift; plus hard NEGATIVES
# that share a subject but do NOT contradict (a lexical judge over-flags these).
# category, is_contradiction, a, b. Facts are Oscar's real ones (vault + rulings).
HARD_PROBES = [
    # --- contradictions the judge SHOULD flag (no easy lexical overlap) ---
    ("paraphrase", True,
     "Yieldbound is a treasury that compounds yield-bearing positions.",
     "Yieldbound just reads balances across wallets; it only shows numbers."),
    ("overlapping-range", True,
     "The Ligurian coast trip runs March 14 to 22.",
     "The Ligurian itinerary is booked August 15 to 24."),
    ("dead-name-as-current", True,
     "Our project RELAY just shipped its points-sink feature this week.",
     "FAVOUR is the project's current name; RELAY is the dead pre-rebrand name."),
    ("unit-drift", True,
     "Ledger secures more than 8 million hardware devices.",
     "Ledger has about 20 million users."),
    ("number-in-words", True,
     "This recording is episode 29 of the podcast.",
     "This is the twenty-fifth episode we have published."),
    ("status-flip", True,
     "The security audit says the escrow bug is NOT patched.",
     "The escrow drain fix was merged into main on July 4."),
    # --- hard NEGATIVES: same subject, different facts, NOT a contradiction ---
    ("same-subject-diff-fact", False,
     "Avery's birthday is May 18.",
     "Avery's wedding is in September."),
    ("definition-plus-history", False,
     "Yieldbound is a yield treasury.",
     "Yieldbound shipped at the Synthesis hackathon."),
    ("two-goals", False,
     "Training for the Berlin marathon in March.",
     "Also signed up for a trail race in the fall."),
    ("refinement", False,
     "The wedding is the second weekend of September.",
     "The wedding is April 11 to 13."),
    ("whole-vs-part", False,
     "FAVOUR is live with real money.",
     "FAVOUR's new points-sink feature is still in review."),
    ("same-value-paraphrase", False,
     "Nine hackathon wins so far.",
     "Won nine hackathons to date."),
]


def build_probes(which: str = "ruled") -> list[dict]:
    """which = 'ruled' (easy, from rulings) | 'hard' (paraphrase/overlap/etc) | 'all'."""
    probes = []
    if which in ("ruled", "all"):
        for subject, true_v, wrong_v in RULED_CONTRADICTIONS:
            probes.append({"subject": subject, "category": "ruled", "is_contradiction": True,
                           "a": f"Memory note: {subject} is {true_v}.",
                           "b": f"Memory note: {subject} is {wrong_v}."})
            probes.append({"subject": subject, "category": "ruled-control", "is_contradiction": False,
                           "a": f"Memory note: {subject} is {true_v}.",
                           "b": f"Confirmed again: {subject} is {true_v}."})
    if which in ("hard", "all"):
        for category, is_c, a, b in HARD_PROBES:
            probes.append({"subject": category, "category": category,
                           "is_contradiction": is_c, "a": a, "b": b})
    return probes


def judge_probes(config: dict, probes: list[dict], tiers) -> dict:
    """Run each tier's Qwen judge over every probe. Returns per-tier verdicts +
    wall-clock latency. Uses the Qwen cache so reruns are free."""
    from helicon.qwen import (detect_contradictions, get_client, resolve_model,
                              _call_log, TIER_COST_PER_1K)
    client = get_client(config)
    if client is None:
        return {"error": "no Qwen key configured (set QWEN_API_KEY)"}
    out = {}
    for tier in tiers:
        model = resolve_model(tier, config)
        verdicts, latency = [], 0.0
        start = len(_call_log)
        for p in probes:
            t0 = time.time()
            res = detect_contradictions(client, p["a"], p["b"], model=model)
            latency += time.time() - t0
            verdicts.append(bool(res and res.get("contradicts")))
        tok = sum((e.get("input_tokens", 0) or 0) + (e.get("output_tokens", 0) or 0)
                  for e in _call_log[start:])
        cost = round(tok / 1000 * TIER_COST_PER_1K.get(model, 0.0), 5)
        out[tier] = {"model": model, "verdicts": verdicts, "latency_s": round(latency, 1),
                     "tokens": tok, "cost_usd": cost}
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
        misses = [f"{probes[i].get('category', probes[i].get('subject', '?'))}"
                  f"({'FN' if probes[i]['is_contradiction'] else 'FP'})"
                  for i in range(len(probes))
                  if v[i] != probes[i]["is_contradiction"]]
        rows[tier] = {
            "model": d["model"], "latency_s": d.get("latency_s"),
            "tokens": d.get("tokens"), "cost_usd": d.get("cost_usd"),
            "pos_n": len(pos), "neg_n": len(neg),
            "recall": round(tp / len(pos), 3) if pos else None,
            "specificity": round(tn / len(neg), 3) if neg else None,
            "accuracy": round((tp + tn) / (len(pos) + len(neg)), 3) if probes else None,
            "caught": tp, "passed": tn, "misses": misses,
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
               f"{'accuracy':>8}  {'cost':>9}  {'latency':>8}")
    for r in rows.values():
        rec = f"{r['caught']}/{r['pos_n']}" if r["recall"] is not None else "n/a"
        spec = f"{r['passed']}/{r['neg_n']}" if r["specificity"] is not None else "n/a"
        cost = f"${r['cost_usd']}" if r.get("cost_usd") is not None else "n/a"
        out.append(f"  {r['model']:22}  {rec:>7}  {spec:>11}  "
                   f"{str(r['accuracy']):>8}  {cost:>9}  {str(r['latency_s'])+'s':>8}")
    for tier, r in rows.items():
        if r["misses"]:
            out.append(f"      {r['model']} missed: {', '.join(r['misses'])}")
    if scored["inter_tier_agreement"] is not None:
        out.append("")
        out.append(f"  inter-tier agreement: {scored['inter_tier_agreement']} "
                   "(how often the cheap tier tracks the deep one)")
    out.append("")
    out.append("  recall = real contradictions caught; specificity = consistent pairs "
               "correctly passed (FN=missed contradiction, FP=over-flagged control).")
    out.append("  ground truth = the operator's own rulings + real vault facts; "
               "sentences constructed, verdicts human. cost from live token usage.")
    out.append("")
    return "\n".join(out)


def run_judge_bench(config: dict, tiers, which: str = "ruled") -> dict:
    probes = build_probes(which)
    judged = judge_probes(config, probes, tiers=tiers)
    if "error" in judged:
        return judged
    return {"probes": probes, "judged": judged, "scored": score_tiers(probes, judged)}
