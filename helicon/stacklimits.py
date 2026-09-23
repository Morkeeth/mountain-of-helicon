"""`helicon stack`: hard limits on a Claude Code setup, each one able to go red.

The old command printed a tool census and "Stack completeness: 100%". On 22 Sep
2026 it said 100% on a machine whose SessionStart hook printed 98,921 characters.
Claude Code keeps 10,000 characters of hook output and shows the model a 2,000
character preview of the rest (https://code.claude.com/docs/en/hooks). The facts
the session needed were in the part that was cut. The completeness number could
not go red on that, so it was a green check about the wrong object.

Each check here names its object, its measured value and its limit. Any red
check makes the command exit 1. A check that cannot be measured says SKIP; it is
never counted as a pass.

Limits (fleet-ops reviews/STACK-REBUILD-2026-09-23.md, section 3.1):
  S1  hook output per event (SessionStart, PostCompact)   <= 8,000 chars
  S2  user CLAUDE.md                                     <= 4,000 bytes, <= 60 lines
  S3  model-invocable skills                             <= 15
  S4  live registry projects missing from memory index   == 0
"""
from __future__ import annotations

import json
import os
import re
import subprocess

HOOK_OUTPUT_LIMIT = 8_000       # our margin
HOOK_HARD_CAP = 10_000          # Claude Code cuts above this
CLAUDE_MD_BYTES = 4_000
CLAUDE_MD_LINES = 60
MODEL_SKILLS = 15
HOOK_EVENTS = ("SessionStart", "PostCompact")
HOOK_TIMEOUT_S = 20

_CURATED = re.compile(r"^- (?![*`])([^:·*`][^:·]*?): [^·]*· ")
_OWNER_REPO = re.compile(r"^[A-Za-z0-9_.-]+/([A-Za-z0-9._-]+)$")


def _check(cid, name, ok, value, limit, source, detail=""):
    return {"id": cid, "name": name, "status": "PASS" if ok else "FAIL",
            "value": value, "limit": limit, "source": source, "detail": detail}


def _skip(cid, name, source, why):
    return {"id": cid, "name": name, "status": "SKIP", "value": None,
            "limit": None, "source": source, "detail": why}


