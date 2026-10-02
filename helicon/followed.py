"""Witnessed staleness: instruction-file paths an agent FOLLOWED and failed on.

THE GAP THIS CLOSES. pointers.py grades a path against the tree it can see, so a
path outside the repo (`~/.local/state/...`, a vault page, a sibling checkout) is
reported as "not graded", and a path that resolves today says nothing about whether
an agent could open it on Tuesday from the directory it was in. witness.py reads
the transcript, but only to grade the agent's PROSE claims. Neither side joins the
instruction to the trace.

The trace holds the missing half. A tool result of the shape

    cat: <path>: No such file or directory
    File does not exist.                       (Read / Edit, path in the tool input)
    [Errno 2] No such file or directory: '<path>'
    ENOENT: no such file or directory, open '<path>'

on a path an instruction file names is an agent following the instruction and
failing. That is staleness with a witness: not "this path does not resolve" but
"an agent went there N times across M sessions and found nothing". The ranking
is by failure count, because the pointer agents hit most is the one to fix first.

Two join strengths, both shown in the receipt:
  by path   the failed path ends with the instruction's path (or equals it once
            `~` is expanded). The strong join.
  by name   only the basename matches, and the basename carries an extension, is
            long enough not to be noise, and is not one every repo has (CLAUDE.md,
            config.json). Weaker; a reader should look.

Honesty rules, as everywhere in Helicon:
  - No transcript read is UNMEASURED, never CLEAN.
  - A missing COMMAND (`command not found: timeout`) is not a missing path.
  - A described absence ("never read `legacy/dead.md`, it is gone") is not an
    instruction to follow, so it is not a candidate. pointers.py already drops it.
  - Transcript text is never printed beyond the path and a short head of the
    error line. The transcript is the user's own; the output goes anywhere.

Run standalone:  python3 -m helicon.followed <repo_root> [--transcripts PATH ...]
"""
from __future__ import annotations

import glob
import json
import os
import re
from collections import defaultdict

from helicon.pointers import _RE_BACKTICK, _extract, instruction_files, read_repo_text
from helicon.witness import parse_transcript

# Basenames every repo carries. A missing CLAUDE.md in some other checkout says
# nothing about the one an instruction names, so these never join by name.
# Measured on 332 real sessions before this guard: the top join was
# `~/.claude/CLAUDE.md` matched by name 15 times to other repos' missing files.
_CONVENTIONAL = {
    "readme.md", "claude.md", "agents.md", "agent.md", "context.md", "gemini.md",
    "skill.md", "license.md", "changelog.md", "contributing.md", "index.md",
    "notes.md", "todo.md", "roadmap.md", "architecture.md", "plan.md", "status.md",
    "config.json", "package.json", "settings.json", "pyproject.toml", "setup.py",
    "requirements.txt", "makefile", "dockerfile", ".env", ".gitignore", ".cursorrules",
    "main.py", "index.ts", "index.js", "app.py", "cli.py", "__init__.py",
}

# Tools whose input names the path they tried to open.
_PATH_TOOLS = ("Read", "Edit", "MultiEdit", "Write", "NotebookEdit", "Glob", "LS")

# The shapes a missing-path error takes. Each one yields the path it was about.
_RE_ERRNO = re.compile(r"No such file or directory: ['\"]([^'\"\n]+)['\"]")
_RE_ENOENT = re.compile(r"ENOENT[^'\"\n]*['\"]([^'\"\n]+)['\"]")
# `cat: /a/b c.md: No such file or directory`. The path may hold spaces, so take
# everything between the previous colon (or line start) and the error phrase.
_RE_SHELL = re.compile(r"(?:^|\n)(?:[\w./+-]+: )?([^\n:]+?): No such file or directory")
# zsh puts the path last and may include an evaluation line number.
_RE_ZSH = re.compile(r"^(?:zsh|\(eval\))(?::[0-9]+)?: no such file or directory: ([^\n]+)$", re.I | re.M)
_RE_READ_MISSING = re.compile(r"File does not exist|does not exist|No such file|ENOENT", re.I)


def _home() -> str:
    return os.path.expanduser("~")


def _tilde(path: str) -> str:
    home = _home()
    if home and path.startswith(home + "/"):
        return "~" + path[len(home):]
    return path


