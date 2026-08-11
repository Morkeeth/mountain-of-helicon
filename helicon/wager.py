"""The local-first Workgraph contract.

This module deliberately records the human's wager around an agent run; it does
not infer value from a diff, run an agent, or score a model.  A declared outcome
and its proof requirement are frozen before execution.  Later evidence can prove,
disprove, or leave that wager unproven.
"""
import json
import hashlib
import os
import uuid
from datetime import datetime, timezone


VALID_OUTCOMES = {"proven", "disproven", "unproven"}
VALID_MOVES = {"BUILD", "INVESTIGATE", "ASK", "DECIDE", "REPAIR", "KILL"}
LEARNING_EVIDENCE_FLOOR = 5
OUTCOME_EVIDENCE_KINDS = {"user-feedback", "human-observation", "business-metric", "outcome-observation"}


class WagerError(Exception):
    """A Workgraph contract or state-machine violation."""


def _now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def _required(**fields) -> None:
    absent = [name for name, value in fields.items() if not (value or "").strip()]
    if absent:
        raise WagerError(f"required: {', '.join(absent)}")


def _json_list(value) -> list:
    try:
        parsed = json.loads(value or "[]")
        return parsed if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        return []


def _loads_or_empty_dict(value) -> dict:
    try:
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _is_outcome_evidence(kind: str) -> bool:
    """Outcome evidence is evidence from the beneficiary/world, not execution."""
    return kind in OUTCOME_EVIDENCE_KINDS or kind.startswith("outcome-")


def open_wager(conn, *, intent: str, beneficiary: str, observable_change: str,
               evidence_contract: str, kill_condition: str, task_run_id: str | None = None) -> str:
    """Open a Wager before execution. The five product claims are immutable.

    `task_run_id`, when supplied, must point to an existing TaskRun.  The link is
    optional so a human can make an ASK, DECIDE, or KILL move before an agent run.
    """
    _required(intent=intent, beneficiary=beneficiary, observable_change=observable_change,
              evidence_contract=evidence_contract, kill_condition=kill_condition)
    if task_run_id and conn.execute("SELECT 1 FROM task_runs WHERE id=?", (task_run_id,)).fetchone() is None:
        raise WagerError(f"no such task run: {task_run_id}")
    wager_id = "wg_" + uuid.uuid4().hex[:12]
    conn.execute(
        "INSERT INTO work_wagers (id, task_run_id, intent, beneficiary, observable_change, "
        "evidence_contract, kill_condition, opened_at, status) VALUES (?,?,?,?,?,?,?,?,?)",
        (wager_id, task_run_id, intent, beneficiary, observable_change, evidence_contract,
         kill_condition, _now(), "open"),
    )
    conn.commit()
    return wager_id


def attach_evidence(conn, wager_id: str, *, kind: str, reference: str, note: str = "",
                    observed_at: str | None = None) -> str:
    """Attach a receipt without treating it as outcome proof automatically."""
    _required(kind=kind, reference=reference)
    if conn.execute("SELECT 1 FROM work_wagers WHERE id=?", (wager_id,)).fetchone() is None:
        raise WagerError(f"no such wager: {wager_id}")
    evidence_id = "we_" + uuid.uuid4().hex[:12]
    conn.execute(
        "INSERT INTO work_evidence (id, wager_id, kind, reference, note, observed_at, recorded_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (evidence_id, wager_id, kind, reference, note, observed_at or _now(), _now()),
    )
    conn.commit()
    return evidence_id


