"""Project-scoped local context delivery, separate from behavior verification.

TaskRun's existing context packets freeze retrieved memories. These packets
instead reference a saved source review and an explicitly selected recipient.
No model, shell, remote provider, redaction or automatic compliance judge runs.
Content remains local, including any sensitive text selected by the operator.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from helicon.context_history import ContextHistory, HistoryError, read_source_bytes


class PacketError(ValueError):
    pass


_HASH = re.compile(r"[0-9a-f]{64}\Z")
MAX_PACKET_BYTES = 128 * 1024


def _encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _now():
    return datetime.now(timezone.utc).isoformat()


def _file_bytes(path, limit=4 * 1024 * 1024):
    try:
        return read_source_bytes(path, limit)
    except HistoryError as exc:
        raise PacketError(str(exc)) from exc


def _identifier(value):
    if not isinstance(value, str) or not _HASH.fullmatch(value):
        raise PacketError("Invalid packet or receipt ID")
    return value


def _recipient(value):
    if not isinstance(value, dict) or set(value) != {"run_id", "provider", "project"}:
        raise PacketError("Recipient requires exact run_id, provider and project")
    if any(not isinstance(v, str) or not v.strip() for v in value.values()):
        raise PacketError("Recipient values must be nonempty strings")
    project = Path(value["project"])
    if not project.is_absolute() or project != project.resolve() or not project.is_dir():
        raise PacketError("Project must be an existing canonical absolute directory")
    if project == Path(project.anchor) or project == Path.home().resolve():
        raise PacketError("Select a project directory, not a filesystem or home root")
    return dict(value)


def _project_file(path, project):
    candidate, root = Path(path), Path(project)
    if not candidate.is_absolute() or not candidate.is_relative_to(root) or candidate == root:
        raise PacketError("Selected file must be inside the recipient project")
    # Reject links even if they currently point inside: the pin names one file.
    if candidate != candidate.resolve() or any(p.is_symlink() for p in [candidate, *candidate.parents] if p.is_relative_to(root)):
        raise PacketError("Symlink or noncanonical project file is not allowed")
    if not candidate.is_file():
        raise PacketError("Selected project file is unavailable")
    return candidate


def _read_record(path):
    if path.is_symlink():
        raise PacketError("Stored packet or receipt cannot be a symlink")
    try:
        record = json.loads(_file_bytes(path))
        payload = {k: v for k, v in record.items() if k not in ("id", "sha256")}
        digest = _sha(_encoded(payload))
        if record.get("id") != digest or record.get("sha256") != digest:
            raise PacketError("Stored packet or receipt hash mismatch")
        return record
    except (OSError, ValueError, AttributeError) as exc:
        raise PacketError("Stored packet or receipt is unavailable or invalid") from exc


def _publish(directory, payload, filename=None):
    digest = _sha(_encoded(payload))
    record = {"id": digest, "sha256": digest, **payload}
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = directory / f"{filename or digest}.json"
    fd, temporary = tempfile.mkstemp(prefix=".packet-", dir=directory)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(_encoded(record))
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            existing = _read_record(path)
            if filename is None and existing != record:
                raise PacketError("An immutable record cannot be replaced")
            record = existing
    finally:
        os.unlink(temporary)
    directory_fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return record


class ContextPackets:
    def __init__(self, root, history_root):
        self.root = Path(root).expanduser().absolute()
        self.history = ContextHistory(history_root)

    def _storage_boundary(self, project):
        resolved = self.root.resolve()
        if resolved.is_relative_to(Path(project)):
            raise PacketError("Packet storage must be outside the project")
        if any((p / ".git").exists() for p in [resolved, *resolved.parents]):
            raise PacketError("Packet storage must be outside git worktrees")
        if self.root != resolved:
            raise PacketError("Packet storage must use a canonical path without symlinks")
        for name in ("issued", "consumed", "behavior"):
            child = self.root / name
            if child.resolve() != child:
                raise PacketError("Packet storage child must not be a symlink")

    def _load(self, packet_id, recipient):
        _identifier(packet_id)
        recipient = _recipient(recipient)
        self._storage_boundary(recipient["project"])
        packet = _read_record(self.root / "issued" / f"{packet_id}.json")
        if packet["id"] != packet_id or packet.get("schema") != "helicon.source-context-packet/1":
            raise PacketError("Packet identity or schema mismatch")
        if packet.get("recipient") != recipient:
            raise PacketError("Packet recipient does not match this run, provider and project")
        return packet

    def _current(self, packet):
        for source in packet["sources"]:
            path = _project_file(source["path"], packet["recipient"]["project"])
            try:
                current = _sha(_file_bytes(path, MAX_PACKET_BYTES))
            except OSError as exc:
                raise PacketError("Packet source is unavailable") from exc
            if current != source["sha256"]:
                raise PacketError("Packet source changed since the saved review")

    def create(self, snapshot_id, source_ids, recipient):
        recipient = _recipient(recipient)
        self._storage_boundary(recipient["project"])
        try:
            snapshot = self.history.load(snapshot_id)
        except HistoryError as exc:
            raise PacketError(str(exc)) from exc
        review = snapshot["review"]
        if review["project"] != recipient["project"]:
            raise PacketError("Saved review belongs to another project")
        if not isinstance(source_ids, list) or not source_ids or any(not isinstance(s, str) for s in source_ids) or len(set(source_ids)) != len(source_ids):
            raise PacketError("Explicit unique source IDs are required")
        sources = {s["id"]: s for s in review["sources"]}
        selected, size = [], 0
        for source_id in source_ids:
            source = sources.get(source_id)
            if source is None or not source.get("sha256"):
                raise PacketError("Selected source has no saved readable revision")
            path = _project_file(source["path"], recipient["project"])
            try:
                data = _file_bytes(path, MAX_PACKET_BYTES)
                content = data.decode("utf-8")
            except (OSError, UnicodeError) as exc:
                raise PacketError("Selected source is not readable UTF-8") from exc
            size += len(data)
            if size > MAX_PACKET_BYTES:
                raise PacketError("Selected context exceeds the local packet byte limit")
            if _sha(data) != source["sha256"]:
                raise PacketError("Selected source changed since the saved review")
            selected.append({"id": source_id, "path": str(path), "sha256": source["sha256"], "content": content})
        packet = {"schema": "helicon.source-context-packet/1", "review_id": snapshot_id,
                  "review_sha256": snapshot["sha256"], "recipient": recipient,
                  "sources": selected, "issued_at": _now(), "egress": "local-only"}
        self._current(packet)
        return _publish(self.root / "issued", packet)

    def inspect(self, packet_id, recipient):
        packet = self._load(packet_id, recipient)
        consumed_path = self.root / "consumed" / f"{packet_id}.json"
        receipt = _read_record(consumed_path) if consumed_path.exists() else None
        if receipt and (receipt.get("packet_id") != packet_id or receipt.get("recipient") != packet["recipient"]):
            raise PacketError("Consumption receipt does not match the packet")
        try:
            self._current(packet)
            source_status = "current"
        except PacketError as exc:
            source_status = str(exc)
        behavior = []
        for path in (self.root / "behavior").glob("*.json"):
            record = _read_record(path)
            if record.get("packet_id") == packet_id:
                try:
                    artifact = _project_file(record["artifact"], packet["recipient"]["project"])
                    current = _sha(_file_bytes(artifact)) == record["artifact_sha256"]
                except (PacketError, OSError):
                    current = False
                behavior.append({**record, "artifact_current": current})
        return {**{k: v for k, v in packet.items() if k != "sources"},
                "sources": [{k: v for k, v in s.items() if k != "content"} for s in packet["sources"]],
                "state": "consumed" if receipt else "issued", "source_status": source_status,
                "consumption": receipt, "behavior": behavior,
                "behavior_status": "reviewer_recorded" if behavior else "unverified"}

    def consume(self, packet_id, recipient, *, transport="local-library"):
        if transport not in {"local-library", "local-stdio"}:
            raise PacketError("Context packets are local only")
        packet = self._load(packet_id, recipient)
        self._current(packet)
        receipt = _publish(self.root / "consumed", {
            "schema": "helicon.context-consumption/1", "packet_id": packet_id,
            "packet_sha256": packet["sha256"], "recipient": packet["recipient"],
            "consumed_at": _now(), "transport": transport,
            "source_hashes": {s["id"]: s["sha256"] for s in packet["sources"]},
            "behavior": "unverified"}, filename=packet_id)
        if receipt.get("packet_id") != packet_id or receipt.get("recipient") != packet["recipient"]:
            raise PacketError("Consumption receipt does not match the packet")
        return {"packet": packet, "consumption": receipt, "behavior_status": "unverified"}

    def attach_behavior(self, packet_id, recipient, artifact, reviewer, evidence, verdict):
        """Record an attributed independent review, never infer compliance.

        This library-only method is intentionally absent from the agent tools.
        Reviewer identity is supplied by the caller, not authenticated here.
        """
        packet = self._load(packet_id, recipient)
        state = self.inspect(packet_id, recipient)
        if not state["consumption"]:
            raise PacketError("Consume the packet before recording behavior evidence")
        if not isinstance(reviewer, str) or not reviewer.strip() or reviewer == recipient["run_id"]:
            raise PacketError("A separate named reviewer is required")
        if not isinstance(evidence, str) or not evidence.strip() or verdict not in {"supported", "contradicted", "unknown"}:
            raise PacketError("Supply the review evidence and supported, contradicted or unknown verdict")
        path = _project_file(artifact, recipient["project"])
        if str(path) in {s["path"] for s in packet["sources"]}:
            raise PacketError("Behavior artifact must be separate from the supplied context")
        return _publish(self.root / "behavior", {
            "schema": "helicon.context-behavior-review/1", "packet_id": packet_id,
            "packet_sha256": packet["sha256"], "consumption_id": state["consumption"]["id"],
            "recipient": packet["recipient"], "artifact": str(path), "artifact_sha256": _sha(_file_bytes(path)),
            "reviewer": reviewer, "evidence": evidence, "verdict": verdict,
            "observed_at": _now(), "verification": "caller-supplied reviewer observation"})


def packet_store_for_project(project, config):
    """Match the human API's configured project scope; no caller-chosen storage."""
    from helicon.config import helicon_home
    requested = Path(project)
    if not requested.is_absolute() or requested != requested.resolve():
        raise PacketError("Project must be canonical and absolute")
    configured = config.get("context_review", {}).get("projects")
    allowed = {str(Path(row["path"]).expanduser().resolve()) for row in configured} if configured else {str(Path.cwd().resolve())}
    if str(requested) not in allowed:
        raise PacketError("Project is not in the local context-review configuration")
    state = Path(helicon_home()).resolve() / "context-review" / _sha(str(requested).encode())[:24]
    return ContextPackets(state / "packets", state / "reviews")