def extract_failed_paths(transcript: str) -> list[dict]:
    """Every missing-path tool error in one session, with the path it was about.

    Returns dicts: path (as the tool saw it), tool, line, head (first 80 chars of
    the error, for the receipt only).
    """
    out: list[dict] = []
    events, _meta = parse_transcript(transcript)
    for e in events:
        if e["kind"] != "tool_use":
            continue
        res = e.get("result")
        if not res:
            continue
        text = res.get("text") or ""
        paths: list[str] = []
        if e["name"] in _PATH_TOOLS:
            if _RE_READ_MISSING.search(text):
                p = (e["input"] or {}).get("file_path") or (e["input"] or {}).get("path")
                if p:
                    paths.append(p)
        else:
            for rx in (_RE_ERRNO, _RE_ENOENT, _RE_SHELL, _RE_ZSH):
                for m in rx.finditer(text):
                    p = m.group(1).strip()
                    if p and not p.startswith("command not found"):
                        paths.append(p)
        seen: set[str] = set()
        for p in paths:
            if p in seen:
                continue
            seen.add(p)
            out.append({"path": p, "tool": e["name"], "line": e["line"],
                        "head": text.strip().splitlines()[0][:80] if text.strip() else ""})
    return out


def instruction_paths(repo_root: str, files: list[str] | None = None) -> list[dict]:
    """Every path an instruction file names, graded or not.

    pointers.py decides what is a path and drops described absences; this keeps
    its resolved pointers (a path that resolves here may still fail elsewhere),
    its ungraded external paths, and adds one shape it refuses: a code-font token
    with a space in it (`00 Dashboard/todo.md`), which vault pages are made of.
    """
    targets, _aliases = instruction_files(repo_root, files, nested=True)
    rows: list[dict] = []
    for rel in targets:
        text = read_repo_text(repo_root, rel)
        if text is None:
            continue
        file_dir = os.path.dirname(rel)
        pointers, unverified = _extract(text, repo_root, file_dir)
        seen: set[str] = set()
        for p in pointers:
            tgt = p.target.strip("`").strip()
            if tgt and tgt not in seen:
                seen.add(tgt)
                rows.append({"file": rel, "line_no": p.line_no, "target": tgt,
                             "kind": p.kind, "resolved": p.resolved})
        for u in unverified:
            tgt = u["raw"].strip("`").strip()
            if tgt and tgt not in seen:
                seen.add(tgt)
                rows.append({"file": rel, "line_no": u["line_no"], "target": tgt,
                             "kind": u["kind"], "resolved": False})
        for ln, line in enumerate(text.splitlines(), 1):
            for m in _RE_BACKTICK.finditer(line):
                tok = m.group(1).strip()
                if " " in tok and "/" in tok and "://" not in tok and tok not in seen \
                        and not tok.startswith(("$", "-")) and len(tok) < 160:
                    seen.add(tok)
                    rows.append({"file": rel, "line_no": ln, "target": tok,
                                 "kind": "BACKTICK", "resolved": False})
    return rows


def _rel_form(target: str) -> str:
    t = target.strip().rstrip("/")
    if t.startswith("~/"):
        t = t[2:]
    while t.startswith("./"):
        t = t[2:]
    return t


def _match(target: str, failed: str) -> str | None:
    """'by path', 'by name' or None."""
    t = target.strip().rstrip("/")
    f = failed.strip().rstrip("/")
    if not t or not f:
        return None
    t_abs = os.path.expanduser(t) if t.startswith("~") else t
    f_abs = os.path.expanduser(f) if f.startswith("~") else f
    rel = _rel_form(t)
    # A bare basename (`registry.md`, `.env`) names no directory, so the strongest
    # join it can earn is by name; equality with a bare failed path is the same.
    if "/" in rel and (f_abs == t_abs or f_abs.endswith("/" + rel)):
        return "by path"
    base = os.path.basename(rel)
    if base and "." in base and len(base) >= 8 and base.lower() not in _CONVENTIONAL \
            and os.path.basename(f_abs) == base:
        return "by name"
    return None


def default_transcripts(limit: int = 50, projects_root: str | None = None) -> list[str]:
    """Newest N session transcripts under ~/.claude/projects, every project.

    Instruction files are followed from wherever the agent sits, so no single
    project directory holds the evidence; the cap keeps the read bounded.
    """
    root = projects_root or os.path.join(_home(), ".claude", "projects")
    paths = glob.glob(os.path.join(root, "*", "*.jsonl"))
    paths = [p for p in paths if os.path.getsize(p) > 0]
    paths.sort(key=os.path.getmtime, reverse=True)
    return paths[:max(int(limit), 0)]


