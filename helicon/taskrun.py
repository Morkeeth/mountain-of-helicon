"""TaskRun + ContextPacket recorder — the read-only, local-only seed of the
"learn from work" loop.

It binds a task's objective <-> the exact frozen context it was given <-> its
artifact <-> a verification outcome, so that later (not now) the engine can learn
which context/skill/model actually helped. This slice does exactly that recording
and NOTHING else:

- READS `helicon_cubes` through a dedicated selector; it never calls the MCP
  retrieval path (`helicon_context` / `record_surfaced` / `update_reward`) or any
  regret/scan path, so it cannot contaminate retrieval, utility, or regret data.
- Writes ONLY task_runs / context_packets / context_packet_items.
- Promotes no memory, compiles no law, runs nothing. Verification is ATTACH-ONLY:
  the operator attaches a receipt; Helicon records it, executes nothing.
- Default-deny privacy: a private/unclassified item never enters a packet, and the
  exclusion log stores only an opaque id + category, never private content.
"""
import hashlib
import json
import uuid
from datetime import datetime, timezone

from helicon.context_policy import (
    CLASSIFICATION_POLICY_VERSION,
    classify,
    eligible_for_local_packet,
)

SELECTION_POLICY_VERSION = "sel-2026-07-19.1"


class TaskRunError(Exception):
    """A state-machine or input violation — raised instead of silently mutating."""


def _now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def _loads(s):
    try:
        return json.loads(s) if s else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _spec_hash(objective, task_class, acceptance_test, model, harness, skill_versions) -> str:
    blob = json.dumps({"objective": objective, "task_class": task_class,
                       "acceptance_test": acceptance_test, "model": model,
                       "harness": harness, "skills": sorted(skill_versions or [])},
                      sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def _get_run(conn, task_run_id):
    return conn.execute("SELECT * FROM task_runs WHERE id=?", (task_run_id,)).fetchone()


def open_run(conn, objective, acceptance_test, *, task_class="", model="", harness="",
             skill_versions=None, context_mode="compact", comparison_group_id=None,
             repo_ref=None) -> str:
    """Declare the task BEFORE work: objective + acceptance_test are frozen now, so
    'verified' later cannot be hindsight."""
    if not objective.strip():
        raise TaskRunError("objective is required")
    rid = "tr_" + uuid.uuid4().hex[:12]
    conn.execute(
        "INSERT INTO task_runs (id, objective, task_class, task_spec_hash, acceptance_test, "
        "model, harness, skill_versions, context_mode, comparison_group_id, repo_ref, "
        "human_acceptance, opened_at, egress_receipt, status) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (rid, objective, task_class, _spec_hash(objective, task_class, acceptance_test, model, harness, skill_versions),
         acceptance_test, model, harness, json.dumps(skill_versions or []), context_mode,
         comparison_group_id, repo_ref, "pending", _now(),
         json.dumps({"policy_result": "local-only", "observed_calls": []}), "opened"))
    conn.commit()
    return rid


def _hash_packet(items, policy_version) -> str:
    """Hash over the ORDERED RENDERED payload + item metadata + policy versions —
    never over cube IDs alone (the same id can render differently later)."""
    payload = [[i["ordered_position"], i["cube_id"], i["cube_content_hash"], i["rendered_fragment_hash"]]
               for i in items]
    blob = json.dumps({"items": payload, "pv": policy_version, "cpv": CLASSIFICATION_POLICY_VERSION},
                      sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()


def build_packet(conn, task_run_id, query="", *, policy_version=SELECTION_POLICY_VERSION) -> dict:
    """Freeze the exact context this run WOULD be given. Read-only over cubes;
    default-deny privacy gate; content-addressed hash. Must run before the artifact."""
    run = _get_run(conn, task_run_id)
    if run is None:
        raise TaskRunError(f"no such task run: {task_run_id}")
    if run["status"] != "opened":
        raise TaskRunError(f"packet already built or run not open (status: {run['status']})")

    like = f"%{query.lower()}%" if query else "%"
    rows = conn.execute(
        "SELECT id, source, source_ref, title, content, created_at, metadata "
        "FROM helicon_cubes WHERE review_status != 'killed' "
        "AND (lower(content) LIKE ? OR lower(title) LIKE ?) ORDER BY created_at DESC",
        (like, like)).fetchall()

    included, excluded, pos = [], [], 0
    for r in rows:
        meta = _loads(r["metadata"])
        scope = meta.get("scope", "") or (r["source_ref"] or "")
        sens = classify(r["source"] or "", scope, r["source_ref"] or "", r["content"] or "")
        if not eligible_for_local_packet(sens):
            # OPAQUE only: a hash + category. Never title / ref / content of a private item.
            excluded.append({"opaque": hashlib.sha1((r["id"] or "").encode()).hexdigest()[:12],
                             "category": "sensitivity", "reason": sens})
            continue
        rendered = f"{r['title'] or ''}: {r['content'] or ''}".strip()
        included.append({
            "cube_id": r["id"],
            "cube_content_hash": hashlib.sha1((r["content"] or "").encode()).hexdigest(),
            "ordered_position": pos,
            "rendered_fragment_hash": hashlib.sha1(rendered.encode()).hexdigest(),
            "provenance": f"{r['source']}·{r['source_ref']}",
            "freshness": meta.get("as_of") or r["created_at"],
            "scope": scope, "sensitivity": sens,
            "selection_reason": f"keyword:{query}" if query else "live-memory",
            "_rendered": rendered,
        })
        pos += 1

    packet_hash = _hash_packet(included, policy_version)
    token_estimate = sum(len(i["_rendered"]) for i in included) // 4
    packet_id = "cp_" + uuid.uuid4().hex[:12]
    now = _now()
    conn.execute(
        "INSERT INTO context_packets (id, task_run_id, created_at, policy_version, "
        "classification_policy_version, packet_hash, token_estimate, excluded_relevant) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (packet_id, task_run_id, now, policy_version, CLASSIFICATION_POLICY_VERSION,
         packet_hash, token_estimate, json.dumps(excluded)))
    for i in included:
        conn.execute(
            "INSERT INTO context_packet_items (packet_id, cube_id, cube_content_hash, "
            "ordered_position, rendered_fragment_hash, provenance, freshness, scope, sensitivity, selection_reason) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (packet_id, i["cube_id"], i["cube_content_hash"], i["ordered_position"],
             i["rendered_fragment_hash"], i["provenance"], i["freshness"], i["scope"],
             i["sensitivity"], i["selection_reason"]))
    conn.execute("UPDATE task_runs SET status='executing', execution_started_at=? WHERE id=?",
                 (now, task_run_id))
    conn.commit()
    return {"packet_id": packet_id, "packet_hash": packet_hash,
            "included": len(included), "excluded": len(excluded), "token_estimate": token_estimate}