def review_declared_skill(conn, wager_id: str, *, skill_version: str, source_path: str) -> dict:
    """Bind one declared skill version to the exact local instructions reviewed.

    This is provenance, not an automated quality verdict: it proves that the
    instructions available to this particular run were inspected as bytes.  A
    skill must already be declared on the Work Card's linked TaskRun so an
    agent cannot launder an unrelated file into the graph.
    """
    _required(skill_version=skill_version, source_path=source_path)
    wager = conn.execute("SELECT task_run_id FROM work_wagers WHERE id=?", (wager_id,)).fetchone()
    if wager is None:
        raise WagerError(f"no such wager: {wager_id}")
    if not wager["task_run_id"]:
        raise WagerError("cannot review a skill before a TaskRun is linked")
    run = conn.execute("SELECT skill_versions FROM task_runs WHERE id=?", (wager["task_run_id"],)).fetchone()
    if run is None or skill_version not in _json_list(run["skill_versions"]):
        raise WagerError("skill version is not declared on the linked TaskRun")
    path = os.path.realpath(os.path.expanduser(source_path))
    if not os.path.isfile(path):
        raise WagerError("skill review source must be a readable local file")
    with open(path, "rb") as handle:
        content_hash = hashlib.sha256(handle.read()).hexdigest()
    review_id = "wsr_" + uuid.uuid4().hex[:12]
    conn.execute(
        "INSERT INTO work_skill_reviews (id, wager_id, skill_version, source_ref, content_hash, reviewed_at) "
        "VALUES (?,?,?,?,?,?) ON CONFLICT(wager_id, skill_version) DO UPDATE SET "
        "id=excluded.id, source_ref=excluded.source_ref, content_hash=excluded.content_hash, reviewed_at=excluded.reviewed_at",
        (review_id, wager_id, skill_version, path, content_hash, _now()),
    )
    conn.commit()
    return {"id": review_id, "wager_id": wager_id, "skill_version": skill_version,
            "content_hash": content_hash, "reviewed": True}


def link_wager_to_run(conn, wager_id: str, task_run_id: str) -> None:
    """Link pre-run planning to its actual TaskRun exactly once.

    A Work Card is deliberately allowed to precede instrumentation. This is the
    explicit join once the operator opens the real run; silently guessing a run
    from prose or timestamps would corrupt the graph.
    """
    wager = conn.execute("SELECT status, task_run_id FROM work_wagers WHERE id=?", (wager_id,)).fetchone()
    if wager is None:
        raise WagerError(f"no such wager: {wager_id}")
    if wager["status"] != "open":
        raise WagerError("cannot link a TaskRun to a resolved wager")
    if wager["task_run_id"]:
        raise WagerError("wager already has a TaskRun; create a new Work Card for a different run")
    if conn.execute("SELECT 1 FROM task_runs WHERE id=?", (task_run_id,)).fetchone() is None:
        raise WagerError(f"no such task run: {task_run_id}")
    conn.execute("UPDATE work_wagers SET task_run_id=? WHERE id=?", (task_run_id, wager_id))
    conn.commit()


def resolve_wager(conn, wager_id: str, outcome: str, *, ruling: str = "") -> None:
    """Record a human outcome. Unproven remains resolvable without a fake pass."""
    if outcome not in VALID_OUTCOMES:
        raise WagerError("outcome must be proven | disproven | unproven")
    wager = conn.execute("SELECT status FROM work_wagers WHERE id=?", (wager_id,)).fetchone()
    if wager is None:
        raise WagerError(f"no such wager: {wager_id}")
    if wager["status"] != "open":
        raise WagerError(f"cannot resolve wager in state: {wager['status']}")
    if outcome in {"proven", "disproven"}:
        receipts = conn.execute("SELECT kind FROM work_evidence WHERE wager_id=?", (wager_id,)).fetchall()
        if not ruling.strip():
            raise WagerError(f"{outcome} requires a human ruling")
        if not any(_is_outcome_evidence(row["kind"]) for row in receipts):
            raise WagerError(f"{outcome} requires at least one outcome evidence receipt, not only execution evidence")
    conn.execute(
        "UPDATE work_wagers SET outcome=?, ruling=?, resolved_at=?, status='resolved' WHERE id=?",
        (outcome, ruling, _now(), wager_id),
    )
    conn.commit()


def record_next_move(conn, wager_id: str, action: str, *, rationale: str, status: str = "proposed") -> str:
    """Record, rather than fabricate, the next human-approved work decision."""
    if action not in VALID_MOVES:
        raise WagerError("action must be one of: " + ", ".join(sorted(VALID_MOVES)))
    _required(rationale=rationale)
    if conn.execute("SELECT 1 FROM work_wagers WHERE id=?", (wager_id,)).fetchone() is None:
        raise WagerError(f"no such wager: {wager_id}")
    move_id = "nm_" + uuid.uuid4().hex[:12]
    conn.execute(
        "INSERT INTO next_moves (id, wager_id, action, rationale, status, created_at) VALUES (?,?,?,?,?,?)",
        (move_id, wager_id, action, rationale, status, _now()),
    )
    conn.commit()
    return move_id


