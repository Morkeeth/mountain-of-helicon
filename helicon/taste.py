"""Taste-verdict memory — the Helicon side of the Taste Machine bridge.

Taste Machine DECIDES whether an agent's OUTPUT is good (its relevance gate + tone
readback + the human's kill/send/exceptional verdict). Helicon REMEMBERS that
decision as law. A verdict is filed as an already-ruled finding; a guard then tells
the generator "you have already ruled this" so the same shape never wastes a human
ruling twice — the never-twice guarantee, applied to taste instead of facts.

Two levels of never-twice:
- **exact**: the same artifact (by content hash) was already ruled.
- **shape**: this (kind, move) has been ruled kill enough times to predict a kill.

Deliberately NOT built on pairing.py's (person, topic, date-interval) selector —
"is this writing good" has no disjoint-interval structure. This uses the general
audit_log ledger + artifact-hash dedup, exactly as the cross-repo analysis advised.
"""
import json
from datetime import datetime, timezone

from helicon.db import insert_audit
from helicon.models import AuditResult

_KILL = {"kill", "killed", "reject", "rejected"}
_SEND = {"send", "sent", "approve", "approved", "exceptional"}


def _existing_taste_keys(conn) -> set[str]:
    keys = set()
    for row in conn.execute("SELECT details FROM audit_log WHERE audit_type = 'taste'"):
        try:
            k = json.loads(row["details"]).get("pair_key")
            if k:
                keys.add(k)
        except (json.JSONDecodeError, TypeError):
            pass
    return keys


def ingest_verdict(conn, v: dict) -> dict:
    """File one Taste Machine verdict as an already-ruled finding. Idempotent by
    artifact hash. `v` is the VerdictRecord emitted at TM's ruling moment:
    {artifact_hash|artifact_id, kind, content, move, reason, human_verdict,
     machine_verdict, scores, decided_at}."""
    h = str(v.get("artifact_hash") or v.get("artifact_id") or "").strip()
    if not h:
        return {"ok": False, "error": "verdict has no artifact_hash/artifact_id"}
    pk = f"taste|{h}"
    if pk in _existing_taste_keys(conn):
        return {"ok": True, "skipped": True, "pair_key": pk}

    hv = str(v.get("human_verdict") or v.get("verdict") or "").lower()
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    reason = v.get("reason") or ""
    text = (f"Taste verdict: {v.get('kind', 'output')} '{v.get('move', '')}' ruled {hv}"
            + (f" — {reason}" if reason else ""))
    finding = AuditResult(
        audit_type="taste",
        target_type="artifact",
        target_id=h,
        finding=text,
        severity="info",
        proposed_action="flag",
        # a REMEMBERED ruling — already decided by the human in Taste Machine
        human_decision=f"resolved:{hv}",
        details={
            "pair_key": pk, "artifact_hash": h, "kind": v.get("kind", ""),
            "move": v.get("move", ""), "reason": reason, "human_verdict": hv,
            "machine_verdict": str(v.get("machine_verdict") or "").lower(),
            "scores": v.get("scores", {}),
            "content_preview": (v.get("content", "") or "")[:200],
            "decided_at": v.get("decided_at", now),
        },
        audited_at=now, resolved_at=now,
    )
    rid = insert_audit(conn, finding)
    conn.commit()
    return {"ok": rid is not None, "pair_key": pk, "verdict": hv}


def ingest_file(conn, path: str) -> dict:
    """Ingest a JSON array (or JSONL) of VerdictRecords."""
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    try:
        records = json.loads(raw)
        if isinstance(records, dict):
            records = [records]
    except json.JSONDecodeError:
        records = [json.loads(line) for line in raw.splitlines() if line.strip()]
    filed = skipped = 0
    for v in records:
        r = ingest_verdict(conn, v)
        if r.get("skipped"):
            skipped += 1
        elif r.get("ok"):
            filed += 1
    return {"ingested": filed, "already_had": skipped, "total": len(records)}


def taste_guard(conn, artifact_hash: str | None = None,
                kind: str | None = None, move: str | None = None,
                shape_threshold: int = 2) -> dict:
    """Has this output already been ruled? Exact (same hash) beats shape (same
    kind/move ruled kill >= threshold and more kills than sends). Returns a guard
    the generator consults BEFORE spending a human ruling."""
    if artifact_hash:
        row = conn.execute(
            "SELECT details FROM audit_log WHERE audit_type = 'taste' "
            "AND target_id = ? ORDER BY id DESC LIMIT 1", (artifact_hash,)).fetchone()
        if row:
            try:
                d = json.loads(row["details"])
            except (json.JSONDecodeError, TypeError):
                d = {}
            return {"already_ruled": True, "match": "exact",
                    "prior_verdict": d.get("human_verdict"),
                    "reason": d.get("reason") or "identical output already ruled",
                    "artifact_hash": artifact_hash}

    if move:
        kills = sends = 0
        for row in conn.execute("SELECT details FROM audit_log WHERE audit_type = 'taste'"):
            try:
                d = json.loads(row["details"])
            except (json.JSONDecodeError, TypeError):
                continue
            if d.get("move") == move and (kind is None or d.get("kind") == kind):
                v = d.get("human_verdict", "")
                if v in _KILL:
                    kills += 1
                elif v in _SEND:
                    sends += 1
        if kills >= shape_threshold and kills > sends:
            return {"already_ruled": True, "match": "shape", "prior_verdict": "kill",
                    "reason": f"move '{move}' ruled kill {kills}x (sent {sends}x) — "
                              f"this shape usually gets killed",
                    "move": move, "kills": kills, "sends": sends}

    return {"already_ruled": False}
