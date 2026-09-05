"""Local, project-scoped review operations. Context is data, never a command.

This surface deliberately has a stricter boundary than older dashboard routes:
only same-origin loopback callers with an explicit header can use it. Writable
roots come from local configuration, never from a submitted source path.
"""
from pathlib import Path
from urllib.parse import urlsplit
import hashlib
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from helicon.config import helicon_home


def get_config():
    from helicon.api.app import get_config as current_config
    return current_config()


def local_request(request: Request):
    authority = request.headers.get("host", "")
    try:
        parsed = urlsplit("http://" + authority)
        host = parsed.hostname
        if parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
            raise ValueError("Invalid authority")
        _ = parsed.port
    except ValueError:
        raise HTTPException(403, "Invalid local review address.")
    if host not in ("localhost", "127.0.0.1", "::1"):
        raise HTTPException(403, "Context review is available on loopback only.")
    if request.headers.get("x-helicon-local") != "1":
        raise HTTPException(403, "An explicit local review request is required.")
    origin = request.headers.get("origin")
    if origin and origin != f"{request.url.scheme}://{authority}":
        raise HTTPException(403, "Cross-origin context access is not allowed.")


router = APIRouter(dependencies=[Depends(local_request)])


def projects():
    configured = (get_config() or {}).get("context_review", {}).get("projects")
    if configured is None:
        configured = [{"id": "current", "name": "Current project", "path": str(Path.cwd())}]
    if not isinstance(configured, list):
        raise HTTPException(503, "Project review configuration is invalid.")
    result = []
    for item in configured:
        if not isinstance(item, dict) or not all(isinstance(item.get(k), str) and item[k] for k in ("id", "path")):
            raise HTTPException(503, "Project review configuration is invalid.")
        path = Path(item["path"]).expanduser().resolve()
        if path == Path(path.anchor) or path == Path.home():
            raise HTTPException(503, "Choose a project folder, not the home or filesystem root.")
        result.append({"id": item["id"], "name": item.get("name", path.name), "path": str(path)})
    if len({p["id"] for p in result}) != len(result):
        raise HTTPException(503, "Project review IDs must be unique.")
    return result


def project_scope(project_id):
    project = next((p for p in projects() if p["id"] == project_id), None)
    if project is None:
        raise HTTPException(404, "Project is not configured for review.")
    identity = hashlib.sha256(project["path"].encode()).hexdigest()[:24]
    return project, Path(helicon_home()) / "context-review" / identity


@router.get("/context-review/projects")
def list_projects():
    return {"projects": projects(), "limit": "Project files can be corrected after review. Global instructions are read-only here. Files found on disk are not proof they were loaded."}


class ProjectRequest(BaseModel):
    project_id: str


class SaveRequest(ProjectRequest):
    revision: str


class PreviewRequest(ProjectRequest):
    snapshot_id: str
    finding_id: str
    evidence_index: int = Field(ge=0)
    replacement: str = Field(max_length=100000)
    reason: str = Field(min_length=1, max_length=4000)


class ApplyRequest(ProjectRequest):
    preview_id: str
    preview_hash: str


class UndoRequest(ProjectRequest):
    correction_id: str


class CompareRequest(ProjectRequest):
    baseline_id: str


class PacketRequest(ProjectRequest):
    snapshot_id: str
    source_ids: list[str] = Field(min_length=1, max_length=30)
    run_id: str = Field(min_length=1, max_length=200)
    provider: str = Field(min_length=1, max_length=100)


def packets(project_id):
    from helicon.context_packet import ContextPackets
    project, state = project_scope(project_id)
    return project, ContextPackets(state / "packets", state / "reviews")


@router.post("/context-review/packets")
def prepare_packet(req: PacketRequest):
    project, store = packets(req.project_id)
    try:
        packet = store.create(req.snapshot_id, req.source_ids,
                              {"run_id": req.run_id, "provider": req.provider, "project": project["path"]})
        return store.inspect(packet["id"], packet["recipient"])
    except (ValueError, OSError) as exc:
        failed(exc)


@router.get("/context-review/packets")
def list_packets(project_id: str):
    project, store = packets(project_id)
    try:
        rows = store.list(project=project["path"])
        return {"packets": [row for row in rows if row.get("state") != "unavailable"],
                "errors": [row.get("error", "A packet record is unavailable.") for row in rows if row.get("state") == "unavailable"]}
    except (ValueError, OSError) as exc:
        failed(exc)


