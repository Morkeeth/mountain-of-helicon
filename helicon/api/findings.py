"""Findings API — the FINDINGS surface of the dashboard.

One unified list of "things that failed a check", aggregated from the
existing signal sources (nothing new is computed here, no synthetic data):

  - audit_log: pending temporal / decay / factual / pattern-staleness findings
    (what `helicon.audit.run_audit` wrote, same rows the Audit tab shows)
  - skills integrity: duplicates / thin descriptions / trigger collisions,
    same lens as /api/integrity/skills (filesystem scan, no DB)
  - battery: per-task BROKEN/DEGRADED verdicts from the context-quality
    battery (same as /api/integrity/battery). Expensive — only computed when
    explicitly requested with ?include=battery so the default load stays fast.

Every finding has the same shape:
  {id, kind, severity, title, why, evidence_preview, source, source_ref,
   cube_id, suggested_action, created_at}
"""
import json
import os
from collections import Counter
from datetime import datetime, timezone
from itertools import combinations

from fastapi import APIRouter

from helicon.api.app import get_conn
from helicon.api.integrity import _SKILL_ROOTS, _terms
from helicon.connectors import skills as skills_connector

router = APIRouter()

PREVIEW_CHARS = 300
BATTERY_K = 5

_SEVERITY_RANK = {"critical": 4, "high": 3, "warning": 2, "medium": 2, "info": 1}

# Rare, actionable classes outrank bulk housekeeping regardless of severity:
# one cross-source contradiction matters more than the 166th stale note.
# Order: contradictions / supersession / wrong evictions / agent flags first,
# then the recurring hygiene kinds.
_KIND_RANK = {"factual": 0, "supersession": 0, "output": 1, "routine": 1, "regret": 1, "agent-flag": 1,
              "battery": 2, "skill": 2, "logical": 2, "temporal": 3, "decay": 3}

# Two lanes. DECISION findings need Oscar's judgment — only a human knows
# whether two sources contradict, whether a kill was wrong, or which skill is
# canonical. AMBIENT findings are age/mechanics the system can manage in bulk
# (a note went stale, a git commit decayed, a path moved). The daily queue is
# the decision lane; ambient is a collapsed, auto-manageable pile. This is
# Oscar's Jul-3 verdict made real: "CI shows failing checks, not every line."
_AMBIENT_KINDS = {"temporal", "decay", "output", "routine", "context", "logical"}


def _lane(kind: str) -> str:
    return "ambient" if kind in _AMBIENT_KINDS else "decision"


def _recal_severity(kind: str, severity: str) -> str:
    """'critical' is reserved for things that need a decision now. Pure age or
    mechanical findings (a 104-day git commit at 0% confidence) are never
    critical no matter what the raw audit stamped — that inflation is exactly
    why 170/281 findings read 'critical' and the word stopped meaning anything."""
    if kind in _AMBIENT_KINDS and severity == "critical":
        return "warning"
    return severity


_LANE_RANK = {"decision": 1, "ambient": 0}

# Which named check an audit_type corresponds to, for the human "why" sentence.
_AUDIT_CHECK = {
    "routine": "Routine health",
    "output": "Dead path",
    "context": "Context weight",
    "temporal": "Freshness",
    "decay": "Decay",
    "factual": "Contradiction",
    "logical": "Pattern staleness",
}

# What the human should do about each audit kind.
_AUDIT_ACTION = {
    "temporal": "kill_stale",
    "decay": "kill_stale",
    "factual": "reconcile",
    "logical": "review",
    "identity": "resolve_identity",
}


def _preview(text: str | None) -> str:
    text = (text or "").strip()
    return text[:PREVIEW_CHARS]


def _audit_findings(conn) -> list[dict]:
    """Pending audit_log rows as findings, joined to their cube for evidence."""
    rows = conn.execute(
        """SELECT a.id, a.audit_type, a.target_type, a.target_id, a.finding,
                  a.severity, a.proposed_action, a.audited_at, a.details,
                  c.title AS cube_title, c.content AS cube_content,
                  c.source AS cube_source, c.source_ref AS cube_source_ref
           FROM audit_log a
           LEFT JOIN helicon_cubes c
             ON a.target_type = 'cube' AND c.id = a.target_id
           WHERE a.human_decision IS NULL
           ORDER BY a.audited_at DESC"""
    ).fetchall()

    findings = []
    for r in rows:
        kind = r["audit_type"]
        check = _AUDIT_CHECK.get(kind, kind.capitalize())
        is_cube = r["target_type"] == "cube" and r["cube_title"] is not None
        # A contradiction finding's evidence is the two conflicting LINES
        # side by side (what lets a human verify in five seconds) — never
        # just the target cube's content, which proves nothing by itself.
        evidence = _preview(r["cube_content"]) if is_cube else ""
        try:
            details = json.loads(r["details"]) if r["details"] else {}
        except (ValueError, TypeError):
            details = {}
        if details.get("pair_key"):
            from helicon.pairing import format_pair_evidence
            evidence = format_pair_evidence(details)
        findings.append({
            "id": f"audit-{r['id']}",
            "kind": kind,
            "severity": r["severity"],
            "title": r["cube_title"] if is_cube else r["target_id"],
            "why": f"{check}: {r['finding']}",
            "evidence_preview": evidence,
            "source": r["cube_source"] if is_cube else "audit",
            "source_ref": r["cube_source_ref"] if is_cube else r["target_id"],
            "cube_id": r["target_id"] if r["target_type"] == "cube" else None,
            "suggested_action": _AUDIT_ACTION.get(kind, "review"),
            "created_at": r["audited_at"],
        })
    return findings


