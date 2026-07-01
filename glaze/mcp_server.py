"""GLAZE MCP Server - expose memory audit as tools for AI agents.

Run with: python -m glaze.mcp_server
"""

import json
import sys
from datetime import datetime

from glaze.config import load_config
from glaze.db import init_db, search_cubes
from glaze.score import compute_score
from glaze.forgetting import get_decay_stats
from glaze.triage import run_auto_triage, init_triage_table


def _read_message():
    header = ""
    while True:
        line = sys.stdin.readline()
        if not line:
            return None
        header += line
        if line == "\r\n" or line == "\n":
            break
    content_length = 0
    for h in header.strip().split("\n"):
        if h.lower().startswith("content-length:"):
            content_length = int(h.split(":")[1].strip())
    if content_length == 0:
        return None
    body = sys.stdin.read(content_length)
    return json.loads(body)


def _send_message(msg):
    body = json.dumps(msg)
    sys.stdout.write(f"Content-Length: {len(body)}\r\n\r\n{body}")
    sys.stdout.flush()


TOOLS = [
    {
        "name": "glaze_health",
        "description": "Get the current health score of your memory system. Returns: overall score (0-100), total cubes, reviewed count, pending count, decay stats by type.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "glaze_stale",
        "description": "Find memory items that have decayed below a confidence threshold. These are candidates for review or pruning.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "threshold": {"type": "number", "description": "Confidence threshold (0.0-1.0). Default 0.1", "default": 0.1},
                "limit": {"type": "integer", "description": "Max results. Default 10", "default": 10},
            },
        },
    },
    {
        "name": "glaze_search",
        "description": "Full-text search across all memory cubes. Use to check if something is already stored or find related memories.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "limit": {"type": "integer", "description": "Max results. Default 10", "default": 10},
            },
            "required": ["query"],
        },
    },
    {
        "name": "glaze_contradictions",
        "description": "Find audit findings that flag contradictions between stored memories.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "glaze_recent_reviews",
        "description": "See the human's most recent review decisions. Useful to understand what they approve vs kill.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Number of recent reviews. Default 10", "default": 10},
            },
        },
    },
    {
        "name": "glaze_patterns",
        "description": "Get learned behavioral patterns about how the human reviews agent output.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "glaze_context",
        "description": "Proactive memory injection. Describe what you're working on and GLAZE returns the most relevant memories, ranked by freshness, confidence, and relevance. Use at the start of a task to load context.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "What you're currently working on"},
                "limit": {"type": "integer", "description": "Max results. Default 10", "default": 10},
                "max_tokens": {"type": "integer", "description": "Max total tokens in returned context. Default 4000", "default": 4000},
            },
            "required": ["task"],
        },
    },
    {
        "name": "glaze_playbook",
        "description": "Get task-specific guidance based on learned review patterns and feedback. Describe what you're about to do and GLAZE returns the relevant playbook with rules, common mistakes, and a prompt template.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "What task you're about to start (e.g., 'build a new feature', 'write content', 'audit the codebase')"},
            },
            "required": ["task"],
        },
    },
    {
        "name": "glaze_compile",
        "description": "Compile GLAZE's learned patterns into injectable files: core-memory.md (top memories), skill files (per-category rules), and a CLAUDE.md patch. Returns the compiled content.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "output_dir": {"type": "string", "description": "Directory to write files. Default: data/compiled", "default": "data/compiled"},
                "core_only": {"type": "boolean", "description": "Only return core memory block, don't write files", "default": False},
            },
        },
    },
    {
        "name": "glaze_triage",
        "description": "Run auto-triage on pending memory items. GLAZE auto-approves/kills items where it has high confidence based on learned patterns. Returns what was triaged and why.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dry_run": {"type": "boolean", "description": "Preview without acting. Default false", "default": False},
            },
        },
    },
    {
        "name": "glaze_consolidate",
        "description": "Find clusters of related memories and merge them into consolidated summaries. Uses embedding similarity to detect semantic duplicates across sources. Reduces memory bloat while preserving information.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "max_clusters": {"type": "integer", "description": "Max clusters to consolidate. Default 10", "default": 10},
                "use_qwen": {"type": "boolean", "description": "Use Qwen LLM for synthesis. Default false (uses extractive summary)", "default": False},
            },
        },
    },
]


