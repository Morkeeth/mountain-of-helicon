"""Prompted rules — the human states the rule; the system gathers and grades.

The Review 2.0 inversion: instead of deriving rules from hundreds of clicks,
Oscar says "kill code edits older than 30 days unless tagged decision", Qwen
compiles it to a RESTRICTED predicate (whitelisted fields, never freeform
code — predicate meaning must not drift), and before anything is approved the
preview shows the Snorkel-style numbers: coverage, samples, empirical
precision against the human's own review history, and conflicts with other
approved rules. Approval freezes the example set (a regression baseline per
rule) and pins (model, prompt_version).

Applied rules write reviews with session_id='rule:<id>' — excluded from
human-evidence everywhere (see triage.py filters), so a rule can never
launder its own output into "the human said so".
"""
import json
import sqlite3
from datetime import datetime

PROMPT_VERSION = "rule-compiler-v1"

# The whole predicate grammar. Anything outside this is rejected at compile.
ALLOWED_FIELDS = {
    "type": str,            # cube type, e.g. code, memory, decision
    "source": str,          # connector, e.g. claude-code, obsidian, git
    "confidence_lt": float, # decayed confidence below X
    "confidence_gte": float,
    "age_days_gt": float,   # created more than N days ago
    "tags_any": list,       # any of these tags present
    "title_contains": str,  # substring match on title
}

COMPILER_SYSTEM = (
    "You compile a human's natural-language memory-triage rule into a strict "
    "JSON predicate for an SQLite memory store. Use ONLY these match fields: "
    "type (cube type string), source (connector string), confidence_lt (float), "
    "confidence_gte (float), age_days_gt (float), tags_any (list of strings), "
    "title_contains (string). action is 'kill' or 'approve'. Omit fields the "
    "human did not ask for. If the rule cannot be expressed with these fields, "
    'return {"error": "<one line why>"}.'
)


def compile_rule(client, nl_text: str, model: str = "qwen3.6-plus") -> dict:
    """NL -> {action, match} via Qwen, strictly validated. Returns
    {"error": ...} when it can't be expressed or the model output is invalid."""
    from helicon.qwen import complete_json

    user = (f'Rule: "{nl_text}"\n\n'
            'Return ONLY JSON: {"action": "kill"|"approve", "match": {<fields>}}\n'
            'Example: "kill code edits older than 30 days below 60% confidence" ->\n'
            '{"action": "kill", "match": {"type": "code", "age_days_gt": 30, "confidence_lt": 0.6}}')
    data = complete_json(client, COMPILER_SYSTEM, user, model=model, operation="rule-compile")
    if not isinstance(data, dict):
        return {"error": "compiler returned no valid JSON"}
    if "error" in data:
        return {"error": str(data["error"])}
    return validate_predicate(data)


def validate_predicate(data: dict) -> dict:
    action = data.get("action")
    match = data.get("match")
    if action not in ("kill", "approve"):
        return {"error": f"action must be kill or approve, got {action!r}"}
    if not isinstance(match, dict) or not match:
        return {"error": "match must be a non-empty object"}
    for key, val in match.items():
        want = ALLOWED_FIELDS.get(key)
        if want is None:
            return {"error": f"field {key!r} not in the predicate grammar"}
        if want is float and not isinstance(val, (int, float)):
            return {"error": f"{key} must be a number"}
        if want is str and not isinstance(val, str):
            return {"error": f"{key} must be a string"}
        if want is list and not isinstance(val, list):
            return {"error": f"{key} must be a list"}
    return {"action": action, "match": match}


def _where(match: dict) -> tuple[str, list]:
    clauses, params = [], []
    if "type" in match:
        clauses.append("type = ?"); params.append(match["type"])
    if "source" in match:
        clauses.append("source = ?"); params.append(match["source"])
    if "confidence_lt" in match:
        clauses.append("confidence < ?"); params.append(match["confidence_lt"])
    if "confidence_gte" in match:
        clauses.append("confidence >= ?"); params.append(match["confidence_gte"])
    if "age_days_gt" in match:
        clauses.append("created_at < datetime('now', ?)")
        params.append(f"-{float(match['age_days_gt'])} days")
    if "title_contains" in match:
        clauses.append("title LIKE ?"); params.append(f"%{match['title_contains']}%")
    if "tags_any" in match:
        ors = []
        for t in match["tags_any"]:
            ors.append("tags LIKE ?"); params.append(f'%"{t}"%')
        clauses.append("(" + " OR ".join(ors) + ")")
    return " AND ".join(clauses) or "1=1", params


