"""Mountain of Helicon MCP Server - expose memory audit as tools for AI agents.

Run with: python -m helicon.mcp_server
"""

import json
import sys
from datetime import datetime, timezone

from helicon.config import load_config
from helicon.db import init_db, search_cubes
from helicon.score import compute_score
from helicon.forgetting import get_decay_stats
from helicon.triage import run_auto_triage, init_triage_table


def _read_message():
    # MCP stdio transport = newline-delimited JSON-RPC (one JSON object per line),
    # NOT LSP Content-Length framing. Skip blank lines; ignore any line that isn't
    # a JSON object so a stray log line can't wedge the loop.
    while True:
        line = sys.stdin.readline()
        if not line:
            return None
        line = line.strip()
        if not line:
            continue
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue


def _send_message(msg):
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


TOOLS = [
    {
        "name": "helicon_health",
        "description": "Get the current health score of your memory system. Returns: overall score (0-100), total memories, reviewed count, pending count, decay stats by type.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "helicon_stale",
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
        "name": "helicon_search",
        "description": "Full-text search across all memories. Use to check if something is already stored or find related memories.",
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
        "name": "helicon_contradictions",
        "description": "Find audit findings that flag contradictions between stored memories.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "helicon_recent_reviews",
        "description": "See the human's most recent review decisions. Useful to understand what they approve vs kill.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Number of recent reviews. Default 10", "default": 10},
            },
        },
    },
    {
        "name": "helicon_patterns",
        "description": "Get learned behavioral patterns about how the human reviews agent output.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "helicon_flag",
        "description": "Flag a memory by its id (from helicon_context results). Use when a retrieved memory is stale (outdated), wrong (never true), or notably useful. stale/wrong become findings the human confirms, nothing is deleted by this call. Call it the moment you or the human notice bad context.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "memory_id": {"type": "string", "description": "Memory id, e.g. gc_ab12cd34ef56"},
                "verdict": {"type": "string", "enum": ["stale", "wrong", "useful"], "description": "stale = outdated, wrong = never true, useful = confirmed helpful"},
                "reason": {"type": "string", "description": "One line on why (optional but valuable)"},
            },
            "required": ["memory_id", "verdict"],
        },
    },
    {
        "name": "helicon_guard",
        "description": "Check a proposed output against the compiled law (GOLDEN_RULES) BEFORE you write it. Pass the claim/text you are about to assert; Mountain of Helicon returns any rulings it contradicts - a dead project name used as current, or a definition a human ruled against. verdict is 'blocked' (a critical ruling contradicts it - do not write it), 'warn', or 'clean'. Call it before asserting facts about the user's projects, names, or decisions, so a ruled-against claim never lands.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The output/claim you are about to write"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "helicon_context",
        "description": "Proactive memory injection. Describe what you're working on and Mountain of Helicon returns the most relevant memories, ranked by freshness, confidence, and relevance. Use at the start of a task to load context. Every memory carries its id, last_verified date and used_count. If any memory is stale or wrong, call helicon_flag with that id.",
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
        "name": "helicon_ask",
        "description": "Guarded retrieve — ask what is safe to believe about a topic BEFORE you answer or act. The read-side mirror of helicon_guard: returns the ruled-true answer for any topic a human has settled, plus retrieved context split into safe_context (nothing contradicts a ruling) and flagged_context (still asserts a value ruled WRONG — do not believe it). Use this before asserting a fact that a stale memory could get wrong.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "What you want the trusted answer + safe context for"},
                "limit": {"type": "integer", "description": "Max retrieved memories to screen. Default 10", "default": 10},
            },
            "required": ["question"],
        },
    },
    {
        "name": "helicon_brief",
        "description": "The morning brief — the whole system of record in one call. Returns all five pillars: truth (what's no longer trustworthy + grade), continuity (verified context carried), direction (which model earned its cost, or insufficient evidence), reflection (what changed), calm (the few findings worth a human ruling). Use to self-orient at the start of a session — what is true, what needs a decision, what to do next.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max items per pillar section. Default 3", "default": 3},
            },
        },
    },
    {
        "name": "helicon_playbook",
        "description": "Get task-specific guidance based on learned review patterns and feedback. Describe what you're about to do and Mountain of Helicon returns the relevant playbook with rules, common mistakes, and a prompt template.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "What task you're about to start (e.g., 'build a new feature', 'write content', 'audit the codebase')"},
            },
            "required": ["task"],
        },
    },
    {
        "name": "helicon_compile",
        "description": "Compile Mountain of Helicon's learned patterns into injectable files: core-memory.md (top memories), skill files (per-category rules), and a CLAUDE.md patch. Returns the compiled content.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "output_dir": {"type": "string", "description": "Directory to write files. Default: data/compiled", "default": "data/compiled"},
                "core_only": {"type": "boolean", "description": "Only return core memory block, don't write files", "default": False},
            },
        },
    },
    {
        "name": "helicon_triage",
        "description": "Run auto-triage on pending memory items. Mountain of Helicon auto-approves/kills items where it has high confidence based on learned patterns. Returns what was triaged and why.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dry_run": {"type": "boolean", "description": "Preview without acting. Default false", "default": False},
            },
        },
    },
    {
        "name": "helicon_consolidate",
        "description": "Find clusters of related memories and merge them into consolidated summaries. Uses embedding similarity to detect semantic duplicates across sources. Reduces memory bloat while preserving information.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "max_clusters": {"type": "integer", "description": "Max clusters to consolidate. Default 10", "default": 10},
                "use_qwen": {"type": "boolean", "description": "Use Qwen LLM for synthesis. Default false (uses extractive summary)", "default": False},
            },
        },
    },
    {
        "name": "helicon_portrait",
        "description": "Read the record: a grounded portrait of who the memory shows this person is. Returns who and what recur, the mix of work they make, the areas they invest in, the record's health (reviewed %, rot classes firing, volatile facts, golden rules), and the three moves the record argues for. Call this at the start of a session to orient fast on who you are working with and what their memory needs.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    # --- Workgraph (salvaged from the frozen submission's 0639b53) ---
    {
        "name": "helicon_prompt_gate",
        "description": "Gate an agent execution prompt through a Workgraph Wager. Pass a wager_id. Helicon returns an approved, outcome-accountable execution prompt only when a human accepted a BUILD or REPAIR move. Otherwise it abstains and explains the required human action. This tool never starts work or fabricates a next move.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "wager_id": {"type": "string", "description": "Workgraph Wager id, e.g. wg_ab12cd34ef56"},
            },
            "required": ["wager_id"],
        },
    },
    {
        "name": "helicon_workgraph_trace",
        "description": "Inspect the connected evidence behind a Work Card: human outcome contract, TaskRun, frozen context/memory item ids, declared skills, artifacts, receipts, and next moves. This is read-only provenance, not a causal score or recommendation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "wager_id": {"type": "string", "description": "Work Card id, e.g. wg_ab12cd34ef56"},
            },
            "required": ["wager_id"],
        },
    },
    {
        "name": "helicon_workgraph_attention",
        "description": "Return factual Work Graph interventions: missing run links, unfrozen context, unverified artifacts, missing outcome receipts, or open cards without a next move. This is a queue of missing record edges, never a performance score or invented recommendation.",
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "default": 30}},
        },
    },
    {
        "name": "helicon_workgraph_learning",
        "description": "Read outcome observations for linked Work Cards by harness, model, and declared skill. Recommendations are explicitly withheld until each observed group reaches Helicon's resolved-outcome evidence floor. This never infers causality from a diff or one successful run.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "helicon_workgraph_review_skill",
        "description": "Bind an exact skill version declared on a Work Card's linked TaskRun to a SHA-256 snapshot of the local instruction file you actually reviewed. This records instruction provenance only; it never claims the skill is good or that the Work Card outcome is proven.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "wager_id": {"type": "string", "description": "Work Card id"},
                "skill_version": {"type": "string", "description": "Exact declared version, e.g. workgraph@1"},
                "source_path": {"type": "string", "description": "Readable local instruction file inspected"},
            },
            "required": ["wager_id", "skill_version", "source_path"],
        },
    },
    {
        "name": "helicon_capture_launch",
        "description": "Start a real local agent run from an accepted BUILD or REPAIR Work Card. It creates the TaskRun, links it to the card, and freezes a privacy-filtered ContextPacket before implementation. It does not run an agent. Call once immediately before work, then use helicon_capture_closeout after you have actual artifacts and a human verification result.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "wager_id": {"type": "string", "description": "Accepted open Work Card id"},
                "acceptance_test": {"type": "string", "description": "Concrete test/observation frozen before work"},
                "query": {"type": "string", "description": "Optional context selection query; defaults to the card intent"},
                "model": {"type": "string", "description": "Model actually executing the work"},
                "harness": {"type": "string", "description": "Harness, e.g. claude-code, cursor, codex"},
                "skill_versions": {"type": "array", "items": {"type": "string"}, "description": "Declared skill versions actually loaded"},
                "repo_ref": {"type": "string", "description": "Local repository path/reference"},
            },
            "required": ["wager_id", "acceptance_test", "harness"],
        },
    },
    {
        "name": "helicon_capture_closeout",
        "description": "Close a previously captured local agent run. Hashes the readable local artifact files, records the supplied human verification result and receipt, and attaches that receipt to its Work Card. This does not resolve the human outcome. Never call it with invented verification or paths you did not produce.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_run_id": {"type": "string", "description": "TaskRun id returned by helicon_capture_launch"},
                "artifacts": {"type": "array", "items": {"type": "string"}, "description": "Readable local files to hash"},
                "verification": {"type": "string", "enum": ["verified", "contradicted", "unverified"], "description": "Human verification result"},
                "evidence": {"type": "string", "description": "Actual command output, URL, or observation supporting the verification"},
                "input_tokens": {"type": "integer", "minimum": 0, "description": "Observed model input tokens, if the harness supplied them; requires output_tokens"},
                "output_tokens": {"type": "integer", "minimum": 0, "description": "Observed model output tokens, if the harness supplied them; requires input_tokens"},
            },
            "required": ["task_run_id", "artifacts", "verification", "evidence"],
        },
    },
]

