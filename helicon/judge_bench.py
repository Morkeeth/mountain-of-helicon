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
import json
import sqlite3
import time
from datetime import datetime, timezone

TIERS = ["fast", "default", "deep"]      # qwen3.6-flash / qwen3.6-plus / qwen3.7-max

# Human-ruled contradictions, from GOLDEN_RULES.md (the rulings + renames the
# operator settled). (subject, true_value, ruled_wrong_value). Stable facts.
RULED_CONTRADICTIONS = [
    ("the number of hackathon wins", "10 wins", "4 wins"),
    ("Lea's birthday", "July 18", "July 13"),
    ("the podcast episode this recording is", "episode 29", "episode 25"),
    ("what Yieldbound is", "a yield treasury", "a wallet tracker"),
    ("Itai's wedding date", "September 11 to 13", "August 14 to 22"),
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
     "The Ligurian coast trip runs August 14 to 22.",
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
     "Lea's birthday is July 18.",
     "Lea's wedding is in September."),
    ("definition-plus-history", False,
     "Yieldbound is a yield treasury.",
     "Yieldbound shipped at the Synthesis hackathon."),
    ("two-goals", False,
     "Training for the Berlin marathon in March.",
     "Also signed up for a trail race in the fall."),
    ("refinement", False,
     "The wedding is the second weekend of September.",
     "The wedding is September 11 to 13."),
    ("whole-vs-part", False,
     "FAVOUR is live with real money.",
     "FAVOUR's new points-sink feature is still in review."),
    ("same-value-paraphrase", False,
     "Ten hackathon wins so far.",
     "Won ten hackathons to date."),
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


def _openrouter_client(config: dict | None = None):
    """Slice 3: any OpenAI-compatible judge (GPT/Claude/...) via OpenRouter, one
    key. Returns None when no key is set - we never fabricate a competitor.

    Reads config.json first and falls back to the environment, which is how
    every other key in this tool is resolved (config.py). This used to be
    env-only, so the Qwen-vs-field comparison was unreachable for anyone who
    keeps their keys where the rest of the tool keeps them."""
    import os
    key = (config or {}).get("openrouter_api_key") or os.environ.get("OPENROUTER_API_KEY")
    if not key:
        return None
    from openai import OpenAI
    return OpenAI(api_key=key, base_url="https://openrouter.ai/api/v1")


def build_judges(config: dict, tiers) -> tuple[list, list]:
    """(judges, notes). Each judge = (label, client, model). Qwen tiers always
    (if a Qwen key exists); competitor models only when OPENROUTER_API_KEY is set."""
    import os
    from helicon.qwen import get_client, resolve_model
    judges, notes = [], []
    qc = get_client(config)
    if qc:
        for t in tiers:
            m = resolve_model(t, config)
            judges.append((m, qc, m))
    else:
        notes.append("no Qwen key (set QWEN_API_KEY)")
    orc = _openrouter_client()
    if orc:
        for m in (os.environ.get("OPENROUTER_JUDGES",
                                 "openai/gpt-5,anthropic/claude-sonnet-5").split(",")):
            m = m.strip()
            if m:
                judges.append((m, orc, m))
    else:
        notes.append("set OPENROUTER_API_KEY (+ optional OPENROUTER_JUDGES) to compare "
                     "Qwen vs GPT/Claude on the same probes")
    return judges, notes


def judge_probes(config: dict, probes: list[dict], tiers) -> dict:
    """Run every judge (Qwen tiers + any competitor) over every probe. Returns
    per-judge verdicts + latency + cost (cost only for models with known pricing).
    Uses the Qwen cache so reruns are free."""
    from helicon.qwen import detect_contradictions, _call_log, TIER_COST_PER_1K
    judges, notes = build_judges(config, tiers)
    if not judges:
        return {"error": "; ".join(notes) or "no judges available"}
    out = {"_notes": notes}
    for label, client, model in judges:
        verdicts, latency, errors = [], 0.0, 0
        start = len(_call_log)
        for p in probes:
            t0 = time.time()
            res = detect_contradictions(client, p["a"], p["b"], model=model)
            latency += time.time() - t0
            # None = the call errored (bad slug / no access / parse fail). Record
            # it as "no verdict", NEVER as "judged not-a-contradiction" - scoring a
            # broken competitor as wrong would fake a Qwen win.
            verdicts.append(None if res is None else bool(res.get("contradicts")))
            errors += 1 if res is None else 0
        tok = sum((e.get("input_tokens", 0) or 0) + (e.get("output_tokens", 0) or 0)
                  for e in _call_log[start:])
        cost = (round(tok / 1000 * TIER_COST_PER_1K[model], 5)
                if model in TIER_COST_PER_1K else None)
        out[label] = {"model": model, "verdicts": verdicts, "latency_s": round(latency, 1),
                      "tokens": tok, "cost_usd": cost, "errors": errors}
    return out


