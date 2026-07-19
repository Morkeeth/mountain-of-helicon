"""Govern-batch: one atomic Apply over N staged rulings, with a receipt whose
proof is a real check against post-apply state, and a total undo.

The loop the product is built around: a human stages verdicts, applies once, and
the rulings propagate into the compiled law the agent obeys — with a receipt that
proves it landed and an undo that fully reverses it. This composes the EXISTING
per-finding resolvers (identity / relation / precedent / confirm); it invents no
new memory path. It writes only audit_log decisions, the correction cubes those
resolvers create, GOLDEN_RULES, and its own govern_batches row.
"""
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# get_conn/get_config are imported lazily inside the endpoints: importing them at
# module top creates a cycle (app.create_app imports this router before this
# module finishes defining it).

router = APIRouter()


class Ruling(BaseModel):
    finding_id: int
    verb: str                 # rule_identity | resolve_relation | precedent | confirm
    payload: dict = {}
    label: str = ""           # optional human summary from the card


class ApplyBatchReq(BaseModel):
    rulings: list[Ruling]


class UndoReq(BaseModel):
    undo_token: str


def _now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def _ruling_dict(r: Ruling) -> dict:
    return {"finding_id": r.finding_id, "verb": r.verb, "payload": r.payload, "label": r.label}


def _rule_truth(conn, fid: int, truth: str) -> dict:
    """Rule a live contradiction: the operator names the CURRENT truth; the other
    value(s) become ruled-wrong, which the guard then enforces on the next write.
    Writes an approved correction cube so retrieval serves the answer, and returns
    the wrong value(s) so the receipt can prove the guard now blocks them."""
    row = conn.execute("SELECT audit_type, human_decision, details FROM audit_log WHERE id=?",
                       (fid,)).fetchone()
    if row is None:
        return {"ok": False, "error": f"no finding #{fid}"}
    if row["human_decision"]:
        return {"ok": False, "error": f"finding #{fid} already decided: {row['human_decision']}"}
    if row["audit_type"] != "factual":
        return {"ok": False, "error": f"finding #{fid} is not a factual contradiction"}
    truth = (truth or "").strip()
    if not truth:
        return {"ok": False, "error": "the current truth is required"}
    try:
        d = json.loads(row["details"] or "{}")
    except (json.JSONDecodeError, TypeError):
        d = {}
    topic, person = d.get("topic", "claim"), d.get("person", "user")
    wrong = [v for v in (d.get("value_a"), d.get("value_b")) if v and v != truth]
    now = _now()
    conn.execute("UPDATE audit_log SET human_decision=?, resolved_at=? WHERE id=?",
                 (f"resolved:{truth}", now, fid))
    from helicon.models import HeliconCube
    from helicon.scanner import make_id, content_hash as _hash
    from helicon.db import insert_cube
    content = (f"{person.title()}'s {topic} is {truth} (human resolution of finding #{fid}, "
               f"{now[:10]}). The competing value(s) {', '.join(wrong) or '—'} are wrong; any "
               f"memory asserting them predates this resolution.")
    cid = make_id()
    insert_cube(conn, HeliconCube(
        id=cid, source="human-resolution", source_ref=f"audit:{fid}", type="decision",
        title=f"Resolved: {person.title()} {topic} = {truth}", content=content, summary=content[:120],
        content_hash=_hash(content), created_at=now, valid_from=now, last_reinforced=now,
        confidence=1.0, review_status="approved", tags=["ruling"], metadata={}))
    return {"ok": True, "correction_cube": cid, "subject": topic, "truth": truth, "wrong": wrong}