def _token_estimate(text: str) -> int:
    return len(text) // 4


def _jaccard_similarity(a: str, b: str) -> float:
    """Word-level Jaccard for diversity penalty."""
    sa = set(a.lower().split())
    sb = set(b.lower().split())
    if not sa or not sb:
        return 0
    return len(sa & sb) / len(sa | sb)


def _proactive_context(conn, task: str, limit: int = 10, max_tokens: int = 4000) -> dict:
    """Context-window-aware RAG: rank by relevance * confidence * recency, enforce diversity."""
    candidates = []

    # Try hybrid search (semantic + FTS5) first, fall back to FTS5-only
    use_hybrid = False
    try:
        from glaze.embeddings import hybrid_search, get_embedding_stats
        stats = get_embedding_stats(conn)
        if stats["embedded"] > 0:
            use_hybrid = True
            hybrid_results = hybrid_search(conn, task, limit=limit * 3)
            for r in hybrid_results:
                candidates.append({
                    "id": r["id"],
                    "title": r["title"],
                    "type": r["type"],
                    "source": r["source"],
                    "confidence": r["confidence"],
                    "content_preview": r["content"][:300] if r.get("content") else "",
                    "created_at": r.get("created_at", ""),
                    "fts_rank": 0,
                    "relevance_source": "hybrid",
                    "semantic_score": r.get("semantic_score"),
                    "hybrid_score": r.get("hybrid_score", 0),
                })
    except Exception:
        pass

    if not use_hybrid:
        try:
            fts_results = search_cubes(conn, task, limit * 3)
            for i, r in enumerate(fts_results):
                candidates.append({
                    "id": r["id"],
                    "title": r["title"],
                    "type": r["type"],
                    "source": r["source"],
                    "confidence": r["confidence"],
                    "content_preview": r["content"][:300] if r.get("content") else "",
                    "created_at": r.get("created_at", ""),
                    "fts_rank": i,
                    "relevance_source": "full-text-search",
                })
        except Exception:
            pass

    if len(candidates) < limit * 2:
        recent = conn.execute(
            "SELECT id, title, type, source, confidence, content, created_at "
            "FROM glaze_cubes WHERE review_status IN ('approved', 'pending') "
            "AND merged_into IS NULL AND confidence > 0.2 "
            "ORDER BY created_at DESC LIMIT ?",
            (limit * 2,),
        ).fetchall()
        seen_ids = {c["id"] for c in candidates}
        for r in recent:
            if r["id"] not in seen_ids:
                candidates.append({
                    "id": r["id"],
                    "title": r["title"],
                    "type": r["type"],
                    "source": r["source"],
                    "confidence": r["confidence"],
                    "content_preview": (r["content"] or "")[:300],
                    "created_at": r["created_at"] if "created_at" in r.keys() else "",
                    "fts_rank": len(candidates),
                    "relevance_source": "recency",
                })

    from glaze.utility import get_q_values_batch, LAMBDA, DEFAULT_Q
    q_values = get_q_values_batch(conn, [c["id"] for c in candidates])

    # Entity boost: find entities mentioned in the task, boost linked cubes
    entity_boost = {}
    task_words = set(task.lower().split())
    try:
        entities = conn.execute(
            "SELECT id, name FROM entities"
        ).fetchall()
        matched_entities = [
            e for e in entities if e["name"].lower() in task_words
            or any(w in e["name"].lower() for w in task_words if len(w) > 3)
        ]
        for ent in matched_entities:
            linked = conn.execute(
                "SELECT source_id FROM edges WHERE target_id = ? AND target_kind = 'entity' "
                "UNION SELECT target_id FROM edges WHERE source_id = ? AND source_kind = 'entity'",
                (ent["id"], ent["id"]),
            ).fetchall()
            for link in linked:
                entity_boost[link[0]] = entity_boost.get(link[0], 0) + 0.15
    except Exception:
        pass

    for c in candidates:
        if use_hybrid and c.get("hybrid_score"):
            base_relevance = c["hybrid_score"]
        else:
            fts_score = max(0, 1.0 - c["fts_rank"] * 0.1)
            recency_bonus = 0
            if c.get("created_at"):
                try:
                    raw = c["created_at"].replace("Z", "").split("+")[0]
                    created = datetime.fromisoformat(raw)
                    age_days = (datetime.utcnow() - created).days
                    recency_bonus = max(0, 0.3 - age_days * 0.01)
                except (ValueError, TypeError):
                    pass
            base_relevance = fts_score * 0.5 + c["confidence"] * 0.3 + recency_bonus * 0.2

        q = q_values.get(c["id"], DEFAULT_Q)
        eboost = entity_boost.get(c["id"], 0)
        c["composite_score"] = (1 - LAMBDA) * base_relevance + LAMBDA * q + eboost
        c["q_value"] = q
        c["entity_boost"] = eboost

    candidates.sort(key=lambda x: x["composite_score"], reverse=True)

    # MMR diversity selection
    selected = []
    token_budget = max_tokens
    for c in candidates:
        if len(selected) >= limit:
            break
        tokens = _token_estimate(c["content_preview"])
        if tokens > token_budget:
            continue

        if selected:
            max_sim = max(
                _jaccard_similarity(c["content_preview"], s["content_preview"])
                for s in selected
            )
            if max_sim > 0.6:
                continue

        selected.append(c)
        token_budget -= tokens

    # Log retrieval + update utility tracking
    from glaze.utility import record_surfaced
    now = datetime.utcnow().isoformat()
    for s in selected:
        try:
            conn.execute(
                "INSERT INTO retrieval_log (cube_id, context, was_surfaced, was_acted_on, retrieved_at) "
                "VALUES (?, ?, 1, 0, ?)",
                (s["id"], task[:200], now),
            )
            record_surfaced(conn, s["id"])
        except Exception:
            pass
    try:
        conn.commit()
    except Exception:
        pass

    patterns = conn.execute(
        "SELECT name, description FROM patterns WHERE status = 'active' "
        "ORDER BY confidence DESC LIMIT 5"
    ).fetchall()

    contradictions = conn.execute(
        "SELECT finding FROM audit_log WHERE audit_type = 'factual' "
        "AND human_decision IS NULL ORDER BY audited_at DESC LIMIT 3"
    ).fetchall()

    clean_results = []
    for s in selected:
        clean_results.append({
            "id": s["id"],
            "title": s["title"],
            "type": s["type"],
            "source": s["source"],
            "confidence": s["confidence"],
            "content_preview": s["content_preview"],
            "relevance_source": s["relevance_source"],
            "composite_score": round(s["composite_score"], 3),
        })

    return {
        "task": task,
        "relevant_memories": clean_results,
        "token_budget_used": max_tokens - token_budget,
        "token_budget_remaining": token_budget,
        "active_patterns": [{"name": p["name"], "description": p["description"]} for p in patterns],
        "open_contradictions": [r["finding"] for r in contradictions],
        "memory_health": compute_score(conn),
    }


