"""Codex connector — closes the loop the GOLDEN_RULES injector left open.

`helicon policy --inject --targets codex` PUSHES the law to ~/.codex/AGENTS.md.
Without this connector that is one-directional: Codex does the same work on the
same vault, and everything it learns dies in ~/.codex/sessions/.

What it reads:
  - sessions/**/rollout-*.jsonl  the real transcripts (session_meta + messages)
  - session_index.jsonl          thread names, cheap and high-signal

What it deliberately does NOT read:
  - ~/.codex/AGENTS.md — THIS TOOL WROTE THAT FILE. Scanning it would file the
    compiled law back in as a memory, where it can compile into the law again:
    an echo that manufactures its own evidence. Same reason auto-triage excludes
    its own decisions. `_is_own_output()` is the guard and it is tested.
  - memories_1.sqlite — Codex's own memory store. Probed Jul 19: stage1_outputs
    and jobs are both EMPTY. Reading it is dead code until Codex fills it, so it
    stays unwritten rather than shipped untested against a shape nobody has seen.
  - reasoning blocks (encrypted_content, not readable), tool calls and their
    output (execution noise, already covered by the git connector), and the
    `developer` role (sandbox permission boilerplate injected every session).
"""
import json
import os
from glob import glob

from helicon.models import ConnectorResult

# Codex's own global instructions file is Helicon's OUTPUT. Never an input.
OWN_OUTPUT = ("agents.md",)
# Roles worth keeping: what the operator asked, what the agent answered.
KEEP_ROLES = ("user", "assistant")
MAX_CHARS = 2000

# The echo guard, aimed at the surface it actually arrives on.
#
# The first version of this file guarded ~/.codex/AGENTS.md by FILENAME and was
# wrong: Codex does not hand its agent a file, it pastes the instructions inline
# as the first user message of every session. So the compiled law came back as
# transcript TEXT, sailed past a path check, and would have been filed as a
# Codex memory — where `gold gather()` could compile it into the law it came
# from. A rule would then cite itself as its own evidence.
#
# Caught Jul 19 by running the connector against real sessions and reading the
# output instead of trusting the guard. Both surfaces are now closed and tested.
OWN_OUTPUT_MARKERS = (
    "# AGENTS.md instructions",
    "# GOLDEN RULES",
    "Compiled by Mount Helicon",
    "by Mount Helicon. Regenerate:",
)


def _is_own_output(path: str) -> bool:
    """True for files this tool generates. The path-surface echo guard."""
    return os.path.basename(path).lower() in OWN_OUTPUT


def _is_echo(text: str) -> bool:
    """True when a message is Helicon's own compiled law pasted back in.
    The text-surface echo guard — the one that actually fires in practice."""
    head = text[:1500]
    return any(m in head for m in OWN_OUTPUT_MARKERS)


def _text_of(content) -> str:
    """A message's content is a list of typed parts; join the textual ones."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    out = []
    for part in content:
        if isinstance(part, dict) and isinstance(part.get("text"), str):
            out.append(part["text"])
        elif isinstance(part, str):
            out.append(part)
    return "\n".join(out).strip()


def _thread_names(codex_dir: str) -> dict:
    """session_id -> human thread name, so a session gets a real title."""
    names = {}
    idx = os.path.join(codex_dir, "session_index.jsonl")
    if not os.path.exists(idx):
        return names
    try:
        with open(idx, encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if d.get("id") and d.get("thread_name"):
                    names[d["id"]] = d["thread_name"]
    except OSError:
        pass
    return names


def _scan_rollout(path: str, names: dict, max_messages: int) -> list[ConnectorResult]:
    meta, messages = {}, []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue  # a truncated tail must not lose the whole session
                kind = d.get("type")
                if kind == "session_meta" and not meta:
                    meta = d.get("payload") or {}
                elif kind == "response_item":
                    p = d.get("payload") or {}
                    if p.get("type") != "message":
                        continue
                    if p.get("role") not in KEEP_ROLES:
                        continue
                    text = _text_of(p.get("content"))
                    if text and not _is_echo(text):
                        messages.append((p["role"], text, d.get("timestamp") or ""))
    except OSError:
        return []

    if not messages:
        return []

    sid = meta.get("session_id") or os.path.basename(path)
    created = meta.get("timestamp") or messages[0][2]
    cwd = meta.get("cwd") or ""
    title = names.get(sid) or (messages[0][1][:60] if messages else "Codex session")
    body = "\n\n".join(f"[{r}] {t}" for r, t, _ in messages[:max_messages])

    # One session can span several rollout files (resume, /compact). Keyed on
    # session_id alone they collide: two different transcripts, one ref, and the
    # store keeps whichever landed last. The rollout stem disambiguates them.
    stem = os.path.basename(path).removeprefix("rollout-").removesuffix(".jsonl")

    return [ConnectorResult(
        source="codex",
        source_ref=f"codex/session/{sid}/{stem[:19]}",
        type="session",
        title=f"Codex session: {title[:60]}",
        content=body[:MAX_CHARS],
        created_at=created,
        tags=["codex", "session"] + ([os.path.basename(cwd)] if cwd else []),
        metadata={"cwd": cwd,
                  "model_provider": meta.get("model_provider") or "",
                  "cli_version": meta.get("cli_version") or "",
                  "source": meta.get("source") or "",
                  "messages": len(messages)},
    )]


def scan(config: dict) -> list[ConnectorResult]:
    codex_dir = os.path.expanduser(config.get("codex_dir", "~/.codex"))
    if not os.path.isdir(codex_dir):
        return []
    max_sessions = int(config.get("max_sessions", 50))
    max_messages = int(config.get("max_messages", 40))

    names = _thread_names(codex_dir)
    pattern = os.path.join(codex_dir, "sessions", "**", "rollout-*.jsonl")
    files = sorted(glob(pattern, recursive=True), reverse=True)[:max_sessions]

    results = []
    for path in files:
        if _is_own_output(path):
            continue
        results.extend(_scan_rollout(path, names, max_messages))
    return results
