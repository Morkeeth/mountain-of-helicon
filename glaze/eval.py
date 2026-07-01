"""Evaluation harness: measures GLAZE's own retrieval, forgetting, and audit quality.

Three benchmarks:
1. Retrieval precision: does glaze_context return the right cubes for known queries?
2. Forgetting accuracy: did Weibull predict kills before humans confirmed them?
3. Audit recall: did the factual audit catch known contradictions?
"""

import json
import sqlite3
from datetime import datetime

from glaze.db import search_cubes
from glaze.score import compute_score


def init_eval_tables(conn: sqlite3.Connection):
    conn.execute("""CREATE TABLE IF NOT EXISTS eval_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_at TEXT NOT NULL,
        precision_at_3 REAL,
        precision_at_5 REAL,
        mrr REAL,
        forgetting_accuracy REAL,
        audit_recall REAL,
        query_count INTEGER,
        details TEXT
    )""")
    conn.commit()


def _build_test_queries(conn: sqlite3.Connection) -> list[dict]:
    """Build test queries from real data: approved cubes become ground truth."""
    queries = []

    approved = conn.execute(
        "SELECT id, title, type, tags, content FROM glaze_cubes "
        "WHERE review_status = 'approved' AND type IN ('memory', 'project', 'draft') "
        "AND title != '' ORDER BY confidence DESC LIMIT 30"
    ).fetchall()

    for cube in approved:
        title = cube["title"]
        tags = []
        try:
            tags = json.loads(cube["tags"]) if cube["tags"] else []
        except (json.JSONDecodeError, TypeError):
            pass

        content = (cube["content"] or "")[:200]

        if "portfolio" in title.lower():
            queries.append({
                "query": "portfolio site design and models",
                "expected_id": cube["id"],
                "description": f"Should find: {title[:50]}",
            })
        elif "relay" in title.lower() or "relay" in str(tags):
            queries.append({
                "query": "RELAY project status and progress",
                "expected_id": cube["id"],
                "description": f"Should find: {title[:50]}",
            })
        elif "bagel" in title.lower() or "bagel" in str(tags):
            queries.append({
                "query": "Bagel agent deployment and operations",
                "expected_id": cube["id"],
                "description": f"Should find: {title[:50]}",
            })
        elif "agent" in title.lower() or "stack" in title.lower():
            queries.append({
                "query": "AI agent stack and multi-agent setup",
                "expected_id": cube["id"],
                "description": f"Should find: {title[:50]}",
            })
        elif "status" in title.lower():
            queries.append({
                "query": "latest project status update",
                "expected_id": cube["id"],
                "description": f"Should find: {title[:50]}",
            })
        elif any(kw in title.lower() for kw in ["proof", "concept", "idea"]):
            queries.append({
                "query": "product concepts and proof of usefulness",
                "expected_id": cube["id"],
                "description": f"Should find: {title[:50]}",
            })
        else:
            words = [w for w in title.split()[:4] if len(w) > 3]
            if words:
                queries.append({
                    "query": " ".join(words),
                    "expected_id": cube["id"],
                    "description": f"Should find: {title[:50]}",
                })

    seen_queries = set()
    deduped = []
    for q in queries:
        if q["query"] not in seen_queries:
            seen_queries.add(q["query"])
            deduped.append(q)

    return deduped[:20]