def preview(conn: sqlite3.Connection, pred: dict) -> dict:
    """The numbers shown before approval: coverage, samples, empirical
    precision vs the human's own past decisions, conflicts with other rules."""
    where, params = _where(pred["match"])

    pending = conn.execute(
        f"SELECT COUNT(*) FROM helicon_cubes WHERE {where} "
        "AND review_status = 'pending' AND merged_into IS NULL", params
    ).fetchone()[0]
    samples = [dict(r) for r in conn.execute(
        f"SELECT id, title, type, confidence FROM helicon_cubes WHERE {where} "
        "AND review_status = 'pending' AND merged_into IS NULL "
        "ORDER BY confidence LIMIT 5", params
    ).fetchall()]

    reviewed = conn.execute(
        f"SELECT review_status, COUNT(*) c FROM helicon_cubes WHERE {where} "
        "AND review_status IN ('approved', 'killed', 'revised') "
        "GROUP BY review_status", params
    ).fetchall()
    counts = {r["review_status"]: r["c"] for r in reviewed}
    n = sum(counts.values())
    agree = counts.get("killed", 0) if pred["action"] == "kill" \
        else counts.get("approved", 0) + counts.get("revised", 0)
    disagreeing = [dict(r) for r in conn.execute(
        f"SELECT id, title, review_status FROM helicon_cubes WHERE {where} "
        "AND review_status IN ('approved', 'killed', 'revised') "
        f"AND review_status {'!=' if pred['action'] == 'kill' else '='} 'killed' "
        "LIMIT 5", params
    ).fetchall()]

    conflicts = []
    for other in list_rules(conn, status="approved"):
        if other["action"] == pred["action"]:
            continue
        o_where, o_params = _where(other["predicate"]["match"])
        overlap = conn.execute(
            f"SELECT COUNT(*) FROM helicon_cubes WHERE ({where}) AND ({o_where}) "
            "AND review_status = 'pending'", params + o_params
        ).fetchone()[0]
        if overlap:
            conflicts.append({"rule_id": other["id"], "nl_text": other["nl_text"],
                              "overlap": overlap})

    return {
        "pending_matches": pending,
        "samples": samples,
        "history_n": n,
        "history_agree": agree,
        "precision_vs_history": round(agree / n, 3) if n else None,
        "disagreeing_samples": disagreeing,
        "conflicts": conflicts,
    }


def save_rule(conn: sqlite3.Connection, nl_text: str, pred: dict, model: str,
              prev: dict) -> int:
    """Persist as 'proposed', freezing the approval-time example set as the
    rule's regression baseline."""
    frozen = {"samples": prev["samples"], "disagreeing": prev["disagreeing_samples"],
              "precision_vs_history": prev["precision_vs_history"], "history_n": prev["history_n"]}
    cur = conn.execute(
        "INSERT INTO rules (nl_text, predicate, action, status, model, prompt_version, "
        "frozen_examples, created_at) VALUES (?, ?, ?, 'proposed', ?, ?, ?, ?)",
        (nl_text, json.dumps(pred), pred["action"], model, PROMPT_VERSION,
         json.dumps(frozen), datetime.utcnow().isoformat()),
    )
    conn.commit()
    return cur.lastrowid


def approve_rule(conn: sqlite3.Connection, rule_id: int) -> bool:
    cur = conn.execute(
        "UPDATE rules SET status = 'approved', approved_at = ? WHERE id = ? AND status = 'proposed'",
        (datetime.utcnow().isoformat(), rule_id),
    )
    conn.commit()
    return cur.rowcount > 0


def retire_rule(conn: sqlite3.Connection, rule_id: int) -> bool:
    cur = conn.execute("UPDATE rules SET status = 'retired' WHERE id = ?", (rule_id,))
    conn.commit()
    return cur.rowcount > 0


def list_rules(conn: sqlite3.Connection, status: str | None = None) -> list[dict]:
    q = "SELECT * FROM rules"
    params: list = []
    if status:
        q += " WHERE status = ?"; params.append(status)
    rows = conn.execute(q + " ORDER BY id", params).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["predicate"] = json.loads(d["predicate"])
        out.append(d)
    return out


def apply_rules(conn: sqlite3.Connection, dry_run: bool = True) -> dict:
    """Run every approved rule over pending cubes. Writes reviews with
    session_id='rule:<id>' (never human evidence) + triage_log receipts."""
    from helicon.models import Review
    from helicon.db import insert_review
    from helicon.triage import init_triage_table

    init_triage_table(conn)
    now = datetime.utcnow().isoformat()
    results = []
    total = 0
    for rule in list_rules(conn, status="approved"):
        where, params = _where(rule["predicate"]["match"])
        rows = conn.execute(
            f"SELECT id, title, type, source, created_at FROM helicon_cubes WHERE {where} "
            "AND review_status = 'pending' AND merged_into IS NULL", params
        ).fetchall()
        decision = "killed" if rule["action"] == "kill" else "approved"
        if not dry_run:
            for c in rows:
                insert_review(conn, Review(
                    id=None, cube_id=c["id"], decision=decision,
                    notes=f"rule:{rule['id']} {rule['nl_text'][:80]}",
                    cube_type=c["type"], cube_source=c["source"],
                    reviewed_at=now, session_id=f"rule:{rule['id']}",
                ))
                conn.execute(
                    "INSERT INTO triage_log (cube_id, action, reason, rule_confidence, triaged_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (c["id"], rule["action"], f"rule:{rule['id']} {rule['nl_text'][:60]}",
                     rule["trust"], now),
                )
            conn.commit()
        results.append({"rule_id": rule["id"], "nl_text": rule["nl_text"],
                        "action": rule["action"], "matched": len(rows)})
        total += len(rows)
    return {"dry_run": dry_run, "total": total, "rules": results}