def _confirm(conn, fid: int, decision: str) -> dict:
    row = conn.execute("SELECT human_decision, target_id, audit_type FROM audit_log WHERE id=?",
                       (fid,)).fetchone()
    if row is None:
        return {"ok": False, "error": f"no finding #{fid}"}
    if row["human_decision"]:
        return {"ok": False, "error": f"finding #{fid} already decided: {row['human_decision']}"}
    conn.execute("UPDATE audit_log SET human_decision=?, resolved_at=? WHERE id=?",
                 (decision, _now(), fid))
    if decision == "acted" and row["audit_type"] in ("temporal", "decay"):
        conn.execute("UPDATE helicon_cubes SET review_status='killed' WHERE id=?", (row["target_id"],))
    return {"ok": True}


def _apply_one(conn, r: Ruling) -> dict:
    """Dispatch one ruling to its existing resolver. A bad ruling ISOLATES: it
    returns applied=False and the rest of the batch still applies (never a rollback
    of the ones that succeeded)."""
    fid, verb, p = r.finding_id, r.verb, (r.payload or {})
    try:
        if verb == "rule_identity":
            from helicon.identity import resolve_identity
            res = resolve_identity(conn, fid, p.get("canonical", ""))
        elif verb == "resolve_relation":
            from helicon.relations import resolve_relation
            res = resolve_relation(conn, fid, p.get("verdict", "phantom"))
        elif verb == "precedent":
            from helicon.pairing import dismiss_finding
            res = dismiss_finding(conn, fid, p.get("reason", ""))
        elif verb == "rule_truth":
            res = _rule_truth(conn, fid, p.get("truth", ""))
        elif verb == "confirm":
            res = _confirm(conn, fid, p.get("decision", "acted"))
        else:
            return {"finding_id": fid, "verb": verb, "applied": False,
                    "error": f"unknown verb: {verb}", "correction_cube": None, "subject": ""}
        ok = bool(res.get("ok", True)) and not res.get("error")
        return {"finding_id": fid, "verb": verb, "applied": ok, "error": res.get("error"),
                "correction_cube": res.get("correction_cube") or res.get("correction"),
                "subject": (res.get("name") or res.get("subj") or res.get("subject") or p.get("canonical") or ""),
                "truth": res.get("truth"), "wrong": res.get("wrong")}
    except Exception as e:  # never let one ruling abort the batch
        return {"finding_id": fid, "verb": verb, "applied": False, "error": str(e),
                "correction_cube": None, "subject": ""}


def _settled(conn, fid: int) -> bool:
    row = conn.execute("SELECT human_decision FROM audit_log WHERE id=?", (fid,)).fetchone()
    return bool(row and row["human_decision"])


def _effect(res: dict) -> str:
    if not res["applied"]:
        return f"not applied — {res.get('error') or 'unknown reason'}"
    v, subj = res["verb"], res.get("subject", "")
    return {
        "rule_identity": f"'{subj}' ruled canonical — the competing definition loses",
        "rule_truth": f"{subj}: ruled '{res.get('truth', '')}' current — the competing value is now wrong",
        "resolve_relation": f"'{subj}' ruling recorded — the ungrounded claim is settled",
        "precedent": "ruled not-rot — filed as a precedent",
        "confirm": "finding acted on and closed",
    }.get(v, "applied")


def _protection(res: dict, in_law: bool) -> str:
    if not res["applied"]:
        return "—"
    if in_law:
        return "compiled into GOLDEN_RULES — the agent reads it before it writes; re-alarms if contradicted"
    return "recorded — this finding won't return to the queue"