def review_revision(report):
    def stable(value):
        if isinstance(value, dict):
            return {k: stable(v) for k, v in value.items() if k not in ("observed_at", "read_at")}
        if isinstance(value, list):
            return [stable(v) for v in value]
        return value
    return hashlib.sha256(json.dumps(stable(report), sort_keys=True).encode()).hexdigest()


def read_report(project_id):
    from helicon.context_review import context_review
    project, _ = project_scope(project_id)
    cfg = (get_config() or {}).get("context_review", {})
    # Optional home is local config only, used by isolated demonstrations/tests.
    return context_review(home=cfg.get("home"), project=project["path"])


def stores(project_id):
    from helicon.context_corrections import CorrectionStore
    from helicon.context_history import ContextHistory
    project, state = project_scope(project_id)
    return ContextHistory(state / "reviews"), CorrectionStore(state / "corrections", [project["path"]])


def failed(exc):
    # Never turn an uncertain source write into a success receipt.
    raise HTTPException(409, str(exc)) from exc


@router.post("/context-review/read")
def read_context(req: ProjectRequest):
    report = read_report(req.project_id)
    return {"report": report, "revision": review_revision(report)}


@router.post("/context-review/snapshots")
def save_context(req: SaveRequest):
    report = read_report(req.project_id)
    if review_revision(report) != req.revision:
        raise HTTPException(409, "The source or object evidence changed. Review sources again before saving.")
    history, _ = stores(req.project_id)
    try:
        saved = history.save(report)
        return {"id": saved["id"]}
    except (ValueError, OSError) as exc:
        failed(exc)


@router.post("/context-review/preview")
def preview_context(req: PreviewRequest):
    history, corrections = stores(req.project_id)
    try:
        saved = history.load(req.snapshot_id)
        report = saved["review"]
        finding = next((f for f in report["findings"] if f["id"] == req.finding_id), None)
        if finding is None or req.evidence_index >= len(finding["evidence"]):
            raise ValueError("The selected evidence does not belong to this saved review.")
        span = finding["evidence"][req.evidence_index]
        if not req.reason.strip():
            raise ValueError("Record why this correction is justified.")
        preview = corrections.preview(
            path=span["path"], source_hash=span["sha256"],
            start_byte=span["start_byte"], end_byte=span["end_byte"],
            expected_text=span["quote"], replacement=req.replacement,
            actor="local-reviewer", reason=req.reason, finding_id=req.finding_id,
        )
        return {"id": preview["preview_id"], "hash": preview["preview_hash"], "diff": preview["diff"]}
    except (ValueError, OSError, KeyError) as exc:
        failed(exc)


@router.post("/context-review/apply")
def apply_context(req: ApplyRequest):
    _, corrections = stores(req.project_id)
    try:
        return corrections.apply(req.preview_id, req.preview_hash, "local-reviewer")
    except (ValueError, OSError) as exc:
        failed(exc)


@router.post("/context-review/undo")
def undo_context(req: UndoRequest):
    _, corrections = stores(req.project_id)
    try:
        return corrections.undo(req.correction_id, "local-reviewer")
    except (ValueError, OSError) as exc:
        failed(exc)


@router.get("/context-review/history")
def context_history(project_id: str):
    project, _ = project_scope(project_id)
    history, corrections = stores(project_id)
    try:
        rows = history.list(project=project["path"])
        return {"snapshots": [{"id": row["id"], "observed_at": row["review"]["observed_at"], "findings": len(row["review"]["findings"])} for row in rows],
                "corrections": corrections.history()}
    except (ValueError, OSError) as exc:
        failed(exc)


@router.post("/context-review/compare")
def compare_context(req: CompareRequest):
    report = read_report(req.project_id)
    history, _ = stores(req.project_id)
    try:
        previous = history.list(project=report["project"])
        comparison = history.compare(req.baseline_id, report, history_ids=[s["id"] for s in previous if s["id"] != req.baseline_id])
        return {"groups": [{"label": label, "items": [
            {"id": row["finding_id"], "title": row["finding"]["title"],
             "reason": row.get("reason", "Checks could not establish whether this still holds." if key == "unchecked" else "")}
            for row in comparison[key]]}
            for key, label in [("new", "New"), ("resolved", "Resolved by the checks run"), ("recurring", "Returned after an earlier clear check"), ("persisting", "Still present"), ("unchecked", "Not checked this time")]],
                "evidence": comparison}
    except (ValueError, OSError) as exc:
        failed(exc)
