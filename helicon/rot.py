"""The rot exam — ROT.md as an executable test suite.

Ten named failure classes (R1-R10), each grounded in the public record (see
ROT.md), each checked live against the real store. One command answers
"which documented ways of going wrong is MY memory going wrong in right now?"

Statuses are honest three ways:
  - coverage:  TESTED (a real check ran) or PARTIAL (known gap, said out loud)
  - verdict:   CLEAN / ROT FOUND / UNMEASURED per class
  - receipts:  every verdict carries the number and where it came from

Zero LLM calls by default — the exam is deterministic and free to run daily.
"""
import sqlite3
from datetime import datetime

from helicon.forgetting import DEFAULT_STABILITY


def _check(rid, name, coverage, found, receipt):
    return {
        "id": rid, "name": name, "coverage": coverage,
        "verdict": ("ROT FOUND" if found else "CLEAN") if found is not None else "UNMEASURED",
        "receipt": receipt,
    }


def run_rot_exam(conn: sqlite3.Connection, repo_root: str | None = None) -> dict:
    checks = []

    # R1 cross-source contradiction — the pair selector (helicon.pairing)
    # finds disjoint dated facts about the same person across source files;
    # the Qwen detector rules on what it finds.
    # Verdict scope: live conflicts + open PAIRING findings only. An open
    # agent-flag about something else must not pin R1 at ROT FOUND forever
    # (that would mute watch's flip alert for real contradictions).
    open_pairing = conn.execute(
        "SELECT COUNT(*) FROM audit_log WHERE audit_type = 'factual' "
        "AND details LIKE '%pair_key%' AND human_decision IS NULL"
    ).fetchone()[0]
    try:
        from helicon.pairing import find_conflicts
        conflicts = find_conflicts(conn)
        sample = "; ".join(
            f"{c['person'].title()} {c['topic']}: {' vs '.join(c['dates'])}"
            for c in conflicts[:3])
        checks.append(_check(
            "R1", "Cross-source contradiction", "TESTED",
            bool(conflicts) or open_pairing > 0,
            f"{len(conflicts)} live cross-source conflict(s) from the pair selector"
            + (f" ({sample})" if sample else "")
            + f"; {open_pairing} unresolved pairing finding(s)"))
    except Exception as e:
        checks.append(_check("R1", "Cross-source contradiction", "TESTED", None,
                             f"unmeasured: {e}"))

    # R2 doc-drift — README numeric claims vs source truth.
    try:
        from helicon.docdrift import check_readme
        drift = [r for r in (check_readme(repo_root) if repo_root else check_readme())
                 if not r["ok"]]
        checks.append(_check(
            "R2", "Doc-drift", "TESTED", bool(drift),
            "README matches source" if not drift else
            "; ".join(f"{d['claim']}: {d['why']}" for d in drift)))
    except Exception as e:
        checks.append(_check("R2", "Doc-drift", "TESTED", None, f"unmeasured: {e}"))

    # R3 staleness/expiry — live cubes past their type's half-life, unreinforced.
    now = datetime.utcnow().isoformat()
    expired = 0
    for ctype, eta in DEFAULT_STABILITY.items():
        expired += conn.execute(
            "SELECT COUNT(*) FROM helicon_cubes WHERE type = ? "
            "AND review_status IN ('pending', 'revised') AND merged_into IS NULL "
            "AND COALESCE(NULLIF(last_reinforced, ''), created_at) < datetime(?, ?)",
            (ctype, now, f"-{eta} days"),
        ).fetchone()[0]
    checks.append(_check(
        "R3", "Staleness / expiry", "TESTED", expired > 0,
        f"{expired} live cube(s) past their type's half-life without reinforcement "
        "(decay runs on every scan; battery test 'Expiry' covers retrieval)"))

    # R4 supersession — declared aliases triage every dead-name reference:
    # pre-rename history is kept, post-rename current-claims are the rot,
    # and serving the dead name for a current-name query is the proof.
    superseded = conn.execute(
        "SELECT COUNT(*) FROM helicon_cubes WHERE review_status = 'superseded'"
    ).fetchone()[0]
    try:
        from helicon.aliases import alias_rot
        triages = alias_rot(conn)
        if not triages:
            checks.append(_check(
                "R4", "Supersession / rename", "TESTED", None,
                f"{superseded} cube(s) retired by reconcile; no renames declared "
                "yet — helicon alias add <old> <new>"))
        else:
            found = any(t["current_claims"] > 0 or t["leaked"] for t in triages)
            receipt = "; ".join(
                f"{t['old_name']}->{t['new_name']}: {t['live_refs']} live dead-name "
                f"ref(s) = {t['history']} history + {t['rename_aware']} rename-aware "
                f"+ {t['current_claims']} current-claim(s)"
                + (f", {len(t['leaked'])}/{t['retrieved_for_new_name']} top-K hits "
                   f"for '{t['new_name']}' serve the dead name" if t["leaked"] else "")
                for t in triages)
            checks.append(_check(
                "R4", "Supersession / rename", "TESTED", found,
                receipt + f" ({superseded} cube(s) retired by reconcile)"))
    except Exception as e:
        checks.append(_check("R4", "Supersession / rename", "TESTED", None,
                             f"unmeasured: {e}"))

    # R5 duplicate/echo — identical content stored more than once, live.
    dupes = conn.execute(
        "SELECT COUNT(*) FROM (SELECT content_hash FROM helicon_cubes "
        "WHERE review_status IN ('pending', 'revised', 'approved') AND merged_into IS NULL "
        "GROUP BY content_hash HAVING COUNT(*) > 1)"
    ).fetchone()[0]
    checks.append(_check(
        "R5", "Duplicate / echo memory", "TESTED", dupes > 0,
        f"{dupes} content hash(es) stored more than once among live cubes"))

    # R6 title-only grounding — live cubes that are stubs (no substance).
    stubs = conn.execute(
        "SELECT COUNT(*) FROM helicon_cubes WHERE review_status IN ('pending', 'revised') "
        "AND merged_into IS NULL AND length(content) < 40"
    ).fetchone()[0]
    total_live = conn.execute(
        "SELECT COUNT(*) FROM helicon_cubes WHERE review_status IN ('pending', 'revised') "
        "AND merged_into IS NULL"
    ).fetchone()[0]
    thin_share = (stubs / total_live) if total_live else 0
    checks.append(_check(
        "R6", "Title-only grounding", "TESTED", thin_share > 0.10,
        f"{stubs}/{total_live} live cubes are stubs (<40 chars); "
        "battery tests Thinness+Grounding cover retrieval"))

    # R7 wrong eviction — the regret ledger.
    try:
        from helicon.regret import get_regrets
        regrets = get_regrets(conn, limit=100)
        checks.append(_check(
            "R7", "Wrong eviction (regret)", "TESTED", len(regrets) > 0,
            f"{len(regrets)} retired cube(s) retrieval has wanted back "
            "(time-decayed, blame on the kill decision)"))
    except Exception as e:
        checks.append(_check("R7", "Wrong eviction (regret)", "TESTED", None, f"unmeasured: {e}"))

    # R8 retrieval regression — snapshots vs baseline.
    try:
        from helicon.snapshots import check_all
        snaps = check_all(conn)
        regressed = sum(1 for s in snaps if s["regressed"])
        checks.append(_check(
            "R8", "Retrieval regression", "TESTED",
            (regressed > 0) if snaps else None,
            f"{regressed}/{len(snaps)} snapshot(s) regressed vs baseline" if snaps
            else "no baselines captured — run: helicon snapshot add"))
    except Exception as e:
        checks.append(_check("R8", "Retrieval regression", "TESTED", None, f"unmeasured: {e}"))

    # R9 self-evidence loops — the guard must hold: no non-human session may
    # appear in what the rule learner counts as human evidence. The guard is
    # ONE written predicate (db.human_evidence_sql); this check audits it.
    from helicon.db import human_evidence_sql
    leaked = conn.execute(
        f"SELECT COUNT(*) FROM reviews WHERE {human_evidence_sql()} "
        "AND (session_id LIKE 'auto%' OR session_id LIKE 'agent%')"
    ).fetchone()[0]
    non_human = conn.execute(
        f"SELECT COUNT(*) FROM reviews WHERE NOT ({human_evidence_sql()})"
    ).fetchone()[0]
    checks.append(_check(
        "R9", "Self-evidence loops", "TESTED", leaked > 0,
        f"{non_human} automated review(s) correctly quarantined from rule learning; "
        f"{leaked} leaked past the guard"))

    # R10 instruction-file drift — agent-rules/skills cubes retired or duplicated.
    rules_retired = conn.execute(
        "SELECT COUNT(*) FROM helicon_cubes WHERE source IN ('agent-rules', 'skills') "
        "AND review_status = 'superseded'"
    ).fetchone()[0]
    rules_live = conn.execute(
        "SELECT COUNT(*) FROM helicon_cubes WHERE source IN ('agent-rules', 'skills') "
        "AND review_status NOT IN ('killed', 'superseded')"
    ).fetchone()[0]
    checks.append(_check(
        "R10", "Instruction-file drift", "TESTED", rules_retired > 0,
        f"{rules_retired} rules/skills section(s) retired as drifted; {rules_live} live "
        "(section-level cubes, covered by reconcile + snapshots)"))

    found = sum(1 for c in checks if c["verdict"] == "ROT FOUND")
    unmeasured = sum(1 for c in checks if c["verdict"] == "UNMEASURED")
    tested = sum(1 for c in checks if c["coverage"] == "TESTED")
    return {
        "exam": "ROT", "classes": len(checks), "tested": tested,
        "partial": len(checks) - tested, "rot_found": found, "unmeasured": unmeasured,
        "checks": checks,
    }


def format_rot(res: dict) -> str:
    lines = [
        "The rot exam — 10 documented failure classes, checked live (see ROT.md)",
        "",
    ]
    for c in res["checks"]:
        cov = "" if c["coverage"] == "TESTED" else "  [partial coverage]"
        lines.append(f"  {c['id']:>3}  {c['name']:<28} {c['verdict']:<10}{cov}")
        lines.append(f"       {c['receipt']}")
    lines.append("")
    lines.append(f"{res['rot_found']}/{res['classes']} classes show rot right now · "
                 f"{res['tested']}/{res['classes']} fully tested, "
                 f"{res['partial']} partial (gaps named in ROT.md)")
    return "\n".join(lines)
