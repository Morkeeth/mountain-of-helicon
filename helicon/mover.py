"""Slice 5: the moonshot context-mover v0.

Read memory from one platform, VERIFY each item, and render it into another
platform's native format - dry-run first. Memory does not move blindly; it moves
verified. That is the difference from a dumb copy, and it is why the neutral
auditor (Helicon) is the one tool that can carry memory across Cursor / Claude
Code / Codex without carrying the rot along.

v0 verification:
  - deterministic + free: volatility markers (TODO/WIP/"as of"/"currently"/...)
    and stale dates (a past date older than a threshold) are held back.
  - optional Qwen judge (validated in judge-bench): --verify-contradictions runs
    the kept items pairwise and holds any that contradict an earlier kept item.
Writes are DRY-RUN by default; --apply backs up the target first.
"""
import difflib
import os
import re
from datetime import datetime

FORMATS = ("claude-code", "cursor", "markdown")
_VOLATILE = re.compile(
    r"\b(TODO|WIP|FIXME|deprecated|as of|currently|right now|this week|last week|"
    r"next week|today|tomorrow|yesterday|for now|temporarily)\b", re.I)
_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")


def read_items(path: str) -> list[dict]:
    """Memory bullets from a file or a directory of rules/memory files. An item
    is a markdown bullet ('- ' / '* '); files with no bullets contribute their
    non-heading, non-empty lines."""
    path = os.path.expanduser(path)
    files = []
    if os.path.isdir(path):
        for root, _, fs in os.walk(path):
            for f in fs:
                if f.endswith((".md", ".mdc", ".cursorrules", ".mdc")) or \
                   f in ("CLAUDE.md", "AGENTS.md", ".cursorrules", ".clinerules"):
                    files.append(os.path.join(root, f))
    elif os.path.isfile(path):
        files = [path]
    items = []
    for fp in files:
        try:
            txt = open(fp, errors="ignore").read()
        except OSError:
            continue
        bullets = [ln.strip()[2:].strip() for ln in txt.splitlines()
                   if ln.strip().startswith(("- ", "* ")) and len(ln.strip()) > 3]
        if bullets:
            items += [{"text": b, "source": fp} for b in bullets]
        else:
            items += [{"text": s, "source": fp} for s in
                      (l.strip() for l in txt.splitlines())
                      if s and not s.startswith(("#", ">", "|", "```"))]
    return items


def verify_item(text: str, now: datetime | None = None, stale_days: int = 30) -> tuple[bool, str]:
    """Deterministic freshness check. Returns (ok_to_move, reason_if_held)."""
    now = now or datetime.now()
    m = _VOLATILE.search(text)
    if m:
        return (False, f"volatile ('{m.group(0).lower()}')")
    for d in _DATE.finditer(text):
        try:
            when = datetime(int(d.group(1)), int(d.group(2)), int(d.group(3)))
        except ValueError:
            continue
        age = (now - when).days
        if age > stale_days:
            return (False, f"stale date {d.group(0)} ({age}d old)")
    return (True, "")


def plan_move(items: list[dict], now: datetime | None = None, stale_days: int = 30) -> dict:
    """Split items into kept (verified fresh) and held (with reasons). Pure."""
    kept, held = [], []
    for it in items:
        ok, reason = verify_item(it["text"], now=now, stale_days=stale_days)
        (kept if ok else held).append({**it, "reason": reason})
    return {"kept": kept, "held": held}


def verify_contradictions(config: dict, kept: list[dict], cap: int = 20) -> dict:
    """Optional Qwen-judge pass: hold any kept item that contradicts an earlier
    kept one. Bounded to `cap` items (pairwise is O(n^2)). Reuses the judge
    validated in judge-bench."""
    from helicon.qwen import detect_contradictions, get_client, resolve_model
    client = get_client(config)
    if client is None:
        return {"kept": kept, "held_contradiction": [], "ran": False}
    model = resolve_model("fast", config)      # flash is the cheap, validated judge
    survivors, held = [], []
    for it in kept[:cap]:
        conflict = None
        for prev in survivors:
            res = detect_contradictions(client, it["text"], prev["text"], model=model)
            if res and res.get("contradicts"):
                conflict = prev
                break
        if conflict:
            held.append({**it, "reason": f"contradicts kept item: \"{conflict['text'][:60]}\""})
        else:
            survivors.append(it)
    survivors += kept[cap:]                     # un-judged tail passes through
    return {"kept": survivors, "held_contradiction": held, "ran": True}


def render(items: list[dict], fmt: str) -> str:
    """Render kept items into the target platform's native memory format."""
    bullets = "\n".join(f"- {i['text']}" for i in items)
    if fmt == "cursor":
        return bullets + "\n"
    if fmt == "claude-code":
        return ("# Memory (moved + verified by Mount Helicon)\n\n" + bullets + "\n")
    return "# Moved memory\n\n" + bullets + "\n"


def move(from_path: str, to_fmt: str, out_path: str | None = None, apply: bool = False,
         verify_contradictions_flag: bool = False, config: dict | None = None,
         now: datetime | None = None) -> dict:
    if to_fmt not in FORMATS:
        return {"error": f"unknown target format '{to_fmt}' (use: {', '.join(FORMATS)})"}
    items = read_items(from_path)
    if not items:
        return {"error": f"no memory items read from {from_path}"}
    plan = plan_move(items, now=now)
    kept, held = plan["kept"], plan["held"]
    held_contra = []
    if verify_contradictions_flag:
        vc = verify_contradictions(config or {}, kept)
        kept, held_contra = vc["kept"], vc["held_contradiction"]
    rendered = render(kept, to_fmt)
    result = {"from": from_path, "to": to_fmt, "items": len(items),
              "kept": kept, "held": held + held_contra, "rendered": rendered,
              "applied": False, "out_path": out_path}
    if apply:
        if not out_path:
            result["error"] = "--apply needs --out <target file>"
            return result
        out_path = os.path.expanduser(out_path)
        if os.path.exists(out_path):
            with open(out_path) as f:
                old = f.read()
            with open(out_path + ".bak", "w") as f:
                f.write(old)
            result["backup"] = out_path + ".bak"
        with open(out_path, "w") as f:
            f.write(rendered)
        result["applied"] = True
    return result


def format_move(res: dict) -> str:
    if "error" in res and not res.get("kept"):
        return f"\n  move: {res['error']}\n"
    kept, held = res["kept"], res["held"]
    out = ["", f"  CONTEXT MOVE — {res['from']} -> {res['to']} format", "",
           f"  {res['items']} item(s): {len(kept)} verified -> move, "
           f"{len(held)} held back", ""]
    if held:
        out.append("  HELD BACK (not moved, memory does not travel with rot):")
        for h in held[:20]:
            out.append(f"    - {h['text'][:70]}   [{h['reason']}]")
        out.append("")
    out.append("  WOULD WRITE:")
    for line in res["rendered"].splitlines()[:24]:
        out.append(f"    {line}")
    out.append("")
    if res.get("applied"):
        out.append(f"  APPLIED -> {res['out_path']}"
                   + (f" (backup {res['backup']})" if res.get("backup") else ""))
    elif "error" in res:
        out.append(f"  (not applied: {res['error']})")
    else:
        out.append("  (dry-run. add --apply --out <file> to write.)")
    out.append("")
    return "\n".join(out)
