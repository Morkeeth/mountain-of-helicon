"""Independent read-only checks of ZUP's events and the displayed projection."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

TERMINAL = {"submitted", "delivered", "accepted", "lost", "won", "cancelled"}


def project_review(home=None):
    root = Path(home) if home is not None else Path(os.environ.get("ZUP_HOME", str(Path.home() / ".zen")))
    result = dict(schema="helicon.project-review/1", observed_at=datetime.now(timezone.utc).isoformat(),
                  source=str(root), status="unmeasured", findings=[], projects=[], latest_event=None,
                  scope="Local project events, board and queue. Not a submission-provider verification or a memory-benefit score.")
    try:
        paths = [root / "active-board.json", root / "zup-next.json", *sorted((root / "project-events").glob("*.json"))]
        # A concurrent writer must not produce a false cross-file contradiction.
        before = {p: (p.stat().st_mtime_ns, p.stat().st_size) for p in paths}
        board, queue, *events = [json.loads(p.read_text()) for p in paths]
        if before != {p: (p.stat().st_mtime_ns, p.stat().st_size) for p in paths}:
            raise ValueError("Project state changed during review; retry")
        if paths[2:] != sorted((root / "project-events").glob("*.json")):
            raise ValueError("Project events changed during review; retry")
        projects = board["projects"]
        ids = [p["id"] for p in projects]
        if len(ids) != len(set(ids)):
            result["findings"].append(dict(kind="duplicate-project-id"))
        by_event = {}
        for e in events:
            if e.get("schema") != "zup.project-event/1" or not e.get("evidence") or not e.get("source"):
                raise ValueError("Invalid project event evidence")
            at = datetime.fromisoformat(e["observedAt"].replace("Z", "+00:00"))
            if at.tzinfo is None or at > datetime.now(timezone.utc):
                raise ValueError("Invalid project event time")
            if e["id"] in by_event:
                raise ValueError("Duplicate project event ID")
            by_event[e["id"]] = e
        for p in projects:
            old_ids = set(p.get("aliases", [])) & (set(ids) - {p["id"]})
            if old_ids:
                result["findings"].append(dict(kind="duplicate-project-identity", project=p["id"], aliases=sorted(old_ids)))
            receipt = by_event.get(p.get("stateEventId"))
            if p.get("stateEventId") and not receipt:
                result["findings"].append(dict(kind="missing-event", project=p["id"]))
            if receipt and (receipt["type"] != p.get("lifecycle") or receipt["evidence"] != p.get("stateEvidence")
                            or receipt["projectId"] not in {p["id"], *p.get("aliases", [])}):
                result["findings"].append(dict(kind="projection-disagrees-with-event", project=p["id"]))
            if p.get("lifecycle") in TERMINAL:
                matching = [q for q in queue["queue"] if q["id"] in {p["id"], *p.get("aliases", [])}]
                if any(q.get("needsHuman") or q.get("band") != "PARKED" for q in matching):
                    result["findings"].append(dict(kind="settled-project-reopened-in-queue", project=p["id"]))
            result["projects"].append(dict(id=p["id"], state=p.get("lifecycle", "not event-backed"),
                event_id=p.get("stateEventId"), source=p.get("stateSource"), observed_at=p.get("stateObservedAt"),
                evidence=p.get("stateEvidence"), historical_ids=p.get("identityHistory", [])))
        for finding in board.get("stateReview", {}).get("findings", []):
            result["findings"].append(dict(kind="zup-reported-conflict", detail=finding))
        result.update(status="attention" if result["findings"] else "measured", event_count=len(events),
                      project_count=len(projects), latest_event=max((e["observedAt"] for e in events), default=None))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result.update(status="unmeasured", reason=str(exc))
    return result