# Remote callers get the agent workflow, not host-level maintenance. `flag`
# writes only a pending finding for later human review, while context retrieval
# records usage. The excluded tools can write arbitrary compiled files or run
# bulk store mutations and therefore retain the stronger local-stdio trust
# boundary.
REMOTE_TOOL_NAMES = frozenset(
    tool["name"] for tool in TOOLS
    if tool["name"] not in {"helicon_compile", "helicon_triage", "helicon_consolidate"}
)
SUPPORTED_PROTOCOL_VERSIONS = ("2025-03-26", "2024-11-05")


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
        from helicon.embeddings import hybrid_search, get_embedding_stats
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
            "FROM helicon_cubes WHERE review_status IN ('approved', 'pending') "
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

    from helicon.utility import get_q_values_batch, LAMBDA, DEFAULT_Q
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
                    age_days = (datetime.now(timezone.utc).replace(tzinfo=None) - created).days
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

    # Ghost pass: would this task have wanted memory we retired? (regret ledger)
    try:
        from helicon.regret import record_ghost_hits
        record_ghost_hits(conn, task, source="mcp")
    except Exception:
        pass

    # Log retrieval + update utility tracking
    from helicon.utility import record_surfaced
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
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
        "AND human_decision IS NULL AND machine_decision IS NULL "
        "ORDER BY audited_at DESC LIMIT 3"
    ).fetchall()

    clean_results = []
    for s in selected:
        # provenance the agent can act on: when this memory was last verified
        # and how often it has been served, plus the id helicon_flag needs
        prov = conn.execute(
            "SELECT c.last_reinforced, COALESCE(u.times_surfaced, 0) AS used "
            "FROM helicon_cubes c LEFT JOIN memory_utility u ON u.cube_id = c.id "
            "WHERE c.id = ?", (s["id"],)
        ).fetchone()
        clean_results.append({
            "id": s["id"],
            "title": s["title"],
            "type": s["type"],
            "source": s["source"],
            "confidence": s["confidence"],
            "content_preview": s["content_preview"],
            "relevance_source": s["relevance_source"],
            "composite_score": round(s["composite_score"], 3),
            "last_verified": (prov["last_reinforced"] or "")[:10] if prov else "",
            "used_count": prov["used"] if prov else 0,
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


def _flag_memory(conn, memory_id: str, verdict: str, reason: str = "") -> dict:
    """Point-of-use correction. stale/wrong become PENDING audit findings the
    human confirms in FINDINGS; the agent proposes, it never kills or directly
    trains utility ranking. Only a later human ruling may update Q-values."""

    cube = conn.execute(
        "SELECT id, title, review_status FROM helicon_cubes WHERE id = ?", (memory_id,)
    ).fetchone()
    if cube is None:
        return {"ok": False, "error": f"no memory with id {memory_id}"}

    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    if verdict == "useful":
        conn.execute(
            "UPDATE retrieval_log SET was_acted_on = 1 WHERE cube_id = ? AND was_acted_on = 0",
            (memory_id,),
        )
        conn.execute(
            """INSERT INTO audit_log (audit_type, target_type, target_id, finding,
               severity, proposed_action, human_decision, details, audited_at)
               VALUES ('agent-flag', 'cube', ?, ?, 'low', 'keep', NULL,
                       '{"agent_verdict":"useful"}', ?)""",
            (memory_id, "Agent flagged as useful", now),
        )
        conn.commit()
        return {"ok": True, "memory_id": memory_id, "verdict": "useful",
                "effect": ("retrieval marked acted-on; pending finding created; "
                           "human confirmation required before utility reward")}

    # stale / wrong -> pending finding, human decides
    finding = f"Agent flagged as {verdict}" + (f": {reason}" if reason else "")
    conn.execute(
        """INSERT INTO audit_log (audit_type, target_type, target_id, finding,
           severity, proposed_action, human_decision, details, audited_at)
           VALUES ('agent-flag', 'cube', ?, ?, ?, 'kill', NULL, ?, ?)""",
        (memory_id, finding, "high" if verdict == "wrong" else "medium",
         json.dumps({"agent_verdict": verdict}), now),
    )
    conn.commit()
    return {"ok": True, "memory_id": memory_id, "verdict": verdict,
            "effect": "pending finding created; human confirms in FINDINGS; nothing deleted"}


def handle_tool_call(name: str, arguments: dict, conn) -> str:
    if name == "helicon_prompt_gate":
        from helicon.wager import WagerError, compile_execution_prompt
        try:
            return json.dumps({
                "verdict": "approved",
                "wager_id": arguments.get("wager_id", ""),
                "prompt": compile_execution_prompt(conn, arguments.get("wager_id", "")),
            }, indent=2)
        except WagerError as exc:
            return json.dumps({
                "verdict": "abstain",
                "wager_id": arguments.get("wager_id", ""),
                "reason": str(exc),
            }, indent=2)

    if name == "helicon_workgraph_trace":
        from helicon.wager import WagerError, trace_work_card
        try:
            return json.dumps(trace_work_card(conn, arguments.get("wager_id", "")), indent=2)
        except WagerError as exc:
            return json.dumps({"error": str(exc)}, indent=2)

    if name == "helicon_workgraph_attention":
        from helicon.wager import workgraph_attention
        return json.dumps({"attention": workgraph_attention(conn, arguments.get("limit", 30))}, indent=2)

    if name == "helicon_workgraph_learning":
        from helicon.wager import workgraph_learning
        return json.dumps(workgraph_learning(conn), indent=2)

    if name == "helicon_workgraph_review_skill":
        from helicon.wager import WagerError, review_declared_skill
        try:
            return json.dumps(review_declared_skill(
                conn, arguments.get("wager_id", ""), skill_version=arguments.get("skill_version", ""),
                source_path=arguments.get("source_path", "")), indent=2)
        except WagerError as exc:
            return json.dumps({"error": str(exc)}, indent=2)

    if name == "helicon_capture_launch":
        from helicon.workgraph_capture import CaptureError, launch
        from helicon.wager import WagerError, compile_execution_prompt
        wager_id = arguments.get("wager_id", "")
        try:
            # A capture cannot become a backdoor around the Prompt Gate.
            prompt = compile_execution_prompt(conn, wager_id)
            result = launch(conn, wager_id, acceptance_test=arguments.get("acceptance_test", ""),
                            query=arguments.get("query", ""), model=arguments.get("model", ""),
                            harness=arguments.get("harness", ""), skills=arguments.get("skill_versions", []) or [],
                            repo_ref=arguments.get("repo_ref"))
            return json.dumps({**result, "execution_prompt": prompt}, indent=2)
        except (CaptureError, WagerError) as exc:
            return json.dumps({"error": str(exc)}, indent=2)

    if name == "helicon_capture_closeout":
        from helicon.workgraph_capture import CaptureError, close
        from helicon.taskrun import TaskRunError
        try:
            return json.dumps(close(conn, arguments.get("task_run_id", ""),
                                    artifacts=arguments.get("artifacts", []) or [],
                                    verification=arguments.get("verification", ""),
                                    evidence=arguments.get("evidence", ""),
                                    input_tokens=arguments.get("input_tokens"),
                                    output_tokens=arguments.get("output_tokens")), indent=2)
        except (CaptureError, TaskRunError) as exc:
            return json.dumps({"error": str(exc)}, indent=2)

    if name == "helicon_flag":
        return json.dumps(_flag_memory(
            conn, arguments.get("memory_id", ""),
            arguments.get("verdict", ""), arguments.get("reason", "")))

    if name == "helicon_guard":
        from helicon.guard import guard_output
        return json.dumps(guard_output(conn, arguments.get("text", "")))

    if name == "helicon_health":
        score = compute_score(conn)
        decay = get_decay_stats(conn)
        return json.dumps({
            "score": score["score"],
            "total": score["total"],
            "reviewed": score["reviewed"],
            "pending": score["pending"],
            "decay_by_type": decay,
        }, indent=2)

    elif name == "helicon_stale":
        threshold = arguments.get("threshold", 0.1)
        limit = arguments.get("limit", 10)
        rows = conn.execute(
            "SELECT id, title, type, source, confidence, created_at "
            "FROM helicon_cubes WHERE confidence < ? AND review_status = 'pending' "
            "AND merged_into IS NULL ORDER BY confidence ASC LIMIT ?",
            (threshold, limit),
        ).fetchall()
        return json.dumps([dict(r) for r in rows], indent=2)

    elif name == "helicon_search":
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

    elif name == "helicon_contradictions":
        rows = conn.execute(
            "SELECT finding, severity, details FROM audit_log "
            "WHERE audit_type = 'factual' AND human_decision IS NULL "
            "AND machine_decision IS NULL "
            "ORDER BY audited_at DESC LIMIT 10"
        ).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            d["details"] = json.loads(d["details"]) if d["details"] else {}
            results.append(d)
        return json.dumps(results, indent=2)

    elif name == "helicon_recent_reviews":
        limit = arguments.get("limit", 10)
        rows = conn.execute(
            "SELECT cube_id, decision, notes, cube_type, cube_source, reviewed_at "
            "FROM reviews ORDER BY reviewed_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return json.dumps([dict(r) for r in rows], indent=2)

    elif name == "helicon_patterns":
        rows = conn.execute(
            "SELECT name, description, pattern_type, data_points, confidence "
            "FROM patterns WHERE status = 'active' ORDER BY confidence DESC"
        ).fetchall()
        return json.dumps([dict(r) for r in rows], indent=2)

    elif name == "helicon_context":
        task = arguments.get("task", "")
        limit = arguments.get("limit", 10)
        max_tokens = arguments.get("max_tokens", 4000)
        results = _proactive_context(conn, task, limit, max_tokens)
        return json.dumps(results, indent=2)

    elif name == "helicon_ask":
        from helicon.retrieve_guard import guarded_context
        question = arguments.get("question", "")
        limit = arguments.get("limit", 10)
        return json.dumps(guarded_context(conn, question, limit=limit), indent=2)

    elif name == "helicon_brief":
        from helicon.brief import build_brief
        limit = arguments.get("limit", 3)
        return json.dumps(build_brief(conn, limit=limit), indent=2)

    elif name == "helicon_playbook":
        task = arguments.get("task", "")
        from helicon.playbooks import get_playbook_for_task, build_playbooks, get_playbooks
        playbooks = get_playbooks(conn)
        if not playbooks:
            build_playbooks(conn)
        result = get_playbook_for_task(conn, task)
        if result:
            return json.dumps(result, indent=2)
        return json.dumps({"error": "No matching playbook", "task": task, "available_categories": list(TASK_CATEGORIES.keys()) if 'TASK_CATEGORIES' in dir() else ["build", "content", "design", "audit", "context", "career"]})

    elif name == "helicon_compile":
        from helicon.compiler import compile_core_memory, write_compiled_files
        core_only = arguments.get("core_only", False)
        if core_only:
            return compile_core_memory(conn)
        output_dir = arguments.get("output_dir", "data/compiled")
        result = write_compiled_files(conn, output_dir)
        return json.dumps(result, indent=2)

    elif name == "helicon_triage":
        dry_run = arguments.get("dry_run", False)
        result = run_auto_triage(conn, dry_run=dry_run)
        return json.dumps({
            "triaged": result["triaged"],
            "rules_applied": result["rules_applied"],
            "dry_run": result["dry_run"],
            "actions": result["actions"][:20],
        }, indent=2)

    elif name == "helicon_consolidate":
        from helicon.consolidation import find_clusters, run_consolidation
        max_clusters = arguments.get("max_clusters", 10)
        use_qwen = arguments.get("use_qwen", False)
        qwen_client = None
        if use_qwen:
            from helicon.qwen import get_client
            qwen_client = get_client(load_config())
        result = run_consolidation(conn, qwen_client, max_clusters)
        return json.dumps(result, indent=2)

    elif name == "helicon_portrait":
        from helicon.portrait import build_portrait
        from helicon.qwen import get_client
        cfg = load_config()
        return json.dumps(build_portrait(conn, cfg, client=get_client(cfg)), indent=2, default=str)

    return json.dumps({"error": f"Unknown tool: {name}"})


def handle_rpc_message(msg: dict, conn, *, allowed_tool_names=None):
    """Handle one MCP JSON-RPC message for stdio or stateless HTTP.

    Notifications intentionally return ``None``. Remote transports pass an
    allowlist so a bearer token grants agent-context access, not arbitrary host
    file writes or bulk maintenance.
    """
    if not isinstance(msg, dict):
        return {
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32600, "message": "Invalid Request"},
        }

    method = msg.get("method", "")
    msg_id = msg.get("id")
    allowed = set(allowed_tool_names) if allowed_tool_names is not None else {
        tool["name"] for tool in TOOLS
    }

    if method == "initialize":
        params = msg.get("params", {})
        requested_version = params.get("protocolVersion") if isinstance(params, dict) else None
        protocol_version = (
            requested_version
            if requested_version in SUPPORTED_PROTOCOL_VERSIONS
            else SUPPORTED_PROTOCOL_VERSIONS[-1]
        )
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": protocol_version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "helicon", "version": "0.2.0"},
            },
        }

    if method == "notifications/initialized":
        return None

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "tools": [tool for tool in TOOLS if tool["name"] in allowed],
            },
        }

    if method == "tools/call":
        params = msg.get("params", {})
        if not isinstance(params, dict) or not isinstance(params.get("arguments", {}), dict):
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32602, "message": "Invalid tool parameters"},
            }
        tool_name = params.get("name", "")
        if tool_name not in allowed:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32602, "message": f"Tool not available: {tool_name}"},
            }
        result_text = handle_tool_call(tool_name, params.get("arguments", {}), conn)
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "content": [{"type": "text", "text": result_text}],
                "isError": False,
            },
        }

    if msg_id is None:
        return None
    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def main():
    config = load_config()
    conn = init_db(config.get("db_path", "data/helicon.db"))
    init_triage_table(conn)

    while True:
        msg = _read_message()
        if msg is None:
            break

        response = handle_rpc_message(msg, conn)
        if response is not None:
            _send_message(response)

    conn.close()


if __name__ == "__main__":
    main()
