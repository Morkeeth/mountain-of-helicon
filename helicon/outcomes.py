"""Outcome coverage, not a quality score. Read-only, no prompt bodies exported."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def outcome_report(db):
    report = dict(schema="helicon.outcomes/1", observed_at=datetime.now(timezone.utc).isoformat(),
                  source=str(Path(db).expanduser().resolve()), status="unmeasured", metrics={},
                  limitations=["All recorded runs, not all agent work", "Recorded acceptance is not independently verified",
                               "Skill benefit, causal model comparisons and cost per accepted outcome are not measured"])
    try:
        with sqlite3.connect(Path(report["source"]).as_uri() + "?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT id, status, verification_outcome, verification_receipt, "
                                "human_acceptance, opened_at FROM task_runs").fetchall()
            total = len(rows)
            backed = sum(r["verification_outcome"] == "verified" and _receipt(r["verification_receipt"]) for r in rows)
            accepted = sum(r["human_acceptance"] == "accepted" for r in rows)
            report.update(status="measured", metrics=dict(recorded_runs=total,
                verified_with_receipt=backed, accepted=accepted,
                rework=sum(r["human_acceptance"] == "rework" for r in rows),
                rollback=sum(r["human_acceptance"] == "rollback" for r in rows),
                awaiting_acceptance=sum(r["human_acceptance"] not in ("accepted", "rework", "rollback") for r in rows),
                acceptance_coverage=round((total - sum(r["human_acceptance"] not in ("accepted", "rework", "rollback") for r in rows)) / total, 4) if total else None),
                latest_run=max((r["opened_at"] for r in rows if r["opened_at"]), default=None),
                cohort=[dict(id=r["id"], acceptance=r["human_acceptance"]) for r in rows],
                pending_run_ids=[r["id"] for r in rows if r["human_acceptance"] not in ("accepted", "rework", "rollback")])
    except (sqlite3.Error, OSError) as exc:
        report["reason"] = str(exc)
    return report


def _receipt(raw):
    try:
        value = json.loads(raw)
        return isinstance(value, dict) and bool(value.get("evidence"))
    except (TypeError, ValueError):
        return False


def compare_cohort(baseline, current):
    """Compare the same IDs. Missing rows cannot count as improvement."""
    if any(r.get("schema") != "helicon.outcomes/1" or r.get("status") != "measured" for r in (baseline, current)):
        raise ValueError("comparison requires two measured outcome reports")
    if baseline["source"] != current["source"]:
        raise ValueError("baseline belongs to a different store")
    old = {r["id"]: r["acceptance"] for r in baseline["cohort"]}
    new = {r["id"]: r["acceptance"] for r in current["cohort"]}
    missing = sorted(set(old) - set(new))
    return dict(baseline_at=baseline["observed_at"], denominator=len(old),
                accepted_before=sum(v == "accepted" for v in old.values()),
                accepted_now=sum(new.get(rid) == "accepted" for rid in old),
                missing_ids=missing, new_runs_excluded=len(set(new) - set(old)),
                status="incomplete" if missing else "comparable",
                interpretation="Acceptance changes within a fixed cohort; not causal setup benefit")


def render_outcomes(report):
    lines = ["OUTCOME COVERAGE", "Source: " + report["source"], "Observed: " + report["observed_at"]]
    if report["status"] != "measured":
        lines.append("NOT MEASURED: " + report.get("reason", "source unavailable"))
    else:
        m = report["metrics"]
        lines.extend([f"{m['recorded_runs']} recorded runs; {m['accepted']} recorded accepted; {m['verified_with_receipt']} verified with attached evidence",
                      f"{m['rework']} rework; {m['rollback']} rollback; {m['awaiting_acceptance']} without an acceptance decision",
                      "Next: review the attached result for a pending run and record accepted, rework or rollback."])
        lines.extend("  Pending: " + rid for rid in report["pending_run_ids"][:5])
    lines.extend(report["limitations"])
    if "comparison" in report:
        c = report["comparison"]
        lines.extend([f"Fixed cohort: {c['accepted_before']} -> {c['accepted_now']} accepted / {c['denominator']} runs ({c['status']})",
                      f"{c['new_runs_excluded']} new runs excluded; {len(c['missing_ids'])} baseline runs missing",
                      c["interpretation"]])
    return "\n".join(lines)
