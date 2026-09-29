"""Read-only setup snapshots and explicit-baseline comparison.

This is deliberately a view over :mod:`helicon.setup_audit`, not another
store.  Discovery proves that a component is present on disk.  It does not
prove that a harness loaded it or that a run used it, so those evidence states
remain separate on every edge.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .setup_audit import audit_setup
from .versions import check_versions


SCHEMA = "helicon.setup-snapshot/1"
STATUS_SCHEMA = "helicon.setup-status/1"


def _stable_id(kind: str, *parts: str) -> str:
    raw = "\0".join((kind, *parts)).encode("utf-8")
    return f"{kind}:" + hashlib.sha256(raw).hexdigest()[:16]


def build_snapshot(home=None, project=None, observed_at=None) -> dict:
    """Inventory the setup now without writing or executing configured code."""
    project_path = Path(project or Path.cwd()).resolve()
    audit = audit_setup(home=home, project=project_path)
    components = []
    edges = []

    harness_ids = {}
    for harness in audit["coverage"]["harnesses"]:
        component_id = f"harness:{harness}"
        harness_ids[harness] = component_id
        components.append({"id": component_id, "kind": "harness", "name": harness})

    for source in audit["files"]:
        component_id = _stable_id("source", source["path"])
        components.append({
            "id": component_id,
            "kind": "instruction_or_hook",
            "name": Path(source["path"]).name,
            "path": source["path"],
            "sha256": source["sha256"],
            "bytes": source["bytes"],
            "stage": source["stage"],
        })
        edges.append({
            "id": _stable_id("edge", component_id, harness_ids[source["harness"]]),
            "from": component_id,
            "to": harness_ids[source["harness"]],
            "relation": "configured_for",
            "fingerprint": source["sha256"],
            "evidence": {
                "configured": "observed",
                "loaded": "unknown",
                "used": "unknown",
            },
        })

    for skill in audit["skills"]:
        component_id = _stable_id("skill", skill["path"])
        components.append({
            "id": component_id,
            "kind": "skill",
            "name": skill["name"],
            "path": skill["path"],
            "sha256": skill["sha256"],
        })
        edges.append({
            "id": _stable_id("edge", component_id, harness_ids[skill["harness"]]),
            "from": component_id,
            "to": harness_ids[skill["harness"]],
            "relation": "available_to",
            "fingerprint": skill["sha256"],
            "evidence": {
                "configured": "discovered",
                "loaded": "unknown",
                "used": "unknown",
            },
        })

    version_report = check_versions(str(project_path))
    for receipt in version_report["receipts"]:
        component_id = _stable_id("version", receipt["file"], receipt["raw"])
        components.append({
            "id": component_id,
            "kind": "version_claim",
            "name": receipt["raw"],
            "path": receipt["file"],
            "verdict": receipt["verdict"],
            "receipt": receipt["receipt"],
        })

    # One file can be a candidate for more than one harness (AGENTS.md is the
    # common case). It is one component with multiple edges, not duplicate
    # components carrying the same id.
    unique_components = {item["id"]: item for item in components}

    return {
        "schema": SCHEMA,
        "observed_at": observed_at or datetime.now(timezone.utc).isoformat(),
        "project": str(project_path),
        "scope": "local setup files and deterministic version claims; read-only",
        "coverage": {
            "status": "partial" if audit["coverage"]["not_observed"] else "covered",
            "observed": ["instruction and hook files", "skill files", "version claims"],
            "unknown": list(audit["coverage"]["not_observed"]),
        },
        "components": sorted(unique_components.values(), key=lambda item: item["id"]),
        "edges": sorted(edges, key=lambda item: item["id"]),
        "findings": audit["findings"],
    }


def _changes(previous: list[dict], current: list[dict]) -> dict:
    before = {item["id"]: item for item in previous}
    after = {item["id"]: item for item in current}
    shared = before.keys() & after.keys()
    return {
        "added": [after[key] for key in sorted(after.keys() - before.keys())],
        "removed": [before[key] for key in sorted(before.keys() - after.keys())],
        "changed": [
            {"id": key, "before": before[key], "after": after[key]}
            for key in sorted(shared) if before[key] != after[key]
        ],
    }


def compare_snapshots(current: dict, previous: dict | None = None) -> dict:
    """Compare only to the snapshot the caller explicitly supplied."""
    if previous is None:
        return {
            "status": "tracking_started",
            "baseline_observed_at": None,
            "message": "Tracking started. No previous snapshot was supplied, so no change is claimed.",
            "components": {"added": [], "removed": [], "changed": []},
            "edges": {"added": [], "removed": [], "changed": []},
        }
    if previous.get("schema") != SCHEMA:
        raise ValueError(f"previous snapshot must use schema {SCHEMA}")
    component_changes = _changes(previous.get("components", []), current["components"])
    edge_changes = _changes(previous.get("edges", []), current["edges"])
    changed = any(component_changes[key] or edge_changes[key]
                  for key in ("added", "removed", "changed"))
    return {
        "status": "changed" if changed else "unchanged",
        "baseline_observed_at": previous.get("observed_at"),
        "message": "Setup changed since the supplied snapshot." if changed
                   else "No setup change was observed against the supplied snapshot.",
        "components": component_changes,
        "edges": edge_changes,
    }


def load_snapshot(path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    # `helicon status --json` emits an envelope. Accept that exact output as the
    # next explicit baseline as well as a raw snapshot object.
    return data.get("snapshot", data)


def setup_status(home=None, project=None, previous=None, observed_at=None) -> dict:
    current = build_snapshot(home=home, project=project, observed_at=observed_at)
    baseline = load_snapshot(previous) if previous else None
    return {
        "schema": STATUS_SCHEMA,
        "snapshot": current,
        "comparison": compare_snapshots(current, baseline),
    }


def render_status(report: dict) -> str:
    snapshot = report["snapshot"]
    comparison = report["comparison"]
    lines = ["WHAT CHANGED IN MY SETUP?", comparison["message"],
             f"Observed {snapshot['observed_at']}",
             f"Coverage: {snapshot['coverage']['status']}"]
    if snapshot["coverage"]["unknown"]:
        lines.append("Unknown: " + ", ".join(snapshot["coverage"]["unknown"]))
    for noun in ("components", "edges"):
        changes = comparison[noun]
        lines.append(f"{noun.title()}: +{len(changes['added'])} "
                     f"-{len(changes['removed'])} ~{len(changes['changed'])}")
    return "\n".join(lines)