def compile_execution_prompt(conn, wager_id: str) -> str:
    """Compile a governed execution prompt only for an accepted build/repair move.

    The gate deliberately abstains for research and human-decision work. It does
    not invent a next action from a thin data set; it makes the approved human
    action accountable to its Wager instead.
    """
    wager = conn.execute("SELECT * FROM work_wagers WHERE id=?", (wager_id,)).fetchone()
    if wager is None:
        raise WagerError(f"no such wager: {wager_id}")
    if wager["status"] != "open":
        raise WagerError("cannot compile a prompt for a resolved wager")
    move = conn.execute(
        "SELECT action, rationale FROM next_moves WHERE wager_id=? AND status='accepted' "
        "ORDER BY created_at DESC LIMIT 1", (wager_id,),
    ).fetchone()
    if move is None:
        raise WagerError("Prompt Gate abstains: record an accepted next move before execution")
    if move["action"] not in {"BUILD", "REPAIR"}:
        raise WagerError(f"Prompt Gate abstains: accepted action is {move['action']}, not agent execution")
    return "\n".join([
        "# Helicon Workgraph execution contract",
        f"Wager: {wager['id']}",
        f"Approved action: {move['action']}",
        f"Intent: {wager['intent']}",
        f"Beneficiary: {wager['beneficiary']}",
        f"Observable change: {wager['observable_change']}",
        f"Evidence required to claim success: {wager['evidence_contract']}",
        f"Kill condition: {wager['kill_condition']}",
        f"Why this action: {move['rationale']}",
        "",
        "Execute the smallest coherent slice that can produce the observable change.",
        "Do not claim the outcome is proven merely because code, tests, or a diff exist.",
        "At closeout, return: artifact references, execution evidence, outcome evidence (if any),",
        "what remains unproven, and whether the kill condition fired.",
    ])


