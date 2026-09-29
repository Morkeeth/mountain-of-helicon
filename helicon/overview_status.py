"""Read-only, source-backed overview of an agent engineering setup.

The overview deliberately keeps unlike denominators separate.  It never emits
an overall health score.  A missing store, baseline, or recent evaluation is an
unmeasured result, not a zero.
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import config_file, load_config
from .forgetting import DEFAULT_STABILITY
from .setup_audit import audit_setup
from .setup_status import setup_status


SCHEMA = "helicon.overview-status/1"
LIVE = "merged_into IS NULL AND review_status IN ('pending','revised')"
CONFLICT_TYPES = ("identity", "factual", "supersession")


def _stamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except (ValueError, TypeError):
        return None


def _point(at: str, numerator: int, denominator: int) -> dict:
    return {
        "at": at,
        "value": round(100 * numerator / denominator, 1) if denominator else None,
        "numerator": numerator,
        "denominator": denominator,
    }


def _metric(key: str, label: str, numerator: int | None,
            denominator: int | None, formula: str, source: str,
            observed_at: str, limit: str, points: list[dict] | None = None,
            unmeasured: str = "") -> dict:
    measured = numerator is not None and denominator not in (None, 0)
    return {
        "id": key,
        "label": label,
        "state": "measured" if measured else "unmeasured",
        "value": round(100 * numerator / denominator, 1) if measured else None,
        "numerator": numerator,
        "denominator": denominator,
        "formula": formula,
        "source": source,
        "observed_at": observed_at,
        "limit": limit,
        "unmeasured": "" if measured else (unmeasured or "The denominator is absent."),
        "points": points or [],
    }


def _table(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _freshness(conn: sqlite3.Connection, observed_at: str, now: datetime) -> dict:
    if not _table(conn, "helicon_cubes"):
        return _metric("freshness", "Context freshness", None, None,
                       "current indexed records / records with a type staleness window",
                       "helicon_cubes", observed_at,
                       "Only live records whose type has a declared Helicon stability window are graded.",
                       unmeasured="The memory table is absent.")
    rows = conn.execute(
        "SELECT type, created_at, last_reinforced FROM helicon_cubes WHERE " + LIVE
    ).fetchall()
    applicable = current = 0
    for row in rows:
        window = DEFAULT_STABILITY.get(row["type"])
        when = _stamp(row["last_reinforced"] or row["created_at"])
        if window is None or when is None:
            continue
        applicable += 1
        if now.replace(tzinfo=None) - when <= timedelta(days=window):
            current += 1
    return _metric(
        "freshness", "Context freshness", current if applicable else None,
        applicable if applicable else None,
        "current indexed records / records with a type staleness window",
        "helicon_cubes.created_at + last_reinforced; forgetting.DEFAULT_STABILITY",
        observed_at,
        "This is freshness against Helicon's declared type windows, not truth or usefulness. Historical ratios were not stored.",
        unmeasured="No live record has both a known timestamp and a declared type window.",
    )


def _json_list(raw) -> list:
    try:
        value = json.loads(raw or "[]")
        return value if isinstance(value, list) else []
    except (ValueError, TypeError):
        return []


def _coverage(conn: sqlite3.Connection, configured: list[str],
              observed_at: str) -> dict:
    formula = "enabled configured sources successfully scanned / enabled configured sources"
    if not configured:
        return _metric("coverage", "Index coverage", None, None, formula,
                       "config.connectors + scan_log", observed_at,
                       "A configured source counts only when the latest completed scan names it and has no scan errors.",
                       unmeasured="No enabled connectors are configured.")
    if not _table(conn, "scan_log"):
        return _metric("coverage", "Index coverage", None, len(configured), formula,
                       "config.connectors + scan_log", observed_at,
                       "A configured source counts only when the latest completed scan names it and has no scan errors.",
                       unmeasured="No scan history exists.")
    rows = conn.execute(
        "SELECT completed_at, connectors_used, errors FROM scan_log "
        "WHERE completed_at IS NOT NULL ORDER BY completed_at"
    ).fetchall()
    points = []
    for row in rows:
        used = set(_json_list(row["connectors_used"]))
        errors = _json_list(row["errors"])
        successful = len(set(configured) & used) if not errors else 0
        points.append(_point(row["completed_at"], successful, len(configured)))
    if not rows:
        return _metric("coverage", "Index coverage", None, len(configured), formula,
                       "config.connectors + scan_log", observed_at,
                       "A configured source counts only when the latest completed scan names it and has no scan errors.",
                       unmeasured="No completed scan exists.")
    latest = rows[-1]
    errors = _json_list(latest["errors"])
    used = set(_json_list(latest["connectors_used"]))
    if errors:
        return _metric("coverage", "Index coverage", None, len(configured), formula,
                       "config.connectors + scan_log", latest["completed_at"],
                       "The scan records errors as one list, not per connector, so partial success cannot be assigned safely.",
                       points=points, unmeasured="The latest completed scan recorded errors.")
    return _metric(
        "coverage", "Index coverage", len(set(configured) & used), len(configured),
        formula, "config.connectors + latest completed scan_log row",
        latest["completed_at"],
        "This proves the connector participated in one completed error-free scan, not raw-source completeness.",
        points=points,
    )


def _retrieval(conn: sqlite3.Connection, observed_at: str, now: datetime) -> dict:
    formula = "labeled queries with an inspectable expected hit in top 3 / labeled queries"
    if not _table(conn, "eval_runs"):
        return _metric("retrieval", "Retrieval evidence", None, None, formula,
                       "eval_runs.details", observed_at,
                       "Only fixed labeled queries count; retrieval_log activity is not relevance evidence.",
                       unmeasured="No retrieval evaluation table exists.")
    rows = conn.execute(
        "SELECT run_at, query_count, details FROM eval_runs ORDER BY run_at"
    ).fetchall()
    points, latest = [], None
    for row in rows:
        try:
            detail = json.loads(row["details"] or "{}")
            cases = detail.get("retrieval", [])
        except (ValueError, AttributeError):
            cases = []
        denominator = len(cases) or int(row["query_count"] or 0)
        numerator = sum(
            1 for case in cases
            if isinstance(case, dict) and isinstance(case.get("found_at_rank"), int)
            and case["found_at_rank"] <= 3
        )
        if denominator:
            point = _point(row["run_at"], numerator, denominator)
            points.append(point)
            latest = (row, numerator, denominator)
    if latest is None:
        return _metric("retrieval", "Retrieval evidence", None, None, formula,
                       "eval_runs.details", observed_at,
                       "Only fixed labeled queries count; retrieval_log activity is not relevance evidence.",
                       points=points, unmeasured="No evaluation contains inspectable labeled cases.")
    row, numerator, denominator = latest
    age = now.replace(tzinfo=None) - (_stamp(row["run_at"]) or datetime.min)
    if age > timedelta(days=30):
        return _metric(
            "retrieval", "Retrieval evidence", None, denominator, formula,
            "latest eval_runs.details", row["run_at"],
            "The last labeled evaluation is older than 30 days; old evidence is shown only in the timeline.",
            points=points,
            unmeasured=f"No labeled retrieval evaluation in the last 30 days; latest is {row['run_at'][:10]}.",
        )
    return _metric(
        "retrieval", "Retrieval evidence", numerator, denominator, formula,
        "latest eval_runs.details", row["run_at"],
        "Expected-hit evidence at rank 1-3; it does not measure benefit to a completed task.",
        points=points,
    )


def _drift(conn: sqlite3.Connection, observed_at: str, now: datetime) -> dict:
    formula = "conflict detections with a canonical resolved value / conflict detections"
    if not _table(conn, "audit_log"):
        return _metric("drift", "Drift resolved", None, None, formula,
                       "audit_log", observed_at,
                       "Dismissed false positives remain in the detection denominator; only resolved:<value> establishes a canonical fact.",
                       unmeasured="No audit history exists.")
    marks = ",".join("?" for _ in CONFLICT_TYPES)
    rows = conn.execute(
        f"SELECT audited_at, resolved_at, human_decision FROM audit_log "
        f"WHERE audit_type IN ({marks}) ORDER BY audited_at", CONFLICT_TYPES
    ).fetchall()
    if not rows:
        return _metric("drift", "Drift resolved", None, None, formula,
                       "audit_log", observed_at,
                       "Dismissed false positives remain in the detection denominator; only resolved:<value> establishes a canonical fact.",
                       unmeasured="No conflict detections exist.")
    resolved = sum(1 for row in rows if (row["human_decision"] or "").startswith("resolved:"))
    points = []
    for days in (30, 14, 7, 0):
        cutoff = now.replace(tzinfo=None) - timedelta(days=days)
        detected_at_cutoff = [row for row in rows if (_stamp(row["audited_at"]) or datetime.max) <= cutoff]
        fixed_at_cutoff = sum(
            1 for row in detected_at_cutoff
            if (row["human_decision"] or "").startswith("resolved:")
            and (_stamp(row["resolved_at"]) or datetime.max) <= cutoff
        )
        points.append(_point(cutoff.isoformat(), fixed_at_cutoff, len(detected_at_cutoff)))
    return _metric(
        "drift", "Drift resolved", resolved, len(rows), formula,
        "audit_log audited_at + resolved_at + human_decision", observed_at,
        "The denominator is detections, not confirmed defects. Dismissals stay visible so detector noise cannot improve the score silently.",
        points=points,
    )


def _compiled_rules(path: Path) -> list[str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    sources = []
    pending = False
    for raw in lines:
        line = raw.strip()
        if line.startswith("- "):
            if pending:
                sources.append("")
            pending = True
        elif pending and line.startswith("_[") and line.endswith("]_"):
            sources.append(line[2:-2])
            pending = False
    if pending:
        sources.append("")
    return sources


def _rules(conn: sqlite3.Connection, cfg: dict, cfg_path: Path,
           db_path: Path, observed_at: str, home: Path) -> dict:
    formula = "compiled rules whose source still exists and was checked / compiled rules"
    gold = db_path.parent / "GOLDEN_RULES.md"
    sources = _compiled_rules(gold)
    if not sources:
        return _metric("rules", "Rule source integrity", None, None, formula,
                       str(gold), observed_at,
                       "Each compiled provenance reference is checked against its row or source file on this read.",
                       unmeasured="No compiled rulebook with provenance was found.")
    memory_roots = []
    for connector in cfg.get("connectors", {}).values():
        if isinstance(connector, dict) and connector.get("memory_dir"):
            memory_roots.append(Path(connector["memory_dir"]).expanduser())
    memory_roots += [p for p in (home / ".codex/memories",) if p.exists()]
    filenames = set()
    for root in memory_roots:
        if root.is_dir():
            filenames.update(p.name for p in root.rglob("*.md"))

    existing = 0
    unknown = 0
    for source in sources:
        found = False
        match = re.search(r"alias #(\d+)", source)
        if match and _table(conn, "entity_aliases"):
            found = conn.execute("SELECT 1 FROM entity_aliases WHERE id=?", (int(match.group(1)),)).fetchone() is not None
        else:
            match = re.search(r"rule #(\d+)", source)
            if match and _table(conn, "rules"):
                found = conn.execute("SELECT 1 FROM rules WHERE id=?", (int(match.group(1)),)).fetchone() is not None
            else:
                match = re.search(r"finding #(\d+)", source)
                if match and _table(conn, "audit_log"):
                    found = conn.execute("SELECT 1 FROM audit_log WHERE id=?", (int(match.group(1)),)).fetchone() is not None
                elif source.endswith(".md"):
                    found = Path(source).expanduser().exists() or Path(source).name in filenames
                elif "config.json" in source:
                    found = cfg_path.exists()
                else:
                    unknown += 1
        existing += int(found)
    return _metric(
        "rules", "Rule source integrity", existing, len(sources), formula,
        f"{gold}; SQLite source rows; configured memory roots", observed_at,
        f"This checks source existence, not whether the rule is still useful. {unknown} provenance references could not be mapped to a check.",
    )


def _inventory(home: Path, cfg: dict, db_path: Path, audit: dict,
               conn: sqlite3.Connection | None) -> dict:
    index_files = []
    trace = home / ".trace/trace.db"
    if trace.is_file():
        index_files.append({"name": "Conversation index", "path": str(trace), "bytes": trace.stat().st_size})
    for item in audit.get("memory_indexes", []):
        path = Path(item["path"])
        index_files.append({"name": path.name, "path": str(path), "files": item["files"]})
    configured_index = cfg.get("index")
    if configured_index:
        path = Path(configured_index).expanduser()
        index_files.append({"name": "Configured index", "path": str(path), "bytes": path.stat().st_size if path.is_file() else None})

    hook_counts = {}
    for hook in audit.get("hooks", []):
        event = hook.get("event") or "unknown"
        hook_counts[event] = hook_counts.get(event, 0) + 1
    routes = [{"name": name, "count": count, "kind": "hook"}
              for name, count in sorted(hook_counts.items())]
    routes += [{"name": name, "count": 1, "kind": "source"}
               for name, value in sorted(cfg.get("connectors", {}).items())
               if isinstance(value, dict) and value.get("enabled")]

    live = None
    if conn is not None and _table(conn, "helicon_cubes"):
        live = conn.execute("SELECT COUNT(*) FROM helicon_cubes WHERE " + LIVE).fetchone()[0]
    stores = []
    if db_path.is_file():
        stores.append({"name": "Helicon memory", "path": str(db_path),
                       "bytes": db_path.stat().st_size, "records": live})
    return {
        "harnesses": audit.get("coverage", {}).get("harnesses", []),
        "index_files": index_files,
        "routes": routes,
        "stores": stores,
    }


def build_overview(home=None, project=None, previous=None, config_path=None,
                   now: datetime | None = None) -> dict:
    home = Path(home or Path.home()).resolve()
    project = Path(project or Path.cwd()).resolve()
    now = now or datetime.now(timezone.utc)
    observed_at = now.isoformat()
    cfg_path = Path(config_path or config_file()).expanduser().resolve()
    try:
        cfg = load_config(str(cfg_path))
    except (OSError, ValueError):
        cfg = {}
    db_path = Path(cfg.get("db_path", home / ".helicon/helicon.db")).expanduser().resolve()
    conn = None
    if db_path.is_file():
        conn = sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
    audit = audit_setup(home=home, project=project)
    enabled = sorted(
        name for name, value in cfg.get("connectors", {}).items()
        if isinstance(value, dict) and value.get("enabled")
    )
    if conn is None:
        absent = lambda key, label, formula: _metric(
            key, label, None, None, formula, str(db_path), observed_at,
            "No substitute value is shown.", unmeasured="The configured memory store is unavailable."
        )
        metrics = [
            absent("freshness", "Context freshness", "current / applicable indexed records"),
            absent("coverage", "Index coverage", "successfully scanned / configured sources"),
            absent("retrieval", "Retrieval evidence", "cited labeled hits / labeled queries"),
            absent("drift", "Drift resolved", "canonical resolutions / conflict detections"),
            absent("rules", "Rule source integrity", "checked existing sources / compiled rules"),
        ]
    else:
        try:
            metrics = [
                _freshness(conn, observed_at, now),
                _coverage(conn, enabled, observed_at),
                _retrieval(conn, observed_at, now),
                _drift(conn, observed_at, now),
                _rules(conn, cfg, cfg_path, db_path, observed_at, home),
            ]
        finally:
            pass
    setup = setup_status(home=home, project=project, previous=previous,
                         observed_at=observed_at)
    unresolved = {"total": None, "critical": None, "source": "audit_log"}
    if conn is not None and _table(conn, "audit_log"):
        row = conn.execute(
            "SELECT COUNT(*) total, SUM(CASE WHEN severity='critical' THEN 1 ELSE 0 END) critical "
            "FROM audit_log WHERE human_decision IS NULL AND machine_decision IS NULL"
        ).fetchone()
        unresolved = {"total": row["total"], "critical": row["critical"] or 0,
                      "source": "unresolved audit_log rows; computed findings are not included"}
    result = {
        "schema": SCHEMA,
        "observed_at": observed_at,
        "metrics": metrics,
        "setup_drift": setup["comparison"],
        "unresolved": unresolved,
        "inventory": _inventory(home, cfg, db_path, audit, conn),
    }
    if conn is not None:
        conn.close()
    return result


def render_overview(report: dict) -> str:
    lines = ["AGENT SETUP OVERVIEW", "No overall score; every meter keeps its own denominator."]
    for metric in report["metrics"]:
        value = f"{metric['value']:.1f}% ({metric['numerator']}/{metric['denominator']})" if metric["state"] == "measured" else "unmeasured"
        lines.append(f"{metric['label']}: {value}")
    lines.append("Setup drift: " + report["setup_drift"]["status"])
    return "\n".join(lines)
