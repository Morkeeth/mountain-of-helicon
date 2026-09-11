#!/usr/bin/env python3
"""Fresh-agent handoff probe — finding → decision → returned-result + ruling/undo.

Keyless. Seeds a temp demo store, drives the same HTTP boundary the dashboard
uses, and prints JSON lines a receipt can cite. Exit 0 always; each step carries
its own pass/fail so a red arm is evidence, not a crash.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

# Make sure the checkout's package wins over any stale install.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _line(step: str, ok: bool, **extra):
    row = {"step": step, "ok": ok, **extra}
    print(json.dumps(row, default=str), flush=True)
    return ok


def main() -> int:
    from fastapi.testclient import TestClient

    from helicon.demo import seed
    from helicon.db import init_db
    import helicon.api.app as app_mod
    import helicon.api.govern as govern
    from helicon.api.govern import ApplyBatchReq, Ruling, UndoReq
    from helicon.guard import guard_output
    from helicon.cockpit import unrule_claim

    import sqlite3

    tmp = tempfile.mkdtemp(prefix="helicon-handoff-")
    db = os.path.join(tmp, "demo.db")
    seed(db)
    # TestClient runs the app in a worker thread; share one cross-thread conn
    # (same pattern as tests/test_govern_api_boundary.py).
    conn = sqlite3.connect(db, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(db)  # ensure schema; seed already created tables

    # get_conn returns module-global _conn; routers that `from … import get_conn`
    # at module load keep the original function object, so patch both.
    app_mod._conn = conn  # type: ignore[attr-defined]
    app_mod._config = {"db_path": db}  # type: ignore[attr-defined]
    app_mod.get_conn = lambda: conn  # type: ignore
    app_mod.get_config = lambda: {"db_path": db}  # type: ignore
    import helicon.api.findings as findings_mod
    import helicon.api.focus as focus_mod
    findings_mod.get_conn = lambda: conn  # type: ignore
    focus_mod.get_config = lambda: {"db_path": db}  # type: ignore

    client = TestClient(app_mod.app)
    results = {"tmp": tmp, "db": db, "passed": [], "failed": []}

    def mark(step, ok, **extra):
        (results["passed"] if ok else results["failed"]).append(step)
        return _line(step, ok, **extra)

    # --- A. FINDING (decision-lane object) ---------------------------------
    r = client.get("/api/findings", params={"lane": "decision", "limit": 20})
    body = r.json()
    findings = body.get("findings") or []
    decision = [f for f in findings if f.get("lane") == "decision"]
    mark(
        "A_findings_decision_lane",
        r.status_code == 200 and len(decision) > 0,
        status=r.status_code,
        decision_count=len(decision),
        needs_you=body.get("summary", {}).get("needs_you") or body.get("needs_you"),
        first_id=(decision[0]["id"] if decision else None),
        first_kind=(decision[0].get("kind") if decision else None),
    )

    # Prefer a factual contradiction (rule_truth) — the hero path.
    fid_row = conn.execute(
        "SELECT id, audit_type, finding, details FROM audit_log "
        "WHERE audit_type='factual' AND human_decision IS NULL LIMIT 1"
    ).fetchone()
    mark(
        "A_factual_finding_in_db",
        fid_row is not None,
        finding_id=(fid_row["id"] if fid_row else None),
        finding_text=((fid_row["finding"] or "")[:120] if fid_row else None),
    )
    if not fid_row:
        _line("ABORT", False, why="no factual finding in demo seed")
        print(json.dumps({"summary": results}, indent=2))
        return 0
    fid = fid_row["id"]

    # --- B. DECISION (govern apply-batch = human ruling; ZUP is FUTURE handoff) -
    details = json.loads(fid_row["details"] or "{}")
    truth = details.get("value_a") or "live — real money"
    wrong_probe_val = details.get("value_b") or details.get("value_a")
    if wrong_probe_val == truth:
        wrong_probe_val = details.get("value_b") or "test mode"

    out = asyncio.run(
        govern.apply_batch(
            ApplyBatchReq(
                rulings=[
                    Ruling(
                        finding_id=fid,
                        verb="rule_truth",
                        payload={"truth": truth},
                        label=f"ruled {truth}",
                    )
                ]
            )
        )
    )
    receipt0 = (out.get("receipt") or [{}])[0]
    mark(
        "B_govern_apply_batch",
        out.get("applied") == 1 and receipt0.get("applied") is True,
        batch_id=out.get("batch_id"),
        undo_token=out.get("undo_token"),
        applied=out.get("applied"),
        effect=receipt0.get("effect"),
        verify=receipt0.get("verify"),
        protection=receipt0.get("protection"),
        correction_cube=receipt0.get("correction_cube")
        if "correction_cube" in receipt0
        else None,
    )

    # Returned-result object: the receipt must prove guard blocks the wrong claim.
    verify = receipt0.get("verify") or {}
    mark(
        "C_returned_result_guard_blocks",
        verify.get("guard_blocks_the_wrong_claim") is True
        and verify.get("recorded_in_audit_log") is True,
        verify=verify,
        truth=truth,
    )

    # Independent re-check at the guard object (not the receipt claim).
    topic = details.get("topic", "claim")
    person = details.get("person", "")
    probe = (
        f"{person}'s {topic} is {wrong_probe_val}"
        if person
        else f"{topic} is {wrong_probe_val}"
    )
    # Prefer an explicit wrong from receipt if present.
    wrongs = None
    # re-read from apply internals via DB cube
    settled = conn.execute(
        "SELECT human_decision FROM audit_log WHERE id=?", (fid,)
    ).fetchone()["human_decision"]
    g = guard_output(conn, probe)
    mark(
        "C_guard_object_independent",
        g.get("clean") is False,
        probe=probe,
        guard_clean=g.get("clean"),
        settled=settled,
        blocks=g.get("blocks") or g.get("violations") or list(g.keys()),
    )

    # --- B2. ZUP-bound FUTURE handoff (Focus route → paste-ready prompt) -----
    # Helicon = PAST; Focus /focus/route is the documented egress toward ZUP.
    move = {
        "title": f"Act on ruled truth: {topic} = {truth}",
        "body": (
            f"Finding #{fid} was ruled. Competing value must not be asserted. "
            f"Next work belongs on the FUTURE surface (ZUP)."
        ),
        "rationale": "Helicon settled PAST; ZUP owns what to do next.",
        "receipts": [
            {
                "ref": f"audit:{fid}",
                "why": receipt0.get("effect") or "ruled",
            }
        ],
    }
    route = client.post(
        "/api/focus/route", json={"move": move, "destination": "prompt"}
    )
    routed = route.json() if route.status_code == 200 else {}
    mark(
        "B2_zup_bound_focus_route",
        route.status_code == 200
        and routed.get("routed") == "prompt"
        and bool(routed.get("prompt"))
        and str(fid) in (routed.get("prompt") or ""),
        status=route.status_code,
        routed=routed.get("routed"),
        prompt_head=(routed.get("prompt") or "")[:220],
    )

    # Vault/local file egress (no Obsidian in this VM → data/next-moves/).
    route_v = client.post(
        "/api/focus/route", json={"move": move, "destination": "vault"}
    )
    rv = route_v.json() if route_v.status_code == 200 else {}
    path_ok = bool(rv.get("path")) and os.path.isfile(rv.get("path") or "")
    mark(
        "B2_zup_bound_vault_file",
        route_v.status_code == 200 and rv.get("routed") == "vault" and path_ok,
        status=route_v.status_code,
        path=rv.get("path"),
        path_exists=path_ok,
    )

    # --- D. BASELINE ARM (naive: flip human_decision only, no correction cube) -
    # Fresh finding for fair compare.
    fid2 = conn.execute(
        "SELECT id FROM audit_log WHERE audit_type='factual' AND human_decision IS NULL LIMIT 1"
    ).fetchone()
    baseline = {"available": False}
    if fid2:
        fid2 = fid2["id"]
        row2 = conn.execute(
            "SELECT details FROM audit_log WHERE id=?", (fid2,)
        ).fetchone()
        d2 = json.loads(row2["details"] or "{}")
        t2 = d2.get("value_a") or "x"
        w2 = d2.get("value_b") or "y"
        conn.execute(
            "UPDATE audit_log SET human_decision=?, resolved_at=datetime('now') WHERE id=?",
            (f"resolved:{t2}", fid2),
        )
        conn.commit()
        topic2, person2 = d2.get("topic", "claim"), d2.get("person", "")
        probe2 = (
            f"{person2}'s {topic2} is {w2}" if person2 else f"{topic2} is {w2}"
        )
        g_naive = guard_output(conn, probe2)
        baseline = {
            "available": True,
            "finding_id": fid2,
            "probe": probe2,
            "guard_clean": g_naive.get("clean"),
            "cubes_for_finding": conn.execute(
                "SELECT COUNT(*) FROM helicon_cubes WHERE source_ref=?",
                (f"audit:{fid2}",),
            ).fetchone()[0],
        }
        # Govern arm already proved guard blocks; naive must NOT block if no cube.
        # (If it still blocks, that is itself a finding.)
        mark(
            "D_baseline_naive_decision_only",
            True,  # the arm ran; outcome is the finding
            **baseline,
            note=(
                "naive sets human_decision only; no correction cube. "
                "If guard_clean is True, govern beats naive on enforcement. "
                "If guard_clean is False, something else already blocks — open the object."
            ),
        )
    else:
        mark("D_baseline_naive_decision_only", False, why="no second factual finding")

    # --- E. RULING / UNDO probes --------------------------------------------
    # E1: total undo of govern batch
    undo = asyncio.run(govern.undo_batch(UndoReq(undo_token=out["undo_token"])))
    still = conn.execute(
        "SELECT human_decision FROM audit_log WHERE id=?", (fid,)
    ).fetchone()["human_decision"]
    cubes_left = conn.execute(
        "SELECT COUNT(*) FROM helicon_cubes WHERE source_ref=?",
        (f"audit:{fid}",),
    ).fetchone()[0]
    mark(
        "E1_govern_undo_total",
        undo.get("fully_reversed") is True and still is None and cubes_left == 0,
        undo=undo,
        human_decision_after=still,
        correction_cubes_left=cubes_left,
    )

    # E2: double undo must 400 (HTTP boundary)
    first = client.post(
        "/api/govern/undo-batch", json={"undo_token": out["undo_token"]}
    )
    # already undone above via function — expect 400
    detail_raw = (
        first.json()
        if first.headers.get("content-type", "").startswith("application/json")
        else first.text
    )
    mark(
        "E2_double_undo_http",
        first.status_code == 400,
        status=first.status_code,
        detail=str(detail_raw)[:200],
    )

    # E3: cockpit undo on a non-review (govern) finding must refuse
    # Re-apply so finding is decided again, then try cockpit unrule.
    out2 = asyncio.run(
        govern.apply_batch(
            ApplyBatchReq(
                rulings=[
                    Ruling(
                        finding_id=fid,
                        verb="rule_truth",
                        payload={"truth": truth},
                    )
                ]
            )
        )
    )
    cross = unrule_claim(conn, fid)
    mark(
        "E3_cockpit_undo_on_govern_finding_refused",
        cross.get("ok") is False
        and "not an output-review" in (cross.get("error") or ""),
        response=cross,
        govern_still_settled=bool(
            conn.execute(
                "SELECT human_decision FROM audit_log WHERE id=?", (fid,)
            ).fetchone()["human_decision"]
        ),
    )

    # E4: confirm+acted on temporal/decay kills a cube; undo must restore it —
    # or we document the hole. Demo seed has no temporal findings — plant one.
    live = conn.execute(
        "SELECT id, review_status FROM helicon_cubes "
        "WHERE id LIKE 'demo-%' AND review_status NOT IN ('killed','superseded') "
        "LIMIT 1"
    ).fetchone()
    if live:
        tid = live["id"]
        before = live["review_status"]
        conn.execute(
            "INSERT INTO audit_log (audit_type, target_type, target_id, finding, "
            "severity, details, audited_at) VALUES "
            "('temporal', 'cube', ?, ?, 'warning', '{}', datetime('now'))",
            (tid, f"planted temporal on {tid} for undo totality probe"),
        )
        conn.commit()
        temp_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        bout = asyncio.run(
            govern.apply_batch(
                ApplyBatchReq(
                    rulings=[
                        Ruling(
                            finding_id=temp_id,
                            verb="confirm",
                            payload={"decision": "acted"},
                        )
                    ]
                )
            )
        )
        mid_status = conn.execute(
            "SELECT review_status FROM helicon_cubes WHERE id=?", (tid,)
        ).fetchone()["review_status"]
        u = asyncio.run(
            govern.undo_batch(UndoReq(undo_token=bout["undo_token"]))
        )
        after_status = conn.execute(
            "SELECT review_status FROM helicon_cubes WHERE id=?", (tid,)
        ).fetchone()["review_status"]
        decision_cleared = (
            conn.execute(
                "SELECT human_decision FROM audit_log WHERE id=?", (temp_id,)
            ).fetchone()["human_decision"]
            is None
        )
        restored = after_status == before
        mark(
            "E4_confirm_kill_undo_restores_cube",
            restored,
            finding_id=temp_id,
            target_id=tid,
            before=before,
            after_apply=mid_status,
            after_undo=after_status,
            decision_cleared=decision_cleared,
            fully_reversed=u.get("fully_reversed"),
            inconsistency=(
                None
                if restored
                else "undo cleared human_decision but left cube killed"
            ),
        )
    else:
        mark(
            "E4_confirm_kill_undo_restores_cube",
            False,
            why="no live demo cube to plant a temporal finding on",
        )

    # E5: Force the UI lie at the HTTP object. Corrupt undo_json so
    # decided_finding_ids is empty; undo returns fully_reversed=true (vacuous)
    # while the ruling remains. FocusReview setsUndone(true) on any 200.
    fid3 = conn.execute(
        "SELECT id FROM audit_log WHERE audit_type='factual' AND human_decision IS NULL LIMIT 1"
    ).fetchone()
    if fid3:
        fid3 = fid3["id"]
        d3 = json.loads(
            conn.execute(
                "SELECT details FROM audit_log WHERE id=?", (fid3,)
            ).fetchone()["details"]
            or "{}"
        )
        t3 = d3.get("value_b") or d3.get("value_a") or "live — real money"
        out3 = asyncio.run(
            govern.apply_batch(
                ApplyBatchReq(
                    rulings=[
                        Ruling(
                            finding_id=fid3,
                            verb="rule_truth",
                            payload={"truth": t3},
                        )
                    ]
                )
            )
        )
        tok3 = out3["undo_token"]
        # Corrupt the undo payload the way a partial-write / older schema could.
        conn.execute(
            "UPDATE govern_batches SET undo_json=? WHERE id=?",
            (
                json.dumps(
                    {"correction_cubes": [], "decided_finding_ids": []}
                ),
                tok3,
            ),
        )
        conn.commit()
        u3 = client.post("/api/govern/undo-batch", json={"undo_token": tok3})
        u3j = u3.json() if u3.status_code == 200 else {}
        still3 = conn.execute(
            "SELECT human_decision FROM audit_log WHERE id=?", (fid3,)
        ).fetchone()["human_decision"]
        ui_would_say_reversed = (
            u3.status_code == 200
            and u3j.get("undone") is True
            and u3j.get("fully_reversed") is True
            and still3 is not None
        )
        ui_src = (ROOT / "web/src/components/FocusReview.tsx").read_text()
        checks_flag = "fully_reversed" in ui_src
        # After the fix: finding must be cleared (receipt_json fallback) AND
        # FocusReview must read fully_reversed. ok=True means CLEARED.
        cleared = (
            still3 is None
            and u3j.get("fully_reversed") is True
            and checks_flag
            and not ui_would_say_reversed
        )
        mark(
            "E5_vacuous_fully_reversed_cleared",
            cleared,
            status=u3.status_code,
            undo_body=u3j,
            human_decision_still=still3,
            focusreview_checks_fully_reversed=checks_flag,
            ui_would_have_lied=ui_would_say_reversed,
            note=(
                "PASS means corrupted empty decided_finding_ids no longer "
                "vacuous-succeeds: receipt_json recovers the finding ids, "
                "and FocusReview refuses undone without fully_reversed."
            ),
        )
        # Leave fid3 decided — evidence, not cleanup theatre.
    else:
        mark(
            "E5_vacuous_fully_reversed_cleared",
            False,
            why="no third factual finding left to plant the vacuous-undo case",
        )

    # E6: queue undo API still returns ok:true with restored:0 for a missing
    # batch (API shape). App.tsx must refuse to treat that as success.
    q = client.post("/api/queue/undo", json={"batch_id": "mb_does_not_exist"})
    qj = q.json() if q.status_code == 200 else {}
    app_src = (ROOT / "web/src/App.tsx").read_text()
    idx = app_src.find("/api/queue/undo")
    q_undo_blob = app_src[idx : idx + 700] if idx >= 0 else ""
    ui_checks = "restored" in q_undo_blob and "setError" in q_undo_blob
    mark(
        "E6_queue_undo_ui_refuses_zero_restore",
        q.status_code == 200
        and qj.get("ok") is True
        and (qj.get("restored") == 0)
        and ui_checks,
        status=q.status_code,
        body=qj,
        app_tsx_checks_restored=ui_checks,
        note=(
            "API still answers ok:true/restored:0 for a missing batch (honest "
            "count). App.tsx now errors when restored is 0 instead of refreshing "
            "as if the undo worked."
        ),
    )

    # Clean up the re-applied govern batch so the temp dir is consistent.
    if out2.get("undo_token"):
        try:
            asyncio.run(govern.undo_batch(UndoReq(undo_token=out2["undo_token"])))
        except Exception as e:
            _line("cleanup_undo", False, error=str(e))

    summary = {
        "tmp": tmp,
        "passed": results["passed"],
        "failed": results["failed"],
        "pass_count": len(results["passed"]),
        "fail_count": len(results["failed"]),
    }
    print(json.dumps({"summary": summary}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