def trace_work_card(conn, wager_id: str) -> dict:
    """Return the evidence graph behind one Work Card, without inferring causality.

    The graph deliberately reports the records actually connected today: the
    human outcome contract, TaskRun, frozen ContextPacket and safe item ids,
    declared skills, artifacts, receipts, and next moves. A missing edge is
    represented as missing—not silently reconstructed from a model's prose.
    """
    wager = conn.execute("SELECT * FROM work_wagers WHERE id=?", (wager_id,)).fetchone()
    if wager is None:
        raise WagerError(f"no such wager: {wager_id}")

    trace = {
        "work_card": {
            "id": wager["id"], "intent": wager["intent"], "beneficiary": wager["beneficiary"],
            "observable_change": wager["observable_change"], "evidence_contract": wager["evidence_contract"],
            "kill_condition": wager["kill_condition"], "outcome": wager["outcome"],
            "ruling": wager["ruling"], "status": wager["status"], "opened_at": wager["opened_at"],
        },
        "task_run": None, "context_packet": None, "skills": [], "skill_reviews": [], "artifacts": [],
        "outcome_evidence": [], "execution_evidence": [], "next_moves": [], "timeline": [],
    }
    evidence = conn.execute(
        "SELECT id, kind, reference, note, observed_at, recorded_at FROM work_evidence WHERE wager_id=? ORDER BY recorded_at",
        (wager_id,),
    ).fetchall()
    trace["evidence"] = [dict(row) for row in evidence]
    trace["outcome_evidence"] = [dict(row) for row in evidence if _is_outcome_evidence(row["kind"])]
    trace["execution_evidence"] = [dict(row) for row in evidence if not _is_outcome_evidence(row["kind"])]
    skill_reviews = conn.execute(
        "SELECT skill_version, content_hash, reviewed_at FROM work_skill_reviews WHERE wager_id=? ORDER BY skill_version",
        (wager_id,),
    ).fetchall()
    trace["skill_reviews"] = [dict(row) for row in skill_reviews]
    moves = conn.execute(
        "SELECT id, action, rationale, status, created_at FROM next_moves WHERE wager_id=? ORDER BY created_at DESC",
        (wager_id,),
    ).fetchall()
    trace["next_moves"] = [dict(row) for row in moves]

    timeline = [{"at": wager["opened_at"], "kind": "work-opened", "label": "Work Card opened"}]
    timeline.extend({"at": row["created_at"], "kind": "next-move", "label": f"{row['action']} move · {row['status']}"}
                    for row in moves)
    timeline.extend({"at": row["recorded_at"], "kind": "outcome-evidence" if _is_outcome_evidence(row["kind"]) else "execution-evidence",
                     "label": f"{row['kind']} receipt"} for row in evidence)
    timeline.extend({"at": row["reviewed_at"], "kind": "skill-review", "label": f"Skill reviewed · {row['skill_version']}"}
                    for row in skill_reviews)
    if wager["resolved_at"]:
        timeline.append({"at": wager["resolved_at"], "kind": "outcome-ruling", "label": f"Outcome ruled · {wager['outcome']}"})

    if not wager["task_run_id"]:
        trace["timeline"] = sorted(timeline, key=lambda event: event["at"] or "")
        return trace
    run = conn.execute("SELECT * FROM task_runs WHERE id=?", (wager["task_run_id"],)).fetchone()
    if run is None:
        trace["timeline"] = sorted(timeline, key=lambda event: event["at"] or "")
        return trace
    trace["task_run"] = {
        "id": run["id"], "objective": run["objective"], "task_class": run["task_class"],
        "model": run["model"], "harness": run["harness"], "status": run["status"],
        "verification_outcome": run["verification_outcome"], "acceptance_test": run["acceptance_test"],
        "cost_observation": _loads_or_empty_dict(run["cost_observation"]),
    }
    try:
        trace["skills"] = json.loads(run["skill_versions"] or "[]")
    except json.JSONDecodeError:
        trace["skills"] = []
    try:
        trace["artifacts"] = json.loads(run["artifact_manifest"] or "[]")
    except json.JSONDecodeError:
        trace["artifacts"] = []
    for at, kind, label in ((run["opened_at"], "run-opened", "TaskRun opened"),
                            (run["execution_started_at"], "context-frozen", "Context packet frozen / execution started"),
                            (run["artifact_attached_at"], "artifact-attached", "Artifact manifest attached"),
                            (run["verified_at"], "run-verified", f"Run verification · {run['verification_outcome'] or 'unknown'}")):
        if at:
            timeline.append({"at": at, "kind": kind, "label": label})

    packet = conn.execute(
        "SELECT id, packet_hash, token_estimate, policy_version, classification_policy_version, excluded_relevant "
        "FROM context_packets WHERE task_run_id=?", (run["id"],),
    ).fetchone()
    if packet is None:
        trace["timeline"] = sorted(timeline, key=lambda event: event["at"] or "")
        return trace
    items = conn.execute(
        "SELECT cube_id, cube_content_hash, provenance, freshness, sensitivity, selection_reason "
        "FROM context_packet_items WHERE packet_id=? ORDER BY ordered_position", (packet["id"],),
    ).fetchall()
    try:
        excluded = json.loads(packet["excluded_relevant"] or "[]")
    except json.JSONDecodeError:
        excluded = []
    trace["context_packet"] = {
        "id": packet["id"], "hash": packet["packet_hash"], "token_estimate": packet["token_estimate"],
        "selection_policy": packet["policy_version"], "classification_policy": packet["classification_policy_version"],
        "included_memory_items": [dict(row) for row in items],
        "excluded_relevant_count": len(excluded),
    }
    trace["timeline"] = sorted(timeline, key=lambda event: event["at"] or "")
    return trace