def _expand_transcripts(transcripts: list[str]) -> list[str]:
    out: list[str] = []
    for t in transcripts:
        t = os.path.expanduser(t)
        if os.path.isdir(t):
            found = glob.glob(os.path.join(t, "**", "*.jsonl"), recursive=True)
            out.extend(sorted(found, key=os.path.getmtime, reverse=True))
        elif os.path.isfile(t):
            out.append(t)
    return out


def check_followed(repo_root: str, files: list[str] | None = None,
                   transcripts: list[str] | None = None, limit: int = 50) -> dict:
    """Join instruction paths to missing-path tool errors across sessions.

    Returns a rot.py-shaped result: verdict CLEAN / ROT FOUND / UNMEASURED, the
    witnessed rows ranked by failure count, and the counts a reader needs to see
    what population was read.
    """
    repo_root = os.path.abspath(os.path.expanduser(repo_root))
    sessions = _expand_transcripts(transcripts) if transcripts is not None \
        else default_transcripts(limit)
    candidates = instruction_paths(repo_root, files)

    hits: dict[tuple[str, int, str], dict] = {}
    unmatched = 0
    total_failures = 0
    read_sessions = unreadable_sessions = 0
    for t in sessions:
        sid = os.path.splitext(os.path.basename(t))[0]
        try:
            failed = extract_failed_paths(t)
        except OSError:
            unreadable_sessions += 1
            continue
        read_sessions += 1
        for f in failed:
            total_failures += 1
            best = None
            for c in candidates:
                m = _match(c["target"], f["path"])
                if m == "by path":
                    best = (c, m)
                    break
                if m == "by name" and best is None:
                    best = (c, m)
            if best is None:
                unmatched += 1
                continue
            c, m = best
            key = (c["file"], c["line_no"], c["target"])
            row = hits.setdefault(key, {
                "file": c["file"], "line_no": c["line_no"], "target": c["target"],
                "kind": c["kind"], "resolved_here": c["resolved"], "match": m,
                "failures": 0, "sessions": set(), "last_path": "", "last_head": "",
            })
            row["failures"] += 1
            row["sessions"].add(sid)
            row["last_path"] = _tilde(f["path"])
            row["last_head"] = f["head"]
            if m == "by path":
                row["match"] = "by path"

    witnessed = []
    for row in hits.values():
        row["session_count"] = len(row.pop("sessions"))
        witnessed.append(row)
    witnessed.sort(key=lambda r: (-r["failures"], -r["session_count"], r["file"], r["line_no"]))

    if not read_sessions:
        verdict = "UNMEASURED"
    else:
        verdict = "ROT FOUND" if witnessed else "CLEAN"
    return {
        "rid": "H1",
        "name": "Instruction paths followed and failed",
        "verdict": verdict,
        "repo": repo_root,
        "sessions": read_sessions,
        "unreadable_sessions": unreadable_sessions,
        "candidates": len(candidates),
        "failures": total_failures,
        "unmatched_failures": unmatched,
        "witnessed": witnessed,
    }


def format_followed(res: dict) -> str:
    head = f"[{res['rid']}] {res['name']}: {res['verdict']}"
    if res["verdict"] == "UNMEASURED":
        return (head + "  (no transcript read; pass --transcripts <file-or-dir> "
                "or run where ~/.claude/projects holds sessions)")
    lines = [head,
             f"  {res['sessions']} session(s) read, {res.get('unreadable_sessions', 0)} unreadable, "
             f"{res['candidates']} instruction path(s), "
             f"{res['failures']} missing-path tool error(s), "
             f"{res['unmatched_failures']} on paths no instruction names"]
    for r in res["witnessed"]:
        note = "resolves in this repo now" if r["resolved_here"] else "not graded by review"
        lines.append(
            f"  ✗ {r['file']}:{r['line_no']}  `{r['target']}`  "
            f"{r['failures']} failures in {r['session_count']} sessions ({r['match']}; {note})")
        lines.append(f"      last: {r['last_path']}  {r['last_head']}")
    if not res["witnessed"]:
        lines.append("  no instruction path was followed and failed in the sessions read")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    import argparse
    import sys
    ap = argparse.ArgumentParser(prog="python3 -m helicon.followed")
    ap.add_argument("repo", nargs="?", default=".")
    ap.add_argument("--transcripts", nargs="*", default=None)
    ap.add_argument("--files", nargs="*", default=None)
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv if argv is not None else sys.argv[1:])
    res = check_followed(a.repo, a.files, a.transcripts, a.limit)
    print(json.dumps(res, ensure_ascii=False) if a.json else format_followed(res))
    return 1 if res["verdict"] == "ROT FOUND" else 0


if __name__ == "__main__":
    raise SystemExit(main())
