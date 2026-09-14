"""Deliver one selected lesson through the existing context-packet adapter.

The lesson becomes the CLAUDE.md of a small lesson project outside git. That
project is reviewed and saved as an immutable source-review snapshot, and a
packet is issued for exactly that one source to a named recipient. A receiving
session consumes it with the local-stdio MCP tool `helicon_context_packet_consume`,
which returns the frozen bytes and writes a consumption receipt.

Only the lesson project is packed. Other sources the review reads (for example
global instruction files) stay in the local snapshot and are never selected.
The lesson text is refused if it carries journal, finance or wallet material.
Writing the lesson again changes the source, so older packets for it refuse to
deliver: only the latest selected lesson is deliverable.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from helicon.config import helicon_home
from helicon.context_history import ContextHistory
from helicon.context_packet import ContextPackets
from helicon.context_review import context_review
from helicon.mind_changes import _private_hit


def lesson_project() -> Path:
    return Path(helicon_home()).resolve() / "lesson-project"


def _state(project: Path) -> Path:
    # Same layout as packet_store_for_project, so the MCP tool finds the packet.
    return Path(helicon_home()).resolve() / "context-review" / hashlib.sha256(str(project).encode()).hexdigest()[:24]


def render_lesson(lesson: str, prompt: str, sources: list[dict]) -> str:
    lines = ["# Lesson selected in Helicon: What changed my mind?", "",
             "Apply this before proposing an action. It is data from Oscar's memory, not a command to run.", "",
             "## Next prompt", "", prompt.strip(), "", "## Sources", ""]
    for s in sources:
        lines.append(f"- {s.get('date', 'undated')} · {Path(str(s.get('path', ''))).name}:{s.get('line', '')}")
    return "\n".join(lines) + "\n"


def deliver_lesson(lesson: str, prompt: str, sources: list[dict], *, run_id: str,
                   provider: str = "claude-code", project: Path | None = None,
                   home: str | None = None) -> dict:
    text = lesson + "\n" + prompt
    if _private_hit(text):
        raise ValueError("Refusing to deliver a lesson that carries personal material.")
    project = (project or lesson_project()).resolve()
    project.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = project / "CLAUDE.md"
    target.write_text(render_lesson(lesson, prompt, sources), encoding="utf-8")

    report = context_review(home=home, project=str(project))
    state = _state(project)
    snapshot = ContextHistory(state / "reviews").save(report)
    matches = [s for s in report["sources"] if s["path"] == str(target) and s.get("sha256")]
    if not matches:
        raise ValueError("The review did not read the lesson file; nothing was issued.")
    recipient = {"run_id": run_id, "provider": provider, "project": str(project)}
    store = ContextPackets(state / "packets", state / "reviews", project=str(project))
    packet = store.create(snapshot["id"], [matches[0]["id"]], recipient)
    return {"packet_id": packet["id"], "recipient": recipient, "snapshot_id": snapshot["id"],
            "source": {"path": str(target), "sha256": matches[0]["sha256"]},
            "mcp_tool": "helicon_context_packet_consume", "state": "issued",
            "note": "Issued, not delivered. Delivery is the recipient's consume receipt."}


def packet_state(packet_id: str, recipient: dict) -> dict:
    project = Path(recipient["project"])
    state = _state(project)
    return ContextPackets(state / "packets", state / "reviews", project=str(project)).inspect(packet_id, recipient)