def handle_tool_call(name: str, arguments: dict, conn) -> str:
    if name == "glaze_health":
        score = compute_score(conn)
        decay = get_decay_stats(conn)
        return json.dumps({
            "score": score["score"],
            "total": score["total"],
            "reviewed": score["reviewed"],
            "pending": score["pending"],
            "decay_by_type": decay,
        }, indent=2)

    elif name == "glaze_stale":
        threshold = arguments.get("threshold", 0.1)
        limit = arguments.get("limit", 10)
        rows = conn.execute(
            "SELECT id, title, type, source, confidence, created_at "
            "FROM glaze_cubes WHERE confidence < ? AND review_status = 'pending' "
            "AND merged_into IS NULL ORDER BY confidence ASC LIMIT ?",
            (threshold, limit),
        ).fetchall()
        return json.dumps([dict(r) for r in rows], indent=2)

    elif name == "glaze_search":
        query = arguments.get("query", "")
        limit = arguments.get("limit", 10)
        try:
            results = search_cubes(conn, query, limit)
            return json.dumps([
                {"id": r["id"], "title": r["title"], "type": r["type"],
                 "source": r["source"], "confidence": r["confidence"]}
                for r in results
            ], indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)})

    elif name == "glaze_contradictions":
        rows = conn.execute(
            "SELECT finding, severity, details FROM audit_log "
            "WHERE audit_type = 'factual' AND human_decision IS NULL "
            "ORDER BY audited_at DESC LIMIT 10"
        ).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            d["details"] = json.loads(d["details"]) if d["details"] else {}
            results.append(d)
        return json.dumps(results, indent=2)

    elif name == "glaze_recent_reviews":
        limit = arguments.get("limit", 10)
        rows = conn.execute(
            "SELECT cube_id, decision, notes, cube_type, cube_source, reviewed_at "
            "FROM reviews ORDER BY reviewed_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return json.dumps([dict(r) for r in rows], indent=2)

    elif name == "glaze_patterns":
        rows = conn.execute(
            "SELECT name, description, pattern_type, data_points, confidence "
            "FROM patterns WHERE status = 'active' ORDER BY confidence DESC"
        ).fetchall()
        return json.dumps([dict(r) for r in rows], indent=2)

    elif name == "glaze_context":
        task = arguments.get("task", "")
        limit = arguments.get("limit", 10)
        max_tokens = arguments.get("max_tokens", 4000)
        results = _proactive_context(conn, task, limit, max_tokens)
        return json.dumps(results, indent=2)

    elif name == "glaze_playbook":
        task = arguments.get("task", "")
        from glaze.playbooks import get_playbook_for_task, build_playbooks, get_playbooks
        playbooks = get_playbooks(conn)
        if not playbooks:
            build_playbooks(conn)
        result = get_playbook_for_task(conn, task)
        if result:
            return json.dumps(result, indent=2)
        return json.dumps({"error": "No matching playbook", "task": task, "available_categories": list(TASK_CATEGORIES.keys()) if 'TASK_CATEGORIES' in dir() else ["build", "content", "design", "audit", "context", "career"]})

    elif name == "glaze_compile":
        from glaze.compiler import compile_core_memory, write_compiled_files
        core_only = arguments.get("core_only", False)
        if core_only:
            return compile_core_memory(conn)
        output_dir = arguments.get("output_dir", "data/compiled")
        result = write_compiled_files(conn, output_dir)
        return json.dumps(result, indent=2)

    elif name == "glaze_triage":
        dry_run = arguments.get("dry_run", False)
        result = run_auto_triage(conn, dry_run=dry_run)
        return json.dumps({
            "triaged": result["triaged"],
            "rules_applied": result["rules_applied"],
            "dry_run": result["dry_run"],
            "actions": result["actions"][:20],
        }, indent=2)

    elif name == "glaze_consolidate":
        from glaze.consolidation import find_clusters, run_consolidation
        max_clusters = arguments.get("max_clusters", 10)
        use_qwen = arguments.get("use_qwen", False)
        qwen_client = None
        if use_qwen:
            from glaze.qwen import get_client
            qwen_client = get_client(load_config())
        result = run_consolidation(conn, qwen_client, max_clusters)
        return json.dumps(result, indent=2)

    return json.dumps({"error": f"Unknown tool: {name}"})


def main():
    config = load_config()
    conn = init_db(config.get("db_path", "data/glaze.db"))
    init_triage_table(conn)

    while True:
        msg = _read_message()
        if msg is None:
            break

        method = msg.get("method", "")
        msg_id = msg.get("id")

        if method == "initialize":
            _send_message({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "glaze", "version": "0.2.0"},
                },
            })

        elif method == "notifications/initialized":
            pass

        elif method == "tools/list":
            _send_message({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"tools": TOOLS},
            })

        elif method == "tools/call":
            params = msg.get("params", {})
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            result_text = handle_tool_call(tool_name, arguments, conn)
            _send_message({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": result_text}],
                    "isError": False,
                },
            })

        elif msg_id is not None:
            _send_message({
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            })

    conn.close()


if __name__ == "__main__":
    main()
