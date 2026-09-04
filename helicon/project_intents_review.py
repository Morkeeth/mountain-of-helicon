"""Read-only validation of ZUP's separate, field-scoped intent records.

No ZUP implementation is imported: this checks persisted evidence independently.
An intent is never a submission, acceptance, or execution receipt.
"""
import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit

SOURCES = {"native-project-editor", "cli"}
ROLES = {"Vision", "PRD", "Build plan"}
DOCUMENT_STATES = {"Draft", "Approved", "Superseded"}


def fingerprint(path):
    try:
        stat = path.stat()
        return stat.st_dev, stat.st_ino, stat.st_mtime_ns, stat.st_size
    except FileNotFoundError:
        return None


def valid_time(value, clock):
    if not isinstance(value, str):
        return False
    try:
        at = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return at.tzinfo is not None and at <= clock
    except ValueError:
        return False


def valid_actor(actor):
    return (isinstance(actor, dict) and actor.get("kind") in {"human", "agent"}
            and isinstance(actor.get("id"), str) and bool(actor["id"].strip()))


def valid_hash(value):
    return isinstance(value, str) and bool(re.fullmatch(r"[a-f0-9]{64}", value))


def finding(kind, project, title, consequence, action, **details):
    return dict(kind=kind, project=project, title=title, consequence=consequence,
                action=action, **details)


def inspect_intents(data, projects, watched, clock=None):
    """Return valid field records and findings; malformed records never add coverage."""
    clock = clock or datetime.now(timezone.utc)
    if (not isinstance(data, dict) or data.get("schema") != "zup.project-intents/1"
            or not isinstance(data.get("projects"), dict)):
        raise ValueError("Invalid project-intents schema or projects map")
    accepted, findings = {}, []
    for key, record in data["projects"].items():
        matches = [p for p in projects if p.get("id") == key]
        valid = (len(matches) == 1 and isinstance(record, dict)
                 and record.get("projectID") == key
                 and type(record.get("revision")) is int and record["revision"] > 0
                 and record.get("source") in SOURCES and valid_actor(record.get("actor"))
                 and valid_time(record.get("observedAt"), clock)
                 and isinstance(record.get("phase"), str)
                 and isinstance(record.get("reason"), str) and record["reason"].strip()
                 and isinstance(record.get("operationID"), str) and record["operationID"].strip()
                 and valid_hash(record.get("requestHash"))
                 and isinstance(record.get("documents"), list))
        if not valid:
            findings.append(finding("invalid-project-intent", key,
                "A project correction has invalid provenance",
                "This record cannot establish a current phase or approved document.",
                "Repair its canonical project, revision, actor, source and recorded time; retain the original bytes."))
            continue
        reviewed = dict(phase=record["phase"].strip(), revision=record["revision"],
                        actor=record["actor"], source=record["source"],
                        observed_at=record["observedAt"], document_checks=[])
        roles = set()
        for document in record["documents"]:
            valid_document = (isinstance(document, dict) and document.get("role") in ROLES
                              and document.get("role") not in roles
                              and document.get("status") in DOCUMENT_STATES
                              and valid_hash(document.get("hash"))
                              and document.get("source") in SOURCES
                              and valid_actor(document.get("actor"))
                              and valid_time(document.get("confirmedAt"), clock)
                              and isinstance(document.get("uri"), str))
            if not valid_document:
                findings.append(finding("invalid-project-document", key,
                    "A document binding has invalid provenance",
                    "Its role, approval status or pinned revision cannot be trusted.",
                    "Read and pin the chosen document again in ZUP."))
                continue
            roles.add(document["role"])
            check = dict(role=document["role"], status=document["status"], uri=document["uri"],
                         expected_hash=document["hash"], confirmed_at=document["confirmedAt"])
            try:
                uri = urlsplit(document["uri"])
                if uri.scheme != "file" or uri.netloc or not uri.path.startswith("/"):
                    raise ValueError("Binding is not an absolute local file URI")
                path = Path(unquote(uri.path))
                watched.setdefault(path, fingerprint(path))
                stat = path.stat()
                if not path.is_file() or stat.st_size > 2_000_000:
                    raise ValueError("Document is not a text file under 2 MB")
                content = path.read_bytes()
                content.decode("utf-8", errors="strict")
                if b"\0" in content:
                    raise ValueError("Document contains binary content")
                current = hashlib.sha256(content).hexdigest()
                check.update(state="unchanged" if current == document["hash"] else "changed", current_hash=current)
            except (OSError, ValueError) as exc:
                check.update(state="unavailable", reason=str(exc))
            reviewed["document_checks"].append(check)
            if check["state"] != "unchanged":
                changed = check["state"] == "changed"
                findings.append(finding("project-document-changed" if changed else "project-document-unavailable", key,
                    f"{document['role']} differs from its pinned revision" if changed else f"{document['role']} cannot be checked",
                    "Approval, if recorded, applies only to the old pinned bytes—not the current file.",
                    "Open the chosen document in ZUP; review and pin a new revision or repair the binding.",
                    document=check))
        accepted[key] = reviewed
    return accepted, findings