def list_work_cards(conn, limit: int = 30) -> list[dict]:
    """Compact, read-only cards for the Work surface; drill-down uses the trace."""
    rows = conn.execute(
        """SELECT w.id, w.intent, w.beneficiary, w.observable_change, w.outcome, w.status, w.opened_at,
                  tr.id AS task_run_id, tr.model, tr.harness, tr.status AS task_run_status,
                  tr.verification_outcome, cp.id AS context_packet_id, cp.token_estimate,
                  (SELECT COUNT(*) FROM context_packet_items cpi WHERE cpi.packet_id=cp.id) AS context_items,
                  (SELECT COUNT(*) FROM work_evidence we WHERE we.wager_id=w.id) AS evidence_count,
                  (SELECT action FROM next_moves nm WHERE nm.wager_id=w.id ORDER BY created_at DESC LIMIT 1) AS next_action,
                  (SELECT status FROM next_moves nm WHERE nm.wager_id=w.id ORDER BY created_at DESC LIMIT 1) AS next_action_status
           FROM work_wagers w LEFT JOIN task_runs tr ON tr.id=w.task_run_id
           LEFT JOIN context_packets cp ON cp.task_run_id=tr.id
           ORDER BY CASE w.status WHEN 'open' THEN 0 ELSE 1 END, w.opened_at DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def measure_workgraph(conn) -> dict:
    """Measured coverage of the connected work record, never a quality score."""
    cards = conn.execute("SELECT id, status, outcome, task_run_id FROM work_wagers").fetchall()
    linked_runs = [r["task_run_id"] for r in cards if r["task_run_id"]]
    skills = set()
    linked = {}
    if linked_runs:
        marks = ",".join("?" for _ in linked_runs)
        for row in conn.execute(f"SELECT id, skill_versions, artifact_manifest, verification_outcome, cost_observation FROM task_runs WHERE id IN ({marks})", linked_runs).fetchall():
            linked[row["id"]] = row
    packets = {}
    if linked_runs:
        marks = ",".join("?" for _ in linked_runs)
        for row in conn.execute(f"SELECT cp.task_run_id, COUNT(cpi.cube_id) AS items FROM context_packets cp LEFT JOIN context_packet_items cpi ON cpi.packet_id=cp.id WHERE cp.task_run_id IN ({marks}) GROUP BY cp.task_run_id", linked_runs).fetchall():
            packets[row["task_run_id"]] = row["items"]
    for row in linked.values():
        try:
            skills.update(json.loads(row["skill_versions"] or "[]"))
        except json.JSONDecodeError:
            continue
    outcome_evidence = {row["wager_id"] for row in conn.execute("SELECT wager_id, kind FROM work_evidence").fetchall()
                        if _is_outcome_evidence(row["kind"])}
    reviewed = {row["id"]: set() for row in cards}
    for row in conn.execute("SELECT wager_id, skill_version FROM work_skill_reviews").fetchall():
        reviewed.setdefault(row["wager_id"], set()).add(row["skill_version"])
    declared_by_card = {}
    for card in cards:
        run = linked.get(card["task_run_id"])
        declared_by_card[card["id"]] = set(_json_list(run["skill_versions"])) if run else set()
    return {
        "work_cards": len(cards),
        "open_cards": sum(r["status"] == "open" for r in cards),
        "outcomes": {state: sum(r["outcome"] == state for r in cards) for state in VALID_OUTCOMES},
        "linked_runs": len(linked_runs),
        "context_packets": len(packets),
        "context_with_memory": sum(items > 0 for items in packets.values()),
        "declared_skills": len(skills),
        "reviewed_skill_versions": sum(len(values) for values in reviewed.values()),
        "cards_with_all_declared_skills_reviewed": sum(
            bool(declared) and declared.issubset(reviewed.get(card_id, set()))
            for card_id, declared in declared_by_card.items()
        ),
        "cards_with_skills": sum(bool(_json_list(row["skill_versions"])) for row in linked.values()),
        "cards_with_artifacts": sum(bool(_json_list(row["artifact_manifest"])) for row in linked.values()),
        "verified_runs": sum(row["verification_outcome"] is not None for row in linked.values()),
        "runs_with_wall_elapsed": sum(_loads_or_empty_dict(row["cost_observation"]).get("wall_elapsed_seconds") is not None for row in linked.values()),
        "runs_with_token_usage": sum(_loads_or_empty_dict(row["cost_observation"]).get("token_usage") == "observed" for row in linked.values()),
        "cards_with_outcome_evidence": sum(card["id"] in outcome_evidence for card in cards),
        "evidence_receipts": conn.execute("SELECT COUNT(*) FROM work_evidence").fetchone()[0],
    }


def workgraph_attention(conn, limit: int = 30) -> list[dict]:
    """Return factual interventions, sorted by the broken graph edge.

    These are not recommendations or scores. Each row names a missing required
    record so the operator can decide whether to link, freeze, verify, or stop.
    """
    rows = conn.execute(
        """SELECT w.id, w.intent, w.task_run_id, w.opened_at,
                  tr.status AS run_status, cp.id AS context_packet_id,
                  (SELECT COUNT(*) FROM context_packet_items cpi WHERE cpi.packet_id=cp.id) AS context_items,
                  (SELECT COUNT(*) FROM next_moves nm WHERE nm.wager_id=w.id) AS moves,
                  (SELECT COUNT(*) FROM work_evidence we WHERE we.wager_id=w.id) AS evidence,
                  (SELECT COUNT(*) FROM work_evidence we WHERE we.wager_id=w.id AND (we.kind IN ('user-feedback', 'human-observation', 'business-metric', 'outcome-observation') OR we.kind LIKE 'outcome-%')) AS outcome_evidence,
                  (SELECT COUNT(*) FROM work_skill_reviews wsr WHERE wsr.wager_id=w.id) AS reviewed_skills,
                  tr.skill_versions,
                  (SELECT COUNT(*) FROM work_evidence we WHERE we.wager_id=w.id AND we.kind='context-decision') AS context_decisions
           FROM work_wagers w
           LEFT JOIN task_runs tr ON tr.id=w.task_run_id
           LEFT JOIN context_packets cp ON cp.task_run_id=tr.id
           WHERE w.status='open' ORDER BY w.opened_at ASC"""
    ).fetchall()
    items = []
    for row in rows:
        base = {"wager_id": row["id"], "intent": row["intent"]}
        if not row["task_run_id"]:
            items.append({**base, "priority": "now", "action": "link_run", "reason": "No TaskRun is linked; the work has no execution record."})
        else:
            # Every edge is independently actionable. Do not let an empty packet
            # conceal a later missing verification or outcome receipt.
            if not row["context_packet_id"]:
                items.append({**base, "priority": "now", "action": "freeze_context", "reason": "The linked TaskRun has no frozen context packet."})
            elif not row["context_items"] and not row["context_decisions"]:
                items.append({**base, "priority": "now", "action": "review_context_query", "reason": "The context packet froze zero eligible memory items; inspect the query or continue explicitly context-free."})
            if row["run_status"] == "executing":
                items.append({**base, "priority": "next", "action": "attach_artifact", "reason": "The run is executing; no artifact receipt is recorded yet."})
            elif row["run_status"] == "artifact_attached":
                items.append({**base, "priority": "next", "action": "verify_run", "reason": "An artifact exists but its verification outcome is missing."})
            elif row["run_status"] == "verified" and not row["outcome_evidence"]:
                items.append({**base, "priority": "next", "action": "attach_outcome_evidence", "reason": "Run verification exists but the Work Card has no beneficiary/world outcome evidence receipt."})
            elif row["run_status"] == "reviewed" and not row["outcome_evidence"]:
                # `helicon run close` ends at 'reviewed', not 'verified' — accept_run
                # is the last writer. Checking only for 'verified' meant the queue
                # went quiet on exactly the cards the CLI produces: the work is
                # finished and the card is the only thing left to settle, which is
                # the moment this list is most worth reading.
                items.append({**base, "priority": "next", "action": "attach_outcome_evidence", "reason": "The run is closed and ruled, but the Work Card has no beneficiary/world outcome evidence receipt."})
        declared_skills = _json_list(row["skill_versions"])
        if declared_skills and row["reviewed_skills"] < len(set(declared_skills)):
            items.append({**base, "priority": "next", "action": "review_declared_skills", "reason": "Declared skill versions are not all bound to reviewed local instruction files."})
        if not row["moves"]:
            items.append({**base, "priority": "next", "action": "choose_move", "reason": "No next move has been recorded for this open Work Card."})
    order = {"now": 0, "next": 1}
    return sorted(items, key=lambda item: (order[item["priority"]], item["wager_id"], item["action"]))[:limit]


def workgraph_learning(conn) -> dict:
    """Expose real outcome observations and withhold recommendations when thin."""
    rows = conn.execute(
        """SELECT w.outcome, tr.model, tr.harness, tr.skill_versions
           FROM work_wagers w JOIN task_runs tr ON tr.id=w.task_run_id
           WHERE w.status='resolved' AND w.outcome IS NOT NULL"""
    ).fetchall()
    groups = {"harness": {}, "model": {}, "skill": {}}
    for row in rows:
        keys = {
            "harness": [row["harness"] or "unknown"],
            "model": [row["model"] or "unknown"],
            "skill": _json_list(row["skill_versions"]) or ["undeclared"],
        }
        for dimension, values in keys.items():
            for value in values:
                bucket = groups[dimension].setdefault(value, {state: 0 for state in VALID_OUTCOMES})
                bucket[row["outcome"]] += 1
    observations = {}
    for dimension, buckets in groups.items():
        observations[dimension] = []
        for value, outcomes in sorted(buckets.items()):
            resolved = sum(outcomes.values())
            observations[dimension].append({
                "value": value, "resolved": resolved, "outcomes": outcomes,
                "evidence_sufficient": resolved >= LEARNING_EVIDENCE_FLOOR,
                "verdict": "observed" if resolved >= LEARNING_EVIDENCE_FLOOR else "insufficient evidence",
            })
    return {
        "evidence_floor": LEARNING_EVIDENCE_FLOOR,
        "resolved_work_cards": len(rows),
        "recommendations_withheld": not any(item["evidence_sufficient"] for values in observations.values() for item in values),
        "observations": observations,
    }


def render_wager(conn, wager_id: str) -> str:
    wager = conn.execute("SELECT * FROM work_wagers WHERE id=?", (wager_id,)).fetchone()
    if wager is None:
        raise WagerError(f"no such wager: {wager_id}")
    evidence = conn.execute("SELECT kind, reference FROM work_evidence WHERE wager_id=? ORDER BY recorded_at", (wager_id,)).fetchall()
    moves = conn.execute("SELECT action, status FROM next_moves WHERE wager_id=? ORDER BY created_at DESC", (wager_id,)).fetchall()
    lines = [
        f"Wager {wager['id']} — {wager['status']}",
        f"  intent:      {wager['intent']}",
        f"  beneficiary: {wager['beneficiary']}",
        f"  change:      {wager['observable_change']}",
        f"  proof:       {wager['evidence_contract']}",
        f"  kill:        {wager['kill_condition']}",
        f"  outcome:     {wager['outcome'] or 'pending'}",
        f"  evidence:    {len(evidence)} receipt(s)",
        f"  next move:   {moves[0]['action'] if moves else '—'}",
    ]
    return "\n".join(lines)


# --- Lift: does a skill make real work better? ---------------------------------
#
# The join this whole salvage exists for. Three tables, one question:
#   work_skill_reviews  — which skill was actually LOADED (content_hash over bytes)
#   work_wagers         — the human's claim, and its resolved outcome
#   task_runs.run_id    — the key added 2026-08-10, stamped at capture
#   run_cards           — what the run cost and whether it verified
#
# It reports what it can prove and refuses to imply the rest. An empty store is
# CLEAN, not healthy: with no runs the honest output is "insufficient", never 0.0.
LIFT_MIN_RUNS_PER_ARM = 3


def skill_lift(conn, skill: str) -> dict:
    """Lift for one skill over real captured work. Never estimates."""
    joined = conn.execute(
        """SELECT tr.id AS task_run_id, tr.run_id,
                  rc.verified_ratio, rc.cost, rc.output_tokens, rc.score,
                  w.outcome,
                  (SELECT COUNT(*) FROM work_skill_reviews wsr
                    WHERE wsr.wager_id = w.id AND wsr.skill_version LIKE ?) AS used
           FROM work_wagers w
           JOIN task_runs tr ON tr.id = w.task_run_id
           JOIN run_cards rc ON rc.run_id = tr.run_id
           WHERE tr.run_id IS NOT NULL""",
        (f"{skill}%",),
    ).fetchall()

    with_arm = [r for r in joined if r["used"]]
    without_arm = [r for r in joined if not r["used"]]

    # Everything the join could not reach, counted rather than quietly dropped.
    unjoinable = conn.execute(
        "SELECT COUNT(*) FROM work_wagers w JOIN task_runs tr ON tr.id=w.task_run_id "
        "WHERE tr.run_id IS NULL").fetchone()[0]
    unlinked = conn.execute(
        "SELECT COUNT(*) FROM work_wagers WHERE task_run_id IS NULL").fetchone()[0]

    report = {
        "skill": skill,
        "with_runs": len(with_arm),
        "without_runs": len(without_arm),
        "unjoinable_runs": unjoinable,
        "unlinked_wagers": unlinked,
        "floor": LIFT_MIN_RUNS_PER_ARM,
    }

    if len(with_arm) < LIFT_MIN_RUNS_PER_ARM or len(without_arm) < LIFT_MIN_RUNS_PER_ARM:
        report["verdict"] = "insufficient"
        report["reason"] = (
            f"{len(with_arm)} run(s) used {skill} and {len(without_arm)} did not; "
            f"{LIFT_MIN_RUNS_PER_ARM} per arm are required before a number means anything."
        )
        if unjoinable:
            report["reason"] += (
                f" {unjoinable} captured run(s) predate the run_id key and cannot be "
                "joined to a cost card; they are excluded, not estimated.")
        return report

    def _mean(rows, col):
        vals = [r[col] for r in rows if r[col] is not None]
        return round(sum(vals) / len(vals), 4) if vals else None

    def _delta(a, b):
        return None if a is None or b is None else round(a - b, 4)

    with_v, without_v = _mean(with_arm, "verified_ratio"), _mean(without_arm, "verified_ratio")
    with_t, without_t = _mean(with_arm, "output_tokens"), _mean(without_arm, "output_tokens")
    report.update({
        "verdict": "measured",
        "verified_ratio": {"with": with_v, "without": without_v, "lift": _delta(with_v, without_v)},
        "output_tokens": {"with": with_t, "without": without_t, "lift": _delta(with_t, without_t)},
        "cost": {"with": _mean(with_arm, "cost"), "without": _mean(without_arm, "cost")},
        "proven": sum(1 for r in with_arm if r["outcome"] == "proven"),
        "disproven": sum(1 for r in with_arm if r["outcome"] == "disproven"),
        "unproven": sum(1 for r in with_arm if r["outcome"] == "unproven" or r["outcome"] is None),
    })
    return report


def render_skill_lift(report: dict) -> str:
    s = report["skill"]
    out = [f"  LIFT  {s}", ""]
    if report["verdict"] == "insufficient":
        out += [f"  insufficient — no number is honest yet.", f"  {report['reason']}", ""]
        if report["unlinked_wagers"]:
            out.append(f"  {report['unlinked_wagers']} wager(s) have no TaskRun at all "
                       f"(helicon wager link).")
        out.append("  An empty store reports CLEAN, not healthy.")
        return "\n".join(out)
    vr, tk = report["verified_ratio"], report["output_tokens"]
    out += [f"  runs        with {report['with_runs']}   without {report['without_runs']}",
            f"  verified    with {vr['with']}   without {vr['without']}   lift {vr['lift']:+}",
            f"  out-tokens  with {tk['with']}   without {tk['without']}   lift {tk['lift']:+}",
            f"  outcomes    proven {report['proven']}  disproven {report['disproven']}  "
            f"unproven {report['unproven']}"]
    if report["unjoinable_runs"]:
        out.append(f"  excluded    {report['unjoinable_runs']} run(s) predate the run_id key")
    return "\n".join(out)