def _run_retrieval_benchmark(conn: sqlite3.Connection) -> dict:
    """Measure retrieval precision with hybrid search (semantic + FTS5)."""
    queries = _build_test_queries(conn)
    if not queries:
        return {"precision_at_3": 0, "precision_at_5": 0, "mrr": 0, "query_count": 0, "details": [], "search_mode": "none"}

    use_hybrid = False
    try:
        from glaze.embeddings import hybrid_search, get_embedding_stats
        stats = get_embedding_stats(conn)
        if stats["embedded"] > 0:
            use_hybrid = True
    except Exception:
        pass

    hits_at_3 = 0
    hits_at_5 = 0
    reciprocal_ranks = []
    details = []

    for q in queries:
        try:
            if use_hybrid:
                results = hybrid_search(conn, q["query"], limit=10)
            else:
                results = search_cubes(conn, q["query"], 10)
            result_ids = [r["id"] for r in results]

            found_at = None
            for i, rid in enumerate(result_ids):
                if rid == q["expected_id"]:
                    found_at = i + 1
                    break

            if found_at and found_at <= 3:
                hits_at_3 += 1
            if found_at and found_at <= 5:
                hits_at_5 += 1

            reciprocal_ranks.append(1.0 / found_at if found_at else 0)

            details.append({
                "query": q["query"],
                "expected": q["description"],
                "found_at_rank": found_at,
                "top_3_titles": [r.get("title", "")[:40] for r in results[:3]],
            })
        except Exception as e:
            details.append({
                "query": q["query"],
                "error": str(e),
                "found_at_rank": None,
            })
            reciprocal_ranks.append(0)

    n = len(queries)
    return {
        "precision_at_3": round(hits_at_3 / n, 3) if n else 0,
        "precision_at_5": round(hits_at_5 / n, 3) if n else 0,
        "mrr": round(sum(reciprocal_ranks) / n, 3) if n else 0,
        "query_count": n,
        "search_mode": "hybrid" if use_hybrid else "fts5",
        "details": details,
    }


def _run_forgetting_benchmark(conn: sqlite3.Connection) -> dict:
    """Honest test: does the decay confidence signal predict what the HUMAN kills?

    Confidence is computed from decay (age + type), independently of the human's
    decision, so this is a real classifier question, not a tautology. We report
    rank-AUC (probability a human-approved cube outranks a human-killed one) and
    balanced accuracy at a single 0.5 threshold, on human labels ONLY (auto-triage
    rows excluded from both sides so the signal isn't graded against itself).

    Returns forgetting_accuracy=None when there aren't enough human labels on both
    sides to measure anything real.
    """
    killed = [r["confidence"] for r in conn.execute(
        "SELECT c.confidence FROM reviews r JOIN glaze_cubes c ON r.cube_id = c.id "
        "WHERE r.decision = 'killed' AND r.session_id != 'auto-triage' "
        "ORDER BY r.reviewed_at DESC LIMIT 200"
    ).fetchall()]

    approved = [r["confidence"] for r in conn.execute(
        "SELECT c.confidence FROM reviews r JOIN glaze_cubes c ON r.cube_id = c.id "
        "WHERE r.decision = 'approved' AND r.session_id != 'auto-triage' "
        "ORDER BY r.reviewed_at DESC LIMIT 200"
    ).fetchall()]

    if len(killed) < 5 or len(approved) < 5:
        return {
            "forgetting_accuracy": None,
            "note": f"insufficient human labels (killed={len(killed)}, approved={len(approved)}; need >=5 each)",
            "killed_total": len(killed),
            "approved_total": len(approved),
        }

    # Rank-AUC = fraction of (approved, killed) pairs where approved has higher
    # confidence, ties counting as 0.5. This is the Mann-Whitney U statistic.
    wins = 0.0
    for a in approved:
        for k in killed:
            if a > k:
                wins += 1.0
            elif a == k:
                wins += 0.5
    auc = wins / (len(approved) * len(killed))

    # Balanced accuracy at threshold 0.5: predict kill if confidence < 0.5.
    sens = sum(1 for k in killed if k < 0.5) / len(killed)      # true kill rate
    spec = sum(1 for a in approved if a >= 0.5) / len(approved)  # true keep rate
    balanced_acc = (sens + spec) / 2

    return {
        # Headline: how well decay separates the human's kills from keeps.
        "forgetting_accuracy": round(auc, 3),
        "metric": "rank_auc (decay predicts human kill)",
        "balanced_accuracy_at_0.5": round(balanced_acc, 3),
        "mean_conf_killed": round(sum(killed) / len(killed), 3),
        "mean_conf_approved": round(sum(approved) / len(approved), 3),
        "killed_total": len(killed),
        "approved_total": len(approved),
    }