def reconstruct_packet_hash(conn, task_run_id) -> str:
    """Recompute the hash from the STORED items — proves the packet is reconstructible
    and immutable (matches context_packets.packet_hash)."""
    p = conn.execute("SELECT id, policy_version FROM context_packets WHERE task_run_id=?",
                     (task_run_id,)).fetchone()
    if p is None:
        raise TaskRunError("no packet for this run")
    rows = conn.execute(
        "SELECT cube_id, cube_content_hash, ordered_position, rendered_fragment_hash "
        "FROM context_packet_items WHERE packet_id=? ORDER BY ordered_position", (p["id"],)).fetchall()
    items = [{"ordered_position": r["ordered_position"], "cube_id": r["cube_id"],
              "cube_content_hash": r["cube_content_hash"], "rendered_fragment_hash": r["rendered_fragment_hash"]}
             for r in rows]
    return _hash_packet(items, p["policy_version"])


def attach_artifact(conn, task_run_id, artifact_manifest: list, *, cost_observation=None) -> None:
    """Attach the produced artifact(s). Each entry should carry a content hash +
    observed_at, so a path+mtime alone can never masquerade as proof."""
    run = _get_run(conn, task_run_id)
    if run is None:
        raise TaskRunError(f"no such task run: {task_run_id}")
    if run["status"] == "opened":
        raise TaskRunError("cannot attach an artifact before a context packet is built")
    if run["status"] in ("artifact_attached", "verified", "reviewed"):
        raise TaskRunError(f"artifact already attached (status: {run['status']})")
    conn.execute(
        "UPDATE task_runs SET artifact_manifest=?, cost_observation=?, artifact_attached_at=?, status='artifact_attached' WHERE id=?",
        (json.dumps(artifact_manifest or []),
         json.dumps(cost_observation or {"status": "unknown"}), _now(), task_run_id))
    conn.commit()


def attach_verification(conn, task_run_id, outcome: str, *, evidence="") -> None:
    """ATTACH-ONLY. The operator ran the acceptance test elsewhere; Helicon records
    the outcome and executes nothing. `unverified` is first-class, never a pass."""
    if outcome not in ("verified", "contradicted", "unverified"):
        raise TaskRunError("outcome must be verified | contradicted | unverified")
    run = _get_run(conn, task_run_id)
    if run is None:
        raise TaskRunError(f"no such task run: {task_run_id}")
    if run["status"] != "artifact_attached":
        raise TaskRunError(f"cannot verify before an artifact is attached (status: {run['status']})")
    conn.execute(
        "UPDATE task_runs SET verification_outcome=?, verification_receipt=?, verified_at=?, status='verified' WHERE id=?",
        (outcome, json.dumps({"source": "attached", "evidence": evidence}), _now(), task_run_id))
    conn.commit()


def render_receipt(conn, task_run_id) -> str:
    run = _get_run(conn, task_run_id)
    if run is None:
        raise TaskRunError(f"no such task run: {task_run_id}")
    p = conn.execute("SELECT included_ct.n, cp.token_estimate, cp.excluded_relevant FROM context_packets cp "
                     "LEFT JOIN (SELECT packet_id, COUNT(*) n FROM context_packet_items GROUP BY packet_id) included_ct "
                     "ON included_ct.packet_id = cp.id WHERE cp.task_run_id=?", (task_run_id,)).fetchone()
    inc = p["n"] if p and p["n"] else 0
    exc = len(_loads(p["excluded_relevant"])) if p else 0
    lines = [
        f"TaskRun {run['id']} — {run['status']}",
        f"  objective:  {run['objective']}",
        f"  context:    {inc} items in packet, {exc} relevant excluded (privacy/scope), "
        f"~{p['token_estimate'] if p else 0} tokens · mode={run['context_mode']}",
        f"  outcome:    {run['verification_outcome'] or 'unverified'} "
        f"(source: {'attached' if run['verification_outcome'] else '—'})",
        f"  egress:     {_loads(run['egress_receipt']).get('policy_result', 'local-only')}",
    ]
    return "\n".join(lines)
