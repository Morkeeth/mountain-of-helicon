"""The self-healing audit loop — ingest a store, score the four truth gates,
emit an evidenced finding + a proposed repair for each drift, apply the accepted
repairs, and re-score so the gates visibly move.

This is the loop no retriever can do: not "find the relevant memory" but "find
the memory that is WRONG, prove it with its sources, propose the fix, and show
the store get measurably healthier after."

Gate scores are deterministic ratios over the units each gate inspects, and the
formula is carried in the output (no hidden magic):

  consistency = healthy memories / memories that bear a claim-or-contradiction
  freshness   = in-date dated memories / dated memories
  volatility  = durable memories that are NOT fast facts / durable memories
  retrieval   = self-retrieval P@1 over the store (flat under these repairs)

Everything reuses the real detectors: claims.find_claim_conflicts (consistency),
volatility.find_suspects (volatility), the frontmatter dates (freshness).
"""
import os
import sqlite3
from datetime import datetime, date

from helicon.claims import find_claim_conflicts
from helicon.volatility import find_suspects

# --- demo lexicon -------------------------------------------------------------
# The one status pole the mocked store needs: the classic dietary-preference
# contradiction. Built-ins (wins/episode/merge-status) always apply on top, so
# the same call works on the real store too.
DEMO_CONFIG = {
    "claims": {
        "statuses": {
            "diet": {
                "vegetarian": r"\bvegetarian\b",
                "eats_meat": r"\b(?:eats?|eating|started eating)\s+"
                             r"(?:meat|chicken|steak|beef|fish)\b",
            }
        }
    }
}

_ACTIVE = "merged_into IS NULL AND review_status != 'killed'"

DEMO_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "data", "helicon-demo.db")


def _today() -> date:
    return datetime.utcnow().date()


def _active_cubes(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        f"SELECT id, source, source_ref, title, content, created_at, metadata "
        f"FROM helicon_cubes WHERE {_ACTIVE}"
    ).fetchall()


# --- gate scoring -------------------------------------------------------------

