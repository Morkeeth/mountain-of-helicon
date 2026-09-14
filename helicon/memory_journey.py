"""Read-only joins over existing source reviews, corrections and delivery receipts.

A source assertion is not adjudicated truth. Same subject text alone cannot bind
consumer evidence: joins require canonical source path AND its exact SHA256.
"""
from datetime import datetime, timezone
import hashlib
from pathlib import Path
from helicon.context_history import read_source_bytes, HistoryError


def memory_journeys(project, snapshots, corrections, packets):
    groups = {}
    unavailable = [p for p in packets if p.get("state") == "unavailable"]
    for snapshot in snapshots:
        review = snapshot["review"]
        for claim in review.get("claims", []):
            key = (claim["subject"], claim["predicate"])
            group = groups.setdefault(key, {"id": hashlib.sha256(repr(key).encode()).hexdigest()[:24],
                "subject": key[0], "predicate": key[1], "observations": []})
            span = claim["evidence"]
            # One physical assertion may be discovered through several harnesses.
            identity = (snapshot["id"], span["path"], span["sha256"], span.get("start_byte"), span.get("end_byte"))
            if any(row["identity"] == identity for row in group["observations"]):
                continue
            group["observations"].append({"identity": identity, "snapshot_id": snapshot["id"],
                "observed_at": review["observed_at"], "value": claim["value"], "source": span,
                "harness": claim.get("harness", "unknown")})
    result = []
    current_hashes = {}
    for group in groups.values():
        observations = sorted(group["observations"], key=lambda r: (r["observed_at"], r["snapshot_id"]))
        source_versions = {(r["source"]["path"], r["source"]["sha256"]) for r in observations}
        for row in observations:
            del row["identity"]
            path = row["source"]["path"]
            if path not in current_hashes:
                try:
                    current_hashes[path] = hashlib.sha256(read_source_bytes(path)).hexdigest()
                except HistoryError:
                    current_hashes[path] = None
            row["source_state"] = ("unavailable" if current_hashes[path] is None else
                "matches_saved_version" if current_hashes[path] == row["source"]["sha256"] else "changed_since_observation")
        linked_corrections = [c for c in corrections if
            (c["path"], c["before_sha256"]) in source_versions or
            (c["path"], c["after_sha256"]) in source_versions]
        # Limit a whole-file correction to the actual assertion span it touched.
        linked_corrections = [c for c in linked_corrections if any(
            r["source"]["path"] == c["path"] and
            r["source"]["sha256"] == c["before_sha256"] and
            r["source"].get("start_byte", -1) < c["end_byte"] and
            r["source"].get("end_byte", -1) > c["start_byte"]
            for r in observations)]
        consumers = []
        for packet in packets:
            if packet.get("state") == "unavailable":
                continue
            matched = [s for s in packet["sources"] if (s["path"], s["sha256"]) in source_versions]
            if not matched:
                continue
            behavior = []
            for review in packet["behavior"]:
                shown = {**review, "artifact_preview": None, "preview_truncated": False}
                if review["artifact_current"]:
                    try:
                        artifact = Path(review["artifact"])
                        artifact.relative_to(Path(project))
                        data = read_source_bytes(artifact)
                        if hashlib.sha256(data).hexdigest() != review["artifact_sha256"]:
                            shown["artifact_current"] = False
                        else:
                            shown["artifact_preview"] = data[:4000].decode("utf-8", errors="replace")
                            shown["preview_truncated"] = len(data) > 4000
                    except (ValueError, HistoryError):
                        shown["artifact_current"] = False
                behavior.append(shown)
            consumers.append({"packet_id": packet["id"], "recipient": packet["recipient"],
                "issued_at": packet["issued_at"], "sources": matched,
                "source_status": packet["source_status"], "consumption": packet["consumption"],
                "read_state": "interface_returned_bytes" if packet["consumption"] else "not_observed",
                "ack_state": "not_recorded_by_this_contract",
                "behavior": behavior,
                "behavior_scope": "packet-level review, not per-assertion use",
                "limit": "Delivery is not comprehension. Behavior is an attributed review, not proof that memory caused the result."})
        current = [r for r in observations if r["source_state"] == "matches_saved_version"]
        # Repeated snapshots do not manufacture independent corroboration.
        values = list(dict.fromkeys(str(r["value"]) for r in current))
        group.update(observations=observations, corrections=linked_corrections, consumers=consumers,
            current_values=values, state="disagreement" if len(values) > 1 else "source_assertion" if values else "current_state_unverified")
        result.append(group)
    return {"schema": "helicon.memory-journey/1", "project": project,
        "checked_at": datetime.now(timezone.utc).isoformat(), "journeys": sorted(result, key=lambda g: (g["subject"], g["predicate"])),
        "receipt_errors": [{"id": p["id"], "error": p.get("error")} for p in unavailable],
        "scope": "Saved explicit source assertions only; free-form memory and unsaved sources are not covered. Read-only joins, no new memory store."}