def _run_audit_recall_benchmark(conn: sqlite3.Connection) -> dict:
    """Measure: did the audit engine find real issues?"""
    total_findings = conn.execute(
        "SELECT COUNT(*) FROM audit_log"
    ).fetchone()[0]

    confirmed = conn.execute(
        "SELECT COUNT(*) FROM audit_log WHERE human_decision IS NOT NULL"
    ).fetchone()[0]

    by_type = conn.execute(
        "SELECT audit_type, COUNT(*) as cnt, "
        "SUM(CASE WHEN human_decision = 'confirmed' THEN 1 ELSE 0 END) as confirmed_cnt "
        "FROM audit_log GROUP BY audit_type"
    ).fetchall()

    stale_cubes = conn.execute(
        "SELECT COUNT(*) FROM glaze_cubes "
        "WHERE confidence < 0.05 AND review_status = 'pending'"
    ).fetchone()[0]

    flagged_stale = conn.execute(
        "SELECT COUNT(*) FROM audit_log WHERE audit_type = 'decay'"
    ).fetchone()[0]

    # Precision/recall both need a negative class (findings a human DISMISSED).
    # The review vocabulary only records positive engagement (acted/acknowledged)
    # and never a rejection, so any "rate" here can only ever be 1.0 - manufactured,
    # not measured. We therefore report engagement descriptively and return None for
    # the rate rather than a fake number. (Previously this divided by a stale-cube
    # count that is structurally 0, always yielding a fake 1.0.)
    negatives = conn.execute(
        "SELECT COUNT(*) FROM audit_log "
        "WHERE human_decision IN ('dismissed', 'rejected', 'ignored', 'false')"
    ).fetchone()[0]

    if confirmed > 0 and negatives > 0:
        positives = confirmed - negatives
        audit_recall = round(positives / confirmed, 3)
        note = f"precision on {confirmed} human-reviewed findings"
    else:
        audit_recall = None
        note = (f"not scored: {confirmed} findings acted on, 0 dismissals recorded "
                f"(no negative class to compute a rate)")

    return {
        "audit_recall": audit_recall,
        "note": note,
        "total_findings": total_findings,
        "human_engaged": confirmed,
        "stale_cubes_found": flagged_stale,
        "stale_cubes_actual": stale_cubes,
        "by_type": [dict(r) for r in by_type],
    }


def run_eval(conn: sqlite3.Connection) -> dict:
    """Run all three benchmarks and store results."""
    init_eval_tables(conn)

    retrieval = _run_retrieval_benchmark(conn)
    forgetting = _run_forgetting_benchmark(conn)
    audit = _run_audit_recall_benchmark(conn)

    now = datetime.utcnow().isoformat()

    # Only average metrics that have real ground truth. A metric that returns None
    # (no labels) is excluded and its weight is redistributed, so the composite is
    # never propped up by a fabricated number.
    components = [
        (retrieval["precision_at_3"], 0.3),
        (retrieval["mrr"], 0.2),
        (forgetting.get("forgetting_accuracy"), 0.3),
        (audit.get("audit_recall"), 0.2),
    ]
    live = [(v, w) for v, w in components if v is not None]
    total_w = sum(w for _, w in live)
    composite = round(sum(v * w for v, w in live) / total_w * 100, 1) if total_w else 0.0

    conn.execute(
        "INSERT INTO eval_runs (run_at, precision_at_3, precision_at_5, mrr, "
        "forgetting_accuracy, audit_recall, query_count, details) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (now, retrieval["precision_at_3"], retrieval["precision_at_5"],
         retrieval["mrr"], forgetting["forgetting_accuracy"],
         audit["audit_recall"], retrieval["query_count"],
         json.dumps({"retrieval": retrieval["details"]})),
    )
    conn.commit()

    return {
        "composite_score": composite,
        "retrieval": {
            "precision_at_3": retrieval["precision_at_3"],
            "precision_at_5": retrieval["precision_at_5"],
            "mrr": retrieval["mrr"],
            "query_count": retrieval["query_count"],
            "search_mode": retrieval.get("search_mode", "fts5"),
            "details": retrieval["details"],
        },
        "forgetting": forgetting,
        "audit": audit,
        "run_at": now,
    }


def _estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars/token). Used for relative raw-vs-consolidated ratios."""
    return max(1, len(text) // 4)


_JUDGE_SYS = (
    "You are a strict evaluator of AI agent memory. Given a question and two memory "
    "representations, score how well each lets an agent answer the question accurately and "
    "completely. Reward concise, current, coherent knowledge. Penalize noise, duplication, "
    "and stale or contradictory claims. Be objective; do not favor longer text."
)


def _judge_prompt(query: str, raw_text: str, cons_text: str) -> str:
    return f"""Question an agent must answer: "{query}"

