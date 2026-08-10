"""The Workgraph capture protocol: launch a run against a Wager, close it with
real artifacts and a real verification receipt.

Salvaged from the frozen submission's 0639b53 (2026-07-30). It lived in
capture.py there, but Mountain's capture.py drifted into a different job —
discovering and importing Claude Code sessions — and already defines _now and
_artifact. Same name, forked meaning: the exact identity fork the tool flags in
other people's docs. So it lives here under its own name instead.

Nothing in this module infers value. launch() freezes the acceptance test before
work starts; close() records what was actually produced and what actually
verified. An unproven outcome is a legal result.
"""
"""Local capture adapter: turn one real agent work cycle into graph evidence.

This adapter never launches an agent or executes a test.  It makes the joins at
the two moments where the operator has reliable facts: launch (freeze context)
and closeout (hash declared artifacts and attach the operator's verification).
"""
import hashlib
import json
import os
from pathlib import Path
from datetime import datetime, timezone

from helicon.taskrun import attach_artifact, attach_verification, build_packet, open_run, render_receipt
from helicon.wager import WagerError, attach_evidence, link_wager_to_run, trace_work_card


class CaptureError(Exception):
    pass


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def launch(conn, wager_id, *, acceptance_test, query="", model="", harness="local-agent",
           skills=None, repo_ref=None):
    """Open and freeze a real TaskRun for an unlinked Work Card."""
    trace = trace_work_card(conn, wager_id)
    card = trace["work_card"]
    if card["status"] != "open":
        raise CaptureError("cannot launch a resolved Work Card")
    if trace["task_run"]:
        raise CaptureError("Work Card already has a TaskRun")
    if not acceptance_test.strip():
        raise CaptureError("acceptance test is required")
    run_id = open_run(conn, card["intent"], acceptance_test, task_class="agentic-work",
                      model=model, harness=harness, skill_versions=skills or [], repo_ref=repo_ref)
    try:
        link_wager_to_run(conn, wager_id, run_id)
        packet = build_packet(conn, run_id, query=query or card["intent"])
    except Exception:
        # The Work Card remains safely unlinked if capture cannot establish its
        # pre-execution packet; no partial provenance is presented as a run.
        raise
    return {"wager_id": wager_id, "task_run_id": run_id, "packet": packet}


