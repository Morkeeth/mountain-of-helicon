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
    open_factual = conn.execute(
        "SELECT COUNT(*) FROM audit_log WHERE audit_type IN ('factual', 'agent-flag') "
        "AND human_decision IS NULL"
    ).fetchone()[0]
    try:
        from helicon.pairing import find_conflicts
        conflicts = find_conflicts(conn)
        sample = "; ".join(
            f"{c['person'].title()} {c['topic']}: {' vs '.join(c['dates'])}"
            for c in conflicts[:3])
        checks.append(_check(
            "R1", "Cross-source contradiction", "TESTED",
            bool(conflicts) or open_factual > 0,
            f"{len(conflicts)} live cross-source conflict(s) from the pair selector"
            + (f" ({sample})" if sample else "")
            + f"; {open_factual} unresolved contradiction/flag finding(s)"))
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

    # R4 supersession — retired cubes exist, but rename propagation (old name
    # asserted in CURRENT claims) is the known gap until aliases ship.
    superseded = conn.execute(
        "SELECT COUNT(*) FROM helicon_cubes WHERE review_status = 'superseded'"
    ).fetchone()[0]
    checks.append(_check(
        "R4", "Supersession / rename", "PARTIAL", None,
        f"{superseded} cube(s) retired by reconcile; renamed-entity propagation "
        "(dead name in current claims vs history) is a known gap"))

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
    # appear in what the rule learner counts as human evidence.
    leaked = conn.execute(
        "SELECT COUNT(*) FROM reviews WHERE session_id NOT IN ('auto-triage', 'agent-flag') "
        "AND session_id NOT LIKE 'rule:%' AND (session_id LIKE 'auto%' OR session_id LIKE 'agent%')"
    ).fetchone()[0]
    non_human = conn.execute(
        "SELECT COUNT(*) FROM reviews WHERE session_id IN ('auto-triage', 'agent-flag') "
        "OR session_id LIKE 'rule:%'"
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