REPRESENTATION A — raw memory items (unconsolidated):
{raw_text[:4000]}

REPRESENTATION B — consolidated memory (single synthesis):
{cons_text[:2000]}

Score each 0-100 on how well it lets the agent answer the question (completeness, accuracy,
freedom from contradiction/noise). Return JSON only:
{{"raw_score": <0-100>, "consolidated_score": <0-100>, "reason": "<one sentence>"}}"""


def run_consolidation_eval(conn: sqlite3.Connection, qwen_client=None, sample: int = 12) -> dict:
    """Before/after consolidation eval: token efficiency + (optional) Qwen-judged answer
    quality, comparing raw source cubes against their consolidated synthesis."""
    from glaze.consolidation import get_consolidations

    cons = get_consolidations(conn)
    if not cons:
        return {"error": "no consolidations found - run `glaze consolidate --qwen` first", "summary": {"consolidations_evaluated": 0}}

    if qwen_client:
        from glaze.qwen import complete_json

    rows_out = []
    raw_tok_total = 0
    cons_tok_total = 0
    quality_pairs = []

    for c in cons[:sample]:
        cube_ids = c.get("cube_ids", [])
        parts = []
        for cid in cube_ids:
            row = conn.execute(
                "SELECT title, content, source, type FROM glaze_cubes WHERE id = ?", (cid,)
            ).fetchone()
            if row:
                parts.append(f"[{row['source']}/{row['type']}] {row['title']}: {(row['content'] or '')[:300]}")
        if not parts:
            continue

        raw_text = "\n\n".join(parts)
        cons_text = (c.get("summary") or "").strip()
        if not cons_text:
            continue

        rt = _estimate_tokens(raw_text)
        ct = _estimate_tokens(cons_text)
        raw_tok_total += rt
        cons_tok_total += ct

        entry = {
            "topic": c.get("topic", ""),
            "title": c.get("title", ""),
            "cube_count": len(cube_ids),
            "raw_tokens": rt,
            "consolidated_tokens": ct,
            "compression": round(rt / ct, 1) if ct else 0,
        }

        if qwen_client:
            try:
                query = f"What do we currently know about {c.get('topic') or 'this topic'}?"
                j = complete_json(qwen_client, _JUDGE_SYS, _judge_prompt(query, raw_text, cons_text), operation="consolidation_eval")
                if j and isinstance(j, dict):
                    rs = float(j.get("raw_score", 0))
                    cs = float(j.get("consolidated_score", 0))
                    entry["raw_score"] = rs
                    entry["consolidated_score"] = cs
                    entry["quality_delta"] = round(cs - rs, 1)
                    quality_pairs.append((rs, cs))
            except Exception as e:
                entry["judge_error"] = str(e)

        rows_out.append(entry)

    summary = {
        "consolidations_evaluated": len(rows_out),
        "raw_tokens_total": raw_tok_total,
        "consolidated_tokens_total": cons_tok_total,
        "avg_compression": round(raw_tok_total / cons_tok_total, 1) if cons_tok_total else 0,
        "token_reduction_pct": round((1 - cons_tok_total / raw_tok_total) * 100, 1) if raw_tok_total else 0,
    }
    if quality_pairs:
        avg_raw = sum(p[0] for p in quality_pairs) / len(quality_pairs)
        avg_cons = sum(p[1] for p in quality_pairs) / len(quality_pairs)
        summary["judged"] = len(quality_pairs)
        summary["avg_raw_quality"] = round(avg_raw, 1)
        summary["avg_consolidated_quality"] = round(avg_cons, 1)
        summary["avg_quality_delta"] = round(avg_cons - avg_raw, 1)
        summary["consolidated_at_least_as_good"] = sum(1 for p in quality_pairs if p[1] >= p[0])

    return {"summary": summary, "details": rows_out}


def get_eval_history(conn: sqlite3.Connection) -> list[dict]:
    init_eval_tables(conn)
    rows = conn.execute(
        "SELECT id, run_at, precision_at_3, precision_at_5, mrr, "
        "forgetting_accuracy, audit_recall, query_count "
        "FROM eval_runs ORDER BY run_at DESC LIMIT 20"
    ).fetchall()
    return [dict(r) for r in rows]