def _artifact(path):
    real = os.path.realpath(path)
    if not os.path.isfile(real):
        raise CaptureError(f"artifact must be a readable file: {path}")
    with open(real, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    return {"path_or_ref": os.path.abspath(path), "content_hash": digest, "observed_at": _now()}


def _cost_observation(conn, task_run_id, *, input_tokens=None, output_tokens=None) -> dict:
    """Record only local wall time and explicitly supplied model usage.

    Wall time is an observed interval, not a claim about active keyboard time.
    Token counts stay unknown unless a harness actually supplied both values;
    zero is valid when observed and is never substituted for missing data.
    """
    if (input_tokens is None) != (output_tokens is None):
        raise CaptureError("input_tokens and output_tokens must be supplied together")
    if input_tokens is not None and (input_tokens < 0 or output_tokens < 0):
        raise CaptureError("token counts cannot be negative")
    run = conn.execute("SELECT execution_started_at FROM task_runs WHERE id=?", (task_run_id,)).fetchone()
    if run is None:
        raise CaptureError(f"no such TaskRun: {task_run_id}")
    closed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    observation = {"wall_elapsed_seconds": None, "token_usage": "unknown"}
    if run["execution_started_at"]:
        try:
            observation["wall_elapsed_seconds"] = max(0, round((closed_at - datetime.fromisoformat(run["execution_started_at"])).total_seconds()))
        except ValueError:
            pass
    if input_tokens is not None:
        observation.update({"token_usage": "observed", "input_tokens": input_tokens,
                            "output_tokens": output_tokens, "total_tokens": input_tokens + output_tokens})
    return observation


def close(conn, task_run_id, *, artifacts, verification, evidence, input_tokens=None, output_tokens=None):
    """Attach locally-hashed artifacts and the operator's verification receipt."""
    if not artifacts:
        raise CaptureError("at least one local artifact is required")
    if not evidence.strip():
        raise CaptureError("verification evidence is required")
    manifest = [_artifact(path) for path in artifacts]
    cost_observation = _cost_observation(conn, task_run_id, input_tokens=input_tokens, output_tokens=output_tokens)
    attach_artifact(conn, task_run_id, manifest, cost_observation=cost_observation)
    attach_verification(conn, task_run_id, verification, evidence=evidence)
    wager = conn.execute("SELECT id FROM work_wagers WHERE task_run_id=?", (task_run_id,)).fetchone()
    if wager:
        attach_evidence(conn, wager["id"], kind="taskrun-verification", reference=task_run_id,
                        note=evidence)
    return {"task_run_id": task_run_id, "work_card_id": wager["id"] if wager else None,
            "receipt": render_receipt(conn, task_run_id), "artifacts": manifest,
            "cost_observation": cost_observation}


def acknowledge_context_free(conn, task_run_id, *, reason):
    """Record an explicit human choice to proceed with an empty packet.

    An empty packet is never silently treated as good context. This receipt only
    says the operator accepted context-free execution for this run.
    """
    if not reason.strip():
        raise CaptureError("context-free reason is required")
    packet = conn.execute(
        "SELECT cp.id, COUNT(cpi.cube_id) AS items FROM context_packets cp "
        "LEFT JOIN context_packet_items cpi ON cpi.packet_id=cp.id WHERE cp.task_run_id=? GROUP BY cp.id",
        (task_run_id,),
    ).fetchone()
    if packet is None:
        raise CaptureError("cannot acknowledge context before a packet is frozen")
    if packet["items"]:
        raise CaptureError("context packet is not empty; there is no context-free exception to acknowledge")
    wager = conn.execute("SELECT id FROM work_wagers WHERE task_run_id=?", (task_run_id,)).fetchone()
    if wager is None:
        raise CaptureError("TaskRun is not linked to a Work Card")
    return attach_evidence(conn, wager["id"], kind="context-decision", reference=task_run_id, note=reason)


def cloud_manifest_template(conn, task_run_id: str) -> dict:
    """Return the handoff contract a cloud agent may fill, without writing it."""
    run = conn.execute("SELECT id, repo_ref, status FROM task_runs WHERE id=?", (task_run_id,)).fetchone()
    if run is None:
        raise CaptureError(f"no such TaskRun: {task_run_id}")
    if run["status"] != "executing":
        raise CaptureError(f"cloud manifest requires an executing TaskRun (status: {run['status']})")
    return {
        "schema": "helicon-capture/v1",
        "task_run_id": task_run_id,
        "repo_ref": run["repo_ref"] or "",
        "artifacts": [{"path": "relative/path/to/artifact", "sha256": "sha256-of-cloud-file"}],
        "verification": {"outcome": "unverified", "evidence": "actual cloud test command and output"},
    }


def ingest_cloud_manifest(conn, manifest_path, *, repo_root) -> dict:
    """Validate a cloud closeout against locally-synced bytes before recording it.

    The manifest is untrusted declaration. Paths are constrained to `repo_root`
    and every declared digest is rechecked locally before `close` records a
    receipt. This lets cloud work cross the local-only boundary without making
    a cloud agent an authority on artifacts or verification.
    """
    try:
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise CaptureError(f"invalid cloud manifest: {exc}") from exc
    if manifest.get("schema") != "helicon-capture/v1":
        raise CaptureError("unsupported cloud manifest schema")
    task_run_id = str(manifest.get("task_run_id") or "")
    verification = manifest.get("verification") or {}
    outcome, evidence = verification.get("outcome", ""), verification.get("evidence", "")
    declared = manifest.get("artifacts")
    if not isinstance(declared, list) or not declared:
        raise CaptureError("cloud manifest requires at least one artifact")
    root = Path(repo_root).resolve()
    artifacts = []
    for item in declared:
        rel, expected = str(item.get("path") or ""), str(item.get("sha256") or "")
        candidate = (root / rel).resolve()
        if root not in candidate.parents or not rel or not expected:
            raise CaptureError(f"cloud artifact path escapes repo or lacks hash: {rel!r}")
        actual = _artifact(str(candidate))
        if actual["content_hash"] != expected:
            raise CaptureError(f"cloud artifact hash mismatch: {rel}")
        artifacts.append(str(candidate))
    return close(conn, task_run_id, artifacts=artifacts, verification=outcome, evidence=evidence)