def _regret_findings(conn) -> list[dict]:
    """Retired cubes that retrieval keeps wanting back — the eviction was
    probably wrong. Keep = restore (an approve review revives the cube)."""
    from helicon.regret import get_regrets

    findings = []
    for r in get_regrets(conn, limit=30):
        findings.append({
            "id": f"regret-{r['cube_id']}",
            "kind": "regret",
            "severity": "high" if (r["total_weight"] or 0) >= 1.0 else "medium",
            "title": r["title"],
            "why": (f"You retired this ({r['review_status']}"
                    + (f", by {r['killed_by']}" if r["killed_by"] else "")
                    + f") and retrieval wanted it {r['events']}x since — "
                    f"e.g. for \"{(r['sample_task'] or '')[:60]}\""),
            "evidence_preview": f"regret weight {round(r['total_weight'] or 0, 2)} "
                                f"(time-decayed), last wanted {(r['last_wanted'] or '')[:16]}",
            "source": r["cube_source"],
            "source_ref": r["source_ref"],
            "cube_id": r["cube_id"],
            "suggested_action": "restore",
            "created_at": r["last_wanted"],
        })
    return findings


def _skill_findings(now: str) -> list[dict]:
    """Skills-integrity issues as findings — same checks as /api/integrity/skills
    (duplicates / trigger collisions / thin descriptions), but scanned here with
    the description kept so evidence_preview shows the actual SKILL.md text."""
    roots = [r for r in _SKILL_ROOTS if os.path.exists(os.path.expanduser(r))]
    if not roots:
        return []
    found = skills_connector.scan({"skill_roots": roots})

    meta = []
    for r in found:
        name = r.metadata["skill_name"]
        desc = r.metadata["description"]
        meta.append({
            "name": name,
            "desc": desc,
            "desc_len": r.metadata["desc_len"],
            "trigger_terms": _terms(f"{name} {desc}"),
            "path": r.metadata["path"],
            "content": r.content,
        })

    findings = []

    by_name: dict[str, list[dict]] = {}
    for m in meta:
        by_name.setdefault(m["name"].lower(), []).append(m)
    # ONE grouped finding per issue class — 19 rows of "X installed twice"
    # reads as hours of work; one row with the list reads as one fix.
    dup_groups = [g for g in by_name.values() if len(g) > 1]
    if dup_groups:
        names = sorted(g[0]["name"] for g in dup_groups)
        findings.append({
            "id": "skill-dups",
            "kind": "skill",
            "severity": "warning",
            "title": f"{len(dup_groups)} skills installed more than once",
            "why": (f"Skills integrity: {len(dup_groups)} skills exist in two "
                    f"places; the agent can load either copy"),
            "evidence_preview": _preview(", ".join(names)),
            "source": "skills",
            "source_ref": dup_groups[0][0]["path"],
            "cube_id": None,
            "suggested_action": "fix_skill",
            "created_at": now,
        })

    uniq = list({m["name"].lower(): m for m in meta}.values())

    thin = [m for m in uniq if m["desc_len"] < 40]
    if thin:
        names = sorted(m["name"] for m in thin)
        findings.append({
            "id": "skill-thin",
            "kind": "skill",
            "severity": "warning" if any(m["desc_len"] == 0 for m in thin) else "info",
            "title": f"{len(thin)} skills with no usable description",
            "why": (f"Skills integrity: {len(thin)} skills are too thin for "
                    f"the agent to know when to trigger them — one command "
                    f"fixes all: helicon fix-skills --apply"),
            "evidence_preview": _preview(", ".join(names)),
            "source": "skills",
            "source_ref": thin[0]["path"],
            "cube_id": None,
            "suggested_action": "fix_skill",
            "created_at": now,
        })

    for a, b in combinations(uniq, 2):
        t1, t2 = a["trigger_terms"], b["trigger_terms"]
        if t1 and t2:
            j = len(t1 & t2) / len(t1 | t2)
            if j > 0.5:
                findings.append({
                    "id": f"skill-collide-{a['name'].lower()}-{b['name'].lower()}",
                    "kind": "skill",
                    "severity": "warning",
                    "title": f"Trigger collision: {a['name']} vs {b['name']}",
                    "why": (f"Skills integrity: '{a['name']}' and '{b['name']}' "
                            f"share {j:.0%} of their trigger terms; "
                            f"the agent may fire the wrong one"),
                    "evidence_preview": _preview(a["desc"] or a["content"]),
                    "source": "skills",
                    "source_ref": a["path"],
                    "cube_id": None,
                    "suggested_action": "fix_skill",
                    "created_at": now,
                })

    return findings


