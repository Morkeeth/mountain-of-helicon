"""Safe fixes for broken instruction-file pointers.

A fix is safe only when the missing path names a file, and exactly one file in
the repo has that same name, outside vendored and sample trees. Anything else
is left for a human. Dry run is the default.
"""
from __future__ import annotations

import os

from helicon.pointers import _VENDORED, _tree, check_pointers

_SKIP_DIRS = _VENDORED | {".git", "node_modules", "__pycache__", ".venv", "venv"}


def _token(raw: str) -> str:
    return (raw or "").strip().strip("`").strip()


def _kept(rel: str) -> bool:
    parts = rel.split("/")[:-1]
    return not any(seg in _SKIP_DIRS or seg.startswith(".") for seg in parts)


def safe_replacement(repo_root: str, raw: str) -> str | None:
    """Repo-root path to write in place of *raw*, or None when the guess is not unique."""
    token = _token(raw)
    if not token or token.endswith("/") or "/" not in token:
        return None
    name = os.path.basename(token)
    if "." not in name or name.startswith("."):
        return None
    _names, _dirs, files = _tree(repo_root)
    hits = [f for f in files if os.path.basename(f) == name and _kept(f)]
    if len(hits) != 1:
        return None
    found = hits[0]
    if found == token.lstrip("./"):
        return None
    return found


def plan_fixes(repo_root: str) -> list[dict]:
    """Broken pointers that have one safe replacement. Nothing is written."""
    repo_root = os.path.abspath(repo_root)
    planned = []
    for receipt in check_pointers(repo_root).get("receipts") or []:
        raw = receipt.get("raw") or ""
        found = safe_replacement(repo_root, raw)
        if not found:
            continue
        where = (receipt.get("receipt") or "").split(" — ", 1)[0]
        file_rel, _, line_s = where.partition(":")
        if not file_rel or not line_s.isdigit():
            continue
        planned.append({
            "file": file_rel,
            "line_no": int(line_s),
            "raw": raw,
            "replacement": found,
            "line": receipt.get("line") or "",
        })
    return planned


def _rewrite_line(line: str, raw: str, replacement: str) -> str | None:
    """Replace the pointer token once. None when the line does not contain it exactly once."""
    if not raw or line.count(raw) != 1:
        return None
    token = _token(raw)
    if raw.startswith("`") and raw.endswith("`"):
        new = f"`{replacement}`"
    else:
        new = replacement
    if token and token not in raw:
        return None
    return line.replace(raw, new, 1)


def apply_fixes(repo_root: str, planned: list[dict] | None = None, apply: bool = False) -> list[dict]:
    """Return the plan, and write it only when *apply* is true."""
    repo_root = os.path.abspath(repo_root)
    planned = list(planned if planned is not None else plan_fixes(repo_root))
    if not apply:
        for row in planned:
            row["written"] = False
        return planned

    by_file: dict[str, list[dict]] = {}
    for row in planned:
        by_file.setdefault(row["file"], []).append(row)

    for file_rel, rows in by_file.items():
        path = os.path.join(repo_root, file_rel)
        if not os.path.realpath(path).startswith(os.path.realpath(repo_root) + os.sep):
            continue
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines(keepends=True)
        for row in rows:
            idx = row["line_no"] - 1
            if idx < 0 or idx >= len(lines):
                row["written"] = False
                row["reason"] = "line is gone"
                continue
            original = lines[idx]
            newline = "\n" if original.endswith("\n") else ""
            body = original[:-1] if newline else original
            if original.endswith("\r\n"):
                newline = "\r\n"
                body = original[:-2]
            updated = _rewrite_line(body, row["raw"], row["replacement"])
            if updated is None:
                row["written"] = False
                row["reason"] = "token is not on that line exactly once"
                continue
            lines[idx] = updated + newline
            row["written"] = True
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("".join(lines))
    return planned


def render_diff(repo_root: str, planned: list[dict]) -> str:
    """Unified diff of the safe rewrites. Does not write."""
    import difflib
    repo_root = os.path.abspath(repo_root)
    by_file: dict[str, list[dict]] = {}
    for row in planned:
        by_file.setdefault(row["file"], []).append(row)
    chunks: list[str] = []
    root_real = os.path.realpath(repo_root)
    for rel, rows in by_file.items():
        path = os.path.join(repo_root, rel)
        if not os.path.realpath(path).startswith(root_real + os.sep):
            continue
        with open(path, encoding="utf-8") as fh:
            original = fh.read()
        lines = original.splitlines(keepends=True)
        for row in rows:
            idx = row["line_no"] - 1
            if idx < 0 or idx >= len(lines):
                continue
            original_line = lines[idx]
            newline = "\n" if original_line.endswith("\n") else ""
            body = original_line[:-1] if newline else original_line
            updated = _rewrite_line(body, row["raw"], row["replacement"])
            if updated is None:
                continue
            lines[idx] = updated + newline
        updated_text = "".join(lines)
        if updated_text == original:
            continue
        chunks.append("".join(difflib.unified_diff(
            original.splitlines(keepends=True),
            updated_text.splitlines(keepends=True),
            fromfile=f"a/{rel}",
            tofile=f"b/{rel}",
        )))
    return "\n".join(chunks)


def format_plan(planned: list[dict], apply: bool) -> str:
    if not planned:
        return "No safe fix. Broken pointers with no single matching file are left as they are.\n"
    mode = "Wrote" if apply else "Would write"
    lines = [f"{mode} {len(planned)} safe fix{'s' if len(planned) != 1 else ''}.", ""]
    for row in planned:
        flag = ""
        if apply and not row.get("written"):
            flag = f"  (skipped: {row.get('reason', 'not written')})"
        lines.append(
            f"  {row['file']}:{row['line_no']}  {row['raw']}  ->  {row['replacement']}{flag}"
        )
    if not apply:
        lines += ["", "Nothing written. Pass --apply to change the files."]
    lines.append("")
    return "\n".join(lines)