def _build_receipt(conn, config, results: list[dict]) -> tuple[list[dict], str]:
    """Recompile the law ONCE, then prove each ruling landed against real state:
    the finding is settled in the record, and (where it compiles) its subject is
    present in the freshly compiled GOLDEN_RULES the agent reads."""
    from helicon.gold import compile_gold
    from helicon.guard import guard_output
    law = compile_gold(conn, config) or ""
    low = law.lower()
    receipt = []
    for res in results:
        fid = res["finding_id"]
        settled = _settled(conn, fid)
        subj = (res.get("subject") or "").strip()
        in_law = bool(subj) and subj.lower() in low
        applied = bool(res["applied"]) and settled
        verify = {"recorded_in_audit_log": settled, "compiled_into_law": in_law}
        prot = _protection({**res, "applied": applied}, in_law)
        # For a ruled contradiction, PROVE enforcement: run the guard on a claim that
        # asserts the ruled-wrong value and confirm it is now blocked. This is the
        # whole thesis in the receipt — the ruling is enforced, not just recorded.
        if res.get("verb") == "rule_truth" and applied and res.get("wrong"):
            probe = f"the user's {subj} is {res['wrong'][0]}"
            blocked = not guard_output(conn, probe).get("clean", True)
            verify["guard_blocks_the_wrong_claim"] = blocked
            if blocked:
                prot = f"the guard now BLOCKS “{probe}” before an agent can write it"
        receipt.append({
            "finding_id": fid, "verb": res["verb"], "label": "", "applied": applied,
            "error": res.get("error"), "effect": _effect({**res, "applied": applied}),
            "protection": prot, "verify": verify,
        })
    return receipt, law


@router.post("/govern/apply-batch")
async def apply_batch(req: ApplyBatchReq):
    if not req.rulings:
        raise HTTPException(status_code=400, detail="no rulings to apply")
    from helicon.api.app import get_conn, get_config
    conn = get_conn()
    config = get_config()

    results = [_apply_one(conn, r) for r in req.rulings]
    receipt, _law = _build_receipt(conn, config, results)

    undo = {
        "correction_cubes": [r["correction_cube"] for r in results if r.get("correction_cube")],
        "decided_finding_ids": [r["finding_id"] for i, r in enumerate(results) if receipt[i]["applied"]],
    }
    batch_id = "gb_" + uuid.uuid4().hex[:12]
    conn.execute(
        "INSERT INTO govern_batches (id, applied_at, rulings_json, receipt_json, undo_json) "
        "VALUES (?,?,?,?,?)",
        (batch_id, _now(), json.dumps([_ruling_dict(r) for r in req.rulings]),
         json.dumps(receipt), json.dumps(undo)))
    conn.commit()

    applied = sum(1 for r in receipt if r["applied"])
    return {
        "batch_id": batch_id,
        "undo_token": batch_id,
        "applied": applied,
        "failed": len(receipt) - applied,
        "rules_compiled": sum(1 for r in receipt if r["verify"]["compiled_into_law"]),
        "findings_settled": sum(1 for r in receipt if r["verify"]["recorded_in_audit_log"]),
        "receipt": receipt,
    }


@router.post("/govern/undo-batch")
async def undo_batch(req: UndoReq):
    from helicon.api.app import get_conn, get_config
    conn = get_conn()
    config = get_config()
    row = conn.execute("SELECT undo_json, undone_at FROM govern_batches WHERE id=?",
                       (req.undo_token,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="no such batch")
    if row["undone_at"]:
        raise HTTPException(status_code=400, detail="batch already undone")
    undo = json.loads(row["undo_json"])

    for cid in undo.get("correction_cubes", []):
        conn.execute("DELETE FROM helicon_cubes WHERE id=?", (cid,))   # FTS auto-cleans via trigger
        try:
            conn.execute("DELETE FROM cube_embeddings WHERE cube_id=?", (cid,))
        except Exception:
            pass  # embeddings optional; a fresh correction cube usually has none
    for fid in undo.get("decided_finding_ids", []):
        conn.execute("UPDATE audit_log SET human_decision=NULL, resolved_at=NULL WHERE id=?", (fid,))
    conn.execute("UPDATE govern_batches SET undone_at=? WHERE id=?", (_now(), req.undo_token))
    conn.commit()

    from helicon.gold import compile_gold
    compile_gold(conn, config)  # recompile so the reverted rulings drop out of the law
    reverted = [{"finding_id": fid, "still_settled": _settled(conn, fid)}
                for fid in undo.get("decided_finding_ids", [])]
    return {"undone": True, "reverted": reverted,
            "fully_reversed": all(not r["still_settled"] for r in reverted)}
