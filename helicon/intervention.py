"""Intervention Gate — the compact factual check a run passes BEFORE it starts.

VISION.md's line: Helicon measures whether activity earns the *right to continue*,
not activity itself. This is the gate that enforces it at the one moment it is
cheapest — before an expensive run begins. It answers a single question with
evidence, never a vibe:

    "Is this run worth initiating right now, or should you intervene first?"

The checks are exactly the ones a governance layer can state as fact (from the
build plan): absent success criterion, no beneficiary, no way to observe an
outcome, missing context, stale memory, unreviewed skill version. Each returns a
status and a one-line reason; nothing is invented, and the gate is READ-ONLY (it
never mutates the store — a factual gate that changed state would not be one).

Severities:
  blocker — the run cannot be judged if it proceeds (refuse unless forced)
  warn    — proceed is defensible, but you are flying with a known gap
  ok      — the check passed

Verdict: "blocked" if any blocker, else "warn" if any warn, else "go".
"""
import re
import sqlite3

from helicon import outcome_contract as _oc

_SKILL_REF = re.compile(r"^[\w.\-/]+@[\w.\-]+$")  # name@version

# Context-rot onset (tokens). Kept in sync with helicon.context_budget when that
# module is present; inlined here so the gate has no hard dependency on it.
_ONSET_TOKENS = 32_000


def _assess_budget(tokens: int) -> dict:
    """Prefer the shared context_budget module; fall back to a minimal inline
    onset check so the gate works regardless of which modules are installed."""
    try:
        from helicon.context_budget import assess
        return assess(tokens)
    except Exception:
        over = tokens >= _ONSET_TOKENS
        return {
            "status": "over" if over else "healthy",
            "note": (f"{tokens:,} tokens — past the ~{_ONSET_TOKENS:,}-token "
                     f"context-rot onset; compress or select" if over
                     else f"{tokens:,} tokens — within the ~{_ONSET_TOKENS:,}-token budget"),
        }


def _check(name, status, reason):
    return {"name": name, "status": status, "reason": reason}


def _retrieve(conn, query, k):
    """Read-only retrieval, tolerant of a store without an FTS index / embeddings."""
    try:
        from helicon.snapshots import _retrieve as retr
        return retr(conn, query, k) or []
    except Exception:
        return []


def _fetch(conn, ids):
    if not ids:
        return {}
    q = ",".join("?" * len(ids))
    try:
        rows = conn.execute(
            f"SELECT id, title, content, confidence, review_status "
            f"FROM helicon_cubes WHERE id IN ({q})", ids).fetchall()
    except sqlite3.Error:
        return {}
    return {r["id"]: dict(r) for r in rows}


def _last_scan_hours(conn):
    try:
        from helicon.db import last_scan_info
        info = last_scan_info(conn)
        return info["hours_ago"] if info else None
    except Exception:
        return None