def _battery_findings(conn, now: str) -> list[dict]:
    """One finding per BROKEN/DEGRADED battery task, naming the failing tests
    and the offending cubes. Deterministic tests only (no LLM) — still needs a
    retrieval pass per task, which is why this is behind ?include=battery."""
    from helicon.battery import run_battery
    from helicon.eval import _build_test_queries
    from helicon.snapshots import _retrieve

    findings = []
    for i, q in enumerate(_build_test_queries(conn)):
        task = q["query"]
        res = run_battery(conn, task, k=BATTERY_K)
        if res["verdict"] not in ("BROKEN", "DEGRADED"):
            continue
        fails = [r for r in res["results"] if r["status"] == "FAIL"]
        fail_names = [f["name"] for f in fails]
        reasons = "; ".join(f"{f['name']}: {f['reason']}" for f in fails)

        if "Freshness" in fail_names:
            action = "kill_stale"
        elif "Redundancy" in fail_names:
            action = "reconcile"
        else:
            action = "review"

        hits = _retrieve(conn, task, BATTERY_K)
        first_cube_id = hits[0]["id"] if hits else None
        evidence = ""
        if first_cube_id:
            row = conn.execute(
                "SELECT content FROM helicon_cubes WHERE id = ?", (first_cube_id,)
            ).fetchone()
            evidence = _preview(row["content"]) if row else ""

        offenders = ", ".join(t[:60] for t in res["retrieved"][:3]) or "nothing retrieved"
        findings.append({
            "id": f"battery-{i}",
            "kind": "battery",
            "severity": "critical" if res["verdict"] == "BROKEN" else "warning",
            "title": f"Battery {res['verdict']}: {task[:80]}",
            "why": (f"Battery: task '{task}' is {res['verdict']}, "
                    f"failed {', '.join(fail_names)} ({reasons}). "
                    f"Retrieved: {offenders}"),
            "evidence_preview": evidence,
            "source": "battery",
            "source_ref": task,
            "cube_id": first_cube_id,
            "suggested_action": action,
            "created_at": now,
        })
    return findings


@router.get("/findings")
async def list_findings(kind: str | None = None, lane: str | None = None,
                        limit: int = 100, include: str = ""):
    """Unified findings list. ?lane=decision (the default daily queue: things
    that need your ruling) or ?lane=ambient (age/mechanics, auto-manageable).
    ?kind= filters to one kind. ?include=battery adds the expensive per-task
    battery findings. Sorted decision-lane first, then severity, then recency."""
    conn = get_conn()
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

    findings = _audit_findings(conn)
    try:
        findings.extend(_regret_findings(conn))
    except Exception:
        pass  # empty/missing regret table must never break the surface
    try:
        findings.extend(_skill_findings(now))
    except Exception:
        pass  # skills roots missing/unreadable must never break the surface
    if "battery" in (include or ""):
        findings.extend(_battery_findings(conn, now))

    # Annotate lane + recalibrate severity once, centrally, for every source.
    for f in findings:
        f["lane"] = _lane(f["kind"])
        f["severity"] = _recal_severity(f["kind"], f["severity"])

    if kind:
        findings = [f for f in findings if f["kind"] == kind]

    # needs_you / ambient always describe the full (kind-filtered) set, so the
    # default call reports "N need you, M ambient" before any lane slice.
    needs_you = sum(1 for f in findings if f["lane"] == "decision")
    ambient = sum(1 for f in findings if f["lane"] == "ambient")

    if lane:
        findings = [f for f in findings if f["lane"] == lane]

    findings.sort(
        key=lambda f: (_LANE_RANK.get(f["lane"], 0),
                       -_KIND_RANK.get(f["kind"], 2),
                       _SEVERITY_RANK.get(f["severity"], 0),
                       f["created_at"] or ""),
        reverse=True,
    )

    summary = {
        "total": len(findings),
        "needs_you": needs_you,
        "ambient": ambient,
        "by_kind": dict(Counter(f["kind"] for f in findings)),
        "by_severity": dict(Counter(f["severity"] for f in findings)),
    }

    return {"findings": findings[: max(limit, 0)], "summary": summary}
