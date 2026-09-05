"""Local, read-only context review. Discovery is carried in from setup_audit.

This is deliberately not a general truth classifier. Only explicit file claims
and exact scalar declarations are checked. Instructions and receipts are data;
neither can cause a command to execute. Findings describe source disagreement,
not which source wins, and never prove model delivery or improved work.
"""
import ast
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .setup_audit import audit_setup

SCHEMA = "helicon.context-review/1"
MAX_BYTES = 2_000_000  # Read bound, not a quality threshold.


def _id(*parts):
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()[:24]


def _read(path):
    try:
        before = path.stat()
        if not path.is_file() or before.st_size > MAX_BYTES:
            return "unreadable", None, None
        data = path.read_bytes()
        after = path.stat()
        if (before.st_dev, before.st_ino, before.st_mtime_ns, before.st_size) != (after.st_dev, after.st_ino, after.st_mtime_ns, after.st_size):
            return "changed", None, None
        if len(data) > MAX_BYTES:
            return "unreadable", None, None
        data.decode("utf-8")
        return "available" if data else "empty", data, after
    except FileNotFoundError:
        return "missing", None, None
    except (OSError, UnicodeError):
        return "unreadable", None, None


def _evidence(source, line, number, offset):
    return dict(source_id=source["id"], path=source["path"], sha256=source["sha256"],
                line_start=number, line_end=number, start_byte=offset,
                end_byte=offset + len(line.encode("utf-8")), quote=line)


def _lines(data):
    """Exact original lines, excluding fenced examples and historical sections."""
    offset, fence, excluded = 0, None, None
    for number, line in enumerate(data.decode("utf-8").splitlines(keepends=True), 1):
        clean = line.strip()
        mark = re.match(r"^(`{3,}|~{3,})", clean)
        heading = re.match(r"^(#{1,6})\s+(.*)", clean)
        if mark:
            token = mark[1][0]
            fence = None if fence == token else token if fence is None else fence
        elif not fence:
            if heading:
                level = len(heading[1])
                if excluded is not None and level <= excluded:
                    excluded = None
                if re.search(r"\b(history|historical|example|examples|baseline|receipts?)\b", heading[2], re.I):
                    excluded = level
            elif excluded is None and not clean.startswith(">") and not re.search(
                    r"\b(example|previously|formerly|used to|was|were|deleted|removed|if|might|would|should|will|planned|do not read|never read)\b", clean, re.I):
                yield number, line, offset
        offset += len(line.encode("utf-8"))


def _claims(source, data, project, home):
    for number, line, offset in _lines(data):
        text = re.sub(r"^\s*[-*]\s+", "", line.strip())
        evidence = _evidence(source, line, number, offset)
        # A literal loader pointer remains useful even when delivery is unknown.
        # Resolve home explicitly against the reviewed home, not this process's.
        pointers = [] if re.search(r"\b(is missing|does not exist|no longer)\b", text) else re.findall(r"`(~/[^`]+)`", text)
        for raw in pointers:
            yield dict(subject=str((home / raw[2:]).resolve()), predicate="reference", value=True, evidence=evidence)
        if source["stage"] == "project instruction candidate":
            count = re.match(r"^MCP Server \((\d+) tools\b", text)
            if count:
                yield dict(subject=str(project / "helicon/mcp_server.py"), predicate="static-mcp-tools",
                           value=int(count[1]), evidence=evidence)
        # Explicit scalar assertions, not a bag of nearby names and values.
        scalar = re.fullmatch(r"(?:\*\*)?([\w][\w ./-]{0,100}?) (phase|version|status)(?:\*\*)?\s*(?:=|:|is)\s*`?([\w][\w .+-]{0,60}?)`?\.?", text)
        if scalar and not re.search(r"\b\d{4}-\d{2}-\d{2}\b", text):
            yield dict(subject=scalar[1].strip(), predicate=scalar[2], value=scalar[3].rstrip("."), evidence=evidence)
        # Current explicit path assertions only: no bare mention, command, link,
        # future instruction or basename search. Relative paths bind to project.
        path = re.fullmatch(r"(?:File |Directory )?`([^`]+)` (exists|is present|is missing|does not exist)\.?", text)
        if path:
            raw = path[1]
            if raw.startswith("~/") or (source["stage"] == "global instruction candidate" and not Path(raw).is_absolute()):
                continue
            target = (project / raw).resolve() if not Path(raw).is_absolute() else Path(raw).resolve()
            yield dict(subject=str(target), predicate="exists", value=path[2] in ("exists", "is present"), evidence=evidence)
        # Common instruction form: read an exact local file. An unavailable
        # reference blocks the instruction; it does not prove the fact is false.
        read = re.fullmatch(r"(?:Read|See|Source:)\s+`([^`]+)`\.?", text)
        if read:
            raw = read[1]
            if raw.startswith("~/") or (source["stage"] == "global instruction candidate" and not Path(raw).is_absolute()):
                continue
            target = (project / raw).resolve() if not Path(raw).is_absolute() else Path(raw).resolve()
            yield dict(subject=str(target), predicate="reference", value=True, evidence=evidence)