def _settings_hooks(claude_dir):
    """(event, command, settings file) for every command hook on the watched events."""
    out = []
    for fname in ("settings.json", "settings.local.json"):
        p = os.path.join(claude_dir, fname)
        try:
            data = json.load(open(p, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for event in HOOK_EVENTS:
            for group in (data.get("hooks") or {}).get(event) or []:
                for h in group.get("hooks") or []:
                    if h.get("type", "command") == "command" and h.get("command"):
                        out.append((event, h["command"], p))
    return out


def _run_hook(command, event, home):
    payload = json.dumps({"hook_event_name": event, "session_id": "helicon-stack-check",
                          "source": "startup" if event == "SessionStart" else "manual",
                          "cwd": home})
    env = dict(os.environ, HOME=home)
    try:
        r = subprocess.run(command, shell=True, input=payload, capture_output=True,
                           text=True, timeout=HOOK_TIMEOUT_S, env=env, cwd=home)
        return len(r.stdout), None
    except subprocess.TimeoutExpired:
        return None, f"timed out after {HOOK_TIMEOUT_S}s"
    except OSError as e:
        return None, str(e)


def check_hook_output(home, run_hooks=True):
    claude_dir = os.path.join(home, ".claude")
    hooks = _settings_hooks(claude_dir)
    src = os.path.join(claude_dir, "settings.json")
    if not hooks:
        return [_check("S1", f"{e} hook output", True, 0, HOOK_OUTPUT_LIMIT, src,
                       "no command hooks on this event") for e in HOOK_EVENTS]
    if not run_hooks:
        return [_skip("S1", "hook output", src, "--no-run-hooks: hooks were not executed")]
    results = []
    for event in HOOK_EVENTS:
        mine = [(c, p) for e, c, p in hooks if e == event]
        total, parts, errors = 0, [], []
        for cmd, p in mine:
            n, err = _run_hook(cmd, event, home)
            if err:
                errors.append(f"{cmd}: {err}")
                continue
            total += n
            parts.append(f"{n:,} chars from `{cmd}`")
        if errors:
            results.append(_skip("S1", f"{event} hook output", src, "; ".join(errors)))
            continue
        detail = "; ".join(parts) or "no command hooks on this event"
        if total > HOOK_HARD_CAP:
            detail += (f". Above {HOOK_HARD_CAP:,} Claude Code saves the output to a file and "
                       f"the model sees a 2,000 character preview")
        results.append(_check("S1", f"{event} hook output", total <= HOOK_OUTPUT_LIMIT,
                              total, HOOK_OUTPUT_LIMIT, src, detail))
    return results


def check_claude_md(home):
    p = os.path.join(home, ".claude", "CLAUDE.md")
    if not os.path.isfile(p):
        return [_check("S2", "user CLAUDE.md size", True, 0, CLAUDE_MD_BYTES, p, "absent")]
    raw = open(p, "rb").read()
    lines = raw.decode("utf-8", "replace").count("\n") + (0 if raw.endswith(b"\n") or not raw else 1)
    ok = len(raw) <= CLAUDE_MD_BYTES and lines <= CLAUDE_MD_LINES
    return [_check("S2", "user CLAUDE.md size", ok, len(raw), CLAUDE_MD_BYTES, p,
                   f"{len(raw):,} bytes, {lines} lines (limits {CLAUDE_MD_BYTES:,} bytes, "
                   f"{CLAUDE_MD_LINES} lines)")]


def _frontmatter(text):
    if not text.startswith("---"):
        return ""
    end = text.find("\n---", 3)
    return text[3:end] if end != -1 else ""


def check_skills(home):
    d = os.path.join(home, ".claude", "skills")
    if not os.path.isdir(d):
        return [_check("S3", "model-invocable skills", True, 0, MODEL_SKILLS, d, "no skills dir")]
    model = []
    for name in sorted(os.listdir(d)):
        sk = os.path.join(d, name, "SKILL.md")
        if not os.path.isfile(sk):
            continue
        fm = _frontmatter(open(sk, encoding="utf-8", errors="replace").read())
        if re.search(r"^disable-model-invocation:\s*true\s*$", fm, re.M | re.I):
            continue
        model.append(name)
    return [_check("S3", "model-invocable skills", len(model) <= MODEL_SKILLS, len(model),
                   MODEL_SKILLS, d, ", ".join(model[:40]))]


def _fold(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def live_registry_projects(registry_path):
    """(name, repo) for every curated registry line whose state starts with 'live'."""
    out = []
    for line in open(registry_path, encoding="utf-8").read().splitlines():
        m = _CURATED.match(line)
        if not m:
            continue
        fields = [f.strip() for f in line.split(" · ")]
        if len(fields) < 4 or not fields[-1].lower().startswith("live"):
            continue
        r = _OWNER_REPO.match(fields[1])
        out.append((m.group(1).strip(), r.group(1) if r else None))
    return out


def _named_in(text, name, repo):
    """Is this project named anywhere in the index text?

    Long keys match after folding case and punctuation ('The Fair' finds
    'the-fair'). Short keys ('ZUP') must stand as a word, or 'zup' would match
    inside any longer token. A trailing version number is optional ('ARC-AGI-3'
    finds 'ARC-AGI').
    """
    folded, lowered = _fold(text), text.lower()
    keys = [name, repo, re.sub(r"[\s_-]*\d+$", "", name or "")]
    for key in keys:
        f = _fold(key)
        if len(f) >= 5 and f in folded:
            return True
        if 3 <= len(f) < 5 and re.search(
                r"(?<![a-z0-9])" + re.escape(key.lower()) + r"(?![a-z0-9])", lowered):
            return True
    return False


def check_memory_index(home, registry_path, memory_dir):
    src = registry_path or "(no registry)"
    if not registry_path or not os.path.isfile(registry_path):
        return [_skip("S4", "memory index covers live projects", src,
                      "no registry found; pass --registry")]
    if not memory_dir or not os.path.isfile(os.path.join(memory_dir, "MEMORY.md")):
        return [_skip("S4", "memory index covers live projects", src,
                      "no MEMORY.md found; pass --memory-dir")]
    parts = [open(os.path.join(memory_dir, "MEMORY.md"), encoding="utf-8").read()]
    idx = os.path.join(memory_dir, "index")
    if os.path.isdir(idx):
        for f in sorted(os.listdir(idx)):
            # An archive index is where a project goes when it stops being live.
            if f.endswith(".md") and not f.upper().startswith("ARCHIVE"):
                parts.append(open(os.path.join(idx, f), encoding="utf-8").read())
    text = "\n".join(parts)
    live = live_registry_projects(registry_path)
    if not live:
        return [_skip("S4", "memory index covers live projects", src,
                      "no curated 'live' rows in the registry")]
    missing = [n for n, repo in live if not _named_in(text, n, repo)]
    return [_check("S4", "memory index covers live projects", not missing, len(missing), 0,
                   src, ("missing: " + ", ".join(missing)) if missing else
                   f"{len(live)} live projects all named in MEMORY.md or index/*.md")]


def default_memory_dir(home):
    projects = os.path.join(home, ".claude", "projects")
    best, best_n = None, -1
    if os.path.isdir(projects):
        for p in os.listdir(projects):
            cand = os.path.join(projects, p, "memory")
            if os.path.isfile(os.path.join(cand, "MEMORY.md")):
                n = len([f for f in os.listdir(cand) if f.endswith(".md")])
                if n > best_n:
                    best, best_n = cand, n
    return best


def audit_stack(home=None, registry_path=None, memory_dir=None, run_hooks=True):
    home = os.path.abspath(os.path.expanduser(home or "~"))
    if not os.path.isdir(os.path.join(home, ".claude")):
        # Nothing to measure is not a clean setup. Every check would read "absent"
        # and pass, which is the green-on-the-wrong-object this command replaces.
        return {"home": home, "checks": [_skip("S0", "Claude Code setup", os.path.join(
            home, ".claude"), "no .claude directory: nothing was measured")],
            "failed": 0, "skipped": 1, "ok": True, "measured": False}
    memory_dir = memory_dir or default_memory_dir(home)
    checks = (check_hook_output(home, run_hooks) + check_claude_md(home)
              + check_skills(home) + check_memory_index(home, registry_path, memory_dir))
    failed = [c for c in checks if c["status"] == "FAIL"]
    return {"home": home, "checks": checks, "failed": len(failed),
            "skipped": sum(1 for c in checks if c["status"] == "SKIP"),
            "ok": not failed, "measured": True}


def render(res):
    lines = [f"Stack limits for {res['home']}", ""]
    for c in res["checks"]:
        val = "" if c["value"] is None else f"{c['value']:,}"
        lim = "" if c["limit"] is None else f" / limit {c['limit']:,}"
        lines.append(f"  {c['status']:<4}  {c['id']}  {c['name']}: {val}{lim}")
        if c["detail"]:
            lines.append(f"              {c['detail']}")
        lines.append(f"              source: {c['source']}")
    lines.append("")
    if not res.get("measured", True):
        lines.append("UNMEASURED: no Claude Code setup found. Exit 2.")
    elif res["failed"]:
        lines.append(f"RED: {res['failed']} limit(s) failed. Exit 1.")
    else:
        tail = f" ({res['skipped']} skipped, not counted as passes)" if res["skipped"] else ""
        lines.append(f"All measured limits pass{tail}.")
    return "\n".join(lines)
