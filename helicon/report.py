"""MemoryAgent compliance report — the exam the track implies, run on real memory.

The MemoryAgent track names four sub-goals: efficient storage & retrieval,
timely forgetting of outdated information, recall under limited context
windows, and cross-session accuracy. Mount Helicon already measures all four;
this module groups the existing checks under the track's own language. Any
memory stack a connector can scan could be scored by this same report.

Every number is computed live from the DB. Sub-goal verdicts use the visible
thresholds below — they are printed with the numbers, never instead of them.
"""
import sqlite3
from collections import Counter

# Sub-goal verdict thresholds. Deliberately few and visible.
THRESHOLDS = {
    "retrieval_mrr_ok": 0.5,        # storage/retrieval: MRR above coin-flip-ish
    "forgetting_auc_ok": 0.7,       # decay signal genuinely predicts human kills
    "recall_pass_rate_ok": 0.8,     # thinness+redundancy pass rate across tasks
    "tokens_per_query_warn": 4000,  # top-K context budget per query
    "regression_free": 0,           # snapshots regressed
}


def _verdict(ok: bool, degraded: bool = False) -> str:
    return "HEALTHY" if ok else ("DEGRADED" if degraded else "BROKEN")


def memoryagent_report(conn: sqlite3.Connection, client=None,
                       model: str = "qwen3.6-plus") -> dict:
    from helicon.battery import run_battery
    from helicon.eval import (_build_test_queries, _run_forgetting_benchmark,
                              _run_retrieval_benchmark)
    from helicon.db import last_scan_info
    from helicon.snapshots import check_all

    # --- shared raw material: the battery over the real benchmark task set ---
    queries = _build_test_queries(conn)
    runs = [run_battery(conn, q["query"], k=5, client=client, model=model)
            for q in queries]
    verdicts = Counter(r["verdict"] for r in runs)
    test_stats: dict = {}
    for r in runs:
        for t in r["results"]:
            s = test_stats.setdefault(t["name"], {"pass": 0, "fail": 0})
            s["pass" if t["status"] == "PASS" else "fail"] += 1
    token_counts = [r["context_tokens"] for r in runs]
    mean_tokens = round(sum(token_counts) / len(token_counts)) if token_counts else 0

    def _rate(name: str) -> float | None:
        s = test_stats.get(name)
        if not s or (s["pass"] + s["fail"]) == 0:
            return None
        return round(s["pass"] / (s["pass"] + s["fail"]), 3)

    # --- 1. efficient storage & retrieval ---
    retrieval = _run_retrieval_benchmark(conn)
    scan = last_scan_info(conn)
    last = conn.execute(
        "SELECT cubes_added, cubes_skipped FROM scan_log "
        "WHERE completed_at IS NOT NULL ORDER BY completed_at DESC LIMIT 1"
    ).fetchone()
    dedup_rate = None
    if last and (last["cubes_added"] + last["cubes_skipped"]):
        dedup_rate = round(last["cubes_skipped"] /
                           (last["cubes_added"] + last["cubes_skipped"]), 3)
    consolidations = conn.execute("SELECT COUNT(*) FROM consolidations").fetchone()[0]
    storage = {
        "precision_at_3": retrieval.get("precision_at_3"),
        "mrr": retrieval.get("mrr"),
        "query_count": retrieval.get("query_count"),
        "search_mode": retrieval.get("search_mode", "hybrid"),
        "ingest_dedup_rate": dedup_rate,
        "consolidations": consolidations,
        "disclosure": "small internal benchmark, one label per query",
        "verdict": _verdict((retrieval.get("mrr") or 0) >= THRESHOLDS["retrieval_mrr_ok"],
                            degraded=(retrieval.get("mrr") or 0) > 0),
    }

    # --- 2. timely forgetting of outdated information ---
    forgetting = _run_forgetting_benchmark(conn)
    retired = conn.execute(
        "SELECT review_status, COUNT(*) c FROM helicon_cubes "
        "WHERE review_status IN ('killed', 'superseded') GROUP BY review_status"
    ).fetchall()
    retired_counts = {r["review_status"]: r["c"] for r in retired}
    auc = forgetting.get("forgetting_accuracy")
    freshness_rate = _rate("Freshness")
    timely_forgetting = {
        "decay_predicts_human_kills_auc": auc,
        "metric_note": forgetting.get("metric") or forgetting.get("note"),
        "retired_superseded": retired_counts.get("superseded", 0),
        "retired_killed": retired_counts.get("killed", 0),
        "freshness_pass_rate": freshness_rate,
        "mechanisms": "Weibull decay per type + reconcile (re-scan retirement) + battery Freshness test",
        "verdict": _verdict(
            auc is not None and auc >= THRESHOLDS["forgetting_auc_ok"]
            and (retired_counts.get("superseded", 0) + retired_counts.get("killed", 0)) > 0,
            degraded=auc is not None),
    }

    # --- 3. recall under limited context windows ---
    thin = _rate("Thinness")
    redun = _rate("Redundancy")
    rates = [x for x in (thin, redun) if x is not None]
    recall_rate = round(sum(rates) / len(rates), 3) if rates else None
    limited_context = {
        "thinness_pass_rate": thin,
        "redundancy_pass_rate": redun,
        "mean_tokens_per_query_top5": mean_tokens,
        "note": "every battery verdict now carries context_tokens: accuracy is priced in budget",
        "verdict": _verdict(
            recall_rate is not None and recall_rate >= THRESHOLDS["recall_pass_rate_ok"]
            and mean_tokens <= THRESHOLDS["tokens_per_query_warn"],
            degraded=recall_rate is not None),
    }

    # --- 4. cross-session accuracy ---
    snaps = check_all(conn)
    regressed = sum(1 for s in snaps if s["regressed"])
    contra_rate = _rate("Contradiction")  # only present when Qwen judged live
    grounding_rate = _rate("Grounding")

    # Cross-source pairing (the R1 selector): every report run scans live
    # memory for disjoint dated facts about the same person across files and
    # files new conflicts into the audit log — the contradiction surfaces
    # here whether or not anyone asked about it.
    from helicon.pairing import pair_scan
    from helicon.claims import claim_scan
    pairing = pair_scan(conn, client=client, model=model)
    claims = claim_scan(conn)
    open_pairs = conn.execute(
        "SELECT COUNT(*) FROM audit_log WHERE audit_type = 'factual' "
        "AND details LIKE '%pair_key%' AND human_decision IS NULL"
    ).fetchone()[0]
    sample_row = conn.execute(
        "SELECT finding FROM audit_log WHERE audit_type = 'factual' "
        "AND details LIKE '%pair_key%' AND human_decision IS NULL "
        "ORDER BY audited_at DESC LIMIT 1"
    ).fetchone()
    cross_source = {
        "conflicts_live": pairing["conflicts_found"] + claims["conflicts_found"],
        "new_findings": len(pairing["filed"]) + len(claims["filed"]),
        "judge_rejected": len(pairing["judge_rejected"]),
        "open_findings": open_pairs,
        "sample": sample_row["finding"] if sample_row else None,
    }

    cross_session = {
        "snapshots_total": len(snaps),
        "snapshots_regressed": regressed,
        "contradiction_pass_rate": contra_rate,
        "grounding_pass_rate": grounding_rate,
        "llm_judged": contra_rate is not None,
        "cross_source_contradictions": cross_source,
        "mechanisms": "snapshot regression (CI for memory) + cross-source pair selector "
                      "+ Qwen-judged Contradiction/Grounding",
        # No baselines captured = unmeasured, not broken. DEGRADED with a
        # pointer beats a fake BROKEN.
        "verdict": ("DEGRADED" if not snaps else _verdict(
            regressed <= THRESHOLDS["regression_free"]
            and (contra_rate is None or contra_rate >= 0.8)
            and open_pairs == 0,
            degraded=True)),
        "note": None if snaps else "no baselines captured — run: helicon snapshot add \"<task>\"",
    }

    from helicon.db import record_battery_point
    if runs:
        record_battery_point(conn, len(runs), verdicts["HEALTHY"],
                             verdicts["DEGRADED"], verdicts["BROKEN"],
                             mean_tokens=mean_tokens, source="report")

    sub_verdicts = [storage["verdict"], timely_forgetting["verdict"],
                    limited_context["verdict"], cross_session["verdict"]]
    overall = ("BROKEN" if "BROKEN" in sub_verdicts
               else "DEGRADED" if "DEGRADED" in sub_verdicts else "HEALTHY")

    return {
        "track": "MemoryAgent",
        "overall": overall,
        "battery_tasks": {"total": len(runs), **{k.lower(): v for k, v in verdicts.items()}},
        "last_scan_hours_ago": scan["hours_ago"] if scan else None,
        "sub_goals": {
            "efficient_storage_retrieval": storage,
            "timely_forgetting": timely_forgetting,
            "recall_under_limited_context": limited_context,
            "cross_session_accuracy": cross_session,
        },
        "thresholds": THRESHOLDS,
    }