def gate(conn, *, objective="", acceptance_test="", outcome_contract=None,
         skill_versions=None, query=None, config=None, k: int = 5,
         stale_after_hours: float = 24.0) -> dict:
    """Run the pre-run checks. Pure read. Returns a compact, honest gate object."""
    checks = []
    v = _oc.validate(outcome_contract or {})

    # 1. Success criterion — the frozen definition of "accepted". Absent = the run
    #    can complete but can never be judged verified rather than in hindsight.
    has_criterion = bool((acceptance_test or "").strip()) and len(acceptance_test.strip()) >= 8
    checks.append(_check(
        "success criterion", "ok" if has_criterion else "blocker",
        "acceptance test frozen before work" if has_criterion
        else "no acceptance test — 'verified' later could only be hindsight"))

    # 2. Beneficiary — who is better off if this run succeeds.
    checks.append(_check(
        "beneficiary", "ok" if v["has_beneficiary"] else "blocker",
        f"for {v['contract']['beneficiary']}" if v["has_beneficiary"]
        else "no beneficiary — a run for no one cannot be worth its cost"))

    # 3. Observable outcome — a stated real-world change AND where we confirm it.
    checks.append(_check(
        "observable outcome", "ok" if v["observable"] else "blocker",
        "change + evidence source declared" if v["observable"]
        else "no way to observe an outcome — state the change and where you'll confirm it"))

    # 4/5. Recommended contract fields — warnings, not blockers.
    for field in _oc.RECOMMENDED:
        present = field in v["contract"]
        checks.append(_check(
            _oc.label(field), "ok" if present else "warn",
            v["contract"].get(field, "") if present
            else f"no {_oc.label(field)} declared"))

    # 6/7. Context: what this objective would retrieve, and whether it is fresh.
    q = (query or objective or "").strip()
    hits = _retrieve(conn, q, k) if q else []
    cubes = _fetch(conn, [h["id"] for h in hits if h.get("id")])
    if not q:
        checks.append(_check("context", "warn", "no objective/query to check context against"))
    elif not hits:
        checks.append(_check("context", "warn",
                             "no memory retrieved for this objective — running blind"))
    else:
        stale = [c for c in cubes.values()
                 if c.get("review_status") in ("killed", "superseded")
                 or (c.get("confidence") or 1.0) < 0.10]
        checks.append(_check(
            "stale memory", "ok" if not stale else "warn",
            f"{len(hits)} memories retrieved, all live" if not stale
            else f"{len(stale)}/{len(hits)} retrieved memories are killed/decayed"))
        # context budget on the retrieved set (context-rot guard)
        tokens = sum(len(f"{c.get('title','')} {c.get('content','')}")
                     for c in cubes.values()) // 4
        b = _assess_budget(tokens)
        checks.append(_check("context budget", "ok" if b["status"] != "over" else "warn",
                             b["note"]))

    # 8. Scan freshness — is the store's knowledge itself stale?
    hours = _last_scan_hours(conn)
    if hours is None:
        checks.append(_check("scan freshness", "warn",
                             "no completed scan logged — memory may be stale"))
    elif hours > stale_after_hours:
        checks.append(_check("scan freshness", "warn",
                             f"last scan {hours:.0f}h ago (> {stale_after_hours:.0f}h)"))
    else:
        checks.append(_check("scan freshness", "ok", f"scanned {hours:.0f}h ago"))

    # 9. Skill version — a run should pin the skills (versioned SOPs) it relied on.
    skills = [s for s in (skill_versions or []) if str(s).strip()]
    if not skills:
        checks.append(_check("skill version", "warn",
                             "no skill version pinned — the run's operating procedure is unrecorded"))
    else:
        malformed = [s for s in skills if not _SKILL_REF.match(str(s))]
        checks.append(_check(
            "skill version", "ok" if not malformed else "warn",
            f"pinned {', '.join(skills)}" if not malformed
            else f"unversioned skill ref(s): {', '.join(malformed)} (want name@version)"))

    blockers = [c for c in checks if c["status"] == "blocker"]
    warns = [c for c in checks if c["status"] == "warn"]
    verdict = "blocked" if blockers else ("warn" if warns else "go")
    return {
        "verdict": verdict,
        "checks": checks,
        "blockers": [c["name"] for c in blockers],
        "warnings": [c["name"] for c in warns],
        "headline": _headline(verdict, blockers, warns),
    }


def _headline(verdict, blockers, warns) -> str:
    if verdict == "blocked":
        return (f"Not worth initiating yet — {len(blockers)} blocker(s): "
                f"{', '.join(c['name'] for c in blockers)}.")
    if verdict == "warn":
        return (f"Clear to run, with {len(warns)} known gap(s): "
                f"{', '.join(c['name'] for c in warns)}.")
    return "Clear to run — every pre-run check passed."


_MARK = {"ok": "PASS", "warn": "WARN", "blocker": "BLOCK"}


def format_gate(g: dict) -> str:
    lines = ["", f"  Intervention gate: {g['verdict'].upper()}", f"  {g['headline']}", ""]
    for c in g["checks"]:
        lines.append(f"  [{_MARK.get(c['status'], c['status'])}] {c['name']:<18} {c['reason']}")
    lines.append("")
    return "\n".join(lines)
