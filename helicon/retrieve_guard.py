"""Guarded retrieve — the read side of the ruling engine (Continuity + Truth).

The guard (`helicon.guard.guard_output`) stops a WRITE that re-asserts a fact a human
ruled wrong. Guarded retrieve does the mirror on READ: before an agent believes the
context it just retrieved, that context is filtered through the same human rulings.

Two things come back:
  1. the *trusted answer* — for any topic the question is about, the value the human
     ruled current (and the values ruled wrong);
  2. the retrieved memory split into `safe_context` (nothing contradicts a ruling)
     and `flagged_context` (still carries a ruled-wrong value), so a stale fact never
     silently rides into the agent's belief.

Same rulings, other direction: the guard stops bad writes; this stops bad beliefs.
It is read-only — it retrieves and screens, it never mutates a memory or a ruling.
"""

from helicon.guard import _load_factual_resolutions, guard_output


def _topics_in_task(resolutions: list[dict], task: str) -> list[dict]:
    """Rulings whose topic noun appears in the question — the ones it's asking about."""
    low = (task or "").lower()
    return [r for r in resolutions if r["topic"] and r["topic"].lower() in low]


def guarded_context(conn, task: str, limit: int = 10, max_tokens: int = 4000) -> dict:
    """Retrieve context for `task`, then screen every retrieved memory through the
    compiled rulings. `conn` must have `row_factory = sqlite3.Row` (as the API and CLI
    connect it) — the ruling loader reads rows by column name."""
    from helicon.mcp_server import _proactive_context

    base = _proactive_context(conn, task, limit=limit, max_tokens=max_tokens)
    resolutions = _load_factual_resolutions(conn)

    trusted = [
        {
            "topic": r["topic"],
            "answer": r["true_value"],
            "ruled_wrong": r["wrong_values"],
            "ruling_id": r["audit_id"],
            "resolved_at": r["resolved_at"],
        }
        for r in _topics_in_task(resolutions, task)
    ]

    safe, flagged = [], []
    for m in base.get("relevant_memories", []):
        text = f"{m.get('title', '')} {m.get('content_preview', '')}"
        g = guard_output(conn, text)
        critical = [v for v in g.get("violations", []) if v.get("severity") == "critical"]
        if critical:
            v = critical[0]
            flagged.append(
                {
                    **m,
                    "ruling_conflict": {
                        "message": v.get("message"),
                        "provenance": v.get("provenance"),
                    },
                }
            )
        else:
            safe.append(m)

    return {
        "task": task,
        "trusted_answer": trusted,          # what the rulings say is true, for topics asked about
        "safe_context": safe,               # retrieved memory no ruling contradicts
        "flagged_context": flagged,         # retrieved memory that still asserts a ruled-wrong value
        "suppressed_count": len(flagged),
        "memory_health": base.get("memory_health"),
        "open_contradictions": base.get("open_contradictions", []),
    }


def format_guarded_context(res: dict) -> str:
    """Human-readable rendering for the CLI."""
    lines = [f'\n  Guarded retrieve for: "{res["task"]}"']

    if res["trusted_answer"]:
        lines.append("\n  Trusted answer (per your rulings):")
        for t in res["trusted_answer"]:
            wrong = ", ".join(t["ruled_wrong"]) if t["ruled_wrong"] else "—"
            lines.append(
                f"    • {t['topic']} = {t['answer']}   "
                f"(ruled wrong: {wrong} · ruling #{t['ruling_id']})"
            )
    else:
        lines.append("\n  Trusted answer: no ruling covers this topic — treat retrieved context as unverified.")

    if res["flagged_context"]:
        lines.append(f"\n  ⚠ {res['suppressed_count']} retrieved memory contradicts a ruling — held back:")
        for m in res["flagged_context"]:
            lines.append(f"    ✗ [{m['id']}] {m.get('title', '')}")
            lines.append(f"        ↳ {m['ruling_conflict']['message']}")

    lines.append(f"\n  Safe context ({len(res['safe_context'])} memories, no ruling contradicts):")
    for m in res["safe_context"][:8]:
        lines.append(f"    ✓ [{m['id']}] {m.get('title', '')}")

    return "\n".join(lines) + "\n"