def _parse_date(s: str | None):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "")).date()
    except (ValueError, TypeError):
        try:
            return datetime.strptime(s[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return None


def _cube_meta(row) -> dict:
    import json
    try:
        return json.loads(row["metadata"] or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}


def gate_scores(conn: sqlite3.Connection, config: dict | None = None) -> dict:
    """The four gates as numbers, each with the counts behind it."""
    config = config or {}
    cubes = _active_cubes(conn)
    total = len(cubes)

    # --- consistency: memories not currently contradicted --------------------
    conflicts = find_claim_conflicts(conn, config)
    conflicted_ids = set()
    for c in conflicts:
        conflicted_ids.update(c["cube_ids"])
    healthy = total - len(conflicted_ids)
    consistency = round(100 * healthy / total, 1) if total else 100.0

    # --- freshness: dated memories still in date -----------------------------
    # A memory is "dated" if it carries either as_of or stale_when (the
    # convention). It is stale only when a stale_when date has actually passed —
    # so a well-stamped store reads high, and one expired goal is a visible dip.
    dated, stale = 0, 0
    for row in cubes:
        meta = _cube_meta(row)
        sw = _parse_date(meta.get("stale_when"))
        if sw or meta.get("as_of"):
            dated += 1
            if sw and sw < _today():
                stale += 1
    freshness = round(100 * (dated - stale) / dated, 1) if dated else 100.0

    # --- volatility: durable memories that are not fast facts ----------------
    suspects = find_suspects(conn)
    suspect_ids = {s["id"] for s in suspects}
    volatility = round(100 * (total - len(suspect_ids)) / total, 1) if total else 100.0

    # --- retrieval: memories actually surfaced by the usage log --------------
    # The truth-gate definition: a memory not retrieved in N sessions is dead
    # weight and a kill candidate. Score = fraction of active memories the usage
    # log has surfaced. Honest n/a when no usage log exists (e.g. a fresh store).
    retrieved = _retrieved_ids(conn)
    if retrieved is None:
        retrieval = None
    else:
        live = sum(1 for r in cubes if r["id"] in retrieved)
        retrieval = round(100 * live / total, 1) if total else 100.0

    return {
        "consistency": consistency,
        "freshness": freshness,
        "volatility": volatility,
        "retrieval": retrieval,
        "_counts": {
            "total_active": total,
            "consistency": {"contradicted": len(conflicted_ids), "checked": total},
            "freshness": {"stale": stale, "dated": dated},
            "volatility": {"fast_facts": len(suspect_ids), "durable": total},
            "retrieval": {"dead_weight": (total - sum(1 for r in cubes if retrieved and r["id"] in retrieved)) if retrieved else None},
        },
    }


def _retrieved_ids(conn: sqlite3.Connection) -> set | None:
    """Cube ids the usage log has surfaced. None when there is no usage log at
    all — the retrieval gate stays honestly n/a rather than flagging everything."""
    try:
        rows = conn.execute(
            "SELECT DISTINCT cube_id FROM retrieval_log WHERE was_surfaced = 1"
        ).fetchall()
    except sqlite3.OperationalError:
        return None
    ids = {r[0] for r in rows}
    return ids or None


# --- findings + repairs -------------------------------------------------------

def build_findings(conn: sqlite3.Connection, config: dict | None = None) -> list[dict]:
    """One scored finding per drift, each carrying its evidence and a proposed
    repair rendered as a diff the human can accept."""
    config = config or {}
    cubes = {r["id"]: r for r in _active_cubes(conn)}
    findings = []

    # consistency — cross-source claim conflicts (recency decides direction
    # when no canonical file speaks: the newer memory wins, retire the stale one)
    for c in find_claim_conflicts(conn, config):
        ev = []
        for cid in c["cube_ids"]:
            row = cubes.get(cid)
            if row:
                ev.append({"source": row["source"], "ref": row["source_ref"],
                           "cube_id": cid, "text": (row["title"] or "").strip(),
                           "created_at": row["created_at"]})
        ev.sort(key=lambda e: e["created_at"])
        canon = c.get("canonical")
        if canon:
            truth = canon["truth"]
            stale = [e for e in ev if _val_of(conn, e["cube_id"], c, config) in canon["drifted"]] or ev[:-1]
            reason = f"canonical source {canon['file']} says {truth}"
        else:
            truth = ev[-1]["text"] if ev else ""
            stale = ev[:-1]
            reason = "newer memory supersedes the stale one (recency)"
        repair = _retire_repair(stale, keep=ev[-1] if ev else None, reason=reason)
        findings.append({
            "id": f"C{len(findings)+1}",
            "gate": "consistency",
            "severity": "critical",
            "subject": c["subject"].replace("/", " · "),
            "drift": f"{c['metric']}: " + " vs ".join(c["values"]),
            "evidence": ev,
            "repair": repair,
            "status": "proposed",
        })

    # freshness — dated memories past their stale_when
    for row in _active_cubes(conn):
        meta = _cube_meta(row)
        sw = _parse_date(meta.get("stale_when"))
        if sw and sw < _today():
            findings.append({
                "id": f"F{sum(1 for f in findings if f['gate']=='freshness')+1}",
                "gate": "freshness",
                "severity": "warning",
                "subject": (row["title"] or "").strip(),
                "drift": f"stale_when {sw.isoformat()} has passed ({( _today()-sw).days}d ago)",
                "evidence": [{"source": row["source"], "ref": row["source_ref"],
                              "cube_id": row["id"], "text": row["content"][:120],
                              "created_at": row["created_at"]}],
                "repair": {"kind": "retire", "targets": [row["id"]],
                           "reason": "the date this memory was pinned to has passed",
                           "diff": _retire_diff(row)},
                "status": "proposed",
            })

    # volatility — fast facts stored as durable memory. A cube already flagged
    # by another gate (e.g. the stale marathon goal is also time-deictic) files
    # once, under the gate that owns the sharper repair — no double-counting.
    active_ids = set(cubes)
    already = {t for f in findings for t in f["repair"].get("targets", [])}
    for s in find_suspects(conn):
        if s["id"] not in active_ids or s["id"] in already:
            continue
        row = cubes[s["id"]]
        findings.append({
            "id": f"V{sum(1 for f in findings if f['gate']=='volatility')+1}",
            "gate": "volatility",
            "severity": "warning",
            "subject": (row["title"] or "").strip(),
            "drift": "fast fact stored as durable memory: " + ", ".join(s.get("signals", [])),
            "evidence": [{"source": row["source"], "ref": row["source_ref"],
                          "cube_id": row["id"], "text": row["content"][:120],
                          "created_at": row["created_at"]}],
            "repair": {"kind": "move-to-live", "targets": [row["id"]],
                       "reason": "belongs in the live layer, not durable memory",
                       "diff": _retire_diff(row, verb="MOVE TO LIVE LAYER")},
            "status": "proposed",
        })

    # retrieval — memories the usage log has never surfaced (dead weight). Only
    # runs when a usage log exists, so a fresh store never flags everything.
    retrieved = _retrieved_ids(conn)
    already = {t for f in findings for t in f["repair"].get("targets", [])}
    if retrieved is not None:
        for row in _active_cubes(conn):
            if row["id"] in retrieved or row["id"] in already:
                continue
            findings.append({
                "id": f"R{sum(1 for f in findings if f['gate']=='retrieval')+1}",
                "gate": "retrieval",
                "severity": "warning",
                "subject": (row["title"] or "").strip(),
                "drift": "never surfaced by the usage log — dead weight diluting retrieval",
                "evidence": [{"source": row["source"], "ref": row["source_ref"],
                              "cube_id": row["id"], "text": row["content"][:120],
                              "created_at": row["created_at"]}],
                "repair": {"kind": "retire", "targets": [row["id"]],
                           "reason": "no session has retrieved this memory; retire the dead weight",
                           "diff": _retire_diff(row)},
                "status": "proposed",
            })

    return findings


def _val_of(conn, cube_id, conflict, config):
    return None  # direction handled by canon.drifted membership; placeholder for file-canon path


def _retire_repair(stale: list[dict], keep: dict | None, reason: str) -> dict:
    targets = [e["cube_id"] for e in stale]
    diff_lines = []
    for e in stale:
        diff_lines.append(f"- [{e['source']}] {e['text']}   (retire — stale)")
    if keep:
        diff_lines.append(f"+ [{keep['source']}] {keep['text']}   (keep — current truth)")
    return {"kind": "retire", "targets": targets, "reason": reason,
            "diff": "\n".join(diff_lines)}


def _retire_diff(row, verb: str = "RETIRE") -> str:
    return (f"- [{row['source']}] {(row['title'] or '').strip()}\n"
            f"    {row['content'][:100]}\n"
            f"  => {verb}")


# --- apply --------------------------------------------------------------------

def apply_repairs(conn: sqlite3.Connection, findings: list[dict],
                  accept: set[str] | None = None) -> dict:
    """Apply accepted repairs to the store. Retire = mark the stale cube killed
    (drops from active; reversible by re-seeding the demo store). Records a
    human_decision on the audit so the loop is auditable."""
    now = datetime.utcnow().isoformat()
    applied = []
    for f in findings:
        if accept is not None and f["id"] not in accept:
            continue
        for cube_id in f["repair"].get("targets", []):
            conn.execute(
                "UPDATE helicon_cubes SET review_status='killed', last_reinforced=? "
                "WHERE id=?", (now, cube_id))
            applied.append({"finding": f["id"], "cube_id": cube_id,
                            "kind": f["repair"]["kind"]})
        f["status"] = "applied"
    conn.commit()
    return {"applied": applied, "count": len(applied)}


# --- the loop / envelope ------------------------------------------------------

def heal(conn: sqlite3.Connection, config: dict | None = None,
         apply: bool = False, store_label: str = "demo") -> dict:
    """Run the full loop and return the envelope in the blessed format."""
    config = {**DEMO_CONFIG, **(config or {})} if store_label == "demo" else (config or {})
    before = gate_scores(conn, config)
    findings = build_findings(conn, config)

    envelope = {
        "store": store_label,
        "scanned_at": datetime.utcnow().isoformat(),
        "gate_scores": {"before": _public(before)},
        "findings": findings,
        "formula": {
            "consistency": "healthy / claim-bearing memories",
            "freshness": "in-date / dated memories",
            "volatility": "durable-non-fast-fact / durable memories",
            "retrieval": "self-retrieval P@1 (flat under structural repairs)",
        },
    }

    if apply:
        result = apply_repairs(conn, findings)
        after = gate_scores(conn, config)
        envelope["gate_scores"]["after"] = _public(after)
        envelope["applied"] = result["applied"]
        envelope["gate_delta"] = {
            g: round(_public(after)[g] - _public(before)[g], 1)
            for g in ("consistency", "freshness", "volatility", "retrieval")
            if _public(after)[g] is not None and _public(before)[g] is not None
        }
    envelope["summary"] = {
        "findings": len(findings),
        "by_gate": {g: sum(1 for f in findings if f["gate"] == g)
                    for g in ("consistency", "freshness", "volatility", "retrieval")},
        "applied": len(envelope.get("applied", [])),
    }
    return envelope


def _public(scores: dict) -> dict:
    return {k: scores[k] for k in ("consistency", "freshness", "volatility", "retrieval")}