def score_tiers(probes: list[dict], judged: dict) -> dict:
    """Pure scoring (no LLM): per tier recall (positives caught), specificity
    (negatives correctly passed), accuracy, plus inter-tier agreement."""
    pos = [i for i, p in enumerate(probes) if p["is_contradiction"]]
    neg = [i for i, p in enumerate(probes) if not p["is_contradiction"]]
    judged = {k: v for k, v in judged.items() if not k.startswith("_")}
    rows = {}
    for tier, d in judged.items():
        v = d["verdicts"]
        pa = [i for i in pos if v[i] is not None]      # positives the judge answered
        na = [i for i in neg if v[i] is not None]
        tp = sum(1 for i in pa if v[i] is True)
        tn = sum(1 for i in na if v[i] is False)
        answered = len(pa) + len(na)
        misses = [f"{probes[i].get('category', probes[i].get('subject', '?'))}"
                  f"({'FN' if probes[i]['is_contradiction'] else 'FP'})"
                  for i in range(len(probes))
                  if v[i] is not None and v[i] != probes[i]["is_contradiction"]]
        rows[tier] = {
            "model": d["model"], "latency_s": d.get("latency_s"),
            "tokens": d.get("tokens"), "cost_usd": d.get("cost_usd"),
            "errors": d.get("errors", 0),
            "coverage": round(answered / len(probes), 3) if probes else None,
            "pos_n": len(pa), "neg_n": len(na),
            "recall": round(tp / len(pa), 3) if pa else None,
            "specificity": round(tn / len(na), 3) if na else None,
            "accuracy": round((tp + tn) / answered, 3) if answered else None,
            "caught": tp, "passed": tn, "misses": misses,
        }
    tiers = list(judged)
    # agreement only over probes every judge actually answered
    both = [i for i in range(len(probes))
            if all(judged[t]["verdicts"][i] is not None for t in tiers)]
    inter = (round(sum(1 for i in both
                       if len({judged[t]["verdicts"][i] for t in tiers}) == 1) / len(both), 3)
             if len(tiers) >= 2 and both else None)
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
        err = f"  [{r['errors']} errored, cov {r['coverage']}]" if r.get("errors") else ""
        out.append(f"  {r['model']:22}  {rec:>7}  {spec:>11}  "
                   f"{str(r['accuracy']):>8}  {cost:>9}  {str(r['latency_s'])+'s':>8}{err}")
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
    return {"probes": probes, "judged": judged, "notes": judged.get("_notes", []),
            "scored": score_tiers(probes, judged)}


# ---------------------------------------------------------------------------
# Persistence. A judge run costs real money and real seconds (live cross-provider
# calls), so no surface may trigger one on page load: the dashboard reads the LAST
# saved run or says there isn't one. Nothing is ever synthesised to fill the gap —
# an absent run renders as absent (see api/rot.py).
# ---------------------------------------------------------------------------

def init_judge_table(conn: sqlite3.Connection):
    conn.execute("""CREATE TABLE IF NOT EXISTS judge_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_at TEXT NOT NULL,
        probe_set TEXT NOT NULL,          -- ruled | hard | all
        probes INTEGER NOT NULL,
        positives INTEGER,                -- real contradictions in the set
        negatives INTEGER,                -- consistent controls in the set
        inter_tier_agreement REAL,
        notes TEXT,                       -- JSON: what was NOT measured, verbatim
        rows_json TEXT NOT NULL           -- JSON: per-model scored rows
    )""")
    conn.commit()


def save_judge_run(conn: sqlite3.Connection, res: dict, which: str = "ruled") -> int:
    """Persist one completed bench. Returns the new run id."""
    init_judge_table(conn)
    scored = res["scored"]
    probes = res.get("probes", [])
    pos = sum(1 for p in probes if p["is_contradiction"])
    cur = conn.execute(
        "INSERT INTO judge_runs (run_at, probe_set, probes, positives, negatives, "
        "inter_tier_agreement, notes, rows_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (datetime.now(timezone.utc).isoformat(timespec="seconds"), which,
         scored["probes"], pos, len(probes) - pos, scored["inter_tier_agreement"],
         json.dumps(res.get("notes", [])), json.dumps(scored["rows"])),
    )
    conn.commit()
    return cur.lastrowid


def latest_judge_run(conn: sqlite3.Connection) -> dict | None:
    """The last saved bench, or None. None means None: the caller must say so."""
    init_judge_table(conn)
    row = conn.execute(
        "SELECT id, run_at, probe_set, probes, positives, negatives, "
        "inter_tier_agreement, notes, rows_json FROM judge_runs "
        "ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    d["notes"] = json.loads(d.pop("notes") or "[]")
    d["rows"] = json.loads(d.pop("rows_json"))
    return d