def _receipt_valid(receipt, source, project, now):
    if not isinstance(receipt, dict):
        return False
    try:
        stamp = datetime.fromisoformat(receipt.get("observed_at", "").replace("Z", "+00:00"))
        return (receipt.get("schema") == "helicon.context-loading-receipt/1"
                and receipt.get("project") == str(project)
                and receipt.get("harness") == source["harness"]
                and receipt.get("path") == source["path"]
                and source["sha256"] is not None
                and receipt.get("sha256") == source["sha256"]
                and isinstance(receipt.get("run_id"), str) and bool(receipt["run_id"].strip())
                and receipt.get("event") == "context_loaded"
                and stamp.tzinfo is not None and stamp <= now)
    except (ValueError, TypeError, AttributeError):
        return False


def _exists(path):
    try:
        path.stat()
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return None


def context_review(home=None, project=None, receipts=None):
    home, project = Path(home or Path.home()).resolve(), Path(project or Path.cwd()).resolve()
    now = datetime.now(timezone.utc)
    audit = audit_setup(home, project)
    rows = audit["files"] + [dict(r, stage="skill candidate; activation unknown") for r in audit["skills"]]
    # Missing conventional entry points remain visible, not silently clean.
    for harness, path in (("claude", home / ".claude/CLAUDE.md"),
                          ("codex", home / ".codex/AGENTS.md"),
                          ("claude", project / "CLAUDE.md"),
                          ("codex", project / "AGENTS.md"),
                          ("cursor", project / ".cursorrules")):
        if not any(r["path"] == str(path) and r["harness"] == harness for r in rows):
            rows.append(dict(path=str(path), harness=harness, stage="conventional entry point; not configured"))
    sources, claims, findings, checks = [], [], [], []
    seen = set()
    for row in rows:
        sid = _id(row["path"], row["harness"])
        if sid in seen:
            continue
        seen.add(sid)
        status, data, stat = _read(Path(row["path"]))
        sha = hashlib.sha256(data).hexdigest() if data is not None else None
        stage = row["stage"]
        source = dict(id=sid, path=row["path"], harness=row["harness"], stage=stage,
                      status=status, sha256=sha, bytes=len(data) if data is not None else None,
                      mtime=datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat() if stat else None,
                      configuration=dict(state="configured" if stage.startswith(("hook script", "post-compaction")) else "candidate",
                                         basis=stage),
                      loading=dict(state="unknown", receipts=[], basis="No matching external runtime receipt supplied."), checks_completed=[])
        matched = [r for r in (receipts if isinstance(receipts, list) else []) if _receipt_valid(r, source, project, now)]
        if matched:
            source["loading"] = dict(state="observed", receipts=matched,
                                     basis="Supplied external receipt; not independently observed by this review.")
        sources.append(source)
        key = "source-read:" + sid
        checks.append(dict(id=key, version="1", status="success" if data is not None else "unknown", source_ids=[sid]))
        if data is not None:
            source["checks_completed"].append(key)
        # Conditional rules, skills, foreign memory and hook bodies are indexed,
        # not conflated with this project's unconditional instruction assertions.
        if data is not None and stage in ("project instruction candidate", "global instruction candidate"):
            for claim in _claims(source, data, project, home):
                claim["id"] = _id(sid, claim["subject"], claim["predicate"], claim["evidence"]["start_byte"])
                claim["harness"] = source["harness"]
                claims.append(claim)

    def finding(kind, subject, predicate, evidence, check, title, consequence, action, probe=None):
        harness = next(s["harness"] for s in sources if s["id"] == evidence[0]["source_id"])
        findings.append(dict(id=_id(kind, subject, predicate, sorted(set(e["source_id"] for e in evidence))),
                             subject=subject, predicate=predicate, harnesses=[harness],
                             kind=kind, title=title, consequence=consequence, action=action,
                             check_id="instruction-claims:" + harness, probe_check_id=check, evidence=evidence,
                             evidence_revision=_id([(e["source_id"], e["sha256"], e["start_byte"], e["end_byte"]) for e in evidence]),
                             probe=probe))

    groups, path_observations = {}, []
    for claim in claims:
        groups.setdefault((claim["harness"], claim["subject"], claim["predicate"]), []).append(claim)
    for (harness, subject, predicate), group in groups.items():
        ids = sorted(set(c["evidence"]["source_id"] for c in group))
        key = "claim:" + _id(harness, subject, predicate)
        check = dict(id=key, version="1", status="success", source_ids=ids)
        checks.append(check)
        if predicate in ("exists", "reference"):
            target = Path(subject)
            # No traversal out of the selected project; existence elsewhere is
            # not evidence about the intended project object.
            scoped = target.is_relative_to(project) or (predicate == "reference" and target.is_relative_to(home))
            exists = _exists(target) if scoped else None
            if scoped:
                path_observations.append((key, target, exists))
            if exists is None:
                check["status"] = "unknown"
            for claim in group:
                verdict = "unknown" if exists is None else "upheld" if exists == claim["value"] else "contradicted"
                probe = dict(object=subject, command=None, operation="filesystem.exists (exact scoped path)",
                             observed_at=now.isoformat(), verdict=verdict, output=dict(exists=exists))
                claim["probe"] = probe
                if verdict != "upheld":
                    finding("unavailable-reference" if predicate == "reference" else "path-claim", subject, predicate,
                            [claim["evidence"]], key, "Local file claim needs review", "An agent may follow a reference that cannot be confirmed.",
                            "Check this exact path and correct the source text.", probe)
        elif predicate == "static-mcp-tools":
            target = Path(subject)
            status, data, stat = _read(target)
            object_id = _id(subject, "local-probe")
            object_sha = hashlib.sha256(data).hexdigest() if data is not None else None
            if not any(s["id"] == object_id for s in sources):
                sources.append(dict(id=object_id, path=subject, harness="local-probe", stage="exact static probe object",
                                    status=status, sha256=object_sha, bytes=len(data) if data is not None else None,
                                    mtime=datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat() if stat else None,
                                    configuration=dict(state="candidate", basis="Exact project-relative probe target"),
                                    loading=dict(state="unknown", receipts=[], basis="Not a context delivery claim"), checks_completed=[]))
            check["source_ids"] = sorted(ids + [object_id])
            observed = None
            try:
                tree = ast.parse(data.decode("utf-8")) if data is not None else None
                assignments = [n for n in tree.body if isinstance(n, ast.Assign)
                               and any(isinstance(t, ast.Name) and t.id == "TOOLS" for t in n.targets)] if tree else []
                if len(assignments) == 1:
                    values = ast.literal_eval(assignments[0].value)
                    mutated = any((isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                                   and isinstance(n.func.value, ast.Name) and n.func.value.id == "TOOLS"
                                   and n.func.attr in ("append", "extend", "insert", "clear", "pop", "remove"))
                                  or (isinstance(n, ast.AugAssign) and isinstance(n.target, ast.Name) and n.target.id == "TOOLS")
                                  for n in ast.walk(tree))
                    if (not mutated and isinstance(values, list)
                            and all(isinstance(v, dict) and isinstance(v.get("name"), str) for v in values)
                            and len({v["name"] for v in values}) == len(values)):
                        observed = len(values)
            except (ValueError, SyntaxError, TypeError, RecursionError):
                pass
            if observed is None:
                check["status"] = "unknown"
            for claim in group:
                verdict = "unknown" if observed is None else "upheld" if observed == claim["value"] else "contradicted"
                probe = dict(object=subject, sha256=object_sha, command=None, operation="AST literal TOOLS declaration count; not runtime availability",
                             observed_at=now.isoformat(), verdict=verdict, output=dict(declared_tools=observed))
                claim["probe"] = probe
                if verdict != "upheld":
                    finding("static-tool-count", subject, predicate, [claim["evidence"]], key,
                            "MCP tool declaration needs review", "The instruction count is not supported by the exact static tool declaration.",
                            "Check the declared tool list and update the instruction; runtime exposure remains unmeasured.", probe)
        elif len(set(c["value"] for c in group)) > 1:
            finding("source-disagreement", subject, predicate, [c["evidence"] for c in group], key,
                    f"Sources disagree about {subject} {predicate}",
                    "The same harness has incompatible explicit declarations; no source was selected as truth.",
                    "Choose the current declaration and correct the outdated source.")
        for source in sources:
            if source["id"] in ids and check["status"] == "success":
                source["checks_completed"].append(key)

    # Re-read source versions after probing; never return a mixed-version finding.
    changed = set()
    for source in sources:
        status, data, _ = _read(Path(source["path"]))
        sha = hashlib.sha256(data).hexdigest() if data is not None else None
        if status != source["status"] or sha != source["sha256"]:
            changed.add(source["id"])
            source.update(status="changed", sha256=None, checks_completed=[])
            source["loading"] = dict(state="unknown", receipts=[], basis="Source changed during review.")
    unstable_checks = {key for key, target, observed in path_observations if _exists(target) != observed}
    if changed or unstable_checks:
        unstable_checks.update(c["id"] for c in checks if changed.intersection(c["source_ids"]))
        findings = [f for f in findings if f["probe_check_id"] not in unstable_checks]
        claims = [c for c in claims if c["evidence"]["source_id"] not in changed]
        for claim in claims:
            if "probe" in claim and "claim:" + _id(claim["harness"], claim["subject"], claim["predicate"]) in unstable_checks:
                claim["probe"].update(verdict="unknown", output={"reason": "Object changed during review"})
        for check in checks:
            if check["id"] in unstable_checks:
                check["status"] = "unknown"
        for source in sources:
            source["checks_completed"] = [key for key in source["checks_completed"] if key not in unstable_checks]
    # Stable extractor population permits a deleted obsolete claim to resolve.
    # Unreadable input or an unknown probe makes absence insufficient evidence.
    for harness in ("claude", "codex", "cursor"):
        population = [s for s in sources if s["harness"] == harness and
                      (s["stage"] in ("project instruction candidate", "global instruction candidate")
                       or s["stage"].startswith("conventional entry point"))]
        ids = sorted(s["id"] for s in population)
        complete = all(s["status"] in ("available", "empty", "missing") for s in population)
        complete = complete and not any(c["status"] != "success" and c["id"].startswith("claim:")
                                        and set(ids).intersection(c["source_ids"]) for c in checks)
        key = "instruction-claims:" + harness
        checks.append(dict(id=key, version="1", status="success" if complete else "unknown", source_ids=ids))
        if complete:
            for source in population:
                source["checks_completed"].append(key)
    for source in sources:
        source["type"] = "probe-object" if source["harness"] == "local-probe" else "context-source"
    # One human issue can have several harness candidate routes. Keep all check
    # dependencies, but show each physical source span only once.
    consolidated = {}
    for item in findings:
        evidence = {}
        for span in item["evidence"]:
            evidence[(span["path"], span["sha256"], span["start_byte"], span["end_byte"])] = span
        signature = (item["kind"], item["subject"], item["predicate"], tuple(sorted(evidence)))
        if signature not in consolidated:
            item["id"] = _id(item["kind"], item["subject"], item["predicate"], sorted(set(e[0] for e in evidence)))
            item["evidence"] = list(evidence.values())
            item["check_ids"] = [item["check_id"]]
            item["probe_check_ids"] = [item["probe_check_id"]]
            item["evidence_revision"] = _id(sorted(evidence))
            consolidated[signature] = item
        else:
            previous = consolidated[signature]
            previous["harnesses"] = sorted(set(previous["harnesses"] + item["harnesses"]))
            previous["check_ids"] = sorted(set(previous["check_ids"] + [item["check_id"]]))
            previous["probe_check_ids"] = sorted(set(previous["probe_check_ids"] + [item["probe_check_id"]]))
    findings = list(consolidated.values())
    return dict(schema=SCHEMA, project=str(project), observed_at=now.isoformat(), sources=sources,
                claims=claims, findings=findings,
                coverage=dict(checks=checks, scope="Local source text; no model or shell execution.",
                              not_observed=["effective context without external receipt", "agent compliance", "memory usefulness",
                                            "conditional rule applicability", "free-form factual claims", "remote outcomes"],
                              carried_in="setup_audit discovery at baseline 4556ccf"))
