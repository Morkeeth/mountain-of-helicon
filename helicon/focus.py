"""Focus engine — the cherry on the iceberg.

Turns the STATE of a memory (what rotted, what stalled) into the developer's
NEXT MOVES: the next prompt, goal, or loop. Detection is automatic; deciding
what to *do* about it is the human act this surfaces.

Every move must cite the exact memory it came from (Trust-Align, arXiv
2409.11242) and the citation must point at the memory that actually justifies
the move, not a vaguely-related one (Correctness != Faithfulness, 2412.18004).
So we hand Qwen a fixed set of ref-ids and drop any move whose citations do not
resolve back to one of them — no free-floating advice ever ships.
"""

from datetime import datetime

from helicon.qwen import get_client, complete_json


_SYSTEM = """You are Mount Helicon's focus engine. You receive the current STATE of a
developer's AI-agent memory: open FINDINGS (memory that failed a rot check —
contradictions, dead renamed names, stale notes, wrongly-retired memory) and
PROJECT signals (what is stalling, spinning, or decaying). Detection already
happened. Your job is to turn this state into 2-4 concrete NEXT MOVES.

A move is the developer's actual next prompt, goal, or loop — the thing they
would paste to their coding agent or set as a goal this week.

HARD RULES:
1. Every move MUST cite one or more ref ids, drawn ONLY from the provided refs.
   Never invent an id. A move with no citation is invalid.
2. The cited memory must be what actually JUSTIFIES the move (point at the
   finding/cube that the move resolves), not something loosely related.
3. "body" is the real text to paste/act on — concrete and specific to the cited
   memory. No generic advice ("review your memory", "stay focused").
4. Prefer moves that resolve rot (fix a contradiction, retire a dead name,
   revive a wrongly-killed memory) or unblock a stalled project.

Return JSON exactly: {"moves":[{"title":str,"kind":"prompt"|"goal"|"loop",
"body":str,"rationale":str,"cites":[ref_id,...]}]}"""


def _findings_context(conn, limit: int = 14) -> list[dict]:
    """Decision-lane findings only (the rot a human should act on), each as a
    compact ref the model can cite. Reuses the exact API finding builders so
    there is one source of truth and no synthetic data."""
    from helicon.api.findings import _audit_findings, _regret_findings, _lane

    findings = _audit_findings(conn)
    try:
        findings.extend(_regret_findings(conn))
    except Exception:
        pass
    decision = [f for f in findings if _lane(f["kind"]) == "decision"]
    # contradictions / dead names / regrets first — the highest-value rot
    decision.sort(key=lambda f: (f["severity"] != "high", f["kind"]))
    return decision[:limit]


def _recs_context(conn, config, limit: int = 5) -> list[dict]:
    from helicon.projects import get_recommendations
    try:
        recs = get_recommendations(conn, config)
    except Exception:
        recs = []
    return recs[:limit]


def generate_next_moves(conn, config: dict | None = None) -> dict:
    config = config or {}
    findings = _findings_context(conn)
    recs = _recs_context(conn, config)

    # Build the ref table the model is allowed to cite from. Ids are stable and
    # human-meaningful so a citation resolves back to a receipt in the UI.
    refs: dict[str, dict] = {}
    lines: list[str] = []
    for f in findings:
        rid = f["id"]
        refs[rid] = {
            "ref": rid, "kind": f["kind"], "title": f.get("title") or "",
            "why": f.get("why") or "", "source": f.get("source") or "",
            "cube_id": f.get("cube_id"),
        }
        lines.append(f"[{rid}] ({f['kind']}) {f.get('why','')[:200]}")
    for r in recs:
        rid = f"project:{r['name']}"
        refs[rid] = {
            "ref": rid, "kind": "project", "title": r["name"],
            "why": r.get("action") or "; ".join(r.get("reasons", [])),
            "source": "project-intelligence", "cube_id": None,
        }
        sig = (f"{r['cube_count']} cubes, {int(r['ship_rate']*100)}% shipped, "
               f"spin {r['spin_score']}x, {r.get('pending',0)} pending, "
               f"{r['days_since_output']}d since output" if r.get("days_since_output") is not None
               else f"{r['cube_count']} cubes, {int(r['ship_rate']*100)}% shipped")
        lines.append(f"[{rid}] (project) {r['name']}: {r.get('action','')} — {sig}")

    if not refs:
        return {"moves": [], "grounded_in": 0, "generated_at": datetime.utcnow().isoformat(),
                "note": "No open findings or project signals — memory is clean."}

    client = get_client(config)
    if client is None:
        return {"moves": [], "grounded_in": len(refs), "generated_at": datetime.utcnow().isoformat(),
                "note": "No Qwen client configured (set qwen_api_key)."}

    user = ("Current memory state. Cite only these ref ids.\n\nFINDINGS & SIGNALS:\n"
            + "\n".join(lines))
    data = complete_json(client, _SYSTEM, user, model="qwen3.6-plus", operation="focus_next_moves")

    moves_in = (data or {}).get("moves", []) if isinstance(data, dict) else []
    moves_out = []
    for m in moves_in:
        cites = [c for c in (m.get("cites") or []) if c in refs]
        if not cites:
            continue  # Faithfulness guard: no valid citation -> does not ship
        moves_out.append({
            "title": (m.get("title") or "").strip(),
            "kind": m.get("kind") if m.get("kind") in ("prompt", "goal", "loop") else "prompt",
            "body": (m.get("body") or "").strip(),
            "rationale": (m.get("rationale") or "").strip(),
            "receipts": [refs[c] for c in cites],
        })

    return {
        "moves": moves_out,
        "grounded_in": len(refs),
        "dropped_uncited": len(moves_in) - len(moves_out),
        "generated_at": datetime.utcnow().isoformat(),
    }
