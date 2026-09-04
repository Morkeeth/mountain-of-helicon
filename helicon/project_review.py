"""Independent read-only checks of ZUP's events and the displayed projection."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

TERMINAL = {"submitted", "delivered", "accepted", "lost", "won", "cancelled"}


def independent_question(row, project):
    relation = (row.get('decision') or {}).get('stateRelation') or {}
    try:
        at = datetime.fromisoformat(relation.get('confirmedAt', '').replace('Z', '+00:00'))
        bound = (relation.get('stateEventID') == project['stateEventId']) if project.get('stateEventId') else bool(project.get('stateObservedAt') and relation.get('stateObservedAt') == project['stateObservedAt'])
        return bool(relation.get('kind') == 'independent-question' and relation.get('source') == 'operator'
                    and str(relation.get('milestoneID') or '').strip() and bound
                    and at.tzinfo is not None and at <= datetime.now(timezone.utc))
    except (ValueError, TypeError):
        return False


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
        undated = []
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
            valid_receipt = bool(receipt and receipt["type"] == p.get("lifecycle")
                                 and receipt["evidence"] == p.get("stateEvidence")
                                 and receipt["projectId"] in {p["id"], *p.get("aliases", [])})
            dated_ruling = False
            try:
                observed = datetime.fromisoformat(p.get("stateObservedAt", "").replace("Z", "+00:00"))
                dated_ruling = bool(p.get("stateEvidence")) and observed.tzinfo is not None and observed <= datetime.now(timezone.utc)
            except (ValueError, TypeError):
                pass
            # A broken linked receipt cannot be upgraded to a trusted ruling by
            # repeating its text and timestamp in the projection being checked.
            if p.get('stateEventId') and not valid_receipt:
                dated_ruling = False
            if not valid_receipt and not dated_ruling:
                undated.append(p["id"])
            if p.get("stateEventId") and not receipt:
                result["findings"].append(dict(kind="missing-event", project=p["id"]))
            if receipt and not valid_receipt:
                result["findings"].append(dict(kind="projection-disagrees-with-event", project=p["id"]))
            if p.get("lifecycle") in TERMINAL:
                matching = [q for q in queue["queue"] if q["id"] in {p["id"], *p.get("aliases", [])}]
                if any(q.get("band") != "PARKED" and not independent_question(q, p) for q in matching):
                    result["findings"].append(dict(kind="settled-project-reopened-in-queue", project=p["id"]))
                if any(q.get('needsHuman') and not independent_question(q, p) for q in matching):
                    result['findings'].append(dict(kind='unscoped-settled-project-request', project=p['id']))
            result["projects"].append(dict(id=p["id"], state=p.get("lifecycle") or ("dated ruling" if dated_ruling else "not verified"),
                evidence_status="event" if valid_receipt else "ruling" if dated_ruling else "unverified",
                event_id=p.get("stateEventId"), source=p.get("stateSource"), observed_at=p.get("stateObservedAt"),
                evidence=p.get("stateEvidence"), historical_ids=p.get("identityHistory", [])))
        for finding in board.get("stateReview", {}).get("findings", []):
            result["findings"].append(dict(kind="zup-reported-conflict", detail=finding))
        if undated:
            result["findings"].append(dict(kind="undated-project-status", projects=undated,
                title=f"{len(undated)} project records have no dated state evidence",
                consequence="Projects remain visible, but their old instructions must not be treated as current tasks.",
                action="Reconcile each next milestone against a current project receipt, not a snapshot timestamp."))
        descriptions = {
            "duplicate-project-id": ("A project ID appears twice", "Counts and routing can disagree.", "Resolve the duplicate identity."),
            "duplicate-project-identity": ("An old name remains a separate project", "An old task can return under the earlier name.", "Merge the identity, keeping its history."),
            "missing-event": ("A displayed state has no matching event", "Its evidence cannot be checked.", "Recover the receipt or mark the state unverified."),
            "projection-disagrees-with-event": ("The board contradicts its event receipt", "The displayed phase is not reliable.", "Rebuild the board from the authoritative event."),
            "settled-project-reopened-in-queue": ("A settled phase is back in the action queue", "Completed work can be requested again.", "Remove the obsolete action; preserve the achievement."),
            "unscoped-settled-project-request": ("A question on a settled project has no decision record", "It may be new work or an obsolete step; this check cannot tell.", "Attach the current question and its evidence before routing it."),
            "zup-reported-conflict": ("Project records conflict", "A current state cannot be selected safely.", "Resolve the conflicting receipts."),
        }
        for finding in result["findings"]:
            if finding["kind"] in descriptions:
                finding["title"], finding["consequence"], finding["action"] = descriptions[finding["kind"]]
        result["coverage"] = dict(total=len(projects), event_backed=sum(p["evidence_status"] == "event" for p in result["projects"]),
                                  dated_rulings=sum(p["evidence_status"] == "ruling" for p in result["projects"]), unverified=len(undated))
        result.update(status="attention" if result["findings"] else "measured", event_count=len(events),
                      project_count=len(projects), latest_event=max((e["observedAt"] for e in events), default=None))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result.update(status="unmeasured", reason=str(exc))
    return result