def format_report(rep: dict) -> str:
    g = rep["sub_goals"]
    b = rep["battery_tasks"]

    def fmt(v):
        return "n/a" if v is None else v

    lines = [
        "MemoryAgent Compliance Report (all numbers live, thresholds printed below)",
        "",
        f"Overall: {rep['overall']}   "
        f"(battery: {b.get('healthy', 0)} healthy / {b.get('degraded', 0)} degraded / "
        f"{b.get('broken', 0)} broken of {b['total']} tasks; "
        f"last scan {fmt(rep['last_scan_hours_ago'])}h ago)",
        "",
        "1. Efficient storage & retrieval          " + g["efficient_storage_retrieval"]["verdict"],
        f"   P@3 {fmt(g['efficient_storage_retrieval']['precision_at_3'])}  "
        f"MRR {fmt(g['efficient_storage_retrieval']['mrr'])}  "
        f"(n={fmt(g['efficient_storage_retrieval']['query_count'])}, "
        f"{g['efficient_storage_retrieval']['disclosure']})",
        f"   ingest dedup rate {fmt(g['efficient_storage_retrieval']['ingest_dedup_rate'])}, "
        f"{g['efficient_storage_retrieval']['consolidations']} consolidations",
        "",
        "2. Timely forgetting                      " + g["timely_forgetting"]["verdict"],
        f"   decay predicts human kills: rank-AUC {fmt(g['timely_forgetting']['decay_predicts_human_kills_auc'])}",
        f"   retired: {g['timely_forgetting']['retired_superseded']} superseded (reconcile) "
        f"+ {g['timely_forgetting']['retired_killed']} killed (review/triage); "
        f"freshness pass rate {fmt(g['timely_forgetting']['freshness_pass_rate'])}",
        "",
        "3. Recall under limited context windows   " + g["recall_under_limited_context"]["verdict"],
        f"   thinness pass {fmt(g['recall_under_limited_context']['thinness_pass_rate'])}, "
        f"redundancy pass {fmt(g['recall_under_limited_context']['redundancy_pass_rate'])}, "
        f"~{g['recall_under_limited_context']['mean_tokens_per_query_top5']} tokens/query (top-5)",
        "",
        "4. Cross-session accuracy                 " + g["cross_session_accuracy"]["verdict"],
        f"   snapshots: {g['cross_session_accuracy']['snapshots_regressed']} regressed "
        f"of {g['cross_session_accuracy']['snapshots_total']}; "
        f"contradiction pass {fmt(g['cross_session_accuracy']['contradiction_pass_rate'])}, "
        f"grounding pass {fmt(g['cross_session_accuracy']['grounding_pass_rate'])}"
        + ("" if g["cross_session_accuracy"]["llm_judged"] else "  (LLM tests off: no key)"),
        f"   cross-source pairing: "
        f"{g['cross_session_accuracy']['cross_source_contradictions']['conflicts_live']} live conflict(s), "
        f"{g['cross_session_accuracy']['cross_source_contradictions']['open_findings']} open finding(s)"
        + (f"\n     -> {g['cross_session_accuracy']['cross_source_contradictions']['sample']}"
           if g['cross_session_accuracy']['cross_source_contradictions']['sample'] else ""),
        "",
        f"Thresholds: {rep['thresholds']}",
    ]
    return "\n".join(lines)
